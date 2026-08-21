import {expect,test} from "@playwright/test";

function deferred(){let resolve!:()=>void;const promise=new Promise<void>(done=>{resolve=done});return {promise,resolve}}

const workspace={
  id:"workspace-1",revision_id:"revision-1",sheet_set:{name:"测试图纸集",sheet_count:2,subset_count:2,custom_properties:{项目号:"P-001"},property_definitions:[{type:"sheetset",name:"项目号",default_value:"P-001"},{type:"sheet",name:"比例",default_value:""}],subsets:[
    {id:"subset-1",name:"001-002 第一册",title:"第一册",number_range:"001-002",display_name:"001-002 第一册",sheets:[{id:"sheet-1",number:"001",title:"第一册 (一)",custom_properties:{比例:"1:100"}},{id:"sheet-2",number:"002",title:"第一册 (二)",custom_properties:{比例:"1:100"}}]},
    {id:"subset-2",name:"第二册",title:"第二册",number_range:"",display_name:"第二册",sheets:[]},
  ]},diagnostics:[],
};

function workspaceVersion(id:string,name:string,revisionId:string){return {...workspace,id,revision_id:revisionId,sheet_set:{...workspace.sheet_set,name}}}

async function openWorkspace(page:any){
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await page.goto("/");
  await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\project\\test.dst");
  await page.getByRole("button",{name:"打开项目"}).click();
}

test("维护属性并按位置创建子集后预览派生变化",async({page})=>{
  const previewRequests:any[][]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{
    const commands=(await route.request().postDataJSON()).commands;previewRequests.push(commands);
    if(["add_custom_property","delete_custom_property"].includes(commands[0]?.type))return route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:commands[0].type,after:commands[0]}],diagnostics:[],affected_files:["C:\\project\\test.dst"],execution_intent:null}});
    return route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"number_range_changed",before:"001-002",after:"001-004"}],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\003-004 新分册.dwg","C:\\project\\001-002 第一册.dwg"],execution_intent:{derived_document:{subsets:[{acsm_id:"subset-new",number_range:"003-004",display_name:"003-004 新分册",title:"新分册"}]},groups:[
      {operation:"create",subset_name:"003-004 新分册",target_file:"C:\\project\\003-004 新分册.dwg",layouts:[{number:"003",title:"新分册 (一)",target_layout:"003 新分册 (一)"},{number:"004",title:"新分册 (二)",target_layout:"004 新分册 (二)"}]},
      {operation:"rebuild",subset_name:"001-002 第一册",target_file:"C:\\project\\001-002 第一册.dwg",layouts:[{number:"001",title:"第一册 (一)",target_layout:"001 第一册 (一)"}]},
    ]}}});
  });
  await openWorkspace(page);
  await page.getByLabel("属性作用域").selectOption("sheet");await page.getByLabel("属性名称").fill("专业");await page.getByLabel("默认值").fill("燃气");await page.getByRole("button",{name:"加入属性定义"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[0]).toEqual([{type:"add_custom_property",property_type:"sheet",name:"专业",default_value:"燃气"}]);
  await page.getByRole("button",{name:"清空"}).click();await page.getByRole("button",{name:"删除 比例"}).click();await page.getByRole("button",{name:"预览变更"}).click();expect(previewRequests[1]).toEqual([{type:"delete_custom_property",property_type:"sheet",name:"比例"}]);
  await page.getByLabel("子集序号").fill("2");await page.getByLabel("子集方向").selectOption("after");await page.getByLabel("子集标题",{exact:true}).fill("新分册");await page.getByLabel("初始图纸数").fill("2");await page.getByLabel("模板文件").fill("C:\\template.dwt");await page.getByLabel("模板布局",{exact:true}).fill("A1模板");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("属性定义与结构变更必须分批预览和执行")).toBeVisible();
  await page.getByRole("button",{name:"清空"}).click();await page.getByRole("button",{name:"新建子集"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[2]).toEqual([{type:"insert_subset",ordinal:2,placement:"after",title:"新分册",initial_sheet_count:2,source:{type:"template_layout",file:"C:\\template.dwt",layout:"A1模板"}}]);expect(previewRequests[2][0]).not.toHaveProperty("number");
  await expect(page.getByText("图号范围变化")).toBeVisible();await expect(page.getByText("创建 DWG")).toBeVisible();await expect(page.getByText("重建 DWG")).toBeVisible();const derivedTable=page.locator(".preview table").filter({hasText:"服务端图号范围"});await expect(derivedTable.getByRole("cell",{name:"003-004",exact:true})).toBeVisible();await expect(derivedTable.getByRole("cell",{name:"003-004 新分册",exact:true})).toBeVisible();const createdGroup=page.locator(".execution-group").filter({hasText:"创建 DWG"});await expect(createdGroup.getByText("C:\\project\\003-004 新分册.dwg",{exact:true})).toBeVisible();await expect(createdGroup.getByRole("cell",{name:"003 新分册 (一)",exact:true})).toBeVisible();
});

