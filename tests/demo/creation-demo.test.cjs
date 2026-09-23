// SPEC-DM-018 交互 Demo 的确定性预览回归；不调用真实创建链路。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function model() {
  const file = path.resolve(__dirname, '../../docs/dst-manager/mockups/SPEC-DM-018-creation-model.js');
  const context = vm.createContext({ window: {} });
  vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  return context.window.CreationDemoModel;
}

function state(groups = model().initialGroups()) {
  return {
    project: { name: '滨河路改造工程', discipline: '道路', phase: '施工图', parent: 'D:\\项目', folder: '新建项目' },
    groups,
    settings: { unnumbered: '封面,目录', suffix: true, suffixType: 'chinese' }
  };
}

test('不编号组全部取零且不占后续图号，预览仅显示一个补零值', () => {
  const m = model();
  const result = m.computePreview(state(), m.standards[0]);
  assert.equal(result.errors.length, 0);
  assert.deepEqual(Array.from(result.rows.map(row => row.range)), ['00', '01-03', '04-05']);
  assert.deepEqual(Array.from(result.rows[0].sheets.map(sheet => sheet.number)), ['00']);
  assert.equal(result.rows[1].titleRange, '平面图 (一)-(三)');
  assert.equal(result.rows[1].filename, 'DL-01-03 平面图.dwg');
});

test('关闭尾序号时同组多张不编号图纸产生重复布局名并阻断创建', () => {
  const m = model();
  const draft = state();
  draft.settings.unnumbered = '封面,平面图';
  draft.settings.suffix = false;
  const result = m.computePreview(draft, m.standards[0]);
  assert.equal(result.errors.length, 2);
  assert.ok(result.errors.every(error => error.text === '布局名重复：00 平面图'));
});

test('图纸组同名按去首尾空格和大小写不敏感判重，不自动附加序号', () => {
  const m = model();
  const groups = m.initialGroups();
  groups.push({ ...groups[1], id: 4, name: '  平面图  ' });
  const errors = m.groupErrors(groups);
  assert.match(errors.get(4).join('；'), /重复/);
  assert.equal(groups[3].name, '  平面图  ');
});

test('最终目录名不从工程名称推断，三位标准按三位补零', () => {
  const m = model();
  const draft = state();
  draft.project.name = '更名后的工程';
  assert.equal(m.finalPath(draft.project), 'D:\\项目\\新建项目');
  const result = m.computePreview(draft, m.standards[1]);
  assert.deepEqual(Array.from(result.rows.map(row => row.range)), ['000', '001-003', '004-005']);
});
