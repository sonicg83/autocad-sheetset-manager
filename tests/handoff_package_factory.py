"""共享测试工厂：合成合法 Builder 成果包与 reseal 工具（PLAN-DB-001 Task 10）。

仅测试使用：用 dst_builder/dst_platform 真实工厂（计划、DST Codec、XLSX、
验证报告、manifest/handoff 装配）在给定根目录产出与 Builder 发布完全同构的
成果包，并提供篡改后重封 manifest/handoff 哈希的 :func:`reseal_package`。
Manager 产品代码不得 import 本模块。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from dst_builder.application.validation import build_validation_report
from dst_builder.domain.models import (
    AssetRole,
    AssetSnapshot,
    DraftProjectV1,
    NumberingInput,
    ProjectInput,
    SheetInput,
    TemplateInput,
)
from dst_builder.domain.normalization import canonical_json
from dst_builder.domain.planning import (
    commit_revision,
    create_plan,
    plan_payload,
    revision_payload,
)
from dst_builder.infrastructure.acsm.factory import build_dst_bytes
from dst_builder.infrastructure.autocad.request import (
    CAD_DRAWING_RESULT_SCHEMA,
    CadDrawingResultV1,
)
from dst_builder.infrastructure.catalog.xlsx import build_sheet_catalog_xlsx
from dst_builder.infrastructure.filesystem.package import (
    MANIFEST_FILE,
    assemble_package_files,
)

BUILD_ID = "11111111-1111-1111-1111-111111111111"
DWG_CONTENT = b"fake built dwg bytes"
CREATED_AT = "2026-09-18T00:00:00Z"
BUILDER_VERSION = "0.3.5"
MANIFEST_SCHEMA = "dst-builder.manifest/v1"
HANDOFF_SCHEMA = "dst-builder.handoff/v1"


@dataclass(slots=True)
class BuiltPackage:
    root: Path
    plan: object
    cad: CadDrawingResultV1
    files: dict[str, bytes]


def _canonical_inputs(title: str):
    draft = DraftProjectV1(
        project=ProjectInput(
            name="示例工程",
            stage="施工图",
            discipline="建筑",
            output_path="D:/deliveries/example-package",
        ),
        numbering=NumberingInput(prefix="A-", start=1, width=3),
        cad_version="2020",
        sheets=(SheetInput(title=title),),
        template=TemplateInput(
            base_asset_id="3f6b5a24-6a8e-4c2a-9c8f-0f5d7a1b2c31",
            layout_asset_id="8c1d2e3f-4a5b-4c6d-8e9f-0a1b2c3d4e5f",
            source_layout="A1",
        ),
    )
    assets = (
        AssetSnapshot(
            role=AssetRole.BASE,
            relative_path=f"assets/base/{'a' * 64}.dwg",
            sha256="a" * 64,
            size=2048,
        ),
        AssetSnapshot(
            role=AssetRole.LAYOUT,
            relative_path=f"assets/layout/{'b' * 64}.dwt",
            sha256="b" * 64,
            size=4096,
        ),
    )
    revision = commit_revision(draft, assets)
    return revision, create_plan(revision)


def make_builder_package(root: Path, *, title: str = "首层平面图") -> BuiltPackage:
    """在 ``root`` 产出一份哈希自洽的合法成果包（真实 DST/DWG/XLSX 字节）。"""
    revision, plan = _canonical_inputs(title)
    task = plan.sheetset_task
    cad = CadDrawingResultV1(
        schema=CAD_DRAWING_RESULT_SCHEMA,
        request_id="req-001",
        layout_name=task.layout_name,
        layout_handle="43D",
        database_version="AC1032",
        layouts=(task.layout_name,),
        diagnostics=(),
        dwg_size=len(DWG_CONTENT),
        dwg_sha256=hashlib.sha256(DWG_CONTENT).hexdigest(),
        cad_version="2020",
    )
    dst_bytes = build_dst_bytes(plan, cad)
    catalog_bytes = build_sheet_catalog_xlsx(
        number=task.sheet_number,
        title=task.sheet_title,
        dwg=task.dwg_path,
        layout=task.layout_name,
    )
    report = build_validation_report(
        plan=plan, cad_result=cad, dst_bytes=dst_bytes, catalog_bytes=catalog_bytes
    )
    files = assemble_package_files(
        plan=plan,
        revision_json=canonical_json(revision_payload(revision, revision.assets)),
        plan_json=canonical_json(plan_payload(revision)),
        report_json=canonical_json(
            {
                "schema": report.schema,
                "plan_id": report.plan_id,
                "revision_id": report.revision_id,
                "validator_versions": [
                    [name, version] for name, version in report.validator_versions
                ],
                "checks": [
                    {"name": check.name, "passed": check.passed, "issues": []}
                    for check in report.checks
                ],
            }
        ),
        dst_bytes=dst_bytes,
        dwg_bytes=DWG_CONTENT,
        catalog_bytes=catalog_bytes,
        build_id=BUILD_ID,
        builder_version=BUILDER_VERSION,
        created_at=CREATED_AT,
    )
    for relative, content in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return BuiltPackage(root=root, plan=plan, cad=cad, files=files)


def manifest_entries(root: Path) -> list[dict]:
    return json.loads((root / MANIFEST_FILE).read_text(encoding="utf-8"))["files"]


def entry_by_path(root: Path, relative: str) -> dict:
    return next(item for item in manifest_entries(root) if item["path"] == relative)


def reseal_package(
    root: Path,
    *,
    entries: list[dict] | None = None,
    patch=None,
) -> None:
    """按当前盘上内容重算 manifest 与 handoff（保持 path/role 不变）。

    ``entries`` 提供时以其为 manifest 文件清单（支持增删与改写条目）；
    盘上不存在的条目保留调用方给定的 size/sha256（越界路径场景）。
    ``patch`` 在 size/sha256 重算之后、封签之前对每个条目做最后改写。
    """
    manifest_path = root / MANIFEST_FILE
    if entries is None:
        entries = manifest_entries(root)
    for entry in entries:
        candidate = root / entry["path"]
        if PureWindowsPath(entry["path"]).drive or not candidate.is_file():
            continue
        payload = candidate.read_bytes()
        entry["size"] = len(payload)
        entry["sha256"] = hashlib.sha256(payload).hexdigest()
    if patch is not None:
        entries = [patch(entry) for entry in entries]
    entries.sort(key=lambda item: item["path"])
    manifest_bytes = canonical_json({"schema": MANIFEST_SCHEMA, "files": entries}).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    handoff_path = root / "metadata" / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["manifest_sha256"] = manifest_sha256
    handoff["package_id"] = str(
        uuid.uuid5(uuid.NAMESPACE_URL, "dst-builder:package:" + manifest_sha256)
    )
    handoff_path.write_bytes(canonical_json(handoff).encode("utf-8"))
