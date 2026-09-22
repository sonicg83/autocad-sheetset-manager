// SPEC-DM-017 独立 Demo 的关键交互回归；不连接业务 API 或真实工程文件。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const file=path.resolve(__dirname,'../../docs/dst-manager/mockups/SPEC-DM-017-standard-properties-and-dwg-naming-demo.html');

function source(){
  assert.ok(fs.existsSync(file),'标准属性与 DWG 命名 Demo 尚未实现');
  return fs.readFileSync(file,'utf8');
}

function functionSlice(html,start,end){
  const from=html.indexOf(`function ${start}`);
  const to=html.indexOf(`function ${end}`,from);
  assert.notEqual(from,-1,`缺少 ${start}`);
  assert.notEqual(to,-1,`缺少 ${end}`);
  return html.slice(from,to);
}

test('必填复选框保持紧凑尺寸，不继承表格输入框的整列宽高',()=>{
  const html=source();
  assert.match(html,/\.data-table input\[type=checkbox\]\{[^}]*width:16px;[^}]*height:16px;/);
  assert.match(html,/class="checkbox-hit"/);
});

test('枚举顺序只显示序号与重排操作，不暴露内部稳定 ID',()=>{
  const dialog=functionSlice(source(),'renderEnumDialog','mappingDialog');
  assert.match(dialog,/data-action="move-enum-up"/);
  assert.match(dialog,/data-action="move-enum-down"/);
  assert.doesNotMatch(dialog,/esc\(x\[0\]\)/);
});

test('组合编辑器把宽度模式应用到外层 dialog，底部取消和保存始终属于固定操作栏',()=>{
  const html=source();
  const dialog=functionSlice(html,'compositionDialog','compositionPreview');
  assert.match(html,/dialog\.composer-dialog\{/);
  assert.match(html,/\.dialog-body\{[^}]*flex:1 1 auto;[^}]*min-height:0;[^}]*overflow:auto/);
  assert.match(dialog,/setDialogMode\('composer-dialog'\)/);
  assert.match(dialog,/data-action="close-dialog">取消</);
  assert.match(dialog,/data-action="save-composition">保存组合</);
});
