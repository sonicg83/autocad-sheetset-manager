import {expect,test,type Page} from "@playwright/test";
import {writeFileSync} from "node:fs";
import {buildPreviewFromBase} from "./fixtures/sheets";

test.beforeEach(async({page})=>{
  await page.addInitScript(() => {
    // 真实 pywebview 在页面加载后才异步注入 window.pywebview 并派发 pywebviewready；
    // ?late-bridge 模拟该时序（load 后 30ms 才注入），验证前端不把"晚到的桥"当成无壳浏览器
    const inject = () => {
      (window as any).pywebview = {
        api: {
          select_file: async (fileTypes: string[]) => (window as any).__fakeSelectResult ?? null,
          on_files_dropped: async () => {},
        },
      };
      window.dispatchEvent(new Event("pywebviewready"));
    };
    if (new URLSearchParams(window.location.search).has("late-bridge")) {
      window.addEventListener("load", () => setTimeout(inject, 30));
    } else {
      inject();
    }
  });
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  const drafts=new Map<string,any>();
  await page.route("**/api/workspaces/*/draft",async route=>{
    const request=route.request();
    const workspaceId=new URL(request.url()).pathname.split("/").at(-2)!;
    const current=drafts.get(workspaceId)??null;
    if(request.method()==="GET")return route.fulfill({json:{draft:current,corrupted:false,stale:false,stale_reasons:[]}});
    if(request.method()==="DELETE"){drafts.delete(workspaceId);return route.fulfill({json:{deleted:current!==null}})}
    const body=await request.postDataJSON();
    const saved={...body,workspace_id:workspaceId,version:(current?.version??0)+1};
    delete saved.expected_version;drafts.set(workspaceId,saved);
    return route.fulfill({json:{draft:saved,corrupted:false,stale:false,stale_reasons:[]}});
  });
});

test("CAD 操作分流",async({page})=>{
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"number_range_changed"}],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\001-002.dwg","C:\\project\\003-004.dwg"],execution_intent:{cad_validation_deferred:true,cardinality_frontier:{index:1,subset_id:"subset-2"},subset_operations:[{subset_id:"subset-1",cad_operation:"rename_only",target_file:"C:\\project\\001-002.dwg",in_cardinality_scope:false},{subset_id:"subset-2",cad_operation:"rebuild",target_file:"C:\\project\\003-004.dwg",in_cardinality_scope:true}],source_baselines:[{path:"C:\\project\\001-002.dwg",sha256:"source-sha-256",identity:["source-id"],source_types:["existing_snapshot"],requested_layouts:["001 第一册(一)"]}],groups:[{subset_id:"subset-1",cad_operation:"rename_only",subset_name:"第一册",target_file:"C:\\project\\001-002.dwg",layouts:[]},{subset_id:"subset-2",cad_operation:"rebuild",subset_name:"第二册",target_file:"C:\\project\\003-004.dwg",layouts:[]},{subset_id:"subset-none",cad_operation:"none",subset_name:"无需操作",target_file:"C:\\project\\none.dwg",layouts:[]},{subset_id:"subset-missing",subset_name:"缺失操作",target_file:"C:\\project\\missing.dwg",layouts:[]},{subset_id:"subset-unknown",cad_operation:"legacy",subset_name:"未知操作",target_file:"C:\\project\\unknown.dwg",layouts:[]}]}}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-cad",status:"FAILED",progress:100,attempt:1,files:[{target_path:"C:\\project\\001-002.dwg",status:"SUCCEEDED",progress:100,cad_operation:"rename_only",started_at:"2026-08-26T10:00:00Z",finished_at:"2026-08-26T10:00:02Z",duration_ms:2000},{target_path:"C:\\project\\003-004.dwg",status:"FAILED",progress:100,cad_operation:"rebuild",started_at:"2026-08-26T10:00:03Z",finished_at:"2026-08-26T10:00:08Z",duration_ms:5000}]}}));
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await page.locator(".summary button").click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("批量改名布局").first()).toBeVisible();await expect(page.getByText("清除并重建布局").first()).toBeVisible();await expect(page.getByText("无需 CAD 操作",{exact:true}).first()).toBeVisible();await expect(page.getByText("未提供 CAD 操作",{exact:true})).toBeVisible();await expect(page.getByText("未知 CAD 操作：legacy",{exact:true})).toBeVisible();await expect(page.getByText("数量变化前沿：第 2 个子集")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("source-sha-256",{exact:true})).toBeVisible();await expect(page.getByText("布局来源验证")).toHaveCount(0);const affectedFiles=page.locator(".preview > section").filter({has:page.getByRole("heading",{name:"受影响文件"})});await expect(affectedFiles.getByText("C:\\project\\001-002.dwg",{exact:true})).toBeVisible();await expect(affectedFiles.getByText("C:\\project\\003-004.dwg",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // 任务详情迁入任务浮层实施进度页签：预览已展开浮层，切到实施进度页签再断言逐文件行
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("tab",{name:"实施进度"}).click();
  const jobDetail=overlay.locator(".job-detail");const renameRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\001-002.dwg"});const rebuildRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\003-004.dwg"});await expect(renameRow.getByText("批量改名布局",{exact:true})).toBeVisible();await expect(renameRow.getByText("2026-08-26T10:00:00Z",{exact:true})).toBeVisible();await expect(renameRow.getByText("2026-08-26T10:00:02Z",{exact:true})).toBeVisible();await expect(renameRow.getByText("2000 ms",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("清除并重建布局",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("2026-08-26T10:00:03Z",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("2026-08-26T10:00:08Z",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("5000 ms",{exact:true})).toBeVisible();
});

function deferred(){let resolve!:()=>void;const promise=new Promise<void>(done=>{resolve=done});return {promise,resolve}}

const workspace={
  id:"workspace-1",revision_id:"revision-1",dst_path:"C:\\project\\test.dst",sheet_set:{name:"测试图纸集",sheet_count:2,subset_count:2,custom_properties:{项目号:"P-001"},property_definitions:[{type:"sheetset",name:"项目号",default_value:"P-001"},{type:"sheet",name:"比例",default_value:""}],subsets:[
    {id:"subset-1",name:"001-002 第一册",title:"第一册",number_range:"001-002",display_name:"001-002 第一册",sheets:[{id:"sheet-1",number:"001",title:"第一册 (一)",custom_properties:{比例:"1:100"},layout:{file_name:"C:\\project\\001-002 第一册.dwg",relative_file_name:".\\001-002 第一册.dwg",resolved_path:"C:\\project\\001-002 第一册.dwg",layout_name:"001 第一册 (一)",handle:"A1"}},{id:"sheet-2",number:"002",title:"第一册 (二)",custom_properties:{比例:"1:100"},layout:{file_name:"C:\\project\\001-002 第一册.dwg",relative_file_name:".\\001-002 第一册.dwg",resolved_path:"C:\\project\\001-002 第一册.dwg",layout_name:"002 第一册 (二)",handle:"A2"}}]},
    {id:"subset-2",name:"第二册",title:"第二册",number_range:"",display_name:"第二册",sheets:[]},
  ]},diagnostics:[],
};

function workspaceVersion(id:string,name:string,revisionId:string){return {...workspace,id,revision_id:revisionId,sheet_set:{...workspace.sheet_set,name}}}

function workspaceWith300Sheets(){
  const subsets=Array.from({length:10},(_,subsetIndex)=>({id:`subset-${subsetIndex}`,name:`子集 ${subsetIndex+1}`,title:`子集 ${subsetIndex+1}`,number_range:`${subsetIndex*30+1}-${subsetIndex*30+30}`,display_name:`子集 ${subsetIndex+1}`,sheets:Array.from({length:30},(_,sheetIndex)=>{const ordinal=subsetIndex*30+sheetIndex+1;const number=String(ordinal).padStart(3,"0");const file=`C:\\project\\${String(subsetIndex+1).padStart(2,"0")}-分册.dwg`;return {id:`sheet-${ordinal}`,number,title:`图纸 ${ordinal}`,custom_properties:{比例:ordinal%2?"1:100":"1:50",专业:ordinal%3?"建筑":"结构"},layout:{file_name:file,relative_file_name:`.\\${file.split("\\").at(-1)}`,resolved_path:ordinal%5?file:null,layout_name:`${number} 图纸 ${ordinal}`,handle:ordinal.toString(16)}}})}));
  return {...workspace,sheet_set:{...workspace.sheet_set,sheet_count:300,subset_count:10,property_definitions:[...workspace.sheet_set.property_definitions,{type:"sheet",name:"专业",default_value:""}],subsets}};
}

async function installMockEventSource(page:any){await page.addInitScript(()=>{class FakeEventSource{url:string;onmessage:((event:{data:string})=>void)|null=null;onerror:(()=>void)|null=null;closed=false;constructor(url:string){this.url=url;(window as any).__eventSources.push(this)}close(){this.closed=true}};(window as any).__eventSources=[];(window as any).__emitJob=(payload:any)=>{for(const source of (window as any).__eventSources)if(!source.closed)source.onmessage?.({data:JSON.stringify(payload)})};(window as any).__closedEventSources=()=>((window as any).__eventSources as FakeEventSource[]).filter(source=>source.closed).length;(window as any).EventSource=FakeEventSource})}

function selectDst(page:Page,dst:string){return page.evaluate(p=>{(window as any).__fakeSelectResult=p},dst).then(()=>page.getByRole("button",{name:"选择 DST 文件"}).click())}

async function openWorkspace(page:Page,dst="C:\\project\\test.dst"){
  await page.goto("/");
  await selectDst(page,dst);
  await expect(page.getByRole("button",{name:"关闭"})).toBeVisible();
}

// 确认模态交互（替代原生 confirm）：需要勾选的模态先勾选，再点按确认按钮
// Task 5 起草稿栈浮窗也带 role="dialog"（aria-label="草稿动作栈"），故确认模态一律以 aria-modal="true" 精确匹配
async function confirmModal(page:Page,confirmName:RegExp|string){
  const modal=page.locator('[role="dialog"][aria-modal="true"]');
  if(await modal.getByRole("checkbox").count())await modal.getByRole("checkbox").check();
  await modal.getByRole("button",{name:confirmName}).click();
}
async function cancelModal(page:Page){
  await page.locator('[role="dialog"][aria-modal="true"]').getByRole("button",{name:"取消"}).click();
}
// 草稿栈浮窗（Task 5）：点计数芯片展开 / Esc 关闭（§7.2 抽屉模型，焦点归还芯片）
// 用 .draft-chip 类精确定位：/草稿/ 名称正则会误中"批量加入草稿"按钮
async function openDraftPop(page:Page){await page.locator(".draft-chip").click()}
async function closeDraftPop(page:Page){await page.keyboard.press("Escape")}

test("草稿按动作持久化并支持 A→B→C 撤销恢复 B、重做和批量原子撤销",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"draft-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.locator(".summary input");
  for(const value of ["A","B","C"]){await name.fill(value);await page.getByRole("button",{name:"更新图纸集"}).click()}
  await page.getByRole("tab",{name:"图纸"}).click();
  await openDraftPop(page);
  await expect(page.getByText("动作 3/3")).toBeVisible();
  await closeDraftPop(page);
  await page.getByRole("button",{name:"撤销"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(name).toHaveValue("B");
  expect(previewBodies.at(-1).commands).toEqual([{type:"update_sheet_set",name:"B",custom_properties:{项目号:"P-001"}}]);
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"重做"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(name).toHaveValue("C");
  expect(previewBodies.at(-1).commands[0].name).toBe("C");
  await page.getByRole("tab",{name:"图纸"}).click();
  // 任务 3 起选择后出现吸顶选择条，批量输入经「批量修改属性」展开
  await page.getByRole("button",{name:"全选当前结果"}).click();await page.getByRole("button",{name:"批量修改属性"}).click();await page.getByLabel("既有图纸属性").selectOption("比例");await page.getByLabel("批量值").fill("1:200");await page.getByRole("button",{name:"批量加入草稿"}).click();
  await openDraftPop(page);
  await expect(page.getByText("批量更新 比例（2 张） · 2 条命令")).toBeVisible();
  await closeDraftPop(page);
  await page.getByRole("button",{name:"撤销"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies.at(-1).commands).toHaveLength(1);expect(previewBodies.at(-1).commands[0].name).toBe("C");
  await page.reload();await selectDst(page,"C:\\project\\test.dst");
  await openDraftPop(page);
  await expect(page.getByText("动作 3/4")).toBeVisible();
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.locator(".summary input")).toHaveValue("C");
});

test("移除 active 动作不会激活 redo 区命令",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"remove-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{sheet_set:[],structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.locator(".summary input");
  for(const value of ["A","B","C"]){await name.fill(value);await page.getByRole("button",{name:"更新图纸集"}).click()}
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"撤销"}).click();
  await openDraftPop(page);
  const actions=page.locator(".draft-actions li");
  await actions.nth(0).getByRole("button",{name:"移除"}).click();
  await expect(page.getByText("动作 1/2")).toBeVisible();
  await closeDraftPop(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(name).toHaveValue("B");
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies.at(-1).commands).toEqual([{type:"update_sheet_set",name:"B",custom_properties:{项目号:"P-001"}}]);
});

