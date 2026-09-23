// 运行真实 Demo 渲染器，守护图纸组操作列的图标与可访问名称。
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function renderGroupStep() {
  const root = path.resolve(__dirname, '../../docs/dst-manager/mockups');
  const app = { innerHTML: '' };
  const elements = new Map([
    ['app', app],
    ['demo-dialog', { addEventListener() {} }],
    ['toast', { textContent: '' }]
  ]);
  const listeners = new Map();
  const document = {
    documentElement: { dataset: { theme: 'light' } },
    getElementById(id) { return elements.get(id); },
    addEventListener(name, listener) { listeners.set(name, listener); }
  };
  const context = vm.createContext({ window: {}, document, setTimeout, clearTimeout });
  for (const filename of ['SPEC-DM-018-creation-model.js', 'SPEC-DM-018-creation-demo.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, filename), 'utf8'), context);
  }
  for (const action of ['start-wizard', 'next', 'next']) {
    listeners.get('click')({ target: { closest() { return { dataset: { action }, disabled: false, matches() { return false; } }; } } });
  }
  return app.innerHTML;
}

test('图纸组操作列以箭头和 X 显示排序删除，并保留清晰的按钮名称', () => {
  const html = renderGroupStep();
  assert.match(html, /<th class="action-col">操作<\/th>/);
  assert.match(html, /aria-label="上移平面图"[^>]*>↑<\/button>/);
  assert.match(html, /aria-label="下移平面图"[^>]*>↓<\/button>/);
  assert.match(html, /aria-label="删除平面图"[^>]*>✕<\/button>/);
  assert.match(html, /aria-label="上移封面"[^>]*disabled[^>]*>↑<\/button>/);
  assert.match(html, /aria-label="下移纵断面图"[^>]*disabled[^>]*>↓<\/button>/);
});
