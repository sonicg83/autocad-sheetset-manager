// 本 Demo 仅演示 SPEC-DM-018 的界面与交互；数据、路径和创建结果均为模拟。
(() => {
  'use strict';

  const M = window.CreationDemoModel;
  const { standards, steps, templates, layoutTemplates, papers, phaseOptions, bulkFields } = M;
  let nextGroupId = 4;
  let returnFocus = null;
  let pendingStandard = null;
  const state = {
    screen: 'welcome',
    step: 1,
    standardId: 'municipal',
    project: { name: '滨河路改造工程', discipline: '道路', phase: '施工图', parent: 'D:\\项目', folder: '新建项目' },
    groups: M.initialGroups(),
    selected: new Set(),
    bulkField: 'designer',
    bulkValue: '',
    xlsxTab: 'SheetSet',
    settings: { unnumbered: '封面,目录', suffix: true, suffixType: 'chinese' },
    preview: null,
    previewStale: true,
    draftTouched: false,
    jobState: 'idle'
  };

  function $(id) { return document.getElementById(id); }
  function h(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, char => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]
    ));
  }
  function standard() { return standards.find(item => item.id === state.standardId) || standards[0]; }
  function projectCode() { return M.projectCode(state.project.discipline); }
  function finalPath() { return M.finalPath(state.project); }
  function touch() {
    state.draftTouched = true;
    state.previewStale = true;
    state.preview = null;
  }
  function toast(message) {
    const node = $('toast');
    node.textContent = message;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.textContent = ''; }, 2900);
  }
  function optionList(options, value) {
    return options.map(item => '<option value="' + h(item) + '"' + (item === value ? ' selected' : '') + '>' + h(item) + '</option>').join('');
  }
  function topbar() {
    const theme = document.documentElement.dataset.theme;
    return '<header class="topbar"><div class="brand">DST Manager <span class="brand-context">/ 新建图纸集</span></div>' +
      '<span class="demo-mark">交互 Demo · 不写入工程</span><span class="topbar-spacer"></span>' +
      '<div class="theme-switch" aria-label="主题"><button type="button" data-action="theme" data-theme="light" class="' + (theme === 'light' ? 'active' : '') + '">浅色</button>' +
      '<button type="button" data-action="theme" data-theme="dark" class="' + (theme === 'dark' ? 'active' : '') + '">深色</button></div>' +
      '<button type="button" class="small" data-action="settings">编号设置</button></header>';
  }
  function welcome() {
    return '<section class="welcome-shell">' +
      '<div class="welcome-intro"><h1>开始使用 DST Manager</h1><p class="muted">打开已有图纸集，或从已发布图纸标准创建新项目。</p></div>' +
      '<div class="welcome-grid"><article class="card welcome-primary"><h2>打开图纸集</h2><p class="muted">选择现有 .dst 文件，进入受控编辑、预览和发布流程。</p>' +
      '<div class="drop-preview"><div><strong>选择一个 DST 文件</strong><p class="muted">此区域展示既有产品入口；本 Demo 聚焦新建图纸集。</p><button type="button" disabled>选择 DST 文件</button></div></div></article>' +
      '<aside class="card welcome-side"><h2>其他任务</h2><p class="muted">不打开工作区也能准备新项目。</p>' +
      '<button type="button" class="welcome-task" data-action="start-wizard"><span><strong>创建新图纸集</strong><span>从已发布标准开始，逐项完成配置。</span></span><span class="task-action">开始</span></button>' +
      '<button type="button" class="welcome-task" data-action="direct-standard"><span><strong>从标准详情用于创建</strong><span>示范固定标准版本后直接进入项目信息。</span></span><span class="task-action">进入</span></button>' +
      (state.draftTouched ? '<button type="button" class="welcome-task" data-action="resume"><span><strong>继续未完成草稿</strong><span>恢复上次离开时的输入与阶段。</span></span><span class="task-action">继续</span></button>' : '') +
      '<div class="callout info small-text">示例数据均为模拟；不会读取、覆盖或创建真实 DST/DWG。</div></aside></div>' +
      '<p class="welcome-note">SPEC-DM-018 设计演示 · 仅用于评审交互与布局，不代表后端已实现。</p></section>';
  }
  function wizardHeader() {
    return '<div class="card wizard-header"><div class="page-lead"><div><h1>创建新图纸集</h1>' +
      '<p class="muted">先配置，再检查；通过预览后才执行创建。</p></div>' +
      '<div class="page-lead-actions"><button type="button" class="small" data-action="home">返回欢迎页</button>' +
      '<button type="button" class="small" data-action="xlsx">XLSX 批量录入</button></div></div>' +
      '<div class="wizard-meta"><span class="badge blue">' + h(standard().name) + ' · v' + h(standard().version) + '</span>' +
      '<span class="badge neutral">草稿暂存于当前页面</span>' +
      (state.previewStale && state.step === 4 ? '<span class="badge warn">预览待更新</span>' : '') + '</div>' +
      '<nav class="stepper" aria-label="创建步骤">' + steps.map((name, index) => {
        const n = index + 1;
        const cls = n === state.step ? 'current' : n < state.step ? 'done' : '';
        return '<div class="step ' + cls + '"' + (n === state.step ? ' aria-current="step"' : '') +
          '><span class="step-number">' + n + '</span><span class="step-label">' + name + '</span></div>';
      }).join('') + '</nav></div>';
  }
  function wizardFooter() {
    const last = state.step === 4;
    return '<div class="wizard-footer"><span class="draft-state">本页为交互示意，不调用创建 API。</span>' +
      '<div class="actions"><button type="button" data-action="back" ' + (state.step === 1 ? 'disabled' : '') + '>上一步</button>' +
      (last ? '<button type="button" data-action="recheck">重新检查</button>' +
        '<button type="button" class="primary" data-action="execute" ' + (!state.preview || state.previewStale || state.preview.errors.length ? 'disabled' : '') +
        '>创建并打开图纸集</button>' :
        '<button type="button" class="primary" data-action="next">' + (state.step === 3 ? '检查创建结果' : '下一步') + '</button>') +
      '</div></div>';
  }
  function standardStep() {
    const selected = standard();
    return '<div class="standard-layout">' +
      '<section class="card"><div class="card-head"><div><h2>选择已发布标准</h2><p class="muted">只有发布完成且模板资产可用的版本可用于创建。</p></div></div>' +
      '<div class="card-body standard-list">' + standards.map(item =>
        '<button type="button" class="standard-option ' + (item.id === state.standardId ? 'selected' : '') +
        '" data-action="select-standard" data-id="' + item.id + '" ' + (item.status !== 'ready' ? 'disabled' : '') +
        '><strong>' + h(item.name) + '</strong><small>' + h(item.source) + ' · v' + h(item.version) +
        ' · ' + (item.status === 'ready' ? '已发布，可创建' : '资产缺失，不可创建') + '</small></button>'
      ).join('') + '</div></section>' +
      '<section class="card"><div class="card-head"><div><h2>标准详情</h2><p class="muted">选定后固定该发布版本，不随标准库的新草稿变化。</p></div></div>' +
      '<div class="card-body standard-details"><div><h3>' + h(selected.name) + '</h3><p class="muted small-text">' + h(selected.note) + '</p></div>' +
      '<dl class="definition-list"><dt>发布版本</dt><dd>v' + h(selected.version) + '</dd><dt>来源</dt><dd>' + h(selected.source) +
      '</dd><dt>图号位数</dt><dd>' + selected.digits + ' 位</dd><dt>DWG 命名</dt><dd class="mono">' + h(selected.naming) +
      '</dd><dt>属性模型</dt><dd>普通属性 + 映射/组合派生属性</dd></dl>' +
      '<div class="asset-chips"><span class="badge good">基础模板可用</span><span class="badge good">布局模板可用</span><span class="badge blue">已发布</span></div>' +
      '<div class="callout info small-text">标准草稿不出现在创建候选中。切换标准后，旧标准的模板与属性输入需要重新确认。</div></div></section></div>';
  }
  function projectStep() {
    return '<div class="project-layout"><section class="card"><div class="card-head"><div><h2>图纸集属性</h2>' +
      '<p class="muted">字段来自所选标准；派生属性只读，不需要在 XLSX 中填写。</p></div></div><div class="card-body">' +
      '<div class="field-grid"><label class="field"><span>工程名称 <span class="faint">· 必填</span></span>' +
      '<input data-project="name" value="' + h(state.project.name) + '" autocomplete="off" aria-label="工程名称"></label>' +
      '<label class="field"><span>专业 <span class="faint">· 枚举</span></span><select data-project="discipline" aria-label="专业">' +
      optionList(['道路', '桥梁', '给排水'], state.project.discipline) + '</select></label>' +
      '<label class="field"><span>项目阶段 <span class="faint">· 枚举</span></span><select data-project="phase" aria-label="项目阶段">' +
      optionList(phaseOptions, state.project.phase) + '</select></label>' +
      '<div class="field"><span>专业代码 <span class="faint">· 派生，只读</span></span><div id="project-code" class="readonly-value mono">' +
      h(projectCode()) + '</div></div></div>' +
      '<div class="callout info small-text" style="margin-top:17px">“工程名称”只是标准属性，不决定文件夹名称。文件夹名可独立修改。</div>' +
      '</div></section>' +
      '<section class="card"><div class="card-head"><div><h2>项目保存路径</h2><p class="muted">先选上一级目录，再命名最终项目文件夹。</p></div></div>' +
      '<div class="card-body path-fields"><div class="field"><span>上一级目录</span><div class="parent-row">' +
      '<input data-project="parent" value="' + h(state.project.parent) + '" aria-label="上一级目录" class="mono">' +
      '<button type="button" data-action="choose-parent">选择目录</button></div></div>' +
      '<label class="field"><span>项目目录名</span><input data-project="folder" value="' + h(state.project.folder) +
      '" aria-label="项目目录名"><span class="inline-help">初值为“新建项目”；不会按工程名称自动命名，也不会自动追加序号。</span></label>' +
      '<div class="result-path"><strong>最终完整路径</strong><span id="final-path" class="mono">' + h(finalPath()) + '</span></div>' +
      '<p class="small-text muted">目标必须尚不存在或为空目录；正式创建时还会再次校验。</p></div></section></div>';
  }
  function groupStep() {
    const errors = M.groupErrors(state.groups);
    const allSelected = state.groups.length > 0 && state.selected.size === state.groups.length;
    return '<section class="card"><div class="card-head"><div><h2>图纸组</h2>' +
      '<p class="muted">一行一个子集、一个主 DWG；同组全部图纸继承这一行的输入属性。</p></div></div>' +
      '<div class="card-body"><div class="group-toolbar"><button type="button" class="primary" data-action="add-group">新建图纸组</button>' +
      '<span class="small-text muted">新组复制上一组的全部输入，图名需自行修改。</span><span class="spacer"></span>' +
      '<span class="badge neutral">' + state.groups.length + ' 组 · ' + state.groups.reduce((sum, item) => sum + (Number(item.count) || 0), 0) + ' 张</span></div>' +
      '<div class="table-scroll"><table class="group-table" aria-label="图纸组编辑表"><thead><tr>' +
      '<th class="select-col"><label><input type="checkbox" data-action="select-all" aria-label="选择全部图纸组" ' + (allSelected ? 'checked' : '') + '></label></th>' +
      '<th class="name-col">图名</th><th class="count-col">张数</th><th class="template-col">基础模板</th>' +
      '<th class="template-col">布局模板</th><th class="paper-col">图幅</th><th class="property-col">设计人</th>' +
      '<th class="property-col">图纸阶段</th><th class="action-col">操作</th></tr></thead><tbody>' +
      state.groups.map((group, index) => '<tr><td class="select-col"><label><input type="checkbox" data-action="select-group" data-id="' +
        group.id + '" aria-label="选择' + h(group.name || '未命名图纸组') + '" ' + (state.selected.has(group.id) ? 'checked' : '') + '></label></td>' +
        '<td class="name-col"><input data-group="' + group.id + '" data-field="name" value="' + h(group.name) +
        '" aria-label="第' + (index + 1) + '组图名" ' + (errors.has(group.id) ? 'aria-invalid="true"' : '') + '>' +
        (errors.has(group.id) ? '<div class="row-error">' + h(errors.get(group.id).join('；')) + '</div>' : '') + '</td>' +
        '<td class="count-col"><input type="number" min="1" step="1" data-group="' + group.id + '" data-field="count" value="' +
        h(group.count) + '" aria-label="' + h(group.name) + '张数"></td>' +
        '<td class="template-col"><select data-group="' + group.id + '" data-field="base" aria-label="' + h(group.name) + '基础模板">' +
        optionList(templates, group.base) + '</select></td>' +
        '<td class="template-col"><select data-group="' + group.id + '" data-field="layout" aria-label="' + h(group.name) + '布局模板">' +
        optionList(layoutTemplates, group.layout) + '</select></td>' +
        '<td class="paper-col"><select data-group="' + group.id + '" data-field="paper" aria-label="' + h(group.name) + '图幅">' +
        optionList(papers, group.paper) + '</select></td>' +
        '<td class="property-col"><input data-group="' + group.id + '" data-field="designer" value="' + h(group.designer) +
        '" aria-label="' + h(group.name) + '设计人"></td>' +
        '<td class="property-col"><select data-group="' + group.id + '" data-field="phase" aria-label="' + h(group.name) + '图纸阶段">' +
        optionList(phaseOptions, group.phase) + '</select></td>' +
        '<td class="action-col"><div class="row-actions"><button type="button" data-action="move-up" data-id="' +
        group.id + '" aria-label="上移' + h(group.name) + '" ' + (index === 0 ? 'disabled' : '') + '>↑</button>' +
        '<button type="button" data-action="move-down" data-id="' + group.id + '" aria-label="下移' + h(group.name) +
        '" ' + (index === state.groups.length - 1 ? 'disabled' : '') + '>↓</button>' +
        '<button type="button" class="danger" data-action="delete-group" data-id="' + group.id +
        '" aria-label="删除' + h(group.name) + '">✕</button></div></td></tr>').join('') +
      '</tbody></table></div>' + bulkBar() +
      '<p class="inline-help">图号、标题、文件名和派生属性由预览计算；需要逐张不同属性，可在创建后进入普通工作区修改。</p>' +
      '</div></section>';
  }
  function bulkBar() {
    const values = [...state.selected].map(id => state.groups.find(group => group.id === id)).filter(Boolean).map(group => String(group[state.bulkField] ?? ''));
    const mixed = values.length > 1 && new Set(values).size > 1;
    const valueControl = bulkValueControl();
    return '<div class="bulk-bar"><strong class="small-text">批量修改</strong><span class="small-text muted">已选 ' + state.selected.size + ' 组</span>' +
      '<select class="bulk-field" data-action="bulk-field" aria-label="批量修改字段">' +
      bulkFields.map(([key, label]) => '<option value="' + key + '"' + (state.bulkField === key ? ' selected' : '') + '>' + label + '</option>').join('') +
      '</select><span class="bulk-indicator">' + (mixed ? '值不相同' : values.length ? '当前：' + h(values[0] || '（空）') : '未选择') + '</span>' +
      valueControl + '<span class="spacer"></span><button type="button" data-action="apply-bulk" ' + (!state.selected.size ? 'disabled' : '') + '>应用到选中组</button>' +
      '<button type="button" data-action="clear-bulk" ' + (!state.selected.size || state.bulkField === 'count' ? 'disabled' : '') +
      '>明确清空</button></div>';
  }
  function bulkValueControl() {
    let choices = null;
    if (state.bulkField === 'base') choices = templates;
    if (state.bulkField === 'layout') choices = layoutTemplates;
    if (state.bulkField === 'paper') choices = papers;
    if (state.bulkField === 'phase') choices = phaseOptions;
    if (choices) {
      return '<select class="bulk-value" data-action="bulk-value" aria-label="批量修改的新值"><option value="">选择新值</option>' +
        choices.map(item => '<option value="' + h(item) + '"' + (state.bulkValue === item ? ' selected' : '') + '>' + h(item) + '</option>').join('') + '</select>';
    }
    return '<input class="bulk-value" data-action="bulk-value" type="' + (state.bulkField === 'count' ? 'number' : 'text') +
      '" ' + (state.bulkField === 'count' ? 'min="1" step="1"' : '') + ' value="' + h(state.bulkValue) +
      '" placeholder="输入新值" aria-label="批量修改的新值">';
  }
  function computePreview() { return M.computePreview(state, standard()); }
  function previewStep() {
    if (state.previewStale || !state.preview) {
      return '<section class="card"><div class="card-head"><div><h2>检查并创建</h2><p class="muted">输入或编号设置已变化，重新检查后才能创建。</p></div></div>' +
        '<div class="card-body"><div class="callout warn">当前预览已失效。点击下方“重新检查”，获取最新图号、标题、DWG 文件名与属性值。</div></div></section>';
    }
    const preview = state.preview;
    const summary = '<div class="summary-row"><span class="badge neutral">' + state.groups.length + ' 个图纸组</span>' +
      '<span class="badge neutral">' + preview.total + ' 张图纸</span><span class="badge neutral">' + state.groups.length + ' 个 DWG</span>' +
      '<span class="badge neutral">图号 ' + standard().digits + ' 位</span>' +
      '<span class="badge ' + (preview.errors.length ? 'bad' : 'good') + '">' + (preview.errors.length ? preview.errors.length + ' 项阻断错误' : '检查通过') + '</span></div>';
    const context = '<dl class="preview-context"><div><dt>固定标准</dt><dd>' + h(standard().name) + ' · v' + h(standard().version) +
      '</dd></div><div><dt>最终项目路径</dt><dd class="mono">' + h(finalPath()) +
      '</dd></div><div><dt>当前编号设置</dt><dd>不编号：' + h(state.settings.unnumbered || '未设置') +
      ' · 尾序号：' + (state.settings.suffix ? (state.settings.suffixType === 'chinese' ? '中文' : '阿拉伯数字') : '关闭') + '</dd></div></dl>';
    const diagnostics = preview.errors.length ? '<div class="diagnostics" id="error-summary" tabindex="-1" role="alert" aria-label="预览错误">' +
      preview.errors.map(error => '<div class="diagnostic">' + h(error.text) +
        '<button type="button" class="link" data-action="jump-error" data-step="' + error.step + '"' +
        (error.groupId ? ' data-id="' + error.groupId + '"' : '') + '>返回修改</button></div>').join('') + '</div>' : '';
    const table = preview.errors.length ? '' :
      '<div class="table-scroll"><table class="preview-table" aria-label="按图纸组汇总的创建预览"><thead><tr>' +
      '<th>图纸组</th><th>图纸范围</th><th>图纸</th><th>张数</th><th>文件名</th>' +
      '<th>基础模板</th><th>布局模板</th><th>图幅</th><th>设计人</th><th>图纸阶段</th><th>图纸代号</th></tr></thead><tbody>' +
      preview.rows.map(row => '<tr><td>' + h(row.group.name) + (row.unnumbered ? ' <span class="badge warn">不编号</span>' : '') +
        '</td><td class="mono derived">' + h(row.range) + '</td><td class="derived">' + h(row.titleRange) +
        '</td><td>' + row.count + '</td><td class="filename derived">' + h(row.filename) +
        '</td><td>' + h(row.group.base) + '</td><td>' + h(row.group.layout) + '</td><td>' + h(row.group.paper) +
        '</td><td>' + h(row.group.designer || '（空）') + '</td><td>' + h(row.group.phase || '（空）') +
        '</td><td class="derived">' + h(row.sheets[0].code) +
        (new Set(row.sheets.map(sheet => sheet.code)).size > 1 ?
          ' <button type="button" class="link more" data-action="property-values" data-id="' + row.group.id +
          '" aria-label="查看' + h(row.group.name) + '组全部图纸的图纸代号">…</button>' : '') +
        '</td></tr>').join('') + '</tbody></table></div>';
    return '<section class="card"><div class="card-head"><div><h2>检查并创建</h2>' +
      '<p class="muted">仅按图纸组汇总；最终值由标准、输入与当前编号设置共同计算。</p></div></div>' +
      '<div class="card-body">' + summary + context + '<div class="callout ' + (preview.errors.length ? 'bad' : 'good') +
      '" style="margin-bottom:13px">' + (preview.errors.length ?
        '请先修正下方问题；创建按钮保持禁用。' : '全部检查通过。正式创建时仍会核验目标目录、标准资产和布局引用。') +
      '</div>' + diagnostics + table +
      (!preview.errors.length ? '<div class="preview-notes"><div class="preview-note"><strong>不编号图纸</strong>' +
        '命中关键字的图纸组范围为单个补零值，如 00；它不占用后续编号。</div>' +
        '<div class="preview-note"><strong>属性值查看</strong>组内不同值显示第一张图纸的值和“…”链接；点击后在模态中查看全部图纸。布局列不显示，但仍参与校验。</div></div>' : '') +
      '</div></section>';
  }
  function successView() {
    return '<section class="card" style="max-width:730px;margin:45px auto"><div class="card-body" style="padding:30px">' +
      '<span class="badge good">演示创建完成</span><h1 style="margin-top:13px">已进入图纸集工作区（模拟）</h1>' +
      '<p class="muted" style="margin-top:10px">真实功能尚未执行。Demo 没有创建目录、DWG 或 DST。</p>' +
      '<div class="result-path" style="margin-top:20px"><strong>本次预览目标</strong><span class="mono">' + h(finalPath()) + '</span></div>' +
      '<div style="display:flex;gap:8px;margin-top:20px"><button type="button" data-action="home">返回欢迎页</button>' +
      '<button type="button" class="primary" data-action="restart">重新演示创建</button></div></div></section>';
  }
  function render() {
    const content = state.screen === 'welcome' ? welcome() :
      state.screen === 'success' ? successView() :
      '<section class="container">' + wizardHeader() + '<div class="wizard-content">' +
      (state.step === 1 ? standardStep() : state.step === 2 ? projectStep() : state.step === 3 ? groupStep() : previewStep()) +
      '</div>' + wizardFooter() + '</section>';
    $('app').innerHTML = topbar() + '<main class="app-main">' + content + '</main>';
  }
  function showDialog(title, description, body, actions) {
    if (!$('demo-dialog').open) returnFocus = document.activeElement;
    $('dialog-content').innerHTML = '<div class="dialog-shell"><div class="dialog-head"><h2 id="dialog-title">' +
      h(title) + '</h2><p class="muted">' + h(description || '') + '</p></div><div class="dialog-body">' + body +
      '</div><div class="dialog-foot">' + actions + '</div></div>';
    if (!$('demo-dialog').open) $('demo-dialog').showModal();
    const focusable = $('demo-dialog').querySelector('button, input, select');
    focusable?.focus();
  }
  function closeDialog() {
    if ($('demo-dialog').open) $('demo-dialog').close();
    const target = returnFocus;
    returnFocus = null;
    target?.focus();
  }
  function settingsDialog() {
    const body = '<div class="field-grid"><label class="field"><span>不编号图纸关键字</span>' +
      '<input id="setting-unnumbered" value="' + h(state.settings.unnumbered) +
      '" aria-label="不编号图纸关键字"><span class="inline-help">半角或全角逗号分隔；图名包含任一关键字则整组不编号。</span></label>' +
      '<div class="field"><span>图号位数</span><div class="readonly-value">' + standard().digits + ' 位（来自固定标准）</div></div>' +
      '<label class="field"><span>标题尾序号</span><select id="setting-suffix"><option value="on"' +
      (state.settings.suffix ? ' selected' : '') + '>启用</option><option value="off"' +
      (!state.settings.suffix ? ' selected' : '') + '>关闭</option></select></label>' +
      '<label class="field"><span>尾序号类型</span><select id="setting-suffix-type">' +
      '<option value="chinese"' + (state.settings.suffixType === 'chinese' ? ' selected' : '') + '>中文：一、二、三</option>' +
      '<option value="arabic"' + (state.settings.suffixType === 'arabic' ? ' selected' : '') + '>阿拉伯数字：1、2、3</option>' +
      '</select></label></div><div class="callout info small-text" style="margin-top:14px">保存后旧预览失效，需要重新检查。真实产品以设置中心当前有效值为准。</div>';
    showDialog('编号设置（演示）', '可切换设置，观察不编号图纸与标题尾序号对预览的影响。', body,
      '<button type="button" data-action="close-dialog">取消</button><button type="button" class="primary" data-action="save-settings">保存设置</button>');
  }
  function folderDialog() {
    const choices = ['D:\\项目', 'E:\\工程', 'C:\\Users\\Public\\Documents'];
    showDialog('选择上一级目录', '选定父目录后，项目目录名仍可独立编辑。这里提供模拟目录。', choices.map(path =>
      '<button type="button" class="dialog-choice" data-action="set-parent" data-path="' + h(path) +
      '"><strong class="mono">' + h(path) + '</strong><small>已存在的上一级目录（模拟）</small></button>').join(''),
    '<button type="button" data-action="close-dialog">取消</button>');
  }
  function xlsxBody() {
    const tab = state.xlsxTab;
    const sheetSet = '<table class="dialog-table"><thead><tr><th>属性名</th><th>输入值</th></tr></thead><tbody>' +
      '<tr><td>工程名称</td><td>滨河路改造工程</td></tr><tr><td>专业</td><td>道路 <span class="badge blue">枚举</span></td></tr>' +
      '<tr><td>项目阶段</td><td>施工图 <span class="badge blue">枚举</span></td></tr>' +
      '<tr><td>项目保存路径</td><td class="mono">D:\\项目\\滨河路新建项目</td></tr></tbody></table>';
    const sheet = '<div class="table-scroll"><table class="dialog-table" style="min-width:680px"><thead><tr>' +
      '<th>图名</th><th>张数</th><th>基础模板</th><th>布局模板</th><th>图幅</th><th>设计人</th><th>图纸阶段</th></tr></thead>' +
      '<tbody><tr><td>封面</td><td>1</td><td>市政基础</td><td>市政图框</td><td>A2</td><td>张工</td><td>施工图</td></tr>' +
      '<tr><td>平面图</td><td>2</td><td>道路基础</td><td>市政图框</td><td>A1</td><td>李工</td><td>施工图</td></tr></tbody></table></div>';
    return '<div class="callout info small-text">仅有两个可见工作表。枚举、模板和图幅使用 Data Validation；派生属性与计算公式不出现。此 Demo 展示结构，不生成或解析真实 XLSX。</div>' +
      '<div class="dialog-tabs" style="margin-top:14px"><button type="button" data-action="xlsx-tab" data-tab="SheetSet" class="' +
      (tab === 'SheetSet' ? 'active' : '') + '">SheetSet</button><button type="button" data-action="xlsx-tab" data-tab="Sheet" class="' +
      (tab === 'Sheet' ? 'active' : '') + '">Sheet</button></div>' +
      (tab === 'SheetSet' ? sheetSet : sheet) +
      '<p class="inline-help">导入成功会直接覆盖当前项目属性、完整路径和全部图纸组，不比较差异。</p>';
  }
  function xlsxDialog() {
    showDialog('XLSX 批量录入', '可先查看模板结构，再模拟有效或错误导入。', xlsxBody(),
      '<button type="button" data-action="close-dialog">关闭</button>' +
      '<button type="button" data-action="xlsx-invalid">模拟错误导入</button>' +
      '<button type="button" class="primary" data-action="xlsx-valid">模拟有效导入</button>');
  }
  function invalidImportDialog() {
    showDialog('导入未完成', '模拟工作簿错误；当前草稿保持原样。', '<div class="diagnostics">' +
      '<div class="diagnostic">Sheet · 第 3 行 · 图幅：所选布局模板不包含 A1。</div>' +
      '<div class="diagnostic">SheetSet · 第 5 行 · 项目保存路径：必须包含最终项目目录名。</div></div>',
      '<button type="button" class="primary" data-action="close-dialog">返回修改工作簿</button>');
  }
  function applyImportedSample() {
    state.project = { name: '滨河路改造工程', discipline: '道路', phase: '施工图', parent: 'D:\\项目', folder: '滨河路新建项目' };
    state.groups = [
      { id: ++nextGroupId, name: '封面', count: 1, base: '市政基础', layout: '市政图框', paper: 'A2', designer: '张工', phase: '施工图' },
      { id: ++nextGroupId, name: '平面图', count: 2, base: '道路基础', layout: '市政图框', paper: 'A1', designer: '李工', phase: '施工图' }
    ];
    state.selected.clear();
    touch();
    closeDialog();
    render();
    toast('已模拟全量导入：旧项目输入和图纸组已被替换');
  }
  function valuesDialog(id) {
    const row = state.preview?.rows.find(item => item.group.id === id);
    if (!row) return;
    const body = '<table class="dialog-table"><thead><tr><th>图号</th><th>图纸标题</th><th>图纸代号</th></tr></thead><tbody>' +
      row.sheets.map(sheet => '<tr><td class="mono">' + h(sheet.number) + '</td><td>' + h(sheet.title) +
        '</td><td class="mono">' + h(sheet.code) + '</td></tr>').join('') + '</tbody></table>';
    showDialog(row.group.name + ' · 图纸代号', '共 ' + row.count + ' 张图纸，按组内顺序列出实际属性值。', body,
      '<button type="button" class="primary" data-action="close-dialog">关闭</button>');
  }
  function goStep(step) {
    state.screen = 'wizard';
    state.step = step;
    if (step === 4 && (state.previewStale || !state.preview)) {
      state.preview = computePreview();
      state.previewStale = false;
    }
    render();
    if (step === 4 && state.preview.errors.length) $('error-summary')?.focus();
  }
  function resetDraft() {
    state.project = { name: '滨河路改造工程', discipline: '道路', phase: '施工图', parent: 'D:\\项目', folder: '新建项目' };
    state.groups = M.initialGroups();
    state.selected.clear();
    state.preview = null;
    state.previewStale = true;
    state.draftTouched = false;
    state.bulkField = 'designer';
    state.bulkValue = '';
    state.standardId = 'municipal';
  }
  function handleAction(button) {
    const action = button.dataset.action;
    const id = Number(button.dataset.id);
    if (action === 'theme') { document.documentElement.dataset.theme = button.dataset.theme; render(); return; }
    if (action === 'settings') { settingsDialog(); return; }
    if (action === 'save-settings') {
      state.settings.unnumbered = $('setting-unnumbered').value;
      state.settings.suffix = $('setting-suffix').value === 'on';
      state.settings.suffixType = $('setting-suffix-type').value;
      touch(); closeDialog(); render(); toast('编号设置已改变；旧预览失效'); return;
    }
    if (action === 'close-dialog') { closeDialog(); return; }
    if (action === 'home') { state.screen = 'welcome'; render(); return; }
    if (action === 'start-wizard') { if (state.draftTouched) { showDialog('重新开始？', '这会放弃当前演示草稿。', '<div class="callout warn">已有输入不会保留。</div>', '<button type="button" data-action="close-dialog">取消</button><button type="button" class="primary" data-action="confirm-restart">重新开始</button>'); } else goStep(1); return; }
    if (action === 'confirm-restart' || action === 'restart') { closeDialog(); resetDraft(); goStep(1); return; }
    if (action === 'resume') { goStep(state.step); return; }
    if (action === 'direct-standard') {
      if (state.draftTouched && state.standardId !== 'municipal') {
        showDialog('切换图纸标准？', '标准详情选中的市政工程图纸标准与当前草稿不同。',
          '<div class="callout warn">切换会清除旧标准输入和预览；取消则保留当前草稿。</div>',
          '<button type="button" data-action="close-dialog">取消</button><button type="button" class="primary" data-action="confirm-direct-standard">切换并创建</button>');
      } else { state.standardId = 'municipal'; goStep(2); }
      return;
    }
    if (action === 'confirm-direct-standard') { closeDialog(); resetDraft(); goStep(2); return; }
    if (action === 'select-standard') {
      if (button.dataset.id === state.standardId) return;
      if (state.draftTouched) {
        pendingStandard = button.dataset.id;
        showDialog('切换图纸标准？', '旧标准的输入和预览将被清除，以免误用不兼容字段。', '<div class="callout warn">请确认是否使用新标准重新填写项目与图纸组。</div>',
          '<button type="button" data-action="close-dialog">取消</button><button type="button" class="primary" data-action="confirm-standard">切换标准</button>');
      } else { state.standardId = button.dataset.id; touch(); render(); }
      return;
    }
    if (action === 'confirm-standard') { resetDraft(); state.standardId = pendingStandard; pendingStandard = null; closeDialog(); render(); return; }
    if (action === 'next') { goStep(Math.min(state.step + 1, 4)); return; }
    if (action === 'back') { goStep(Math.max(state.step - 1, 1)); return; }
    if (action === 'recheck') { state.preview = computePreview(); state.previewStale = false; render(); if (state.preview.errors.length) $('error-summary')?.focus(); return; }
    if (action === 'choose-parent') { folderDialog(); return; }
    if (action === 'set-parent') { state.project.parent = button.dataset.path; touch(); closeDialog(); render(); return; }
    if (action === 'xlsx') { xlsxDialog(); return; }
    if (action === 'xlsx-tab') { state.xlsxTab = button.dataset.tab; const body = $('dialog-content').querySelector('.dialog-body'); body.innerHTML = xlsxBody(); return; }
    if (action === 'xlsx-invalid') { invalidImportDialog(); return; }
    if (action === 'xlsx-valid') {
      showDialog('覆盖当前草稿？', '有效 XLSX 导入将全量替换现有输入，不比较差异。', '<div class="callout warn">项目属性、最终路径和全部图纸组都会被替换；固定标准版本不变。</div>',
        '<button type="button" data-action="close-dialog">取消</button><button type="button" class="primary" data-action="confirm-import">覆盖并导入</button>'); return;
    }
    if (action === 'confirm-import') { applyImportedSample(); return; }
    if (action === 'add-group') {
      const source = state.groups.reduce((latest, group) => !latest || group.id > latest.id ? group : latest, null) ||
        { name: '新图纸组', count: 1, base: templates[0], layout: layoutTemplates[0], paper: 'A2', designer: '', phase: phaseOptions[0] };
      const group = { ...source, id: ++nextGroupId };
      state.groups.push(group); touch(); render();
      const input = document.querySelector('[data-group="' + group.id + '"][data-field="name"]');
      input?.focus(); input?.select(); return;
    }
    if (action === 'select-all') { state.selected = button.checked ? new Set(state.groups.map(group => group.id)) : new Set(); render(); return; }
    if (action === 'select-group') { button.checked ? state.selected.add(id) : state.selected.delete(id); render(); return; }
    if (action === 'move-up' || action === 'move-down') {
      const index = state.groups.findIndex(group => group.id === id);
      const to = index + (action === 'move-up' ? -1 : 1);
      if (to >= 0 && to < state.groups.length) {
        [state.groups[index], state.groups[to]] = [state.groups[to], state.groups[index]];
        touch(); render();
      }
      return;
    }
    if (action === 'delete-group') {
      const group = state.groups.find(item => item.id === id);
      showDialog('删除图纸组？', '只修改演示草稿，尚未创建任何 DWG。', '<div class="callout warn">将删除“' + h(group?.name || '该组') + '”及其组内 ' + h(group?.count || 0) + ' 张预设图纸。</div>',
        '<button type="button" data-action="close-dialog">取消</button><button type="button" class="danger" data-action="confirm-delete" data-id="' + id + '">删除图纸组</button>');
      return;
    }
    if (action === 'confirm-delete') { state.groups = state.groups.filter(group => group.id !== id); state.selected.delete(id); touch(); closeDialog(); render(); return; }
    if (action === 'apply-bulk' || action === 'clear-bulk') {
      if (!state.selected.size) return;
      const field = state.bulkField;
      const value = action === 'clear-bulk' ? '' : String(state.bulkValue).trim();
      if (action === 'clear-bulk' && field === 'count') return;
      if (action === 'apply-bulk' && !value) { toast('请先填写新值；清空请使用“明确清空”'); return; }
      if (field === 'count' && (!Number.isInteger(Number(value)) || Number(value) < 1)) { toast('张数必须为正整数'); return; }
      state.groups.forEach(group => { if (state.selected.has(group.id)) group[field] = field === 'count' ? Number(value) : value; });
      state.bulkValue = ''; touch(); render(); toast('已批量修改 ' + state.selected.size + ' 个图纸组'); return;
    }
    if (action === 'property-values') { valuesDialog(id); return; }
    if (action === 'jump-error') {
      const step = Number(button.dataset.step);
      closeDialog(); goStep(step);
      if (id) document.querySelector('[data-group="' + id + '"][data-field="name"]')?.focus();
      else if (step === 2) document.querySelector('[data-project="name"]')?.focus();
      return;
    }
    if (action === 'execute') {
      if (!state.preview || state.previewStale || state.preview.errors.length) return;
      showDialog('正在创建（演示）', '真实创建会通过后台任务生成并发布 DST/DWG。', '<div class="callout info">正在检查目标与资产，准备切换到工作区……</div>',
        '<button type="button" disabled>执行中</button>');
      state.jobState = 'running';
      setTimeout(() => {
        if (state.jobState !== 'running') return;
        state.jobState = 'done'; closeDialog(); state.screen = 'success'; render();
      }, 850);
    }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button || button.disabled) return;
    if (button.matches('input[type="checkbox"]')) return;
    handleAction(button);
  });
  document.addEventListener('change', event => {
    const target = event.target;
    if (target.matches('input[type="checkbox"][data-action]')) { handleAction(target); return; }
    if (target.dataset.action === 'bulk-field') { state.bulkField = target.value; state.bulkValue = ''; render(); return; }
    if (target.dataset.action === 'bulk-value') { state.bulkValue = target.value; return; }
    if (target.dataset.project) {
      state.project[target.dataset.project] = target.value; touch(); render(); return;
    }
    if (target.dataset.group) {
      const group = state.groups.find(item => item.id === Number(target.dataset.group));
      if (group) {
        group[target.dataset.field] = target.dataset.field === 'count' ? target.value : target.value;
        touch(); render();
      }
    }
  });
  document.addEventListener('input', event => {
    const target = event.target;
    if (target.dataset.action === 'bulk-value') { state.bulkValue = target.value; return; }
    if (target.dataset.project) {
      state.project[target.dataset.project] = target.value; touch();
      if (target.dataset.project === 'parent' || target.dataset.project === 'folder') {
        const pathNode = $('final-path');
        if (pathNode) pathNode.textContent = finalPath();
      }
      if (target.dataset.project === 'discipline') {
        const codeNode = $('project-code');
        if (codeNode) codeNode.textContent = projectCode();
      }
    }
    if (target.dataset.group) {
      const group = state.groups.find(item => item.id === Number(target.dataset.group));
      if (group) { group[target.dataset.field] = target.value; touch(); }
    }
  });
  $('demo-dialog').addEventListener('cancel', event => {
    event.preventDefault();
    if (state.jobState !== 'running') closeDialog();
  });
  render();
})();