test("关闭未发布改动时确认放弃会先冲刷在途草稿保存再删除",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  const firstPutStarted=deferred();const releaseFirstPut=deferred();const savedByWorkspace=new Map<string,any>();let putCount=0,deleted=false;
  await page.route("**/api/workspaces/*/draft",async route=>{
    const request=route.request();const workspaceId=new URL(request.url()).pathname.split("/").at(-2)!;
    if(request.method()==="GET")return route.fulfill({json:{draft:savedByWorkspace.get(workspaceId)??null,corrupted:false,stale:false,stale_reasons:[]}});
    if(request.method()==="DELETE"){deleted=true;savedByWorkspace.delete(workspaceId);return route.fulfill({json:{deleted:true}})}
    const body=await request.postDataJSON();putCount+=1;if(putCount===1){firstPutStarted.resolve();await releaseFirstPut.promise}
    const saved={...body,workspace_id:workspaceId,version:putCount};delete saved.expected_version;savedByWorkspace.set(workspaceId,saved);
    return route.fulfill({json:{draft:saved,corrupted:false,stale:false,stale_reasons:[]}});
  });
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.includes("B.dst")?workspaceVersion("workspace-2","工作区 B","revision-2"):workspace})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.locator(".summary input");await name.fill("A");await page.getByRole("button",{name:"更新图纸集"}).click();await firstPutStarted.promise;await name.fill("B");await page.getByRole("button",{name:"更新图纸集"}).click();
  // 关闭 A：存在未发布改动 → 确认放弃 → discardDraft 先等待在途草稿保存全部完成再删除
  await page.getByRole("button",{name:"关闭"}).click();
  await confirmModal(page,/确定关闭并放弃当前改动/);
  releaseFirstPut.resolve();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await selectDst(page,"C:\\B.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 B");
  expect(putCount).toBe(2);expect(deleted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();await selectDst(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("草稿网络保存失败会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:500,json:{code:"DRAFT_SAVE_FAILED",message:"保存失败"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();const name=page.locator(".summary input");await name.fill("未保存名称");await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText(/保存失败/)).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();await cancelModal(page);
  await page.getByRole("tab",{name:"属性"}).click();await expect(name).toHaveValue("未保存名称");await page.getByRole("tab",{name:"图纸"}).click();await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
});

test("草稿版本冲突会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:409,json:{code:"DRAFT_CONFLICT",message:"版本冲突"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();const name=page.locator(".summary input");await name.fill("冲突名称");await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByText(/其他窗口更新/)).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();await cancelModal(page);
  await expect(name).toHaveValue("冲突名称");await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
  await page.getByRole("button",{name:"放弃本地冲突动作并重新加载"}).click();await confirmModal(page,/确定放弃冲突动作并重新加载/);await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");await page.getByRole("tab",{name:"图纸"}).click();await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("过期草稿只展示旧意图、阻断预览且可明确丢弃",async({page})=>{
  let deleted=false;await page.unroute("**/api/workspaces/*/draft");await page.route("**/api/workspaces/*/draft",async route=>{if(route.request().method()==="DELETE"){deleted=true;return route.fulfill({json:{deleted:true}})}return route.fulfill({json:{corrupted:false,stale:true,stale_reasons:["BASE_REVISION_CHANGED"],draft:{schema_version:1,workspace_id:"workspace-1",base_revision_id:"old-revision",repair_status:"VALID",version:3,cursor:1,actions:[{id:"old-action",kind:"command_batch",label:"旧图纸集名称",commands:[{type:"update_sheet_set",name:"旧值",custom_properties:{项目号:"P-001"}}]}]}}})});
  await openWorkspace(page);await openDraftPop(page);await expect(page.getByText(/草稿已过期（BASE_REVISION_CHANGED）/)).toBeVisible();await expect(page.getByText("旧图纸集名称 · 1 条命令")).toBeVisible();await closeDraftPop(page);await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();await openDraftPop(page);await page.getByRole("button",{name:"丢弃过期草稿"}).click();expect(deleted).toBe(true);await expect(page.getByText(/草稿已过期/)).toHaveCount(0);
});

test("三级导航可按 DWG 路径筛选、多选批量修改并确认删除整个子集",async({page})=>{
  let previewCommands:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewCommands=(await route.request().postDataJSON()).commands;return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"delete-digest",executable:true,requires_cad:true,changes:[],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\001-002 第一册.dwg"],semantic_diff:{structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:{groups:[],deleted_subsets:[]}}})});
  await openWorkspace(page);
  await page.getByLabel("搜索图纸").fill("001-002 第一册.DWG");await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(2);
  // 任务 3 起子集范围经树切换（树与范围筛选共用一个范围状态，不再有独立子集下拉）
  await page.getByRole("treeitem",{name:/第二册/}).click();await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(0);await page.getByRole("treeitem",{name:/001-002 第一册/}).click();
  await page.getByRole("button",{name:"全选当前结果"}).click();await expect(page.getByText("已选 2")).toBeVisible();
  await page.getByRole("button",{name:"批量修改属性"}).click();await page.getByLabel("既有图纸属性").selectOption("比例");await page.getByLabel("批量值").fill("1:50");await page.getByRole("button",{name:"批量加入草稿"}).click();await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);
  // 任务 3 起「删除整个子集」迁入非驻留的编辑子集表单
  await page.getByRole("button",{name:"编辑子集"}).click();await page.getByRole("button",{name:"删除整个子集"}).click();const deleteModal=page.getByRole("dialog");await expect(deleteModal.getByText(/系统不会证明工程外部引用/)).toBeVisible();await deleteModal.getByRole("checkbox").check();await deleteModal.getByRole("button",{name:/确定删除整个子集/}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewCommands).toEqual([{type:"delete_subset",subset_id:"subset-1",confirm_delete_all_sheets:true,confirm_delete_main_dwg:true}]);
});

