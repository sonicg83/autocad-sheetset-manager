// 独立演示模型测试；不连接业务 API、浏览器或真实工程。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function model(){
  const file=path.resolve(__dirname,'../../docs/dst-manager/mockups/SPEC-DM-010-properties-demo.html');
  assert.ok(fs.existsSync(file),'属性页 Demo 尚未实现');
  const code=fs.readFileSync(file,'utf8').match(/<script id="properties-model">([\s\S]*?)<\/script>/)[1];
  const ctx=vm.createContext({structuredClone});vm.runInContext(code,ctx);return vm.runInContext('PropertyDemo',ctx);
}
test('未提交与待写入独立比较，能同时存在',()=>{
  const m=model(),b=m.seed(),d=structuredClone(b),i=m.buffer(d);
  d.values.工程名称='草稿工程';i.values.工程名称='当前工程';
  assert.deepEqual({...m.status(b,d,i,'工程名称')},{dirty:true,pending:true});
  i.values.工程名称='草稿工程';assert.equal(m.status(b,d,i,'工程名称').dirty,false);
  assert.equal(m.status(b,d,i,'工程名称').pending,true);
});
test('提交全部缓冲值而非搜索结果，不污染原模型',()=>{
  const m=model(),b=m.seed(),i=m.buffer(b);i.values.工程名称='改名';i.values.说明='隐藏修改';
  const d=m.applyValues(b,i);assert.equal(d.values.说明,'隐藏修改');assert.notEqual(b.values.说明,'隐藏修改');
});
test('清空保留属性，文本中的空格与前导零不被转换',()=>{
  const m=model(),b=m.seed(),i=m.buffer(b);i.values.工程编号=' 001 ';i.values.说明='';
  const d=m.applyValues(b,i);assert.equal(d.values.工程编号,' 001 ');assert.ok(Object.hasOwn(d.values,'说明'));assert.equal(d.values.说明,'');
});
test('字段名与当前值搜索独立，修改筛选同时包含两个阶段',()=>{
  const m=model(),b=m.seed(),d=structuredClone(b),i=m.buffer(d);i.values.工程名称='ABC测试';
  assert.deepEqual(Array.from(m.filter(b,d,i,'abc','value',false)),['工程名称']);
  assert.equal(m.filter(b,d,i,'abc','name',false).length,0);
  d.values.工程编号='DRAFT';i.values.工程编号='DRAFT';
  assert.deepEqual(Array.from(m.filter(b,d,i,'','both',true)),['工程名称','工程编号']);
});
test('同名不同作用域可以新增，同作用域重复必须拒绝',()=>{
  const m=model(),b=m.seed();const d=m.addDefinition(b,{scope:'sheet',name:'工程名称',defaultValue:'默认'});
  assert.equal(d.definitions.length,b.definitions.length+1);
  assert.throws(()=>m.addDefinition(b,{scope:'sheetset',name:'工程名称',defaultValue:''}));
});
test('定义删除只影响指定作用域并保留原快照',()=>{
  const m=model(),b=m.seed(),d=m.removeDefinition(b,'sheetset','工程名称');
  assert.ok(!Object.hasOwn(d.values,'工程名称'));assert.ok(Object.hasOwn(b.values,'工程名称'));
  assert.ok(d.definitions.some(x=>x.scope==='sheet'&&x.name==='图幅'));
});
test('失效字段缓冲不能被静默丢弃或写到其他字段',()=>{
  const m=model(),b=m.seed(),i=m.buffer(b),d=m.removeDefinition(b,'sheetset','工程名称');i.values.工程名称='保留核对';
  assert.throws(()=>m.applyValues(d,i));
});
test('CSV 模拟合并区分新增跳过冲突，不覆盖已有值',()=>{
  const m=model(),b=m.seed();
  const rows=m.csvPreview(b,[{scope:'sheetset',name:'工程名称',defaultValue:''},{scope:'sheetset',name:'工程名称',defaultValue:'冲突'},{scope:'sheet',name:'复核意见',defaultValue:''}]);
  assert.deepEqual(Array.from(rows.map(r=>r.status)),['跳过','冲突','新增']);
  assert.notEqual(b.values.工程名称,'冲突');
});
test('搜索不匹配的活动字段暂留可见，结束后不再计入显示集合',()=>{
  const m=model();
  assert.deepEqual(Array.from(m.visibleKeys([], '工程名称', {工程名称:'已改'})),['工程名称']);
  assert.equal(m.visibleKeys([],null,{工程名称:'已改'}).length,0);
  assert.equal(m.visibleKeys([], '失效字段', {工程名称:'已改'}).length,0);
});
