"""草稿校验、不可变修订与确定性计划（SPEC-DB-001 §4/§5/§11，纯函数无 I/O）。

入口：

* ``validate_draft(draft, *, output_exists)``：字段规则与构建前校验，产出诊断；
* ``commit_revision(draft, assets)``：冻结不可变修订（确定性哈希与 ID）；
* ``create_plan(revision)``：由修订派生确定性生成计划；
* ``check_plan_stale(plan, revision)``：修订漂移使已确认计划失效（PLAN_STALE）。

诊断码只使用 §11 固定错误码（PROJECT_PATH_INVALID / PACKAGE_TARGET_EXISTS /
PLAN_STALE）；§4 字段级违规统一归入 DRAFT_FIELD_INVALID 并以 ``field`` 区分。
``output_path`` 不进入修订与计划的规范化载荷，由 ``BuildRun`` 单独快照。
"""

from __future__ import annotations

import uuid

from dst_builder.domain.models import (
    DRAFT_FIELD_INVALID,
    DRAFT_SCHEMA_VERSION,
    PACKAGE_TARGET_EXISTS,
    PLAN_STALE,
    PROJECT_PATH_INVALID,
    RULESET_VERSION,
    WORKER_COMMAND_NAME,
    AssetRole,
    AssetSnapshot,
    Diagnostic,
    DiagnosticSeverity,
    DraftProjectV1,
    DrawingTask,
    ExpectedArtifact,
    GenerationPlanV1,
    NumberingInput,
    ProjectRevisionV1,
    RevisionProject,
    SheetInput,
    SheetsetTask,
    TemplateInput,
)
from dst_builder.domain.normalization import (
    MAX_NUMBERING_START,
    MAX_NUMBERING_WIDTH,
    canonical_json,
    dwg_name,
    layout_name,
    plan_id_from_sha256,
    revision_id_from_sha256,
    sha256_hex,
    sheet_number,
    task_id_from_revision_sha256,
)
from dst_platform.contracts.naming import (
    contains_unsafe_filename_char,
    ends_with_dot_or_space,
    validate_windows_file_name,
)

__all__ = [
    "PACKAGE_TARGET_EXISTS",
    "PLAN_STALE",
    "PROJECT_PATH_INVALID",
    "SHEETSET_PATH",
    "SHEET_CATALOG_PATH",
    "check_plan_stale",
    "commit_revision",
    "create_plan",
    "plan_payload",
    "revision_payload",
    "validate_draft",
]

# 正式成果固定路径（§9）：目标目录内直接包含三件套，无包装子目录。
SHEETSET_PATH = "sheetset.dst"
SHEET_CATALOG_PATH = "图纸目录.xlsx"

_MAX_TEXT_CHARS = 100
_MAX_PREFIX_CHARS = 20
_CAD_VERSIONS = frozenset({"2016", "2020"})


def _is_absolute_output_path(value: str) -> bool:
    """接受 Windows 盘符/UNC 与 POSIX 绝对路径形态。"""
    if not value:
        return False
    if value.startswith(("\\\\", "//", "/")):
        return True
    drive = value[:2]
    return (
        len(value) > 2
        and drive[0].isascii()
        and drive[0].isalpha()
        and drive[1] == ":"
        and value[2] in "\\/"
    )


def _has_control_char(value: str) -> bool:
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)


def _blocking(code: str, message: str, field: str | None = None) -> Diagnostic:
    return Diagnostic(
        code=code, severity=DiagnosticSeverity.BLOCKING, message=message, field=field
    )


def _text_diagnostic(field: str, value: str, label: str) -> Diagnostic | None:
    normalized = value.strip()
    if not normalized or len(normalized) > _MAX_TEXT_CHARS or _has_control_char(normalized):
        return _blocking(
            DRAFT_FIELD_INVALID,
            f"{label}长度必须为 1～{_MAX_TEXT_CHARS} 个字符且不含控制字符",
            field,
        )
    return None