test("300 行搜索过滤全选与首屏渲染满足性能预算",async({page},testInfo)=>{
  const large=workspaceWith300Sheets();
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:large}));
  const started=Date.now();await openWorkspace(page);await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(80);const firstInteractiveMs=Date.now()-started;
  const samples:number[]=[];
  for(let index=0;index<20;index++){
    const elapsed=await page.evaluate(async value=>{
      const input=document.querySelector<HTMLInputElement>('input[placeholder="图号、标题、属性或 DWG"]')!;const start=performance.now();input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);return performance.now()-start;
    },index%2?"结构":"分册.dwg");
    samples.push(elapsed);
  }
  await page.getByRole("button",{name:/继续加载/}).click();await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(100);await page.locator(".sheet-table-window").focus();await page.keyboard.press("Tab");await expect(page.getByLabel("选择图纸 003")).toBeFocused();
  await page.getByRole("button",{name:"全选当前结果"}).click();await expect(page.getByText(/已选 \d+/)).toBeVisible();
  const sorted=[...samples].sort((a,b)=>a-b);const median=sorted[Math.floor(sorted.length/2)];const p95=sorted[Math.ceil(sorted.length*.95)-1];
  console.info("PERF_300",JSON.stringify({browser:"Chromium",rows:300,firstInteractiveMs,samples,median,p95}));
  const performanceResult={browser:"Chromium",rows:300,firstInteractiveMs,samples,median,p95};const performancePath=testInfo.outputPath("performance-300.json");writeFileSync(performancePath,JSON.stringify(performanceResult,null,2),"utf8");await testInfo.attach("performance-300.json",{path:performancePath,contentType:"application/json"});
  expect(firstInteractiveMs).toBeLessThanOrEqual(1500);expect(median).toBeLessThanOrEqual(50);expect(p95).toBeLessThanOrEqual(100);
});

test("维护属性并按位置创建子集后预览派生变化",async({page})=>{
  const previewRequests:any[][]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{
    const commands=(await route.request().postDataJSON()).commands;previewRequests.push(commands);
    if(["add_custom_property","delete_custom_property"].includes(commands[0]?.type))return route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:commands[0].type,after:commands[0]}],diagnostics:[],affected_files:["C:\\project\\test.dst"],execution_intent:null}});
    return route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"number_range_changed",before:"001-002",after:"001-004"}],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\003-004 新分册.dwg"],execution_intent:{cad_validation_deferred:true,cardinality_frontier:{index:2,subset_id:"subset-new"},subset_operations:[{subset_id:"subset-1",cad_operation:"none",target_file:"C:\\project\\001-002 第一册.dwg",in_cardinality_scope:false},{subset_id:"subset-2",cad_operation:"none",target_file:"C:\\project\\002-003 第二册.dwg",in_cardinality_scope:false},{subset_id:"subset-new",cad_operation:"rebuild",target_file:"C:\\project\\003-004 新分册.dwg",in_cardinality_scope:true}],derived_document:{subsets:[{acsm_id:"subset-new",number_range:"003-004",display_name:"003-004 新分册",title:"新分册",sheets:[]}]},groups:[
      {subset_id:"subset-new",operation:"create",cad_operation:"rebuild",subset_name:"003-004 新分册",target_file:"C:\\project\\003-004 新分册.dwg",layouts:[{number:"003",title:"新分册 (一)",target_layout:"003 新分册 (一)"},{number:"004",title:"新分册 (二)",target_layout:"004 新分册 (二)"}]},
    ]}}});
  });
  await openWorkspace(page);
  await page.route("**/api/layout-names",route=>route.fulfill({json:{layouts:["A1模板"],cached:false,file_hash:"x"}}));
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByLabel("属性作用域").selectOption("sheet");await page.getByLabel("属性名称").fill("专业");await page.getByLabel("默认值").fill("燃气");await page.getByRole("button",{name:"加入属性定义"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[0]).toEqual([{type:"add_custom_property",property_type:"sheet",name:"专业",default_value:"燃气"}]);
  await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"删除 比例"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();expect(previewRequests[1]).toEqual([{type:"delete_custom_property",property_type:"sheet",name:"比例"}]);
  // 任务 6 起新建子集表单选择参照子集而非手填序号：参照子集 2 + 之后 → ordinal 2
  await page.getByRole("button",{name:"新建子集"}).click();
  await page.getByLabel("参照子集").selectOption("subset-2");
  await page.getByLabel("子集方向").selectOption("after");
  await page.getByLabel("子集标题",{exact:true}).fill("新分册");
  await page.getByLabel("初始图纸数").fill("2");
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\base.dwt"});await page.getByRole("button",{name:"选择基础模板文件"}).click();
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\template.dwt"});await page.getByRole("button",{name:"选择布局模板文件"}).click();
  await page.getByLabel("布局模板名称").selectOption("A1模板");
  await page.getByRole("button",{name:"加入草稿"}).click();
  await expect(page.getByText("属性定义与结构变更必须分批预览和执行")).toBeVisible();
  // 提交失败保留输入：清空属性定义草稿后直接重新提交（不重新填写）
  await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);
  await page.getByRole("button",{name:"加入草稿"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[2]).toEqual([{type:"insert_subset",ordinal:2,placement:"after",title:"新分册",initial_sheet_count:2,base_template_file:"C:\\base.dwt",source:{type:"template_layout",file:"C:\\template.dwt",layout:"A1模板"}}]);expect(previewRequests[2][0]).not.toHaveProperty("number");
  await expect(page.getByText("图号范围变化")).toBeVisible();await expect(page.getByText("清除并重建布局").first()).toBeVisible();await expect(page.getByText("数量变化前沿：第 3 个子集")).toBeVisible();const subsetOperationTable=page.locator(".preview section").filter({has:page.getByRole("heading",{name:"子集 CAD 操作"})}).locator("table");await expect(subsetOperationTable.locator("tbody tr").filter({hasText:"subset-1"}).getByText("无需 CAD 操作",{exact:true})).toBeVisible();await expect(subsetOperationTable.locator("tbody tr").filter({hasText:"subset-2"}).getByText("无需 CAD 操作",{exact:true})).toBeVisible();await expect(subsetOperationTable.locator("tbody tr").filter({hasText:"subset-new"}).getByText("清除并重建布局",{exact:true})).toBeVisible();const affectedFiles=page.locator(".preview > section").filter({has:page.getByRole("heading",{name:"受影响文件"})});await expect(affectedFiles.getByText("C:\\project\\003-004 新分册.dwg",{exact:true})).toBeVisible();await expect(affectedFiles.getByText("C:\\project\\001-002 第一册.dwg",{exact:true})).toHaveCount(0);const derivedTable=page.locator(".preview table").filter({hasText:"服务端图号范围"});await expect(derivedTable.getByRole("cell",{name:"003-004",exact:true})).toBeVisible();await expect(derivedTable.getByRole("cell",{name:"003-004 新分册",exact:true})).toBeVisible();const createdGroup=page.locator(".execution-group").filter({hasText:"清除并重建布局"});await expect(createdGroup.getByText("C:\\project\\003-004 新分册.dwg",{exact:true})).toBeVisible();await expect(createdGroup.getByRole("cell",{name:"003 新分册 (一)",exact:true})).toBeVisible();
});

test("冻结CAD版本并展示服务端语义差异与来源证据",async({page})=>{
  const previewBodies:any[]=[];let executeBody:any=null;
  const semantic={
    structure:{before:[{position:1,id:"subset-1",title:"第一册",number_range:"001-002",display_name:"001-002 第一册",dwg_file:"C:\\project\\A.dwg",sheets:[{position:1,id:"sheet-1",number:"001",title:"第一册 (一)",suffix:"一",dwg_file:"C:\\project\\A.dwg",layout_name:"001 第一册 (一)"}]}],after:[{position:1,id:"subset-1",title:"第一册",number_range:"001-003",display_name:"001-003 第一册",dwg_file:"C:\\project\\A.dwg",sheets:[{position:1,id:"sheet-1",number:"001",title:"第一册 (一)",suffix:"一",dwg_file:"C:\\project\\A.dwg",layout_name:"001 第一册 (一)"}]}]},
    properties:[{action:"add",type:"sheet",name:"专业",before:null,after:{name:"专业",default_value:"燃气"},affected_sheet_count:2}],
    dwgs:[{action:"rebuild",subset_id:"subset-1",before:{file:"C:\\project\\A.dwg",layouts:["001 第一册 (一)"]},after:{file:"C:\\project\\A.dwg",layouts:["001 第一册 (一)","003 第一册 (三)"]}}],
  };
  const inspection={path:"C:\\project\\template.dwt",sha256:"abc123",cad_version:"2016",layouts:["A1模板"],requested_layouts:["A1模板"]};
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());await route.fulfill({json:{executable:true,requires_cad:true,preview_digest:"digest-2016",changes:[{type:"add_custom_property",affected_sheet_count:2}],diagnostics:[],affected_files:["C:\\project\\test.dst"],semantic_diff:semantic,execution_intent:{cad_validation_deferred:true,source_baselines:[{path:inspection.path,sha256:inspection.sha256,identity:["source-id"],source_types:["template_layout"],requested_layouts:inspection.requested_layouts}],derived_document:{subsets:[]},groups:[]}}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",async route=>{executeBody=await route.request().postDataJSON();await route.fulfill({json:{id:"job-version",status:"FAILED",progress:0,attempt:1,files:[]}})});
  await openWorkspace(page);await page.getByLabel("AutoCAD 版本").selectOption("2016");await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies[0].cad_version).toBe("2016");await expect(page.getByText("前后有序结构")).toBeVisible();await expect(page.getByRole("columnheader",{name:"受影响图纸"})).toBeVisible();await expect(page.getByText("DWG 与布局差异")).toBeVisible();await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("abc123",{exact:true})).toBeVisible();await expect(page.getByText("A1模板",{exact:true}).first()).toBeVisible();await expect(page.getByText("[object Object]",{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);expect(executeBody.cad_version).toBe("2016");expect(executeBody.preview_digest).toBe("digest-2016");
  await page.getByRole("button",{name:"预览变更"}).click();await expect(page.getByText("完整变更预览")).toBeVisible();await page.getByLabel("AutoCAD 版本").selectOption("2020");await expect(page.getByText("完整变更预览")).toHaveCount(0);
});

test("普通预览丢弃乱序响应并只执行冻结命令",async({page})=>{
  const gates=[deferred(),deferred(),deferred(),deferred()];const previewBodies:any[]=[];let executeBody:any=null;
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{const index=previewBodies.length;previewBodies.push(await route.request().postDataJSON());await gates[index].promise;await route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:`preview-${index+1}`}],diagnostics:[],affected_files:[`preview-${index+1}.dst`],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",async route=>{executeBody=await route.request().postDataJSON();await route.fulfill({json:{id:"job-race",status:"FAILED",progress:0,attempt:1,files:[]}})});
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(2);
  gates[1].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();gates[0].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();await expect(page.getByText("preview-1",{exact:true})).toHaveCount(0);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(3);await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);gates[2].resolve();await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(4);gates[3].resolve();await expect(page.getByText("preview-4",{exact:true})).toBeVisible();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect.poll(()=>executeBody).not.toBeNull();expect(executeBody.base_revision_id).toBe(previewBodies[3].base_revision_id);expect(executeBody.commands).toEqual(previewBodies[3].commands);expect(executeBody.commands).not.toBe(previewBodies[3].commands);
});

