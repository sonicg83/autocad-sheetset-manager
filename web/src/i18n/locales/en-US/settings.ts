// en-US 设置中心域语言资源（PLAN-DM-021 Task 3；ARCH-DM-005 §5.1）。
// 键集合必须与 zh-CN 完全一致（check:i18n 门禁）；动态句子用命名参数插值，
// 不在调用点拼接可翻译片段（I18N-08）；语言名保留自称形式（SPEC-DM-013 §5.1）。
export default {
  title: "Settings",
  revision: "Config revision r{revision}",
  close: "Close settings",
  loading: "Loading settings…",
  loadFailed: "Failed to load settings. Check whether the service is available.",
  retry: "Retry",
  cancel: "Cancel",
  save: "Save",
  saving: "Saving…",
  saved: "Saved",
  sections: {
    nav: "Settings sections",
    general: "General",
    about: "About",
    extensions: "Extensions",
  },
  // Extensions section (disable must stay reversible / ARCH-DM-006 §7; SPEC-DM-011
  // revision "extension toggle interaction" switched the control to a sliding switch).
  // The toggle applies immediately, independent of the buffered Cancel/Save below. stateOn/stateOff is the visible
  // state text next to the switch; enableNamed/disableNamed is the switch's
  // accessible name.
  extensions: {
    immediateNotice: "Extension changes take effect immediately and are not affected by Cancel below.",
    loading: "Loading extensions…",
    loadFailed: "Failed to load the extension list.",
    empty: "No registered extensions.",
    stateOn: "Enabled",
    stateOff: "Disabled",
    enableNamed: "Enable {name}",
    disableNamed: "Disable {name}",
    diagnosticCode: "Code {code}",
  },
  // Extension settings entry and config sub-view (SC-17): entry copy, sub-view header,
  // independent saving, dirty-state gate and the two server-state exits (revision
  // conflict / newer schema read-only). The read-only body reuses
  // errors.extension.schemaNewer instead of a second wording for the same code.
  extensionSettings: {
    open: "Configure",
    openNamed: "Configure {name}",
    title: "Configure · {name}",
    revision: "Settings revision r{revision}",
    schemaVersion: "Schema v{schema_version}",
    readOnlyBadge: "Read-only",
    sharedNotice: "Extension settings belong to the current Windows user and are shared across workspaces: you can enter, edit and save them without a loaded workspace. Each extension saves independently — it does not enter the core settings buffer below and does not share its revision.",
    back: "Back to extension list",
    save: "Save",
    saving: "Saving…",
    saved: "Extension settings saved",
    loading: "Loading extension settings…",
    loadFailed: "Failed to load the extension settings.",
    // Refresh failure while a snapshot exists: one in-place notice shared by the
    // read-only, conflict and normal editing states (the snapshot is kept).
    refreshFailed: "Refreshing the extension settings failed; the content below may be stale.",
    closeExtra: "Closing will also discard the unsaved changes of the current extension settings.",
    unsupportedControl: "The control type ({control}) of this field is not supported by the settings center; no JSON text box is provided.",
    customUnavailable: "The settings component declared by this extension (route_key {route_key}) is not in this build's compile-time allowlist; its content is not rendered and is never degraded into a JSON text box.",
    // Distinct cause from the line above: custom declared without a component key,
    // so there is no key value to echo back.
    customUnavailableMissingRouteKey: "This extension declares a dedicated settings component but registers no component key (route_key); its content is not rendered and is never degraded into a JSON text box.",
    confirmBack: {
      title: "Unsaved extension settings changes",
      message: "Going back to the extension list discards the unsaved changes of “{name}”; saved settings are not affected.",
      discard: "Discard and go back",
    },
    conflict: {
      title: "Save conflict",
      message: "The settings of “{name}” were updated by another save; your local edits are kept. Retry with the server's new revision or discard the local edits.",
      // The endpoint prefix matches the frozen demo's wire contract line.
      diagnostic: "PUT /api/extensions/{extension_id}/settings → 409 {code} (expected_revision={expected_revision}, current_revision={current_revision})",
      retry: "Retry with new revision",
      discard: "Discard local edits",
    },
    errors: {
      summaryTitle: "The extension settings could not be saved; fix the errors below and retry",
    },
  },
  confirm: {
    title: "Unsaved changes",
    message: "Closing discards all unsaved changes in this dialog. Saved settings are not affected.",
    discard: "Discard and close",
    stay: "Stay here",
  },
  toast: {
    savedTitle: "Saved",
    savedBody: "Settings updated",
    savedRecalcBody: "Related previews will be recalculated with the new settings",
    linkTitle: "External link",
    linkOpened: "Opened in the system browser",
    linkRejected: "Only registered https links can be opened",
    linkUnsupported: "The desktop app cannot open links in the system browser yet. Copy the address to visit it.",
  },
  about: {
    app: "App",
    licenseTitle: "License (MIT)",
    linksTitle: "Project homepage / Feedback",
    homepage: "Project homepage",
    feedback: "Report an issue",
    loadFailed: "Failed to load about information.",
    loading: "Loading…",
  },
  errors: {
    summaryTitle: "Settings could not be saved. Fix the fields below and retry.",
    conflict: "The settings were updated in another window. The latest configuration has been loaded; review your changes and retry.",
    saveFailed: "Save failed. Check the service and try again.",
  },
  diagnostics: {
    fileMissing: "The user settings file does not exist; this session runs on default values. (Diagnostic code {code})",
    fileCorrupt: "The user settings file could not be read (a backup was kept); this session runs on default values. (Diagnostic code {code})",
    schemaNewer: "The settings file schema version is incompatible with this program. Read-only mode is on and saving is disabled. (Diagnostic code {code})",
  },
  categories: {
    interface: "Interface",
    autocad2016: "AutoCAD 2016",
    autocad2020: "AutoCAD 2020",
    execution: "Job execution",
    numbering: "Numbering rules",
  },
  items: {
    uiLocale: "UI language",
    autocad2016Console: "Core Console",
    autocad2016Plugin: "Worker plugin",
    autocad2020Console: "Core Console",
    autocad2020Plugin: "Worker plugin",
    cadTimeout: "CAD timeout (seconds)",
    cadMaxParallel: "Maximum parallel jobs",
    workerLease: "Worker lease (seconds)",
    addNumberSuffix: "Append number suffix to sheet titles",
    numberSuffixType: "Suffix type",
    unnumberedSubsetKeywords: "Keywords for unnumbered sheets",
  },
  locale: {
    system: "Follow system",
    systemCurrent: "Follow system (current: {current})",
    zhCN: "简体中文",
    enUS: "English",
  },
  enumOptions: {
    suffixChinese: "Chinese numerals (一、二、三…)",
    suffixArabic: "Arabic numerals (1, 2, 3…)",
  },
  fileFilters: {
    executable: "Executable program (*.exe)",
    dotnetAssembly: ".NET assembly (*.dll)",
  },
  validation: {
    pathType: "Must be a file path",
    pathIllegalChars: "Contains characters not allowed in paths",
    boolType: "Must be true or false",
    integerType: "Must be an integer",
    textType: "Must be text",
    integerRange: "Must be between {min} and {max}",
    enumValue: "Value must be one of: {allowedValues}",
    unknownKey: "Unknown setting: {key}",
    invalidFormat: "The value type or format is invalid. Check it and retry.",
    keywordCountLimit: "At most {limit} keywords (currently {actual})",
    keywordLengthLimit: "Each keyword must be at most {limit} characters (currently {actual})",
  },
  row: {
    browse: "Browse…",
    browseUnavailable: "The desktop shell is not ready. Enter the path manually.",
    clear: "Clear",
    restoreInherited: "Restore inherited",
    undoRestoreInherited: "Undo restore inherited",
    placeholderNotSet: "Not set",
    keywordPlaceholder: "e.g. Cover, Index (comma separated)",
    keywordHint: "Separate with half- or full-width commas: at most {limit} keywords of {chars} characters each. Sheets in a subset whose name contains a keyword are numbered 0",
    on: "On",
    off: "Off",
    sourceDefault: "Default",
    sourceEnv: "Environment variable",
    sourceFile: "User override",
  },
} as const;
