"""标准模板资产检查与 DST 草稿导入（PLAN-DM-035 Task 5）。

`StandardAssetOperations` 以 mixin 组合进 `DstManagerService`：资产检查复用
`get_layout_names` 的固定 CAD 只读读取协议，把能力缺失/读取失败/文件缺失
全部转换为稳定诊断而不抛出；布局模板声明的图幅与非 Model 布局严格比较
（大小写与空白敏感）。DST 导入只提取属性定义，构成最小安全草稿。
"""

from dataclasses import dataclass
from pathlib import Path

from dst_manager.application.errors import ApplicationError
from dst_manager.domain.models import Severity, ValidationIssue
from dst_manager.domain.standards import parse_standard_draft_document
from dst_manager.infrastructure.acsm_xml import AcsmValidationError
from dst_manager.infrastructure.dst_codec import CodecError
from dst_manager.infrastructure.standards.asset_paths import (
    StandardAssetError,
    resolve_asset_file,
)
from dst_manager.infrastructure.standards.dst_import import (
    ImportedStandardDraft,
    extract_standard_document,
)
from dst_manager.infrastructure.standards.store import StandardStoreError

MODEL_LAYOUT = "Model"

#: 资产复制端点稳定错误码 → HTTP 状态；未登记码一律 422。
_ASSET_STORE_STATUS = {"STANDARD_ASSET_SOURCE_NOT_FOUND": 404}


def _asset_store_error(exc: StandardStoreError) -> ApplicationError:
    code = str(exc).split(":", 1)[0]
    return ApplicationError(code, str(exc), _ASSET_STORE_STATUS.get(code, 422))


@dataclass(frozen=True, slots=True)
class AssetInspection:
    """一次资产检查的结果：实际布局与诊断列表。

    诊断非空表示资产不能通过发布门禁；``layouts`` 为已成功读取的布局名。
    """

    asset_id: str
    kind: str
    layouts: tuple[str, ...] = ()
    diagnostics: tuple[ValidationIssue, ...] = ()


class StandardAssetOperations:
    """经 `self` 访问 standard_store/codec/get_layout_names 的资产功能域。"""

    standard_store: object  # 由 DstManagerService.__init__ 注入 StandardStore

    # ---- 资产检查 --------------------------------------------------------

    def inspect_standard_asset(
        self, draft_id: str, asset_id: str, cad_version: str
    ) -> AssetInspection:
        """检查草稿中一个模板资产；问题以诊断返回，不抛出读取类错误。"""
        draft = self.standard_store.get_draft(draft_id)
        if draft is None:
            raise ApplicationError("STANDARD_DRAFT_NOT_FOUND", f"草稿 {draft_id!r} 不存在", 404)
        standard = parse_standard_draft_document(draft.document)
        asset = next(
            (item for item in standard.assets if item.asset_id == asset_id), None
        )
        if asset is None:
            raise ApplicationError("STANDARD_ASSET_NOT_FOUND", f"资产 {asset_id!r} 不在草稿 {draft_id!r} 中", 404)
        draft_dir = Path(self.standard_store.drafts_root) / draft_id
        diagnostics: list[ValidationIssue] = []
        layouts: list[str] = []
        seen_layouts: set[str] = set()
        for file in asset.files:
            source = self._asset_file(draft_dir, file.path)
            if source is None:
                diagnostics.append(
                    ValidationIssue(
                        "STANDARD_ASSET_FILE_MISSING",
                        Severity("error"),
                        f"资产 {asset_id!r} 声明的文件 {file.path!r} 不在草稿中",
                    ),
                )
                continue
            read = self._read_layouts(source, cad_version)
            if isinstance(read, ValidationIssue):
                diagnostics.append(read)
                continue
            for name in read:
                if name not in seen_layouts:
                    seen_layouts.add(name)
                    layouts.append(name)
            if file.role:
                mismatch = _layout_mismatch(file.role, read)
                if mismatch is not None:
                    diagnostics.insert(0, mismatch)
        return AssetInspection(
            asset_id=asset_id,
            kind=asset.kind,
            layouts=tuple(layouts),
            diagnostics=tuple(diagnostics),
        )

    @staticmethod
    def _asset_file(draft_dir: Path, relative: str) -> Path | None:
        """复用仓储同源的资产路径边界；非法路径转 422，缺失文件返回 None。"""
        try:
            resolved = resolve_asset_file(draft_dir, relative)
        except StandardAssetError as exc:
            raise ApplicationError(
                str(exc).split(":", 1)[0], str(exc), 422
            ) from exc
        return resolved if resolved.is_file() else None

    def _read_layouts(self, source: Path, cad_version: str):
        """复用固定 CAD 读取协议；任何读取失败都转换为诊断而非抛出。"""
        try:
            result = self.get_layout_names(source, cad_version)
        except ApplicationError as exc:
            if exc.code == "CAD_CAPABILITY_UNAVAILABLE":
                return ValidationIssue(
                    "STANDARD_CAD_CAPABILITY_MISSING",
                    Severity("error"),
                    f"AutoCAD {cad_version} 未配置，无法检查资产布局：{exc}",
                )
            return ValidationIssue(
                "STANDARD_LAYOUT_READ_FAILED",
                Severity("error"),
                f"读取资产布局失败：{exc}",
            )
        return tuple(result.get("layouts", ()))

    # ---- 本机模板受控复制 ------------------------------------------------

    def copy_draft_asset_file(self, draft_id: str, source_path: Path) -> dict[str, str]:
        """把用户显式选择的本机模板复制到草稿受控目录，只返回包内相对路径。

        本机绝对路径只作一次性导入来源，不写入文档、不返回给前端。
        """
        try:
            relative = self.standard_store.copy_draft_asset(draft_id, Path(source_path))
        except StandardStoreError as exc:
            raise _asset_store_error(exc) from exc
        return {"path": relative}

    # ---- DST 导入 --------------------------------------------------------

    def create_draft_from_dst(self, path: Path) -> ImportedStandardDraft:
        """从现有 DST 建立最小标准草稿；失败不留任何草稿半成品。"""
        source = Path(path).expanduser().resolve()
        if source.suffix.casefold() != ".dst":
            raise ApplicationError("STANDARD_DST_IMPORT_SOURCE_INVALID", "来源文件必须是 .dst", 422)
        if not source.is_file():
            raise ApplicationError("STANDARD_DST_IMPORT_SOURCE_NOT_FOUND", f"来源 DST 不存在：{source}", 404)
        document = self._extract_import_document(source)
        try:
            draft = self.standard_store.create_draft(document)
        except StandardStoreError as exc:
            raise ApplicationError("STANDARD_DST_IMPORT_INVALID", f"DST 导入草稿被拒绝：{exc}", 422) from exc
        return ImportedStandardDraft(draft_id=draft.draft_id, document=draft.document)

    def _extract_import_document(self, source: Path) -> dict[str, object]:
        try:
            xml = self.codec.decode_file(source)
            return extract_standard_document(xml)
        except (CodecError, AcsmValidationError, ValueError) as exc:
            raise ApplicationError(
                "STANDARD_DST_IMPORT_INVALID", f"DST 无法导入：{exc}", 422
            ) from exc


def _layout_mismatch(role: str, layouts: tuple[str, ...]) -> ValidationIssue | None:
    actual = {name for name in layouts if name != MODEL_LAYOUT}
    if actual == {role}:
        return None
    return ValidationIssue(
        "STANDARD_LAYOUT_NAME_MISMATCH",
        Severity("error"),
        f"声明图幅 {role!r} 与实际布局 {sorted(actual)} 严格不一致",
    )