test("CSV 预览丢弃换文件和乱序响应并只导入冻结文本",async({page})=>{
  const gates=[deferred(),deferred(),deferred()];const previewBodies:any[]=[];let importBody:any=null;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{const index=previewBodies.length;const body=await route.request().postDataJSON();previewBodies.push(body);const name=body.csv.match(/sheet,([^,]+)/)?.[1]??`属性${index}`;await gates[index].promise;await route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name,default_value:""}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/custom-properties/import",async route=>{importBody=await route.request().postDataJSON();await route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}})});
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();const csvInput=page.getByLabel("属性 CSV 文件");const csv=(name:string)=>({name:`${name}.csv`,mimeType:"text/csv",buffer:Buffer.from(`type,name,default_value\nsheet,${name},\n`,"utf8")});
  await csvInput.setInputFiles(csv("A属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await csvInput.setInputFiles(csv("B属性"));gates[0].resolve();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();await expect(page.locator(".csv-preview").getByText("A属性")).toHaveCount(0);
  await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(2);await csvInput.setInputFiles(csv("C属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(3);gates[2].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();gates[1].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();await expect(page.locator(".csv-preview").getByText("B属性")).toHaveCount(0);
  await page.getByRole("button",{name:"确认导入"}).click();await confirmModal(page,/确认导入/);await expect.poll(()=>importBody).not.toBeNull();expect(importBody).toEqual(previewBodies[2]);
});

test("非法 UTF-8 CSV 在本地阻断且不请求 API",async({page})=>{
  let previewCalls=0,importCalls=0;await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>{previewCalls++;return route.abort()});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>{importCalls++;return route.abort()});await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();
  await page.getByLabel("属性 CSV 文件").setInputFiles({name:"invalid.csv",mimeType:"text/csv",buffer:Buffer.from([0x74,0x79,0x70,0x65,0x0a,0xc3,0x28])});await expect(page.getByText("CSV 必须使用 UTF-8 编码",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"预览 CSV 导入"})).toBeDisabled();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();expect(previewCalls).toBe(0);expect(importCalls).toBe(0);
});

test("CSV 导入确认模态为强确认：未勾选时确认按钮禁用",async({page})=>{
  // SPEC-DM-006 §6.2/§10.3：CSV 不得走弱确认旁路，与 §9.1 全部正式写入共用同一危险确认（danger+requireCheckbox+impactLines）
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"比例",default_value:"1:100",affected_sheet_count:2},{line:3,action:"skip",type:"sheet",name:"专业",default_value:"建筑",affected_sheet_count:0}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByLabel("属性 CSV 文件").setInputFiles({name:"props.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,比例,1:100\nsheet,专业,建筑\n","utf8")});
  await page.getByRole("button",{name:"预览 CSV 导入"}).click();
  await expect(page.getByRole("button",{name:"确认导入"})).toBeEnabled();
  await page.getByRole("button",{name:"确认导入"}).click();
  const modal=page.getByRole("dialog");
  await expect(modal).toBeVisible();
  // 强确认要素：不可逆徽标 + 受影响定义清单 + 未勾选确认按钮禁用
  await expect(modal.getByText("不可逆",{exact:true})).toBeVisible();
  await expect(modal.getByText(/新增属性「比例」/)).toBeVisible();
  await expect(modal.getByText(/跳过属性「专业」/)).toBeVisible();
  await expect(modal.getByRole("button",{name:/确认导入/})).toBeDisabled();
  await modal.getByRole("checkbox").check();
  await expect(modal.getByRole("button",{name:/确认导入/})).toBeEnabled();
  await modal.getByRole("button",{name:/确认导入/}).click();
  await expect(modal).toHaveCount(0);
});

test("加载新工作区时隐藏旧编辑器并阻断跨工作区执行",async({page})=>{
  const openB=deferred();let openCalls=0,executeCalls=0,importCalls=0;
  await page.route("**/api/workspaces/open",async route=>{openCalls++;if(openCalls===1)return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"A-preview"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"A属性",default_value:""}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/changes/execute",route=>{executeCalls++;return route.fulfill({json:{id:"stale-execute",status:"FAILED",progress:0,files:[]}})});await page.route("**/api/workspaces/workspace-A/custom-properties/import",route=>{importCalls++;return route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.locator(".summary input")).toHaveValue("工作区 A");
  await page.getByRole("button",{name:"关闭"}).click();
  const switching=selectDst(page,"C:\\B.dst");
  await expect.poll(()=>openCalls).toBe(2);
  const loadingWasVisible=await page.getByText("正在加载工作区…",{exact:true}).isVisible();
  // 任务 3 起旧编辑器区改名为左树右表工作区容器
  const editorWasVisible=await page.locator(".sheets-workspace").isVisible();
  openB.resolve();await switching;await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 B");
  await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  expect(loadingWasVisible).toBe(true);expect(editorWasVisible).toBe(false);expect(executeCalls).toBe(0);expect(importCalls).toBe(0);
});

test("多次打开及刷新与打开竞争时仅最新工作区生效",async({page})=>{
  const openA=deferred(),openB=deferred(),openC=deferred(),refreshC=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst")){await openA.promise;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")})}if(path.endsWith("B.dst")){await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})}if(path.endsWith("C.dst")){await openC.promise;return route.fulfill({json:workspaceVersion("workspace-C","工作区 C","revision-C")})}return route.fulfill({json:workspaceVersion("workspace-D","工作区 D","revision-D")})});
  await page.route("**/api/workspaces/workspace-C/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"C-preview"}],diagnostics:[],affected_files:["C.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-C/changes/execute",route=>route.fulfill({json:{id:"job-C",status:"SUCCEEDED",progress:100,files:[]}}));await page.route("**/api/workspaces/workspace-C",async route=>{refreshStarted=true;await refreshC.promise;await route.fulfill({json:workspaceVersion("workspace-C","工作区 C 刷新","revision-C2")})});
  await page.goto("/");
  await selectDst(page,"C:\\A.dst");await selectDst(page,"C:\\B.dst");await selectDst(page,"C:\\C.dst");
  openC.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 C");openB.resolve();openA.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 C");
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect.poll(()=>refreshStarted).toBe(true);
  // 执行成功已 discardDraft，此处关闭无未发布改动，不弹确认模态
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\D.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 D");refreshC.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 D");
});

test("切换工作区会关闭旧任务监控且忽略迟到终态",async({page})=>{
  await installMockEventSource(page);const openB=deferred();let refreshACalls=0,openBStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst"))return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});openBStarted=true;await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"A-command"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-A/changes/execute",route=>route.fulfill({json:{id:"job-A",workspace_id:"workspace-A",status:"QUEUED",progress:0,attempt:0,files:[]}}));await page.route("**/api/workspaces/workspace-A",route=>{refreshACalls++;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A 被旧任务刷新","revision-A2")})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect(page.getByText("任务 job-A")).toBeVisible();
  // 任务仍在排队，草稿命令未发布成功：关闭会弹确认模态
  await page.getByRole("button",{name:"关闭"}).click();await confirmModal(page,/确定关闭并放弃当前改动/);
  const switching=selectDst(page,"C:\\B.dst");await expect.poll(()=>openBStarted).toBe(true);await page.evaluate(()=>(window as any).__emitJob({id:"job-A",workspace_id:"workspace-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}));openB.resolve();await switching;await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);
  expect(refreshACalls).toBe(0);await expect(page.getByText("任务 job-A")).toHaveCount(0);expect(await page.evaluate(()=>(window as any).__closedEventSources())).toBe(1);
});

test("关闭工作区后停留在未打开态时任务与修订面板不残留",async({page})=>{
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-close",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-close-1234567890",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  await expect(page.getByText("任务 job-close")).toBeVisible();
  await page.getByRole("tab",{name:"修订历史"}).click();
  await expect(page.getByRole("heading",{name:"永久修订"})).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();await confirmModal(page,/确定关闭并放弃当前改动/);
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.getByText("任务 job-close")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"永久修订"})).toHaveCount(0);
  await expect(page.getByText("revision-close")).toHaveCount(0);
  expect(await page.evaluate(()=>(window as any).__closedEventSources())).toBe(1);
});

test("工作区切换会丢弃迟到的修订列表和恢复预览",async({page})=>{
  const revisionList=deferred(),restorePreviewGate=deferred();let revisionCalls=0,restoreCalls=0;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.endsWith("A.dst")?workspaceVersion("workspace-A","工作区 A","revision-A"):workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/revisions?workspace_id=workspace-A",async route=>{revisionCalls++;if(revisionCalls===1)await revisionList.promise;return route.fulfill({json:[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",async route=>{await restorePreviewGate.promise;return route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}})});await page.route("**/api/workspaces/**/revisions/revision-A-old/restore",route=>{restoreCalls++;return route.fulfill({json:{id:"wrong-restore",status:"SUCCEEDED",progress:100,files:[]}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"修订历史"}).click();await expect.poll(()=>revisionCalls).toBe(1);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\B.dst");revisionList.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);await expect(page.getByText("revision-A-old")).toHaveCount(0);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\A.dst");await page.getByRole("tab",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\B.dst");restorePreviewGate.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);const restoreButton=page.getByRole("button",{name:"恢复为新修订"});if(await restoreButton.isVisible()){await restoreButton.click()}expect(restoreCalls).toBe(0);await expect(page.getByText("恢复确认")).toHaveCount(0);
});