def validate_draft(
    draft: DraftProjectV1, *, output_exists: bool
) -> tuple[Diagnostic, ...]:
    """校验草稿字段与构建前条件；返回按固定字段顺序排列的阻断诊断。"""
    diagnostics: list[Diagnostic] = []

    for field, label in (
        ("project.name", "工程名称"),
        ("project.stage", "工程阶段"),
        ("project.discipline", "专业"),
    ):
        value = getattr(draft.project, field.removeprefix("project."))
        issue = _text_diagnostic(field, value, label)
        if issue is not None:
            diagnostics.append(issue)

    output_path = draft.project.output_path.strip()
    if not _is_absolute_output_path(output_path):
        diagnostics.append(
            _blocking(PROJECT_PATH_INVALID, "成果目录必须是绝对路径", "project.output_path")
        )
    elif output_exists:
        diagnostics.append(
            _blocking(
                PACKAGE_TARGET_EXISTS,
                "成果目录已存在；首期不覆盖或合并既有目录",
                "project.output_path",
            )
        )

    prefix = draft.numbering.prefix.strip()
    start = draft.numbering.start
    width = draft.numbering.width
    prefix_ok = not (
        len(prefix) > _MAX_PREFIX_CHARS
        or contains_unsafe_filename_char(prefix)
        or ends_with_dot_or_space(prefix)
    )
    if not prefix_ok:
        diagnostics.append(
            _blocking(
                DRAFT_FIELD_INVALID,
                "图号前缀长度为 0～20，不得包含 Windows 文件名非法字符、"
                "路径分隔符、控制字符或尾部句点/空格",
                "numbering.prefix",
            )
        )
    start_ok = 0 <= start <= MAX_NUMBERING_START
    if not start_ok:
        diagnostics.append(
            _blocking(
                DRAFT_FIELD_INVALID,
                f"起始序号必须在 0～{MAX_NUMBERING_START} 之间",
                "numbering.start",
            )
        )
    width_ok = 1 <= width <= MAX_NUMBERING_WIDTH
    if not width_ok:
        diagnostics.append(
            _blocking(
                DRAFT_FIELD_INVALID,
                f"位数必须在 1～{MAX_NUMBERING_WIDTH} 之间",
                "numbering.width",
            )
        )
    elif len(str(start)) > width:
        diagnostics.append(
            _blocking(
                DRAFT_FIELD_INVALID,
                f"起始序号 {start} 的十进制位数不得超过位数 {width}",
                "numbering.start",
            )
        )

    if draft.cad_version.strip() not in _CAD_VERSIONS:
        diagnostics.append(
            _blocking(DRAFT_FIELD_INVALID, "AutoCAD 版本只接受 2016 或 2020", "cad_version")
        )

    title = ""
    if len(draft.sheets) != 1:
        diagnostics.append(
            _blocking(DRAFT_FIELD_INVALID, "首期必须恰好编排一张图纸", "sheets")
        )
    else:
        title = draft.sheets[0].title.strip()
        title_issue = _text_diagnostic("sheets[0].title", draft.sheets[0].title, "图名")
        if title_issue is not None:
            diagnostics.append(title_issue)

    for field, label in (
        ("base_asset_id", "基础资产"),
        ("layout_asset_id", "布局资产"),
    ):
        value = getattr(draft.template, field).strip()
        try:
            uuid.UUID(value)
        except ValueError:
            diagnostics.append(
                _blocking(
                    DRAFT_FIELD_INVALID,
                    f"{label} ID 必须是 UUID",
                    f"template.{field}",
                )
            )

    source_layout = draft.template.source_layout.strip()
    if not source_layout or source_layout.casefold() == "model":
        diagnostics.append(
            _blocking(
                DRAFT_FIELD_INVALID,
                "源布局必须是非 Model 的实际布局名",
                "template.source_layout",
            )
        )

    derived_issue = _derived_name_diagnostic(
        prefix, start, width, title, prefix_ok and start_ok and width_ok
    )
    if derived_issue is not None:
        diagnostics.append(derived_issue)

    return tuple(diagnostics)


