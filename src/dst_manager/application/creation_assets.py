"""创建受控标准资产解析与身份快照（PLAN-DM-036 Task 4）。

只列**已发布且依赖、受控资产可用**的标准候选：依赖按扩展注册表清单校验，
模板文件必须是标准包内声明路径下真实存在的文件；不可用的候选同样返回（带
原因），由界面说明为什么不能选，不静默隐藏。

资产候选标签取包内受控文件名（同类内唯一），模板生成、导入校验与草稿保存
共用同一份身份，因此不存在「标签 → ``asset_id``」猜测。预览用快照额外计算
声明文件的内容哈希，作为 `preview_digest` 的资产绑定项。

本模块不启动 CAD、不写任何文件、不修改标准库；包内目录定位只读。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from dst_manager.application.errors import ApplicationError
from dst_manager.application.standard_assets import StandardAssetOperations
from dst_manager.domain.creation import CreationAssetOption
from dst_manager.domain.creation_plan_inputs import (
    BASE_TEMPLATE_KIND,
    LAYOUT_TEMPLATE_KIND,
)
from dst_manager.domain.standard_models import (
    DrawingStandard,
    StandardAsset,
    StandardDependency,
)
from dst_manager.domain.standards import StandardSchemaError
from dst_manager.extensions.capabilities import standard_dependency_gaps
from dst_manager.infrastructure.standards.store import StandardStore, StandardStoreError

__all__ = [
    "CREATION_ASSET_KINDS",
    "CreationAssetFile",
    "CreationAssetSnapshot",
    "CreationStandardCandidate",
    "creation_asset_options",
    "creation_standard_candidates",
    "resolve_creation_assets",
    "standard_document_digest",
]

#: 创建只消费标准包的两种模板资产（与标准 Schema 的资产种类同口径）。
CREATION_ASSET_KINDS = (BASE_TEMPLATE_KIND, LAYOUT_TEMPLATE_KIND)


@dataclass(frozen=True, slots=True)
class CreationAssetFile:
    """一个受控资产声明文件：包内相对路径与内容哈希。

    ``sha256`` 为空串表示文件不存在或路径非法（即不可用），与「内容为空的
    文件」区分开。
    """

    asset_id: str
    path: str
    sha256: str = ""

    @property
    def present(self) -> bool:
        return bool(self.sha256)


@dataclass(frozen=True, slots=True)
class CreationAssetSnapshot:
    """一次资产解析结果：候选选项、声明文件身份与资产内容摘要。"""

    options: tuple[CreationAssetOption, ...]
    files: tuple[CreationAssetFile, ...]
    digest: str

    @property
    def missing_files(self) -> tuple[CreationAssetFile, ...]:
        """声明了但不存在（或路径非法）的资产文件。"""
        return tuple(item for item in self.files if not item.present)

    def unavailable_reasons(self) -> tuple[str, ...]:
        """候选不可选的原因：文件缺失与模板候选缺失分别说明。"""
        reasons = [
            f"标准资产 {item.asset_id!r} 声明的文件 {item.path!r} 不存在或路径非法"
            for item in self.missing_files
        ]
        if not any(option.kind == BASE_TEMPLATE_KIND for option in self.options):
            reasons.append("标准没有可用的基础模板候选")
        if not any(
            option.kind == LAYOUT_TEMPLATE_KIND and option.layouts for option in self.options
        ):
            reasons.append("标准没有声明图幅的布局模板候选")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class CreationStandardCandidate:
    """一个创建标准候选：可用时可直接建草稿，不可用时带原因。"""

    standard_id: str
    #: 服务端分配的整数发布版本（与 API 契约一致）。
    version: int
    name: str
    supported_cad_versions: tuple[str, ...] = ()
    available: bool = False
    reasons: tuple[str, ...] = ()
    asset_options: tuple[CreationAssetOption, ...] = ()


def creation_asset_options(standard: DrawingStandard) -> tuple[CreationAssetOption, ...]:
    """标准声明的创建资产候选（按资产种类分组、组内保持文档顺序）。

    标签取声明文件的**文件名**；同类内文件名冲突时该冲突项退回完整包内相对
    路径，保证标签同类内唯一且与文档顺序无关（不依赖字典/集合顺序）。
    布局模板的可用图幅取声明文件的 ``role``（去重保序）；无文件的资产不产生
    候选——声明了却无法使用的资产不能进入模板候选。
    """
    options: list[CreationAssetOption] = []
    for kind in CREATION_ASSET_KINDS:
        assets = [asset for asset in standard.assets if asset.kind == kind and asset.files]
        labels = _asset_labels(assets)
        options.extend(
            CreationAssetOption(
                asset_id=asset.asset_id,
                kind=kind,
                label=labels[asset.asset_id],
                layouts=_asset_layouts(asset),
            )
            for asset in assets
        )
    return tuple(options)


def resolve_creation_assets(
    store: StandardStore, standard: DrawingStandard
) -> CreationAssetSnapshot:
    """解析候选与声明文件内容哈希；文件缺失只记录，不抛出（由预览显式阻断）。"""
    root = standard_package_root(store, standard.standard_id, standard.version)
    files = tuple(
        CreationAssetFile(
            asset_id=asset.asset_id,
            path=file.path,
            sha256=_file_digest(_controlled_file(root, file.path)),
        )
        for asset in _creation_assets(standard)
        for file in asset.files
    )
    return CreationAssetSnapshot(
        options=creation_asset_options(standard),
        files=files,
        digest=_assets_digest(files),
    )


def creation_standard_candidates(
    store: StandardStore, manifests: Mapping[str, object]
) -> tuple[CreationStandardCandidate, ...]:
    """已发布标准的创建候选（含不可用候选与其原因），顺序沿用标准库列表顺序。"""
    return tuple(
        _candidate(store, summary.standard_id, summary.version, manifests)
        for summary in store.list()
        if summary.status == "published" and isinstance(summary.version, int)
    )


def standard_package_root(
    store: StandardStore, standard_id: str, version: int | str
) -> Path | None:
    """已发布标准的包目录；读取顺序与 :meth:`StandardStore.get` 一致。"""
    segment = str(version)
    for root in (store.published_root, store.official_root):
        candidate = Path(root) / standard_id / segment
        if (candidate / "document.json").is_file():
            return candidate
    return None


def standard_document_digest(document: Mapping[str, object]) -> str:
    """已发布标准文档的内容哈希：标准任一处内容变化都改变预览摘要。"""
    return _digest(document)


def _candidate(
    store: StandardStore, standard_id: str, version: int, manifests: Mapping[str, object]
) -> CreationStandardCandidate:
    """单个候选：文档不可解析时也要给出稳定原因，不冒泡成 500。

    已发布文件是不可信输入：截断/非 UTF-8 的 ``document.json`` 在 ``StandardStore.get``
    内部抛出 ``OSError``/``ValueError``（含 ``UnicodeDecodeError``），与 Schema 解析失败
    同一口径处理——该标准不可用并附原因，其它候选不受影响。
    """
    try:
        standard = store.get(standard_id, version)
    except (StandardSchemaError, StandardStoreError, OSError, ValueError) as exc:
        return CreationStandardCandidate(
            standard_id=standard_id,
            version=version,
            name="",
            available=False,
            reasons=(f"标准文档无法解析：{exc}",),
        )
    if standard is None:
        return CreationStandardCandidate(
            standard_id=standard_id,
            version=version,
            name="",
            available=False,
            reasons=("标准已发布内容不可读取",),
        )
    snapshot = resolve_creation_assets(store, standard)
    reasons = (
        *_dependency_reasons(standard.dependencies, manifests),
        *snapshot.unavailable_reasons(),
    )
    return CreationStandardCandidate(
        standard_id=standard.standard_id,
        version=standard.version,
        name=standard.name,
        supported_cad_versions=standard.supported_cad_versions,
        available=not reasons,
        reasons=reasons,
        asset_options=snapshot.options,
    )


def _dependency_reasons(
    dependencies: Sequence[StandardDependency], manifests: Mapping[str, object]
) -> list[str]:
    """标准声明的受信依赖缺口（与发布门禁同一份判定）。"""
    return [
        f"受信扩展依赖未满足：{gap.extension_id}/{gap.capability_id}（{gap.reason}）"
        for gap in standard_dependency_gaps(dependencies, manifests)
    ]


def _creation_assets(standard: DrawingStandard) -> tuple[StandardAsset, ...]:
    """参与创建的资产：只含两种模板种类且至少声明一个文件。"""
    return tuple(
        asset
        for asset in standard.assets
        if asset.kind in CREATION_ASSET_KINDS and asset.files
    )


def _asset_labels(assets: Sequence[StandardAsset]) -> dict[str, str]:
    """同类资产标签：文件名优先，文件名冲突项退回完整包内相对路径。"""
    names = [_file_name(asset.files[0].path) for asset in assets]
    duplicated = {name for name in names if names.count(name) > 1}
    labels: dict[str, str] = {}
    for asset, name in zip(assets, names, strict=True):
        labels[asset.asset_id] = asset.files[0].path if name in duplicated else name
    return labels


def _asset_layouts(asset: StandardAsset) -> tuple[str, ...]:
    """布局模板声明的图幅角色（去重保序）；基础模板通常没有角色。"""
    layouts: list[str] = []
    for file in asset.files:
        if file.role and file.role not in layouts:
            layouts.append(file.role)
    return tuple(layouts)


def _file_name(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).name


def _controlled_file(root: Path | None, relative: str) -> Path | None:
    """受控资产文件定位：越界路径与缺失文件都返回 None。

    路径安全规则复用标准资产检查（``StandardAssetOperations._asset_file``），
    不另立第二套「包内相对路径」判定。
    """
    if root is None:
        return None
    try:
        return StandardAssetOperations._asset_file(root, relative)
    except ApplicationError:
        return None


def _file_digest(path: Path | None) -> str:
    if path is None:
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assets_digest(files: Sequence[CreationAssetFile]) -> str:
    """资产内容摘要：``asset_id + 包内路径 + 内容哈希``（缺失文件记空哈希）。"""
    return _digest([[item.asset_id, item.path, item.sha256] for item in files])


def _digest(payload: object) -> str:
    """稳定序列化（排序键 + 固定分隔符）后取 SHA-256；不使用 ``hash()``。"""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
