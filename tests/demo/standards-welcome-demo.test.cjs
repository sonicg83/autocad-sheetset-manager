// 图纸标准欢迎页独立 Demo 模型测试；不连接业务 API、浏览器或真实工程文件。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

function model(){
  const file=path.resolve(__dirname,'../../docs/dst-manager/mockups/SPEC-DM-016-welcome-demo.html');
  assert.ok(fs.existsSync(file),'欢迎页 Demo 尚未实现');
  const html=fs.readFileSync(file,'utf8');
  const match=html.match(/<script id="welcome-model">([\s\S]*?)<\/script>/);
  assert.ok(match,'欢迎页 Demo 缺少独立交互模型');
  const context=vm.createContext({});
  vm.runInContext(match[1],context);
  return vm.runInContext('WelcomeDemoModel',context);
}

test('打开 DST 是唯一主动作，其他任务保持固定顺序',()=>{
  const m=model();
  assert.equal(m.primary().id,'open-dst');
  assert.deepEqual(Array.from(m.secondary().map(item=>item.id)),['create-sheetset','manage-standards','import-standard']);
});

test('文件类型分别限制为 DST 与标准包',()=>{
  const m=model();
  assert.equal(m.validate('open-dst','D:\\项目\\示例.dst').ok,true);
  assert.equal(m.validate('open-dst','D:\\项目\\示例.dststandard').ok,false);
  assert.equal(m.validate('import-standard','D:\\标准\\市政.dststandard').ok,true);
  assert.equal(m.validate('import-standard','D:\\标准\\市政.zip').ok,false);
});

test('创建图纸集只能进入标准选择，不提供无标准回退',()=>{
  const m=model();
  const result=m.activate('create-sheetset');
  assert.equal(result.next,'standard-selection');
  assert.equal(result.fallback,null);
  assert.equal(result.available,false);
});

test('最近记录为空时不生成占位项目',()=>{
  const m=model();
  assert.deepEqual(Array.from(m.recent([])),[]);
});
