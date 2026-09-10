// en-US 错误域语言资源（PLAN-DM-021 Task 9；ARCH-DM-005 §6.2 / I18N-11）。
// 键集合必须与 zh-CN 完全一致（check:i18n 门禁），且与后端
// src/dst_manager/interfaces/message_catalog.py 的 message_key/参数 schema
// 严格对称（tests/unit/test_message_catalog.py 交叉守护）。
// Path/ID/name/version parameters stay verbatim (I18N-16); unknown errors show
// ui.unknownSummary and keep the original text only in expandable diagnostics.
export default {
  workspace: {
    notFound: "Workspace not found. Reopen the sheet set",
    writeBusy: "The workspace is busy with another operation. Try again later",
    dstNotFound: "DST file not found: {dst_path}",
  },
  revision: {
    conflict: "The base revision has changed. Preview again",
    notFound: "Revision not found",
    manifestMissing: "Revision manifest is missing",
    restoreConflict: "The restore baseline has changed. Preview the restore again",
    restoreSourceChanged: "The restore source has drifted from the preview",
  },
  draft: {
    conflict: "Draft version conflict. Refresh and try again",
  },
  job: {
    notFound: "Job not found",
    notRetryable: "This job cannot be retried in its current state",
  },
  plan: {
    invalid: "The execution plan contains blocking issues and cannot continue",
    repreviewRequired: "The preview has changed or was not confirmed. Preview again",
  },
  repair: {
    blocked: "Blocking issues remain. Writing is not allowed",
    notRequired: "This DST has no pending repairs to confirm",
    confirmationRequired: "Repairable DST metadata loss detected. Confirm and publish a repair revision first",
    unrecoverable: "The DST has unrecoverable issues. Writing is not allowed",
  },
  export: {
    baselineRequired: "Exporting a non-primary DST requires previewing the destination baseline first",
    outsideWorkspace: "The export destination must be inside the workspace",
  },
  cad: {
    versionInvalid: "Unsupported AutoCAD version: {cad_version}",
    capabilityUnavailable: "AutoCAD Core Console or Worker plugin is not configured. Run dst-manager doctor to check",
  },
  layout: {
    readFailed: "Failed to read layouts. The DWG may be locked or the CAD environment is unavailable",
    sourceNotFound: "Source file not found",
    sourceTypeInvalid: "The source file must be a .dwg or .dwt file",
  },
  command: {
    unsupported: "Unsupported command: {command}",
    requiresCad: "This command requires CAD execution: {command}",
  },
  settings: {
    conflict: "Settings were changed by another process. Refresh and try again",
    schemaBlocked: "The settings file schema version is incompatible with this program; read-only mode is active",
    schemaOlder: "The settings file schema version is older than this program; read-only mode is active",
    validationFailed: "Settings validation failed. Fix the highlighted fields",
  },
  sheet: {
    notFound: "Sheet not found: {object_id}",
    nodeNotFound: "Sheet node not found: {object_id}",
    nodeDuplicated: "Duplicate sheet node: {object_id}",
    titleEmpty: "Sheet title cannot be empty",
    layoutCount: "Sheet references an invalid number of layouts: {object_id}",
    positionInvalid: "Invalid insertion position: {position}",
    insertCountInvalid: "Insert count must be a positive integer: {value}",
  },
  subset: {
    notFound: "Subset not found: {subset_id}",
    nodeNotFound: "Subset node not found: {object_id}",
    nodeDuplicated: "Duplicate subset node: {object_id}",
    positionInvalid: "Invalid insertion position: {position}",
    empty: "Subset cannot be empty",
  },
  sheetSet: {
    invalid: "Invalid sheet set node",
    missing: "The AcSmSheetSet node is missing",
  },
  property: {
    notFound: "Custom property not found: {name}",
    duplicated: "Duplicate custom property: {name}",
    valueDuplicated: "Custom property has multiple values: {name}",
    bagDuplicated: "Duplicate property bag: {owner_id}",
    flagsMissing: "Custom property is missing its Flags marker: {name}",
    flagsInvalid: "Invalid custom property Flags marker: {name}",
    typeInvalid: "Invalid custom property type: {type}",
    typeConflict: "Custom property type conflict: {name}",
    nameDuplicate: "Duplicate custom property name: {name}",
    nameEmpty: "Custom property name cannot be empty",
    nameInvalid: "Custom property name contains invalid characters",
    valueInvalid: "Custom property value contains characters forbidden in XML 1.0",
    scopeMismatch: "Custom property scope does not match the edited object: {name}",
  },
  dwg: {
    duplicateAcsmId: "Duplicate AcSm ID: {acsm_id}",
    outsideWorkspace: "The DWG path is outside the workspace: {path}",
    unknownReferenceBlocked: "Unregistered reference nodes block this operation: {object_id}",
    layoutSourceInvalid: "Invalid layout source",
  },
  xml: {
    validationFailed: "DST XML validation failed",
    invalid: "Invalid XML content",
    rootInvalid: "The XML root element must be AcSmDatabase",
    textInvalid: "Text contains characters forbidden in XML 1.0",
    controlledPropertyInvalid: "Invalid controlled property update: {name}",
    childReconciliationFailed: "Failed to reconcile controlled child nodes",
  },
  shell: {
    workspaceUnavailable: "No matching open workspace",
    openFailed: "Failed to open in File Explorer",
    directoryNotFound: "The sheet set directory does not exist; it may have been moved or deleted",
    artifactDirectoryNotFound: "The folder containing the exported file does not exist; it may have been moved or deleted",
    externalUrlRejected: "Only registered https links can be opened",
    preferencesIo: "Failed to read or write sheet column preferences",
    preferencesInvalid: "Sheet column preference data is invalid",
  },
  // Extension platform errors (PLAN-DM-020 Task 10); key names mirror
  // extension_contracts.py EXTENSION_MESSAGE_KEYS plus the runtime/preview
  // key_override entries. Key set cross-locked by web/src/i18n/extensions-domain.test.ts.
  extension: {
    notFound: "The extension is not registered and the operation cannot be performed",
    disabled: "The extension is disabled; enable it before performing this operation",
    incompatible: "The extension is incompatible with the current host version",
    capabilityUnavailable: "The extension is currently unavailable",
    settingsInvalid: "The extension settings are invalid or were changed elsewhere; reopen and retry",
    actionNotFound: "The extension does not declare this action",
    saveGrantInvalid: "The save grant is invalid or expired; run Save As again",
    exportDestinationChanged: "The export destination changed; choose a save location again",
    repreviewRequired: "The preview is stale; preview again before exporting",
    artifactWriteFailed: "Writing the output file failed; the original file is unchanged and a retry is safe",
    artifactNotFound: "The exported artifact no longer exists or has been moved",
    preferenceSaveFailed: "Saving workspace preferences failed; the export result is unaffected",
  },
  // ---- Sheet catalog extension (PLAN-DM-020 Task 11; keys mirror SHEET_CATALOG_MESSAGE_KEYS) ----
  sheetCatalog: {
    expressionInvalid: "Invalid expression syntax (position {source_start})",
    fieldUndefined: "The expression references an undefined field: [{scope}] {name}",
    valueMissing: "Field value is empty: [{scope}] {name} ({sheet_count} sheets affected)",
    columnDuplicate: "Duplicate name: {header}",
    templateLimit: "Template limit exceeded {kind}: {actual}/{limit}",
    templateConflict: "The template was updated by another save (local r{current_revision}, server r{expected_revision}); local edits are kept — save as a new template or retry with the new revision",
    xlsxInvalid: "Candidate file validation failed: {check}",
  },
  ui: {
    unknownSummary: "The operation failed due to an unknown error",
    diagnosticsDetails: "Raw error details",
  },
};
