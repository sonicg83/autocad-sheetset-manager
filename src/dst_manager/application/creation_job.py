"""创建暂存工作单元：在隔离 attempt 中生成候选成果（PLAN-DM-036 Task 5）。

`CreationJobRunner.stage(job_id, attempt, plan)` 只做**暂存**，不写目标项目目录、
不调用发布器（发布是新项目发布事务的职责）：它把计划实例化成 Manager 内置的
最小 DST 骨架，对每个图纸组从标准包内受控基础模板复制一个主 DWG，用固定
Worker 请求导入选中图幅并为组内每张 Sheet 创建计划布局，回填真实 Handle，然后
完成契约/XSD/语义校验、DST 编码→解码往返与 DWG 实际布局集合的逐项比对。

隔离与失败语义：

- 候选物（DST、每组主 DWG、脚本与日志）全部落在 Manager 应用数据目录下的
  ``creation-jobs/<job_id>/attempt-<NNN>/``，与既有 CAD 作业的 attempt 命名一致；
  重试使用新 attempt，不覆盖旧 attempt；
- 布局模板的真实布局集合必须包含标准声明的图幅，主 DWG 的实际布局集合必须与
  计划逐项一致，任何非法/占位/重复 Handle 都拒绝：任一项不符即整个任务失败；
- 任何一步失败只留隔离 attempt 日志，不产出半成品候选，也不在目标目录留下文件。

本模块不启动 CAD：CAD 能力与固定命令由 :mod:`dst_manager.infrastructure.autocad.worker`
承担，可在测试中注入替身。候选物的对外值类型与稳定错误见
:mod:`dst_manager.application.creation_candidate`（容量契约：单文件约 500 行，
本模块只留运行流程）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dst_manager.application.creation_candidate import (
    CreationCandidate,
    CreationJobError,
    CreationValidationReport,
    StagedDrawing,
)
from dst_manager.application.errors import ApplicationError
from dst_manager.application.standard_assets import StandardAssetOperations
from dst_manager.domain.creation import SHEET_SCOPE, SHEETSET_SCOPE
from dst_manager.domain.creation_plan_models import CreationPlan, SheetPlan
from dst_manager.domain.models import Severity
from dst_manager.infrastructure.acsm_xml import (
    AcsmDocument,
    AcsmValidationError,
    load_acsm,
)
from dst_manager.infrastructure.acsm_xml.creation import (
    CREATION_DST_NAME,
    STANDARD_IDENTITY_PROPERTY,
    STANDARD_OPTIONS_PROPERTY,
    CreationAcsmError,
    apply_layout_handles,
    build_minimal_acsm,
    pending_layout_handles,
    standard_options_value,
)
from dst_manager.infrastructure.autocad.worker import (
    LayoutCreationError,
    LayoutCreationOutcome,
    LayoutCreationRequest,
    LayoutCreationWorker,
)
from dst_manager.infrastructure.dst_codec import DstCodec
from dst_manager.infrastructure.filesystem.publisher import file_sha256
from dst_manager.infrastructure.logging_text import sanitize_log_text

__all__ = [
    "CREATION_JOBS_DIR_NAME",
    "CreationCandidate",
    "CreationJobError",
    "CreationJobRunner",
    "CreationValidationReport",
    "StagedDrawing",
]

#: 创建暂存的作业根：Manager 应用数据目录下的独立命名空间（与创建草稿同级）。
CREATION_JOBS_DIR_NAME = "creation-jobs"
#: 作业 ID 参与暂存路径拼接，只接受受控字符集与长度（越界片段一律拒绝）。
_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: Worker/回读失败码 → 创建暂存稳定错误码。
_CAD_FAILURE_CODES = {
    "HANDLE_OUTPUT_INVALID": "CREATION_HANDLE_INVALID",
    "HANDLE_OUTPUT_EMPTY": "CREATION_HANDLE_INVALID",
    "LAYOUT_READ_FAILED": "CREATION_LAYOUT_READ_FAILED",
    "LAYOUT_CREATION_REQUEST_INVALID": "CREATION_PLAN_INVALID",
    "CAD_CAPABILITY_UNAVAILABLE": "CREATION_CAD_UNAVAILABLE",
}


@dataclass(frozen=True, slots=True)
class _AttemptLayout:
    """一个 attempt 的隔离目录结构（与既有 CAD 作业的 attempt 布局一致）。"""

    root: Path

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def scripts_dir(self) -> Path:
        return self.root / "scripts"

    @property
    def staging_dir(self) -> Path:
        return self.root / "staging"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "creation.log"

    @property
    def directories(self) -> tuple[Path, ...]:
        return (self.input_dir, self.scripts_dir, self.staging_dir, self.logs_dir)


class CreationJobRunner:
    """创建暂存运行器：把已校验的创建计划变成隔离 attempt 中的候选成果。"""

    def __init__(
        self,
        *,
        data_dir: Path,
        asset_root: Path,
        worker: LayoutCreationWorker,
        timeout: int,
        codec: DstCodec | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("CREATION_TIMEOUT_INVALID")
        self.data_dir = Path(data_dir)
        #: 标准包根：计划里的模板路径是包内相对路径，这里解析成真实文件。
        self.asset_root = Path(asset_root)
        self.worker = worker
        self.timeout = timeout
        self.codec = codec if codec is not None else DstCodec()

    def stage(self, job_id: str, attempt: int, plan: CreationPlan) -> CreationCandidate:
        """在独立 attempt 暂存目录生成候选成果；不写目标项目目录、不调用发布器。"""
        self._require_job_identity(job_id, attempt)
        self._require_plan(plan)
        layout = _AttemptLayout(
            self.data_dir / CREATION_JOBS_DIR_NAME / job_id / f"attempt-{attempt:03d}"
        )
        for directory in layout.directories:
            directory.mkdir(parents=True, exist_ok=True)
        try:
            return self._stage(job_id, attempt, plan, layout)
        except CreationAcsmError as exc:
            # 骨架实例化/回填的稳定码原样透出（统一成创建暂存错误类型）
            _append_attempt_log(layout.log_path, f"FAILED {exc.code}: {exc}")
            raise CreationJobError(exc.code, str(exc)) from exc
        except Exception as exc:
            _append_attempt_log(
                layout.log_path,
                f"FAILED {getattr(exc, 'code', type(exc).__name__)}: {exc}",
            )
            raise

    # ---- 暂存主流程 ------------------------------------------------------

    def _stage(
        self, job_id: str, attempt: int, plan: CreationPlan, layout: _AttemptLayout
    ) -> CreationCandidate:
        document = build_minimal_acsm(plan)
        _append_attempt_log(layout.log_path, "SKELETON_INSTANTIATED")
        pairs = _planned_sheet_pairs(document, plan)
        staged, references, handles, layouts = self._stage_groups(plan, pairs, layout)
        try:
            document.apply_layout_references(references, Path(plan.target_path))
        except AcsmValidationError as exc:
            raise CreationJobError("CREATION_LAYOUT_REFERENCE_INVALID", str(exc)) from exc
        apply_layout_handles(document, handles)
        pending = pending_layout_handles(document)
        if pending:
            raise CreationJobError(
                "CREATION_HANDLE_PLACEHOLDER",
                f"仍有 {len(pending)} 张图纸未回填布局 Handle",
            )
        dst_path, report = self._write_candidate_dst(document, plan, handles, layout)
        _append_attempt_log(
            layout.log_path, f"CANDIDATE {dst_path.name} sha256={report.encoded_sha256}"
        )
        return CreationCandidate(
            job_id=job_id,
            attempt=attempt,
            attempt_dir=layout.root,
            target_path=plan.target_path,
            dst_name=CREATION_DST_NAME,
            dst_path=dst_path,
            dwgs=staged,
            layouts=layouts,
            handles=handles,
            report=report,
        )

    def _stage_groups(
        self,
        plan: CreationPlan,
        pairs: tuple[tuple[tuple[str, SheetPlan], ...], ...],
        layout: _AttemptLayout,
    ) -> tuple[
        tuple[StagedDrawing, ...], dict[str, dict[str, str]], dict[str, str], dict[str, str]
    ]:
        """逐组复制主 DWG 并运行固定布局创建请求；任一组失败即整个任务失败。"""
        staged: list[StagedDrawing] = []
        references: dict[str, dict[str, str]] = {}
        handles: dict[str, str] = {}
        layouts: dict[str, str] = {}
        templates: dict[str, tuple[Path, tuple[str, ...]]] = {}
        for index, group in enumerate(plan.groups):
            template_source = templates.get(group.layout_template)
            if template_source is None:
                template_source = self._prepare_layout_template(
                    len(templates), group.layout_template, layout
                )
                templates[group.layout_template] = template_source
            import_source, real_layouts = template_source
            if group.paper_layout not in real_layouts:
                raise CreationJobError(
                    "CREATION_LAYOUT_TEMPLATE_MISMATCH",
                    f"布局模板 {group.layout_template!r} 的真实布局 {sorted(real_layouts)!r} "
                    f"不含标准声明的图幅 {group.paper_layout!r}",
                )
            staged_path = layout.staging_dir / f"group-{index:03d}" / group.dwg_name
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self._asset_file(group.base_template), staged_path)
            request = LayoutCreationRequest(
                layout_template=import_source,
                paper_layout=group.paper_layout,
                target_layouts=tuple(sheet.layout_name for sheet in group.sheets),
            )
            outcome = self._create_group_layouts(
                staged_path,
                request,
                layout.scripts_dir / f"create-{index:03d}.scr",
                layout,
            )
            expected = {sheet.layout_name for sheet in group.sheets}
            if set(outcome.layouts) != expected or len(outcome.layouts) != len(group.sheets):
                raise CreationJobError(
                    "CREATION_LAYOUT_SET_MISMATCH",
                    f"图纸组 {group.group_id!r} 的实际布局 {sorted(outcome.layouts)!r} "
                    f"与计划 {sorted(expected)!r} 不一致",
                )
            _append_attempt_log(
                layout.log_path,
                f"GROUP {index:03d} {group.dwg_name} layouts={sorted(outcome.layouts)} "
                f"handles={sorted(outcome.handles.values())}",
            )
            staged.append(StagedDrawing(group.group_id, staged_path, group.dwg_name))
            for sheet_id, sheet_plan in pairs[index]:
                references[sheet_id] = {
                    "file": group.target_path,
                    "layout": sheet_plan.layout_name,
                }
                handles[sheet_id] = outcome.handles[sheet_plan.layout_name]
                layouts[sheet_id] = sheet_plan.layout_name
        return tuple(staged), references, handles, layouts

    def _prepare_layout_template(
        self, index: int, relative: str, layout: _AttemptLayout
    ) -> tuple[Path, tuple[str, ...]]:
        """把布局模板复制进 attempt 并读回真实布局集合。

        两份副本各司其职：``.dwg`` 副本用于只读枚举（accoreconsole ``/i`` 打开
        ``.dwt`` 会按模板新建图形，枚举结果不可信），保留原扩展名的副本用于
        ``-LAYOUT _Template``（与既有 CAD 作业同一路径）。两份都不碰标准包原件。
        """
        source = self._asset_file(relative)
        import_source = layout.input_dir / f"template-{index:03d}-{source.name}"
        shutil.copy2(source, import_source)
        enumeration_copy = layout.input_dir / f"template-{index:03d}.dwg"
        shutil.copy2(source, enumeration_copy)
        return import_source, self._layout_template_layouts(enumeration_copy, layout)

    def _layout_template_layouts(
        self, drawing: Path, layout: _AttemptLayout
    ) -> tuple[str, ...]:
        try:
            names = self.worker.layout_names(drawing, layout.input_dir, self.timeout)
        except (LayoutCreationError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
            raise CreationJobError(_cad_failure_code(exc), str(exc)) from exc
        _append_attempt_log(
            layout.log_path, f"TEMPLATE {drawing.name} layouts={sorted(names)}"
        )
        return tuple(names)

    def _create_group_layouts(
        self,
        drawing: Path,
        request: LayoutCreationRequest,
        script_path: Path,
        layout: _AttemptLayout,
    ) -> LayoutCreationOutcome:
        try:
            return self.worker.create_layouts(drawing, request, script_path, self.timeout)
        except (LayoutCreationError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
            raise CreationJobError(_cad_failure_code(exc), str(exc)) from exc

    def _write_candidate_dst(
        self,
        document: AcsmDocument,
        plan: CreationPlan,
        handles: dict[str, str],
        layout: _AttemptLayout,
    ) -> tuple[Path, CreationValidationReport]:
        """写出暂存 DST 并做编码往返校验：失败即整个任务失败，不留候选。"""
        final_dir = layout.staging_dir / "final-dst"
        final_dir.mkdir(parents=True, exist_ok=True)
        dst_path = final_dir / CREATION_DST_NAME
        self.codec.encode_file(document.to_bytes(), dst_path)
        roundtrip = load_acsm(self.codec.decode_file(dst_path))
        if roundtrip.repair_report.status != "VALID":
            raise CreationJobError(
                "CREATION_DST_INVALID",
                "候选 DST 的修复状态非 VALID：" + roundtrip.repair_report.status,
            )
        issues = roundtrip.validate()
        errors = [issue for issue in issues if issue.severity == Severity.ERROR]
        if errors:
            raise CreationJobError(
                "CREATION_DST_INVALID",
                "候选 DST 未通过契约/XSD/语义校验："
                + ", ".join(sorted({issue.code for issue in errors})),
            )
        _verify_roundtrip(roundtrip, plan, handles)
        return dst_path, CreationValidationReport(
            repair_status=roundtrip.repair_report.status,
            semantic_issue_codes=tuple(sorted({issue.code for issue in issues})),
            encoded_sha256=file_sha256(dst_path),
            dwg_count=len(plan.groups),
            sheet_count=sum(group.sheet_count for group in plan.groups),
        )

    # ---- 门禁与资产定位 --------------------------------------------------

    @staticmethod
    def _require_job_identity(job_id: str, attempt: int) -> None:
        """作业身份门禁：作业 ID 参与暂存路径拼接，必须是受控形状。"""
        if not isinstance(job_id, str) or not _JOB_ID_PATTERN.fullmatch(job_id):
            raise CreationJobError("CREATION_JOB_ID_INVALID", f"作业 ID 非法：{job_id!r}")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise CreationJobError(
                "CREATION_ATTEMPT_INVALID", f"attempt 必须为正整数：{attempt!r}"
            )

    @staticmethod
    def _require_plan(plan: CreationPlan) -> None:
        """计划门禁：阻断计划、空路径、空组与缺命名结果都不得进入暂存。"""
        if plan.has_errors:
            raise CreationJobError(
                "CREATION_PLAN_INVALID",
                "创建计划存在阻断诊断："
                + ", ".join(sorted({item.code for item in plan.diagnostics if item.is_error})),
            )
        if not plan.target_path:
            raise CreationJobError("CREATION_PLAN_INVALID", "创建计划缺少最终项目路径")
        if not plan.groups:
            raise CreationJobError("CREATION_PLAN_INVALID", "创建计划没有任何图纸组")
        for group in plan.groups:
            if not group.dwg_name or not group.target_path or not group.sheets:
                raise CreationJobError(
                    "CREATION_PLAN_INVALID",
                    f"图纸组 {group.group_id!r} 缺少可执行的命名结果",
                )

    def _asset_file(self, relative: str) -> Path:
        """标准包内受控资产定位：路径安全规则复用标准资产的唯一实现。"""
        try:
            resolved = StandardAssetOperations._asset_file(self.asset_root, relative)
        except ApplicationError as exc:
            raise CreationJobError("CREATION_ASSET_PATH_INVALID", str(exc)) from exc
        if resolved is None:
            raise CreationJobError(
                "CREATION_ASSET_FILE_MISSING", f"标准包资产文件不存在：{relative!r}"
            )
        return resolved


def _planned_sheet_pairs(
    document: AcsmDocument, plan: CreationPlan
) -> tuple[tuple[tuple[str, SheetPlan], ...], ...]:
    """按计划顺序把骨架里的图纸与计划配对（骨架由同一计划实例化，顺序一致）。

    配对结果同时用于写最终布局引用/Handle 与往返逐项比对；数量不一致说明骨架
    实例化有缺陷，直接失败而不是猜测对应关系。
    """
    subsets = document.root.xpath("//*[local-name()='AcSmSubset']")
    if len(subsets) != len(plan.groups):
        raise CreationJobError(
            "CREATION_SKELETON_INVALID",
            f"骨架子集数 {len(subsets)} 与计划组数 {len(plan.groups)} 不一致",
        )
    groups: list[tuple[tuple[str, SheetPlan], ...]] = []
    for subset, group in zip(subsets, plan.groups, strict=True):
        sheets = subset.xpath("./*[local-name()='AcSmSheet']")
        if len(sheets) != group.sheet_count:
            raise CreationJobError(
                "CREATION_SKELETON_INVALID",
                f"图纸组 {group.group_id!r} 的骨架图纸数 {len(sheets)} 与计划 {group.sheet_count} 不一致",
            )
        groups.append(
            tuple(
                (sheet.get("ID", ""), sheet_plan)
                for sheet, sheet_plan in zip(sheets, group.sheets, strict=True)
            )
        )
    return tuple(groups)


def _verify_roundtrip(
    document: AcsmDocument, plan: CreationPlan, handles: dict[str, str]
) -> None:
    """编码→解码→加载→project()：DST 内容必须与计划逐项一致。"""
    projected = document.project(Path(plan.target_path))
    if projected.name != Path(plan.target_path).name:
        raise _roundtrip_error(f"图纸集名称 {projected.name!r} 与目录名不一致")
    if [subset.name for subset in projected.subsets] != [
        group.title for group in plan.groups
    ]:
        raise _roundtrip_error("子集名称与计划不一致")
    expected = [
        (group, sheet) for group in plan.groups for sheet in group.sheets
    ]
    if len(projected.sheets) != len(expected):
        raise _roundtrip_error(
            f"往返后图纸数 {len(projected.sheets)} 与计划 {len(expected)} 不一致"
        )
    for sheet, (group, sheet_plan) in zip(projected.sheets, expected, strict=True):
        if (sheet.number, sheet.title) != (sheet_plan.number, sheet_plan.title):
            raise _roundtrip_error(
                f"图纸 {sheet.acsm_id} 的图号/标题与计划不一致：{sheet.number!r}/{sheet.title!r}"
            )
        if sheet.layout.layout_name != sheet_plan.layout_name:
            raise _roundtrip_error(f"图纸 {sheet.acsm_id} 的布局名与计划不一致")
        if sheet.layout.file_name != group.target_path:
            raise _roundtrip_error(f"图纸 {sheet.acsm_id} 的绝对 DWG 引用与计划不一致")
        if sheet.layout.relative_file_name != ".\\" + group.dwg_name:
            raise _roundtrip_error(f"图纸 {sheet.acsm_id} 的相对 DWG 引用与计划不一致")
        if sheet.layout.handle.upper() != handles.get(sheet.acsm_id, "").upper():
            raise _roundtrip_error(f"图纸 {sheet.acsm_id} 的 Handle 与回读结果不一致")
        for prop in plan.settings.properties:
            if prop.scope != SHEET_SCOPE:
                continue
            if sheet.custom_properties.get(prop.name, "") != sheet_plan.values.get(
                prop.property_id, ""
            ):
                raise _roundtrip_error(
                    f"图纸 {sheet.acsm_id} 的属性 {prop.name!r} 与计划不一致"
                )
    for prop in plan.settings.properties:
        if prop.scope != SHEETSET_SCOPE:
            continue
        if projected.custom_properties.get(prop.name, "") != plan.sheetset_values.get(
            prop.property_id, ""
        ):
            raise _roundtrip_error(f"图纸集属性 {prop.name!r} 与计划不一致")
    if projected.custom_properties.get(STANDARD_IDENTITY_PROPERTY) != (
        plan.settings.standard_identity
    ):
        raise _roundtrip_error("标准身份保留属性与计划不一致")
    if projected.custom_properties.get(STANDARD_OPTIONS_PROPERTY) != (
        standard_options_value(plan.settings)
    ):
        raise _roundtrip_error("有效编号配置保留属性与计划不一致")


def _roundtrip_error(detail: str) -> CreationJobError:
    return CreationJobError("CREATION_ROUNDTRIP_MISMATCH", detail)


def _cad_failure_code(exc: BaseException) -> str:
    """Worker/回读故障 → 创建暂存稳定错误码。"""
    if "CAD_CAPABILITY_UNAVAILABLE" in str(exc):
        return "CREATION_CAD_UNAVAILABLE"
    code = getattr(exc, "code", "")
    if isinstance(code, str) and code:
        return _CAD_FAILURE_CODES.get(code, "CREATION_CAD_FAILED")
    return "CREATION_CAD_FAILED"


def _append_attempt_log(path: Path, message: str) -> None:
    """追加一条隔离 attempt 日志；日志本身失败不得掩盖真实失败原因。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(UTC).isoformat()} {sanitize_log_text(message)}\n")
    except OSError:
        pass