test("普通预览丢弃乱序响应并只执行冻结命令",async({page})=>{
  const gates=[deferred(),deferred(),deferred(),deferred()];const previewBodies:any[]=[];let executeBody:any=null;
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{const index=previewBodies.length;previewBodies.push(await route.request().postDataJSON());await gates[index].promise;await route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:`preview-${index+1}`}],diagnostics:[],affected_files:[`preview-${index+1}.dst`],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",async route=>{executeBody=await route.request().postDataJSON();await route.fulfill({json:{id:"job-race",status:"FAILED",progress:0,attempt:1,files:[]}})});
  await openWorkspace(page);await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(2);
  gates[1].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();gates[0].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();await expect(page.getByText("preview-1",{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByRole("button",{name:"确认并执行"})).toHaveCount(0);await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(3);await page.getByRole("button",{name:"清空"}).click();gates[2].resolve();await expect(page.getByRole("button",{name:"确认并执行"})).toHaveCount(0);
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(4);gates[3].resolve();await expect(page.getByText("preview-4",{exact:true})).toBeVisible();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect.poll(()=>executeBody).not.toBeNull();expect(executeBody.base_revision_id).toBe(previewBodies[3].base_revision_id);expect(executeBody.commands).toEqual(previewBodies[3].commands);expect(executeBody.commands).not.toBe(previewBodies[3].commands);
});

test("CSV 预览丢弃换文件和乱序响应并只导入冻结文本",async({page})=>{
  const gates=[deferred(),deferred(),deferred()];const previewBodies:any[]=[];let importBody:any=null;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{const index=previewBodies.length;const body=await route.request().postDataJSON();previewBodies.push(body);const name=body.csv.match(/sheet,([^,]+)/)?.[1]??`属性${index}`;await gates[index].promise;await route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name,default_value:""}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/custom-properties/import",async route=>{importBody=await route.request().postDataJSON();await route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}})});
  await openWorkspace(page);const csvInput=page.getByLabel("属性 CSV 文件");const csv=(name:string)=>({name:`${name}.csv`,mimeType:"text/csv",buffer:Buffer.from(`type,name,default_value\nsheet,${name},\n`,"utf8")});
  await csvInput.setInputFiles(csv("A属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await csvInput.setInputFiles(csv("B属性"));gates[0].resolve();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();await expect(page.locator(".csv-preview").getByText("A属性")).toHaveCount(0);
  await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(2);await csvInput.setInputFiles(csv("C属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(3);gates[2].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();gates[1].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();await expect(page.locator(".csv-preview").getByText("B属性")).toHaveCount(0);
  page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认导入"}).click();await expect.poll(()=>importBody).not.toBeNull();expect(importBody).toEqual(previewBodies[2]);
});

test("非法 UTF-8 CSV 在本地阻断且不请求 API",async({page})=>{
  let previewCalls=0,importCalls=0;await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>{previewCalls++;return route.abort()});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>{importCalls++;return route.abort()});await openWorkspace(page);
  await page.getByLabel("属性 CSV 文件").setInputFiles({name:"invalid.csv",mimeType:"text/csv",buffer:Buffer.from([0x74,0x79,0x70,0x65,0x0a,0xc3,0x28])});await expect(page.getByText("CSV 必须使用 UTF-8 编码",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"预览 CSV 导入"})).toBeDisabled();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();expect(previewCalls).toBe(0);expect(importCalls).toBe(0);
});

test("加载新工作区时隐藏旧编辑器并阻断跨工作区执行",async({page})=>{
  const openB=deferred();let openCalls=0,executeCalls=0,importCalls=0;
  await page.route("**/api/workspaces/open",async route=>{openCalls++;if(openCalls===1)return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"A-preview"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"A属性",default_value:""}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/changes/execute",route=>{executeCalls++;return route.fulfill({json:{id:"stale-execute",status:"FAILED",progress:0,files:[]}})});await page.route("**/api/workspaces/workspace-A/custom-properties/import",route=>{importCalls++;return route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}})});
  await page.goto("/");await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\A.dst");await page.getByRole("button",{name:"打开项目"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 A");await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\B.dst");await page.getByRole("button",{name:"打开项目"}).click();await expect.poll(()=>openCalls).toBe(2);
  const loadingWasVisible=await page.getByText("正在加载工作区…",{exact:true}).isVisible();const oldEditorWasVisible=await page.locator(".editor").isVisible();if(oldEditorWasVisible){await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByLabel("属性 CSV 文件").setInputFiles({name:"A.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,A属性,\n","utf8")});await page.getByRole("button",{name:"预览 CSV 导入"}).click()}
  openB.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 B");const staleExecute=page.getByRole("button",{name:"确认并执行"});if(await staleExecute.isVisible()){page.once("dialog",dialog=>dialog.accept());await staleExecute.click()}const staleImport=page.getByRole("button",{name:"确认导入"});if(await staleImport.isEnabled()){page.once("dialog",dialog=>dialog.accept());await staleImport.click()}
  expect(loadingWasVisible).toBe(true);expect(oldEditorWasVisible).toBe(false);expect(executeCalls).toBe(0);expect(importCalls).toBe(0);await expect(staleExecute).toHaveCount(0);await expect(staleImport).toBeDisabled();
});

test("多次打开及刷新与打开竞争时仅最新工作区生效",async({page})=>{
  const openB=deferred(),openC=deferred(),refreshC=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst"))return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});if(path.endsWith("B.dst")){await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})}if(path.endsWith("C.dst")){await openC.promise;return route.fulfill({json:workspaceVersion("workspace-C","工作区 C","revision-C")})}return route.fulfill({json:workspaceVersion("workspace-D","工作区 D","revision-D")})});
  await page.route("**/api/workspaces/workspace-C/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"C-preview"}],diagnostics:[],affected_files:["C.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-C/changes/execute",route=>route.fulfill({json:{id:"job-C",status:"SUCCEEDED",progress:100,files:[]}}));await page.route("**/api/workspaces/workspace-C",async route=>{refreshStarted=true;await refreshC.promise;await route.fulfill({json:workspaceVersion("workspace-C","工作区 C 刷新","revision-C2")})});
  await page.goto("/");const pathInput=page.getByPlaceholder("输入 .dst 绝对路径");await pathInput.fill("C:\\A.dst");await page.getByRole("button",{name:"打开项目"}).click();await pathInput.fill("C:\\B.dst");await page.getByRole("button",{name:"打开项目"}).click();await pathInput.fill("C:\\C.dst");await page.getByRole("button",{name:"打开项目"}).click();openC.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 C");openB.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 C");
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect.poll(()=>refreshStarted).toBe(true);await pathInput.fill("C:\\D.dst");await page.getByRole("button",{name:"打开项目"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 D");refreshC.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 D");
});

test("旧编辑入口已移除且图号标题只读",async({page})=>{
  await openWorkspace(page);await expect(page.getByRole("button",{name:"子集↑"})).toHaveCount(0);await expect(page.getByRole("button",{name:"子集↓"})).toHaveCount(0);await expect(page.getByText("移动到",{exact:true})).toHaveCount(0);const sheetRow=page.locator(".subset-editor tbody tr").filter({has:page.getByText("001",{exact:true})});await expect(sheetRow.locator("td").nth(0).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(1).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(0)).toHaveText("001");await expect(sheetRow.locator("td").nth(1)).toHaveText("第一册 (一)");
});

test("批量新增图纸校验位置数量和布局来源",async({page})=>{
  let previewCommands:any[]=[];await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewCommands=(await route.request().postDataJSON()).commands;await route.fulfill({json:{executable:true,requires_cad:true,changes:[],diagnostics:[],affected_files:[],execution_intent:{groups:[]}}})});await openWorkspace(page);
  await page.getByLabel("图纸序号").fill("3");await page.getByLabel("新增图纸数量").fill("0");await page.getByRole("button",{name:"批量新增图纸"}).click();await expect(page.getByText("图纸序号必须在 1 到 2 之间")).toBeVisible();expect(previewCommands).toHaveLength(0);
  await page.getByLabel("图纸序号").fill("2");await page.getByLabel("新增图纸数量").fill("2");await page.getByRole("button",{name:"批量新增图纸"}).click();await expect(page.getByText("来源文件和来源布局不能为空")).toBeVisible();await page.getByLabel("来源文件").fill("C:\\source.dwg");await page.getByLabel("来源布局").fill("A1");await page.getByLabel("图纸方向").selectOption("before");await page.getByRole("button",{name:"批量新增图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewCommands).toEqual([{type:"insert_sheet",target_subset_id:"subset-1",ordinal:2,placement:"before",count:2,source:{type:"template_layout",file:"C:\\source.dwg",layout:"A1"}}]);expect(previewCommands[0]).not.toHaveProperty("number");expect(previewCommands[0]).not.toHaveProperty("title");
});

test("空图纸集首个子集只能用序号一且必须提供模板",async({page})=>{
  const empty={...workspace,sheet_set:{...workspace.sheet_set,sheet_count:0,subset_count:0,subsets:[]}};let previewCalls=0;await page.route("**/api/workspaces/open",route=>route.fulfill({json:empty}));await page.route("**/api/workspaces/workspace-1/changes/preview",route=>{previewCalls++;return route.fulfill({json:{executable:true,changes:[],diagnostics:[]}})});await page.goto("/");await page.getByPlaceholder("输入 .dst 绝对路径").fill("C:\\project\\test.dst");await page.getByRole("button",{name:"打开项目"}).click();await page.getByLabel("子集序号").fill("2");await page.getByLabel("子集标题",{exact:true}).fill("首册");await page.getByLabel("初始图纸数").fill("1");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("空图纸集的首个子集序号必须为 1")).toBeVisible();await page.getByLabel("子集序号").fill("1");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("模板文件和模板布局不能为空")).toBeVisible();expect(previewCalls).toBe(0);
});