test("恢复写入期间阻断冲突入口并在成功后刷新工作区与修订",async({page})=>{
  const restorePost=deferred();let openCalls=0,revisionCalls=0,previewCalls=0,restoreCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",async route=>{openCalls++;const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.endsWith("B.dst")?workspaceVersion("workspace-B","工作区 B","revision-B"):workspaceVersion("workspace-A","工作区 A","revision-A")})});await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:revisionCalls===1?[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]:[{id:"revision-A-new",created_at:"2026-08-13T00:00:00Z",before_hash:"bbbbbbbb",result_hash:"cccccccc"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>{previewCalls++;return route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreCalls++;restoreStarted=true;await restorePost.promise;return route.fulfill({json:{id:"restore-job-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}})});await page.route("**/api/workspaces/workspace-A",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A 已恢复","revision-A2")}));
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await expect.poll(()=>restoreStarted).toBe(true);
  const restoringWasVisible=await page.getByText("正在恢复修订…",{exact:true}).isVisible();const closeWasDisabled=await page.getByRole("button",{name:"关闭"}).isDisabled();const historyWasDisabled=await page.getByRole("tab",{name:"修订历史"}).isDisabled();const previewButton=page.getByRole("button",{name:"恢复预览"});const previewWasDisabled=await previewButton.isDisabled();const confirmWasDisabled=await page.getByRole("button",{name:"恢复为新修订"}).isDisabled();if(!historyWasDisabled)await page.getByRole("tab",{name:"修订历史"}).click();if(!previewWasDisabled)await previewButton.click();
  restorePost.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("工作区 A 已恢复");await page.getByRole("tab",{name:"修订历史"}).click();await expect(page.getByText("revision-A-new")).toBeVisible();
  // 恢复任务详情迁入任务浮层实施进度页签：刷新复位后先展开浮层
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("button",{name:"展开任务浮层"}).click();await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("任务 restore-job-A")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);
  expect(restoringWasVisible).toBe(true);expect(closeWasDisabled).toBe(true);expect(historyWasDisabled).toBe(true);expect(previewWasDisabled).toBe(true);expect(confirmWasDisabled).toBe(true);expect(openCalls).toBe(1);expect(revisionCalls).toBe(3);expect(previewCalls).toBe(1);expect(restoreCalls).toBe(1); // 3 次 = 首次切标签① + 恢复成功后自动刷新 + 断言后切回标签③（沿用旧按钮每次点击即加载语义）
});

test("恢复写入错误会显示消息并解除入口锁定",async({page})=>{
  const restorePost=deferred();let revisionCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")}));await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreStarted=true;await restorePost.promise;return route.fulfill({status:500,json:{message:"恢复失败"}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await expect.poll(()=>restoreStarted).toBe(true);await expect(page.getByText("正在恢复修订…",{exact:true})).toBeVisible();restorePost.resolve();await expect(page.getByText("恢复失败")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭"})).toBeEnabled();await expect(page.getByRole("tab",{name:"修订历史"})).toBeEnabled();await page.getByRole("tab",{name:"修订历史"}).click();expect(revisionCalls).toBe(2);await page.getByRole("tab",{name:"图纸"}).click();await expect(page.locator(".sheets-workspace")).toBeVisible();
});

test("旧编辑入口已移除且图号标题只读",async({page})=>{
  await openWorkspace(page);await expect(page.getByRole("button",{name:"子集↑"})).toHaveCount(0);await expect(page.getByRole("button",{name:"子集↓"})).toHaveCount(0);await expect(page.getByText("移动到",{exact:true})).toHaveCount(0);
  // 任务 3/4 起唯一主表图号/标题为只读文本（列：选择/图号/标题/子集/文件名/布局/状态/操作）
  const sheetRow=page.locator(".sheet-table-window tbody tr").filter({has:page.getByText("001",{exact:true})});await expect(sheetRow.locator("td").nth(1).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(2).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(1)).toHaveText("001");await expect(sheetRow.locator("td").nth(2)).toHaveText("第一册 (一)");
});

test("批量新增图纸校验位置数量和布局来源",async({page})=>{
  let previewCommands:any[]=[];await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{const body=await route.request().postDataJSON();previewCommands=body.commands;await route.fulfill({json:buildPreviewFromBase(workspace,body.commands)})});await page.route("**/api/layout-names",route=>route.fulfill({json:{layouts:["A1","A2"],cached:false,file_hash:"x"}}));await openWorkspace(page);
  // 任务 6 起新增图纸表单选择参照对象而非手填序号：先点「新增图纸」入口展开
  await page.getByRole("button",{name:"新增图纸"}).click();
  // 未选参照图纸直接提交 → 提示选择参照
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByRole("button",{name:"加入草稿"}).click();await expect(page.getByRole("alert")).toHaveText("请选择参照图纸");expect(previewCommands).toHaveLength(0);
  // 数量非法
  await page.getByLabel("参照图纸").selectOption("sheet-2");await page.getByLabel("新增图纸数量").fill("0");await page.getByRole("button",{name:"加入草稿"}).click();await expect(page.getByText("新增图纸数量必须为正整数")).toBeVisible();expect(previewCommands).toHaveLength(0);
  // 模板来源必填文件与布局
  await page.getByLabel("新增图纸数量").fill("2");await page.getByLabel("图纸方向").selectOption("before");await page.getByRole("button",{name:"加入草稿"}).click();await expect(page.getByText("布局模板文件和布局模板名称不能为空")).toBeVisible();
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\source.dwg"});await page.getByRole("button",{name:"选择模板文件"}).click();await page.getByRole("combobox",{name:/布局模板名称/}).selectOption("A1");await page.getByRole("button",{name:"加入草稿"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewCommands).toEqual([{type:"insert_sheet",target_subset_id:"subset-1",ordinal:2,placement:"before",count:2,source:{type:"template_layout",file:"C:\\source.dwg",layout:"A1"}}]);expect(previewCommands[0]).not.toHaveProperty("number");expect(previewCommands[0]).not.toHaveProperty("title");
});

test("选择来源文件后加载布局下拉",async({page})=>{
  await page.route("**/api/layout-names",(route)=>route.fulfill({json:{layouts:["A-01","A-02"],cached:false,file_hash:"abc"}}));
  await openWorkspace(page);
  await page.getByRole("button",{name:"新增图纸"}).click();
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/tpl/frame.dwg"});
  await page.getByRole("button",{name:"选择模板文件"}).click();
  await expect(page.getByRole("combobox",{name:/布局模板名称/})).toBeEnabled();
  await expect(page.getByRole("combobox",{name:/布局模板名称/})).toContainText("A-01");
});

test("布局读取失败回退手动输入",async({page})=>{
  await page.route("**/api/layout-names",(route)=>route.fulfill({status:502,json:{code:"LAYOUT_READ_FAILED",message:"读取布局失败"}}));
  await openWorkspace(page);
  await page.getByRole("button",{name:"新增图纸"}).click();
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/tpl/frame.dwg"});
  await page.getByRole("button",{name:"选择模板文件"}).click();
  await expect(page.getByText("读取布局失败")).toBeVisible();
  // 作用域限定在新增图纸表单：仅该表单渲染时布局模板名称文本框出现
  await expect(page.getByRole("region",{name:"新增图纸"}).getByRole("textbox",{name:/布局模板名称/})).toBeVisible();
});

test("空图纸集新建首个子集沿用序号一契约且必须提供模板",async({page})=>{
  const empty={...workspace,sheet_set:{...workspace.sheet_set,sheet_count:0,subset_count:0,subsets:[]}};let previewCalls=0;await page.route("**/api/workspaces/open",route=>route.fulfill({json:empty}));await page.route("**/api/workspaces/workspace-1/changes/preview",route=>{previewCalls++;return route.fulfill({json:{executable:true,changes:[],diagnostics:[]}})});await openWorkspace(page);
  // 空集显示「创建首个子集」入口；新建子集表单无序号输入（沿用首个序号为 1 的契约）
  await page.getByRole("button",{name:"创建首个子集"}).click();
  await expect(page.getByRole("region",{name:"新建子集"})).toBeVisible();
  await expect(page.getByLabel("子集序号")).toHaveCount(0);
  await expect(page.getByLabel("参照子集")).toHaveCount(0);
  await page.getByLabel("子集标题",{exact:true}).fill("首册");
  await page.getByLabel("初始图纸数").fill("1");
  await page.getByRole("button",{name:"加入草稿"}).click();
  await expect(page.getByText("基础模板文件不能为空")).toBeVisible();
  expect(previewCalls).toBe(0);
});

