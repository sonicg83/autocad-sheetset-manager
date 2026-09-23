// 仅供 SPEC-DM-018 Demo 使用的示例数据与确定性预览计算，不接入真实标准或工程文件。
window.CreationDemoModel = (() => {
  'use strict';

  const standards = [
    { id: 'municipal', name: '市政工程图纸标准', version: '2.1.0', source: '官方', digits: 2, status: 'ready', naming: '{专业代码}-{图纸范围} {图名}.dwg', note: '包含道路基础、通用基础与两套布局模板。' },
    { id: 'building', name: '建筑设计图纸标准', version: '1.3.0', source: '用户', digits: 3, status: 'ready', naming: '{专业代码}-{图纸范围} {图名}.dwg', note: '演示不同标准版本与三位图号。' },
    { id: 'old', name: '旧版市政模板', version: '0.9.0', source: '用户', digits: 2, status: 'unavailable', naming: '', note: '布局模板资产缺失，不能用于正式创建。' }
  ];
  const steps = ['选择标准', '项目信息', '图纸组', '检查并创建'];
  const templates = ['市政基础', '道路基础', '通用基础'];
  const layoutTemplates = ['市政图框', '通用图框'];
  const papers = ['A1', 'A2', 'A3'];
  const phaseOptions = ['施工图', '初步设计', '竣工图'];
  const bulkFields = [
    ['count', '张数'], ['base', '基础模板'], ['layout', '布局模板'],
    ['paper', '图幅'], ['designer', '设计人'], ['phase', '图纸阶段']
  ];
  function initialGroups() {
    return [
      { id: 1, name: '封面', count: 1, base: '市政基础', layout: '市政图框', paper: 'A2', designer: '张工', phase: '施工图' },
      { id: 2, name: '平面图', count: 3, base: '道路基础', layout: '市政图框', paper: 'A1', designer: '李工', phase: '施工图' },
      { id: 3, name: '纵断面图', count: 2, base: '道路基础', layout: '市政图框', paper: 'A2', designer: '李工', phase: '施工图' }
    ];
  }
  function projectCode(discipline) {
    return { '道路': 'DL', '桥梁': 'QL', '给排水': 'GPS' }[discipline] || 'XM';
  }
  function finalPath(project) {
    return project.parent.replace(/[\\/]+$/, '') + '\\' + project.folder.trim();
  }
  function groupErrors(groups) {
    const names = new Map();
    const errors = new Map();
    groups.forEach(group => {
      const list = [];
      const key = group.name.trim().toLocaleLowerCase();
      if (!key) list.push('图名不能为空');
      if (key && names.has(key)) list.push('图名与其他图纸组重复');
      if (key) names.set(key, group.id);
      if (!Number.isInteger(Number(group.count)) || Number(group.count) < 1) list.push('张数必须为正整数');
      if (group.layout === '通用图框' && group.paper === 'A1') list.push('通用图框不含 A1 布局');
      if (list.length) errors.set(group.id, list);
    });
    return errors;
  }
  function chinese(value) {
    const digits = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
    if (value < 10) return digits[value];
    if (value === 10) return '十';
    if (value < 20) return '十' + digits[value % 10];
    return String(value);
  }
  function computePreview(state, selectedStandard) {
    const errors = [];
    if (!state.project.name.trim()) errors.push({ step: 2, text: '工程名称不能为空。' });
    if (!/^[A-Za-z]:\\/.test(state.project.parent.trim())) errors.push({ step: 2, text: '上一级目录需为 Windows 绝对路径。' });
    if (!state.project.folder.trim() || /[<>:"/\\|?*]/.test(state.project.folder) || state.project.folder.trim().endsWith('.')) {
      errors.push({ step: 2, text: '项目目录名为空或含 Windows 非法字符。' });
    }
    if (state.project.folder.trim() === '现有项目') errors.push({ step: 2, text: '目标目录非空（模拟场景），不可覆盖。' });
    groupErrors(state.groups).forEach((messages, id) => messages.forEach(text => errors.push({ step: 3, groupId: id, text: '图纸组“' +
      (state.groups.find(group => group.id === id)?.name || '未命名') + '”：' + text + '。' })));
    if (!state.groups.length) errors.push({ step: 3, text: '至少需要一个图纸组。' });
    if (errors.length) return { errors, rows: [], total: 0 };

    const keywords = state.settings.unnumbered.split(/[,，]/).map(item => item.trim().toLocaleLowerCase()).filter(Boolean);
    const width = selectedStandard.digits;
    const code = projectCode(state.project.discipline);
    let nextNumber = 1;
    const rows = state.groups.map(group => {
      const unnumbered = keywords.some(item => group.name.toLocaleLowerCase().includes(item));
      const count = Number(group.count);
      const sheets = Array.from({ length: count }, (_, index) => {
        const number = unnumbered ? '0'.repeat(width) : String(nextNumber++).padStart(width, '0');
        const suffix = state.settings.suffixType === 'chinese' ? chinese(index + 1) : String(index + 1);
        const title = state.settings.suffix && count > 1 ? group.name + ' (' + suffix + ')' : group.name;
        return { number, title, code: code + '-' + number, layoutName: number + ' ' + title };
      });
      const first = sheets[0], last = sheets[sheets.length - 1];
      const range = first.number === last.number ? first.number : first.number + '-' + last.number;
      const titleRange = state.settings.suffix && count > 1 ?
        group.name + ' (' + first.title.slice(group.name.length + 2, -1) + ')-(' + last.title.slice(group.name.length + 2, -1) + ')' : group.name;
      const filename = selectedStandard.naming
        .replace('{专业代码}', code).replace('{图纸范围}', range).replace('{图名}', group.name);
      return { group, unnumbered, sheets, range, titleRange, count, filename };
    });
    const filenames = new Set(), layouts = new Set();
    rows.forEach(row => {
      const fileKey = row.filename.toLocaleLowerCase();
      if (filenames.has(fileKey)) errors.push({ step: 3, groupId: row.group.id, text: 'DWG 文件名重复：' + row.filename });
      filenames.add(fileKey);
      row.sheets.forEach(sheet => {
        const key = fileKey + '/' + sheet.layoutName.toLocaleLowerCase();
        if (layouts.has(key)) errors.push({ step: 3, groupId: row.group.id, text: '布局名重复：' + sheet.layoutName });
        layouts.add(key);
      });
    });
    return { errors, rows, total: rows.reduce((sum, row) => sum + row.count, 0) };
  }
  return Object.freeze({ standards, steps, templates, layoutTemplates, papers, phaseOptions, bulkFields, initialGroups, projectCode, finalPath, groupErrors, computePreview });
})();