test("属性命令与结构命令分批并支持 CSV 行级预览导入",async({page})=>{
  let importedCsv="";await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{importedCsv=(await route.request().postDataJSON()).csv;await route.fulfill({json:{executable:false,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[{line:3,severity:"error",code:"CUSTOM_PROPERTY_NAME_EMPTY",message:"名称不能为空"}],affected_files:["test.dst"],execution_intent:null}})});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:"csv-job",status:"SUCCEEDED",progress:100,files:[]}}));await openWorkspace(page);
  await expect(page.getByRole("link",{name:"下载 CSV 模板"})).toHaveAttribute("href","/api/custom-properties/template");await expect(page.getByRole("link",{name:"导出当前属性"})).toHaveAttribute("href","/api/workspaces/workspace-1/custom-properties/export");await page.getByLabel("属性 CSV 文件").setInputFiles({name:"properties.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,专业,燃气\nsheet,,\n","utf8")});await page.getByRole("button",{name:"预览 CSV 导入"}).click();expect(importedCsv).toContain("sheet,专业,燃气");await expect(page.getByText("第 3 行")).toBeVisible();await expect(page.getByText("CUSTOM_PROPERTY_NAME_EMPTY")).toBeVisible();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  await page.unroute("**/api/workspaces/workspace-1/custom-properties/import/preview");await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.getByRole("button",{name:"预览 CSV 导入"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认导入"}).click();await expect(page.getByText("任务 csv-job")).toBeVisible();
});

test("失败任务显示逐 DWG 详情并可安全重试",async({page})=>{
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,duration_ms:600000,error_code:"CAD_TIMEOUT"}]}}));await page.route("**/api/jobs/job-failed/retry",route=>route.fulfill({json:{id:"job-failed",status:"QUEUED",progress:0,attempt:1,files:[]}}));await openWorkspace(page);await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();await expect(page.getByText("A.dwg")).toBeVisible();await expect(page.getByText("检查 CAD 日志")).toBeVisible();await page.getByRole("button",{name:"安全重试"}).click();await expect(page.getByText(/QUEUED/)).toBeVisible();
});

test("修订恢复先预览再确认为新修订",async({page})=>{
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-1",status:"SUCCEEDED",progress:100,attempt:0,files:[]}}));await openWorkspace(page);await page.getByRole("button",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();await expect(page.getByText("replace test.dst")).toBeVisible();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"恢复为新修订"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");
});