test("已有布局来源隐藏模板输入并以空来源提交",async({page})=>{
  let previewCommands:any[]=[];await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{const body=await route.request().postDataJSON();previewCommands=body.commands;await route.fulfill({json:buildPreviewFromBase(workspace,body.commands)})});await openWorkspace(page);
  await page.getByRole("button",{name:"新增图纸"}).click();
  const insertForm=page.getByRole("region",{name:"新增图纸"});
  await page.getByLabel("目标子集").selectOption("subset-1");
  await page.getByLabel("参照图纸").selectOption("sheet-1");
  await page.getByLabel("模板来源").selectOption("existing_snapshot");
  await expect(insertForm.getByRole("button",{name:"选择模板文件"})).toHaveCount(0);
  await expect(page.getByText("来源为目标子集 DWG 的第一个非 Model 布局")).toBeVisible();
  await page.getByRole("button",{name:"加入草稿"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewCommands).toEqual([{type:"insert_sheet",target_subset_id:"subset-1",ordinal:1,placement:"after",count:1,source:{type:"existing_snapshot",file:"",layout:""}}]);
});

test("关闭工作区重置模板表单状态且布局读取跟随 CAD 版本",async({page})=>{
  const layoutBodies:any[]=[];
  await page.route("**/api/layout-names",async route=>{layoutBodies.push(await route.request().postDataJSON());await route.fulfill({json:{layouts:["A1"],cached:false,file_hash:"x"}})});
  await openWorkspace(page);
  // 任务 6 起操作表单共用唯一编辑上下文：先开新增图纸，切换新建子集经三选一（放弃输入）
  await page.getByRole("button",{name:"新增图纸"}).click();
  const insertForm=page.getByRole("region",{name:"新增图纸"});
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\source.dwg"});await page.getByRole("button",{name:"选择模板文件"}).click();
  await page.getByRole("button",{name:"新建子集"}).click();
  await page.getByRole("dialog",{name:"未提交输入"}).getByRole("button",{name:"放弃输入"}).click();
  const subsetForm=page.getByRole("region",{name:"新建子集"});
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\base.dwt"});await page.getByRole("button",{name:"选择基础模板文件"}).click();
  // 新建子集布局模板文件与添加图纸对齐：按钮选文件 → 读取布局 → 下拉选择
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\template.dwt"});await subsetForm.getByRole("button",{name:"选择布局模板文件"}).click();
  await expect(subsetForm.getByRole("combobox",{name:/布局模板名称/})).toContainText("A1");
  // 关闭工作区：有未提交表单输入先三选一（放弃输入），无草稿动作直接关闭
  await page.getByRole("button",{name:"关闭"}).click();
  await page.getByRole("dialog",{name:"未提交输入"}).getByRole("button",{name:"放弃输入"}).click();
  await selectDst(page,"C:\\project\\test.dst");
  // M6：重开工作区后表单模板状态已清空（重开表单后断言才有意义）
  await page.getByRole("button",{name:"新建子集"}).click();
  await expect(subsetForm.getByText("C:\\template.dwt")).toHaveCount(0);
  await expect(subsetForm.getByRole("combobox",{name:/布局模板名称/})).toHaveCount(0);
  await page.getByRole("button",{name:"新增图纸"}).click();
  await expect(insertForm.getByText("C:\\source.dwg")).toHaveCount(0);
  // M4：布局读取 cad_version 跟随所选 AutoCAD 版本而非硬编码 "2020"
  await page.getByLabel("AutoCAD 版本").selectOption("2016");
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\source2.dwg"});await page.getByRole("button",{name:"选择模板文件"}).click();
  expect(layoutBodies.at(-1).cad_version).toBe("2016");
});

test("属性命令与结构命令分批并支持 CSV 行级预览导入",async({page})=>{
  let importedCsv="";await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{importedCsv=(await route.request().postDataJSON()).csv;await route.fulfill({json:{executable:false,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[{line:3,severity:"error",code:"CUSTOM_PROPERTY_NAME_EMPTY",message:"名称不能为空"}],affected_files:["test.dst"],execution_intent:null}})});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:"csv-job",status:"SUCCEEDED",progress:100,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.getByRole("link",{name:"下载 CSV 模板"})).toHaveAttribute("href","/api/custom-properties/template");await expect(page.getByRole("link",{name:"导出当前属性"})).toHaveAttribute("href","/api/workspaces/workspace-1/custom-properties/export");await page.getByLabel("属性 CSV 文件").setInputFiles({name:"properties.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,专业,燃气\nsheet,,\n","utf8")});await page.getByRole("button",{name:"预览 CSV 导入"}).click();expect(importedCsv).toContain("sheet,专业,燃气");await expect(page.getByText("第 3 行")).toBeVisible();await expect(page.getByText("CUSTOM_PROPERTY_NAME_EMPTY")).toBeVisible();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  await page.unroute("**/api/workspaces/workspace-1/custom-properties/import/preview");await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await page.getByRole("button",{name:"确认导入"}).click();await confirmModal(page,/确认导入/);
  // CSV 导入任务迁入任务浮层实施进度页签：刷新复位后先展开浮层
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("button",{name:"展开任务浮层"}).click();await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("任务 csv-job")).toBeVisible();
});

test("失败任务显示逐 DWG 详情并可安全重试",async({page})=>{
  await installMockEventSource(page);await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,duration_ms:600000,error_code:"CAD_TIMEOUT"}]}}));await page.route("**/api/jobs/job-failed/retry",route=>route.fulfill({json:{id:"job-failed",status:"QUEUED",progress:0,attempt:1,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // 失败任务详情迁入任务浮层实施进度页签：预览已展开浮层，切到实施进度页签再断言逐 DWG 详情
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();await expect(page.getByText("A.dwg")).toBeVisible();await expect(page.getByText("检查 CAD 日志")).toBeVisible();await page.getByRole("button",{name:"安全重试"}).click();await expect(page.getByText(/QUEUED/)).toBeVisible();
});

test("修订恢复先预览再确认为新修订",async({page})=>{
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-1",status:"SUCCEEDED",progress:100,attempt:0,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();await expect(page.getByText("replace test.dst")).toBeVisible();await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await page.getByRole("tab",{name:"属性"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");
});

test("恢复直返终态 FAILED 时任务浮层自动展开到实施进度页签",async({page})=>{
  // fix round 1 回归：后端 restore 为同步发布可直返终态 FAILED（不设 error），任务详情不得再藏进折叠浮层——setJob 收到任何状态均展开浮层到实施进度页签
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-failed",status:"FAILED",progress:40,attempt:1,error_code:"RESTORE_FAILED",suggestion:"检查原文件",files:[{target_path:"test.dst",status:"FAILED",progress:0,error_code:"RESTORE_FAILED"}]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"修订历史"}).click();
  await page.getByRole("button",{name:"恢复预览"}).click();
  await expect(page.getByText("replace test.dst")).toBeVisible();
  await page.getByRole("button",{name:"恢复为新修订"}).click();
  await confirmModal(page,/确认恢复/);
  // 终态 FAILED 响应：浮层可见且实施进度页签激活，任务详情不再静默
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole("tab",{name:"实施进度"})).toHaveAttribute("aria-selected","true");
  await expect(page.getByText("任务 restore-failed")).toBeVisible();
  await expect(page.getByText("RESTORE_FAILED").first()).toBeVisible();
});

test("修复状态展示、写入门禁与确认发布流程",async({page})=>{
  const repaired:any=workspaceVersion("workspace-1","测试图纸集","revision-1");
  repaired.dst_validation={status:"REPAIRED",actions:[{code:"REPAIR_ATTR_MISSING",node_path:"/AcSmDatabase/AcSmSheetSet[@ID=\"x\"]/AcSmSheet",object_id:null,confidence:"deterministic",before:{clsid:null},after:{clsid:"g16A07941-BC15-4D48-A880-9D5A211D5065"},message:"补齐 AcSmSheet 的 clsid"}],blocking_issues:[]};
  const valid:any=workspaceVersion("workspace-1","测试图纸集","revision-2");
  valid.dst_validation={status:"VALID",actions:[],blocking_issues:[]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:repaired}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:valid}));
  await page.route("**/api/workspaces/workspace-1/repairs/preview",route=>route.fulfill({json:{status:"REPAIRED",actions:repaired.dst_validation.actions,blocking_issues:[],preview_digest:"digest-1234567890abcdef",executable:true}}));
  await page.route("**/api/workspaces/workspace-1/repairs/execute",route=>route.fulfill({json:{id:"repair-job",status:"SUCCEEDED",progress:100,files:[]}}));
  await openWorkspace(page);
  // 修复门禁迁入任务浮层诊断页签：先展开浮层并切到诊断
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await overlay.getByRole("button",{name:"展开任务浮层"}).click();
  await overlay.getByRole("tab",{name:"诊断"}).click();
  await expect(page.getByText("DST 修复状态：已修复（待确认）")).toBeVisible();
  await page.getByText("修复明细（1）").click();
  await expect(page.getByText("REPAIR_ATTR_MISSING")).toBeVisible();
  // 确认前普通编辑发布被禁用
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();
  await page.getByRole("button",{name:"预览并确认修复"}).click();
  await expect(page.getByText(/修复 1 项 · 摘要 digest-12345678/)).toBeVisible();
  await page.getByRole("button",{name:"确认发布修复修订"}).click();
  await confirmModal(page,/确认把内存修复发布/);
  // 修复直接返回 SUCCEEDED 且刷新后浮层复位（overlayOpen=false）：重新展开到实施进度页签查看任务
  await overlay.getByRole("button",{name:"展开任务浮层"}).click();
  await overlay.getByRole("tab",{name:"实施进度"}).click();
  await expect(page.getByText("任务 repair-job")).toBeVisible();
  // 修复成功后刷新为 VALID，修复面板消失且普通编辑恢复
  await expect(page.getByText("已修复（待确认）")).toHaveCount(0);
  await expect(page.getByText("DST 修复状态")).toHaveCount(0);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeEnabled();
});

