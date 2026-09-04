// 独立 HTML 演示的数据行为测试，不连接浏览器或真实工程。
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function model(){
  const file=path.resolve(__dirname,'../../docs/dst-manager/mockups/SPEC-DM-009-sheets-demo.html');
  assert.ok(fs.existsSync(file),'图纸页 Demo 尚未实现');
  const html=fs.readFileSync(file,'utf8');
  const code=html.match(/<script id="demo-model">([\s\S]*?)<\/script>/)[1];
  const context=vm.createContext({structuredClone});vm.runInContext(code,context);
  return vm.runInContext('DemoModel',context);
}
test('全部范围与子集范围只改变结果，不更改数据',()=>{
  const m=model(),s=m.seed();assert.equal(m.rows(s).length,13);
  assert.equal(m.filter(s,{scope:'g4',q:'',status:'all',path:'all'}).length,3);
  assert.equal(m.filter(s,{scope:'all',q:'1:500',status:'all',path:'all'}).length,13);
});
test('属性跨页修改一并提交，原始模型不被污染',()=>{
  const m=model(),s=m.seed(),values={...m.rows(s)[0].props,图幅:'A2横向',校核人:'新校核'};
  const result=m.apply(s,{type:'props',id:'s1',values});
  assert.equal(m.rows(result)[0].props.图幅,'A2横向');assert.equal(m.rows(result)[0].props.校核人,'新校核');
  assert.equal(m.rows(s)[0].props.图幅,'A3横向');
});
test('参照图纸前插按对象定位，并保持其他对象 ID',()=>{
  const m=model(),s=m.seed(),r=m.apply(s,{type:'insert',group:'g4',ref:'s9',direction:'before',count:2,source:'existing',token:'a'});
  assert.deepEqual(Array.from(r.groups[3].sheets.map(x=>x.id)),['s8','a-0','a-1','s9','s10']);
  assert.equal(m.rows(r).length,15);assert.equal(m.rows(r).find(x=>x.id==='s9').number,'011');
});
test('拒绝跨子集参照、失效参照与非法数量',()=>{
  const m=model(),s=m.seed();
  for(const command of [{type:'insert',group:'g4',ref:'s1',count:1},{type:'insert',group:'g4',ref:'gone',count:1},{type:'insert',group:'g4',ref:'s9',count:0}])assert.throws(()=>m.apply(s,command));
});
test('删除为新投影，保留旧快照可供撤销',()=>{
  const m=model(),s=m.seed(),r=m.apply(s,{type:'delete',id:'s9'});
  assert.equal(m.rows(r).length,12);assert.equal(m.rows(s).length,13);assert.ok(!m.rows(r).some(x=>x.id==='s9'));
});
test('批量设置空值不隐式清空；显式清空影响指定集合',()=>{
  const m=model(),s=m.seed();assert.throws(()=>m.apply(s,{type:'bulk',ids:['s1'],name:'备注',mode:'set',value:''}));
  const r=m.apply(s,{type:'bulk',ids:['s1','s8'],name:'备注',mode:'clear'});
  assert.equal(m.rows(r).find(x=>x.id==='s8').props.备注,'');assert.equal(m.rows(r).find(x=>x.id==='s2').props.备注,'待复核');
});
test('新建子集按参照定位，基础与布局模板必须分别提供',()=>{
  const m=model(),s=m.seed(),c={type:'group',title:'新增分册',ref:'g2',direction:'after',count:2,base:'基础.dwt',template:'布局.dwg',layout:'标准图框',token:'new'};
  const r=m.apply(s,c);assert.equal(r.groups[2].title,'新增分册');assert.equal(m.rows(r).length,15);
  assert.throws(()=>m.apply(s,{...c,base:''}));
});