def _derived_name_diagnostic(
    prefix: str, start: int, width: int, title: str, inputs_valid: bool
) -> Diagnostic | None:
    """派生 layout_name/dwg_name 的危险名称校验（§4），根因字段归到图名。"""
    if not inputs_valid or not title:
        return None
    try:
        name = layout_name(sheet_number(prefix, start, width), title)
        validate_windows_file_name(name)
        validate_windows_file_name(dwg_name(name))
    except ValueError:
        return _blocking(
            DRAFT_FIELD_INVALID,
            "图号与图名组合出的布局名/文件名违反 Windows 命名规则"
            "（非法字符、保留设备名、尾点或超过 180 字符）",
            "sheets[0].title",
        )
    return None


def _asset_sort_key(asset: AssetSnapshot) -> tuple[str, str]:
    return (asset.role.value, asset.relative_path)


def revision_payload(
    draft: DraftProjectV1, assets: tuple[AssetSnapshot, ...]
) -> dict:
    """修订规范化载荷：业务字段 + 项目内资产；不含 output_path、时间与机器信息。"""
    project = draft.project
    return {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "project": {
            "name": project.name.strip(),
            "stage": project.stage.strip(),
            "discipline": project.discipline.strip(),
        },
        "numbering": {
            "prefix": draft.numbering.prefix.strip(),
            "start": draft.numbering.start,
            "width": draft.numbering.width,
        },
        "cad_version": draft.cad_version.strip(),
        "sheets": [{"title": sheet.title.strip()} for sheet in draft.sheets],
        "template": {
            "base_asset_id": draft.template.base_asset_id.strip(),
            "layout_asset_id": draft.template.layout_asset_id.strip(),
            "source_layout": draft.template.source_layout.strip(),
        },
        "assets": [
            {
                "role": asset.role.value,
                "relative_path": asset.relative_path,
                "sha256": asset.sha256,
                "size": asset.size,
            }
            for asset in sorted(assets, key=_asset_sort_key)
        ],
    }


def commit_revision(
    draft: DraftProjectV1, assets: tuple[AssetSnapshot, ...]
) -> ProjectRevisionV1:
    """把草稿冻结为不可变修订；相同业务输入与资产字节得到相同哈希与 ID。"""
    project = draft.project
    payload = revision_payload(draft, assets)
    sha256 = sha256_hex(canonical_json(payload))
    return ProjectRevisionV1(
        schema_version=DRAFT_SCHEMA_VERSION,
        ruleset_version=RULESET_VERSION,
        project=RevisionProject(
            name=project.name.strip(),
            stage=project.stage.strip(),
            discipline=project.discipline.strip(),
        ),
        numbering=NumberingInput(
            prefix=draft.numbering.prefix.strip(),
            start=draft.numbering.start,
            width=draft.numbering.width,
        ),
        cad_version=draft.cad_version.strip(),
        sheets=tuple(SheetInput(title=sheet.title.strip()) for sheet in draft.sheets),
        template=TemplateInput(
            base_asset_id=draft.template.base_asset_id.strip(),
            layout_asset_id=draft.template.layout_asset_id.strip(),
            source_layout=draft.template.source_layout.strip(),
        ),
        assets=tuple(sorted(assets, key=_asset_sort_key)),
        revision_sha256=sha256,
        revision_id=revision_id_from_sha256(sha256),
    )


def _revision_asset(revision: ProjectRevisionV1, role: AssetRole) -> AssetSnapshot:
    for asset in revision.assets:
        if asset.role is role:
            return asset
    raise ValueError(f"修订缺少资产：{role.value}")


def _derived_sheet_values(revision: ProjectRevisionV1) -> tuple[str, str, str]:
    number = sheet_number(
        revision.numbering.prefix, revision.numbering.start, revision.numbering.width
    )
    name = layout_name(number, revision.sheets[0].title)
    return number, name, dwg_name(name)


def _expected_artifacts(dwg: str) -> tuple[ExpectedArtifact, ...]:
    """正式成果全部预期文件（§9）：目标目录直接包含 DST、DWG 与图纸目录。"""
    entries = (
        ExpectedArtifact(path=SHEETSET_PATH, role="dst", required=True),
        ExpectedArtifact(path=dwg, role="dwg", required=True),
        ExpectedArtifact(path=SHEET_CATALOG_PATH, role="sheet-catalog", required=True),
    )
    return tuple(sorted(entries, key=lambda item: item.path))