test("发布确认模态必须显式勾选后才可提交",async({page})=>{
  // 前置 mock 构造预览有效态（跟随既有发布流程用例）
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-gate",status:"FAILED",progress:0,attempt:1,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  // Task 5：全局操作栏"确认写入"为唯一写入门禁出口，触发同一发布模态
  await page.getByRole("button",{name:"确认写入"}).click();
  const modal=page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.getByText("不可逆",{exact:true})).toBeVisible();
  await expect(modal.getByRole("button",{name:/确认发布/})).toBeDisabled();
  await modal.getByRole("checkbox").check();
  await expect(modal.getByRole("button",{name:/确认发布/})).toBeEnabled();
  await modal.getByRole("button",{name:/确认发布/}).click();
  await expect(modal).toHaveCount(0);
});

test("取消高门槛模态后低风险模态不残留勾选与不可逆徽标",async({page})=>{
  // 回归：useConfirm 共享 reactive 状态跨次泄漏——先触发 requireCheckbox+impactLines 模态并取消，
  // 再触发低风险模态，断言干净状态（无复选框、无"不可逆"徽标、无上次受影响文件清单、确认按钮不被门禁）
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["leak-test.dst"],execution_intent:null}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  // 先打开发布模态（requireCheckbox + impactLines + 不可逆）并取消
  await page.getByRole("button",{name:"确认写入"}).click();
  const gated=page.getByRole("dialog");
  await expect(gated.getByText("不可逆",{exact:true})).toBeVisible();
  await gated.getByRole("button",{name:"取消"}).click();
  await expect(gated).toHaveCount(0);
  // 再触发单张图纸删除（低风险：danger:false、无勾选）
  await page.locator(".sheet-table-window tbody tr").filter({has:page.getByText("001",{exact:true})}).getByRole("button",{name:"删除"}).click();
  const lowRisk=page.getByRole("dialog");
  await expect(lowRisk).toBeVisible();
  await expect(lowRisk.getByRole("checkbox")).toHaveCount(0);
  await expect(lowRisk.getByText("不可逆",{exact:true})).toHaveCount(0);
  await expect(lowRisk.locator(".modal-impact")).toHaveCount(0);
  await expect(lowRisk.getByRole("button",{name:/确认删除/})).toBeEnabled();
});

test("未打开态只有文件选择区，不显示修订历史",async({page})=>{
  await page.goto("/");
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.getByRole("tab",{name:"修订历史"})).toHaveCount(0);
  await expect(page.getByRole("button",{name:"打开项目"})).toHaveCount(0);
});

test("选择非 .dst 文件给出提示且不发起打开",async({page})=>{
  let opened=false;
  await page.route("**/api/workspaces/open",route=>{opened=true;return route.fulfill({json:{}})});
  await page.goto("/");
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/x/proj.txt"});
  await page.getByRole("button",{name:"选择 DST 文件"}).click();
  await expect(page.getByText("仅支持 DST 文件")).toBeVisible();
  expect(opened).toBeFalsy();
});

test("打开时恢复非空草稿显示恢复提示",async({page})=>{
  await page.route("**/api/workspaces/workspace-1/draft",async route=>{
    if(route.request().method()==="GET")return route.fulfill({json:{draft:{schema_version:1,workspace_id:"workspace-1",base_revision_id:"revision-1",repair_status:"VALID",version:3,cursor:1,actions:[{id:"recovered-action",kind:"command_batch",label:"图纸集名称",commands:[{type:"update_sheet_set",name:"新名称",custom_properties:{项目号:"P-001"}}]}]},corrupted:false,stale:false,stale_reasons:[]}});
    return route.fallback();
  });
  await openWorkspace(page);
  await expect(page.getByText(/已恢复上次未完成的改动/)).toBeVisible();
  await page.getByRole("button",{name:"清空重来"}).click();
  await expect(page.getByText(/已恢复上次未完成的改动/)).toHaveCount(0);
});

test("草稿保存失败时显示保存失败与重试入口",async({page})=>{
  await page.route("**/api/workspaces/workspace-1/draft",async route=>{
    if(route.request().method()==="PUT")return route.fulfill({status:409,json:{code:"DRAFT_CONFLICT",message:"冲突"}});
    return route.fallback();
  });
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await openDraftPop(page);
  await expect(page.getByText("保存失败")).toBeVisible();
  await expect(page.getByRole("button",{name:"重试"})).toBeVisible();
});

test("关闭且有未发布改动时弹确认，放弃后回未打开态",async({page})=>{
  await page.route("**/api/workspaces/workspace-1/draft",async route=>{
    const method=route.request().method();
    if(method==="GET")return route.fulfill({json:{draft:{schema_version:1,workspace_id:"workspace-1",base_revision_id:"revision-1",repair_status:"VALID",version:1,cursor:1,actions:[{id:"pending-action",kind:"command_batch",label:"图纸集名称",commands:[{type:"update_sheet_set",name:"新名称",custom_properties:{项目号:"P-001"}}]}]},corrupted:false,stale:false,stale_reasons:[]}});
    if(method==="DELETE")return route.fulfill({json:{deleted:true}});
    return route.fallback();
  });
  await openWorkspace(page);
  await page.getByRole("button",{name:"关闭"}).click();
  await confirmModal(page,/确定关闭并放弃当前改动/);
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
});

test("关闭后迟到的刷新响应不会复活工作区",async({page})=>{
  const refreshGate=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")}));
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"A-preview"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/changes/execute",route=>route.fulfill({json:{id:"job-refresh",status:"SUCCEEDED",progress:100,files:[]}}));
  await page.route("**/api/workspaces/workspace-A",async route=>{refreshStarted=true;await refreshGate.promise;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A 已刷新","revision-A2")})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  await expect.poll(()=>refreshStarted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  refreshGate.resolve();await page.waitForTimeout(100);
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.locator(".summary input")).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭工作区"})).toHaveCount(0);
});

test("壳桥延迟注入（pywebviewready）时初始界面切换为文件选择区",async({page})=>{
  await page.goto("/?late-bridge");
  // 注入前：无壳降级态（浏览器场景）
  await expect(page.getByRole("button",{name:"打开项目"})).toBeVisible();
  // load 后 30ms 注入桥并派发 pywebviewready：界面应切换，而非永远停留在降级态
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible({timeout:5000});
  await expect(page.getByRole("button",{name:"打开项目"})).toHaveCount(0);
});

test("主题切换写 html data-theme 并持久化",async({page})=>{
  // 仅首次导航播种浅色初始态；reload 时 addInitScript 会重跑，若无条件覆盖会把已持久化的 dark 冲回 light
  await page.addInitScript(()=>{if(!localStorage.getItem("dst-manager-theme"))localStorage.setItem("dst-manager-theme","light")});
  await page.goto("/");
  await page.getByRole("button",{name:"切换主题"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
});

test("深色模式下中心视图区域随主题切换背景",async({page})=>{
  // 回归：旧单页样式块硬编码 background:white，中心区域不随 data-theme 切换
  await page.addInitScript(()=>{localStorage.setItem("dst-manager-theme","dark")});
  await openWorkspace(page);
  const panelBg=await page.locator(".sheets-workspace").evaluate(el=>getComputedStyle(el).backgroundColor);
  expect(panelBg).toBe("rgb(23, 30, 41)"); // --color-bg-surface 深色值 #171E29
});

test("深色模式下文本输入框与下拉选单随主题切换背景",async({page})=>{
  // 回归：旧样式块只设 input/select 的 padding/border，背景落到 UA 默认白底且未声明 color-scheme
  await page.addInitScript(()=>{localStorage.setItem("dst-manager-theme","dark")});
  await openWorkspace(page);
  // 任务 3 起低频筛选经「筛选」展开后才渲染下拉选单
  await page.getByRole("button",{name:"筛选"}).click();
  for(const locator of [page.locator(".sheets-toolbar input").first(),page.locator(".sheets-toolbar select").first()]){
    const bg=await locator.evaluate(el=>getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(23, 30, 41)"); // --color-bg-surface 深色值 #171E29
  }
});

// —— Task 4 外壳骨架（SPEC-DM-006 §4.1/§4.2/§7.2）——

test("打开工作区后显示三个固定标签且默认激活图纸标签",async({page})=>{
  await openWorkspace(page);
  const tabs=page.getByRole("tablist",{name:"功能分区"}).getByRole("tab");
  await expect(tabs).toHaveCount(3);
  await expect(tabs.filter({hasText:"图纸"})).toHaveAttribute("aria-selected","true");
  await tabs.filter({hasText:"属性"}).click();
  await expect(page.getByRole("tabpanel",{name:/属性/})).toBeVisible();
  await expect(page.getByRole("tabpanel",{name:/图纸/})).toHaveCount(0); // 未激活面板不渲染
  await tabs.filter({hasText:"修订历史"}).click();
  await expect(page.getByRole("tabpanel",{name:/修订历史/})).toBeVisible();
});

test("标签栏支持方向键切换",async({page})=>{
  await openWorkspace(page);
  await page.getByRole("tab",{name:/图纸/}).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab",{name:/属性/})).toHaveAttribute("aria-selected","true");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab",{name:/图纸/})).toHaveAttribute("aria-selected","true");
});

test("关闭按钮位于顶栏且确认后回未打开态",async({page})=>{
  await openWorkspace(page);
  // 无未发布改动时关闭直接回未打开态；此处先制造未发布改动以走勾选确认路径（与既有 closeWorkspace 契约一致）
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"关闭工作区"}).click();
  const modal=page.getByRole("dialog");
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button",{name:/确定关闭并放弃当前改动/}).click();
  await expect(page.getByText("打开图纸集")).toBeVisible(); // WelcomeView
  await expect(page.getByRole("tablist",{name:"功能分区"})).toHaveCount(0);
});

