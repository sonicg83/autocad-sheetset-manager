"""验证报告聚合（SPEC-DB-001 §8/§9）：``dst-builder.validation-report/v1`` 装配。

汇总五类检查：输入计划、DWG 结果、DST、图纸目录 XLSX 与引用边界（DST 内
DWG 引用与预期成果路径都必须是目标目录内的裸文件名），并记录校验器版本；
诊断统一使用 ``dst_platform.contracts`` 共享类型（ValidationIssue/
Severity），绝不复制第二套诊断模型。本模块只聚合报告结构；正式成果写盘与
完整性判定由发布层（``infrastructure.filesystem.package``）负责，不再生成
manifest.json 与 handoff.json。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dst_builder.domain.models import (
    RULESET_VERSION,
    VALIDATION_REPORT_SCHEMA,
    DiagnosticSeverity,
    GenerationPlanV1,
)
from dst_builder.domain.planning import SHEET_CATALOG_PATH, SHEETSET_PATH
from dst_builder.infrastructure.acsm.factory import DST_DB_VERSION
from dst_builder.infrastructure.acsm.projection import validate_dst_bytes
from dst_builder.infrastructure.autocad.request import CadDrawingResultV1
from dst_builder.infrastructure.catalog import xlsx
from dst_platform.acsm.contract import CONTRACT_VERSION
from dst_platform.contracts.diagnostics import Severity, ValidationIssue

__all__ = [
    "VALIDATOR_VERSIONS",
    "ValidationCheck",
    "ValidationReportV1",
    "build_validation_report",
]

_HANDLE_PATTERN = re.compile(r"^[0-9A-Fa-f]+$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

VALIDATOR_VERSIONS: tuple[tuple[str, str], ...] = (
    ("acsm-contract", CONTRACT_VERSION),
    ("acsm-db-version", DST_DB_VERSION),
    ("dst-builder-ruleset", str(RULESET_VERSION)),
)


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    """单项检查：按名称聚合共享诊断；无 ERROR 即通过。"""

    name: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(issue.severity is Severity.ERROR for issue in self.issues)


@dataclass(frozen=True, slots=True)
class ValidationReportV1:
    """§9 ``dst-builder.validation-report/v1`` 报告结构。"""

    schema: str
    plan_id: str
    revision_id: str
    validator_versions: tuple[tuple[str, str], ...]
    checks: tuple[ValidationCheck, ...]

    @property
    def blocking(self) -> bool:
        return any(not check.passed for check in self.checks)

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for check in self.checks for issue in check.issues)


def build_validation_report(
    *,
    plan: GenerationPlanV1,
    cad_result: CadDrawingResultV1,
    dst_bytes: bytes,
    catalog_bytes: bytes,
) -> ValidationReportV1:
    """聚合全部检查生成报告结构（纯函数，无 I/O）。"""
    return ValidationReportV1(
        schema=VALIDATION_REPORT_SCHEMA,
        plan_id=plan.plan_id,
        revision_id=plan.revision_id,
        validator_versions=VALIDATOR_VERSIONS,
        checks=(
            _check_input(plan),
            _check_dwg(plan, cad_result),
            _check_dst(plan, cad_result, dst_bytes),
            _check_catalog(plan, catalog_bytes),
            _check_reference_boundary(plan),
        ),
    )


def _issue(code: str, message: str) -> ValidationIssue:
    return ValidationIssue(code, Severity.ERROR, message)


def _check_input(plan: GenerationPlanV1) -> ValidationCheck:
    issues: list[ValidationIssue] = []
    if plan.schema_version != 1:
        issues.append(_issue("PLAN_SCHEMA_UNSUPPORTED", f"计划 Schema 版本不支持：{plan.schema_version}"))
    if plan.ruleset_version != RULESET_VERSION:
        issues.append(_issue("PLAN_RULESET_UNSUPPORTED", f"规则集版本不支持：{plan.ruleset_version}"))
    severity_map = {
        DiagnosticSeverity.BLOCKING: Severity.ERROR,
        DiagnosticSeverity.WARNING: Severity.WARNING,
        DiagnosticSeverity.INFO: Severity.INFO,
    }
    issues.extend(
        ValidationIssue(
            diagnostic.code,
            severity_map[diagnostic.severity],
            diagnostic.message,
            diagnostic.field,
        )
        for diagnostic in plan.diagnostics
    )
    return ValidationCheck("input", tuple(issues))


def _check_dwg(plan: GenerationPlanV1, cad_result: CadDrawingResultV1) -> ValidationCheck:
    issues: list[ValidationIssue] = []
    if cad_result.layout_name != plan.drawing_task.target_layout:
        issues.append(
            _issue(
                "DWG_LAYOUT_MISMATCH",
                f"DWG 布局名应为 {plan.drawing_task.target_layout!r}，实际 {cad_result.layout_name!r}",
            )
        )
    if cad_result.layout_name != plan.sheetset_task.layout_name:
        issues.append(
            _issue(
                "DWG_LAYOUT_MISMATCH",
                f"DST 布局名应为 {plan.sheetset_task.layout_name!r}，实际 {cad_result.layout_name!r}",
            )
        )
    handle = cad_result.layout_handle
    if not handle or handle == "0" or not _HANDLE_PATTERN.fullmatch(handle):
        issues.append(_issue("DWG_HANDLE_INVALID", f"布局 Handle 非法：{handle!r}"))
    if not cad_result.dwg_sha256 or not _SHA256_PATTERN.fullmatch(cad_result.dwg_sha256):
        issues.append(_issue("DWG_HASH_MISSING", "DWG 最终 SHA-256 缺失或非法"))
    if cad_result.cad_version != plan.cad_version:
        issues.append(
            _issue(
                "CAD_VERSION_MISMATCH",
                f"构建版本应为计划版本 {plan.cad_version}，实际 {cad_result.cad_version}",
            )
        )
    return ValidationCheck("dwg", tuple(issues))


def _check_dst(
    plan: GenerationPlanV1,
    cad_result: CadDrawingResultV1,
    dst_bytes: bytes,
) -> ValidationCheck:
    return ValidationCheck("dst", validate_dst_bytes(dst_bytes, plan, cad_result))


def _check_catalog(plan: GenerationPlanV1, catalog_bytes: bytes) -> ValidationCheck:
    issues: list[ValidationIssue] = []
    task = plan.sheetset_task
    expected_rows = [
        list(xlsx.SHEET_CATALOG_HEADERS),
        [task.sheet_number, task.sheet_title, task.dwg_path, task.layout_name],
    ]
    try:
        rows = xlsx.load_sheet_catalog(catalog_bytes)
    except Exception as error:  # noqa: BLE001 - openpyxl/zip 异常都归为目录损坏
        return ValidationCheck("sheet-catalog", (_issue("SHEET_CATALOG_INVALID", f"图纸目录读取失败：{error}"),))
    if rows != expected_rows:
        issues.append(
            _issue("SHEET_CATALOG_CONTENT_MISMATCH", "图纸目录工作表/表头/数据行与计划不一致")
        )
    return ValidationCheck("sheet-catalog", tuple(issues))


def _check_reference_boundary(plan: GenerationPlanV1) -> ValidationCheck:
    issues: list[ValidationIssue] = []
    task = plan.sheetset_task
    if not task.dwg_path or "/" in task.dwg_path or "\\" in task.dwg_path or ".." in task.dwg_path:
        issues.append(_issue("DWG_REFERENCE_ESCAPE", f"DST 内 DWG 引用必须是裸文件名：{task.dwg_path!r}"))
    expected_dwg_artifact = task.dwg_path
    if plan.drawing_task.target_dwg_path != expected_dwg_artifact:
        issues.append(
            _issue(
                "PLAN_DWG_PATH_MISMATCH",
                f"DWG 成果路径应为 {expected_dwg_artifact!r}，实际 {plan.drawing_task.target_dwg_path!r}",
            )
        )
    expected = {expected_dwg_artifact, SHEETSET_PATH, SHEET_CATALOG_PATH}
    actual = {artifact.path: artifact for artifact in plan.expected_artifacts}
    for path in sorted(expected - set(actual)):
        issues.append(_issue("EXPECTED_ARTIFACT_MISSING", f"计划缺少预期成果登记：{path}"))
    for path in sorted(expected & set(actual)):
        if not actual[path].required:
            issues.append(_issue("EXPECTED_ARTIFACT_OPTIONAL", f"核心成果不得标记为可选：{path}"))
    for path in actual:
        # 扁平布局：每个预期产物都必须是目标目录内的裸文件名。
        if "/" in path or "\\" in path or ".." in path:
            issues.append(_issue("ARTIFACT_PATH_ESCAPE", f"预期成果路径必须是目标目录内的裸文件名：{path}"))
    return ValidationCheck("reference-boundary", tuple(issues))