def plan_payload(revision: ProjectRevisionV1) -> dict:
    """计划规范化载荷；confirmed_at、构建 ID、attempt 与日志路径不进入哈希。"""
    number, name, drawing = _derived_sheet_values(revision)
    base = _revision_asset(revision, AssetRole.BASE)
    layout_asset = _revision_asset(revision, AssetRole.LAYOUT)

    def asset_payload(asset: AssetSnapshot) -> dict:
        return {
            "role": asset.role.value,
            "relative_path": asset.relative_path,
            "sha256": asset.sha256,
            "size": asset.size,
        }

    return {
        "schema_version": DRAFT_SCHEMA_VERSION,
        "ruleset_version": RULESET_VERSION,
        "revision_id": revision.revision_id,
        "revision_sha256": revision.revision_sha256,
        "cad_version": revision.cad_version,
        "worker_command": WORKER_COMMAND_NAME,
        "drawing_task": {
            "task_id": task_id_from_revision_sha256(revision.revision_sha256, "drawing"),
            "base_asset": asset_payload(base),
            "layout_asset": asset_payload(layout_asset),
            "source_layout": revision.template.source_layout,
            "target_layout": name,
            "target_dwg_path": drawing,
        },
        "sheetset_task": {
            "dst_path": SHEETSET_PATH,
            "sheetset_name": revision.project.name,
            "subset_name": revision.project.discipline,
            "sheet_number": number,
            "sheet_title": revision.sheets[0].title,
            "dwg_path": drawing,
            "layout_name": name,
        },
        "expected_artifacts": [
            {"path": artifact.path, "role": artifact.role, "required": artifact.required}
            for artifact in _expected_artifacts(drawing)
        ],
        "diagnostics": [],
    }


def create_plan(revision: ProjectRevisionV1) -> GenerationPlanV1:
    """由不可变修订派生确定性计划；相同修订必然得到相同计划哈希与 ID。"""
    number, name, drawing = _derived_sheet_values(revision)
    payload = plan_payload(revision)
    sha256 = sha256_hex(canonical_json(payload))
    return GenerationPlanV1(
        schema_version=DRAFT_SCHEMA_VERSION,
        ruleset_version=RULESET_VERSION,
        revision_id=revision.revision_id,
        revision_sha256=revision.revision_sha256,
        cad_version=revision.cad_version,
        worker_command=WORKER_COMMAND_NAME,
        drawing_task=DrawingTask(
            task_id=task_id_from_revision_sha256(revision.revision_sha256, "drawing"),
            base_asset=_revision_asset(revision, AssetRole.BASE),
            layout_asset=_revision_asset(revision, AssetRole.LAYOUT),
            source_layout=revision.template.source_layout,
            target_layout=name,
            target_dwg_path=drawing,
        ),
        sheetset_task=SheetsetTask(
            dst_path=SHEETSET_PATH,
            sheetset_name=revision.project.name,
            subset_name=revision.project.discipline,
            sheet_number=number,
            sheet_title=revision.sheets[0].title,
            dwg_path=drawing,
            layout_name=name,
        ),
        expected_artifacts=_expected_artifacts(drawing),
        diagnostics=(),
        plan_sha256=sha256,
        plan_id=plan_id_from_sha256(sha256),
    )


def check_plan_stale(
    plan: GenerationPlanV1, revision: ProjectRevisionV1
) -> tuple[Diagnostic, ...]:
    """任何进入规范化修订的业务字段或资产变化都使当前确认失效（§5）。"""
    if (
        plan.revision_id == revision.revision_id
        and plan.revision_sha256 == revision.revision_sha256
    ):
        return ()
    return (
        _blocking(
            PLAN_STALE,
            "草稿已变化，当前确认的计划对应旧修订，必须重新提交修订与计划",
        ),
    )