// —— Task 5 全局 ActionDock 与草稿栈浮窗 + 快捷键（SPEC-DM-006 §4.1/§6.8/§6.9/§7.1）——

test("ActionDock：无草稿时写入禁用并可见原因，有草稿未预览引导先预览",async({page})=>{
  await openWorkspace(page); // mock 草稿 actions 为空
  await expect(page.getByText("没有待发布变更")).toBeVisible(); // 禁用原因以内联文本呈现（原生 title 不进 DOM，不作为断言通道）
  // 加入一条动作后（跟随既有 mock 方式触发一次属性变更）
  await page.getByRole("tab",{name:"属性"}).click();
  await page.locator(".summary input").fill("新名称");
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await expect(page.getByText("请先预览")).toBeVisible();
});

test("Ctrl+S 只打开确认模态不直接执行",async({page})=>{
  // 前置：加入动作并生成有效预览（跟随既有"普通预览丢弃乱序响应"用例的前置）
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"ctrl-s-preview"}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  let executed=false;
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>{executed=true;return route.fulfill({json:{}})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await expect(page.getByRole("button",{name:"确认写入"})).toBeEnabled(); // 等待预览完成进入"有效可执行"态
  await page.keyboard.press("Control+s");
  const modal=page.getByRole("dialog");
  await expect(modal).toBeVisible();
  await expect(modal.getByRole("checkbox")).toBeVisible(); // 模态内仍需勾选
  await page.keyboard.press("Escape"); // Esc 关闭 = 取消
  await expect(modal).toHaveCount(0);
  expect(executed).toBeFalsy();
});

test("任务回滚终态后 ActionDock 解锁不再锁定任务进行中",async({page})=>{
  // 回归：dock 的 taskRunning 复用 useJobMonitor.terminal 终态集（SUCCEEDED/FAILED/ROLLED_BACK/BLOCKED_FILE_LOCK/NEEDS_REVIEW），
  // ROLLED_BACK 属终态应释放矩阵，而非误锁"任务进行中"
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-rolled",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // QUEUED 非终态：dock 锁定并显示"任务进行中"
  await expect(page.getByText("任务进行中")).toBeVisible();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();
  // 任务终态 ROLLED_BACK：释放矩阵，预览/写入解锁
  await page.evaluate(()=>(window as any).__emitJob({id:"job-rolled",workspace_id:"workspace-1",status:"ROLLED_BACK",progress:100,attempt:0,files:[]}));
  await expect(page.getByText("任务进行中")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"预览变更"})).toBeEnabled();
});

test("NEEDS_REVIEW 终态时 ActionDock 锁定并提示需人工检查禁止直接重试",async({page})=>{
  // 回归：dst_validation 是加载时快照、仅 SUCCEEDED 刷新；VALID 工作区遇 NEEDS_REVIEW 后不能落入"有效可执行"，
  // 须由 dock 独立分支锁定（§6.9 行"需人工检查，禁止直接重试"，与 useJobMonitor.retryJob 的 NEEDS_REVIEW 禁止重试一致）
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-review",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  await expect(page.getByText("任务进行中")).toBeVisible();
  // 终态 NEEDS_REVIEW：需人工检查，预览/确认写入均禁用且内联文本可见（不依赖 dst_validation 快照）
  await page.evaluate(()=>(window as any).__emitJob({id:"job-review",workspace_id:"workspace-1",status:"NEEDS_REVIEW",progress:100,attempt:0,files:[]}));
  await expect(page.getByText("需人工检查，禁止直接重试")).toBeVisible();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();
  await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();
});

// —— Task 6 任务浮层：进度 / 预览 / 诊断三页签（SPEC-DM-006 §4.1/§4.2/§7.2）——

test("点击预览后任务浮层自动展开到修改预览页签",async({page})=>{
  // 跟随既有用例构造草稿并 mock 预览成功（Task 6 前预览面板为 App 直属、浮层不存在，用例先红后绿）
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole("tab",{name:"修改预览"})).toHaveAttribute("aria-selected","true");
  // 折叠：页签行保留窄条（始终可见触发按钮 §4.3），面板体 hidden；折叠不卸载，收起后任务仍在执行
  await overlay.getByRole("button",{name:"收起任务浮层"}).click();
  await expect(overlay.locator(".ov-body")).toBeHidden();
  await expect(overlay.getByRole("button",{name:"展开任务浮层"})).toHaveAttribute("aria-expanded","false");
});

test("存在阻断诊断时任务浮层诊断页签显示红点并可打开",async({page})=>{
  // mock workspace.diagnostics 含 severity==="error" 两条（跟随既有诊断用例前置）
  const diag:any={...workspace,diagnostics:[
    {code:"DWG_UNRESOLVED",severity:"error",message:"图纸 001 布局未解析",object_id:"sheet-1"},
    {code:"DWG_UNRESOLVED",severity:"error",message:"图纸 002 布局未解析",object_id:"sheet-2"},
  ]};
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:diag}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:diag}));
  await openWorkspace(page);
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  // 折叠态页签行仅剩触发按钮窄条（§4.3）：先展开再断言诊断页签红点
  await overlay.getByRole("button",{name:"展开任务浮层"}).click();
  await expect(overlay.getByRole("tab",{name:/诊断/})).toContainText("●");
  await overlay.getByRole("tab",{name:/诊断/}).click();
  await expect(overlay.getByRole("tab",{name:/诊断/})).toHaveAttribute("aria-selected","true");
});

// —— Task 7 SSE 任务通知 toast（SPEC-DM-006 §6.6）——

test("任务成功经 SSE 推送 toast 且失败通知常驻可查看",async({page})=>{
  // 跟随既有"失败任务显示逐 DWG 详情并可安全重试"用例的 SSE mock：execute 返回 QUEUED 启动 watchJob，
  // 随后经 __emitJob 推送终态 FAILED 事件（终态分支直写 job.value，不经 setJob）
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-toast",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // 用户折叠/切走浮层后任务到达终态：toast 抑制规则（overlayOpen&&overlayTab==="prog"）才不命中
  await page.getByRole("complementary",{name:"任务浮层"}).getByRole("button",{name:"收起任务浮层"}).click();
  // 推送终态 FAILED 事件后
  await page.evaluate(()=>(window as any).__emitJob({id:"job-toast",workspace_id:"workspace-1",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[]}));
  const toast=page.getByRole("alert").filter({hasText:"任务失败"});
  await expect(toast).toBeVisible();
  await page.waitForTimeout(6000); // 超过成功类自动消失时长
  await expect(toast).toBeVisible(); // 失败常驻
  await toast.getByRole("button",{name:"查看"}).click();
  await expect(page.getByRole("complementary",{name:"任务浮层"}).getByRole("tab",{name:"实施进度"})).toHaveAttribute("aria-selected","true");
  await toast.getByRole("button",{name:"✕"}).click();
  await expect(toast).toHaveCount(0);
});

test("修订历史标签激活时加载列表，空修订显示暂无修订历史",async({page})=>{
  await openWorkspace(page);
  let asked=false;
  await page.route("**/api/revisions**",route=>{asked=true;return route.fulfill({json:[]})});
  await page.getByRole("tab",{name:/修订历史/}).click();
  await expect(page.getByText("暂无修订历史")).toBeVisible();
  expect(asked).toBeTruthy(); // 激活时才加载
});

test("停留在修订历史标签重开工作区后修订列表重新加载",async({page})=>{
  // 回归：active 停在 revisions 时重开工作区，beginWorkspaceLoad 已 invalidateRevisionState 清空列表，
  // 若不重载会停留在虚假"暂无修订历史"空态（closeWorkspace 与发布 SUCCEEDED 后 refreshWorkspace 均触发）
  let revisionCalls=0;
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>{revisionCalls++;return route.fulfill({json:revisionCalls===1?[]:[{id:"revision-reopen-1234567890",created_at:"2026-08-13T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"修订历史"}).click();
  await expect(page.getByText("暂无修订历史")).toBeVisible();
  // 关闭（无未发布改动，不弹模态）后停留在未打开态，标签仍停在修订历史
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await selectDst(page,"C:\\project\\test.dst");
  // 重开工作区后修订列表应重新加载，而非停留在被清空的虚假空态
  await expect(page.getByRole("heading",{name:"永久修订"})).toBeVisible();
  await expect(page.getByText("revision-reopen")).toBeVisible();
  expect(revisionCalls).toBe(2);
});

test("恢复预览在任务浮层修改预览页签呈现",async({page})=>{
  await openWorkspace(page);
  // 跟随既有"修订恢复先预览再确认为新修订"用例 mock 修订列表与 restore-preview
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
  await page.getByRole("tab",{name:/修订历史/}).click();
  await page.getByRole("button",{name:"恢复预览"}).first().click();
  await expect(page.getByRole("complementary",{name:"任务浮层"}).getByRole("tab",{name:"修改预览"})).toHaveAttribute("aria-selected","true");
});
