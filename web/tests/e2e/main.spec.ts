import {expect,test,type Page} from "@playwright/test";
import {writeFileSync} from "node:fs";

test.beforeEach(async({page})=>{
  await page.addInitScript(() => {
    (window as any).pywebview = {
      api: {
        select_file: async (fileTypes: string[]) => (window as any).__fakeSelectResult ?? null,
        on_files_dropped: async () => {},
      },
    };
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
  await openWorkspace(page);await page.locator(".summary button").click();await page.getByRole("button",{name:"预览变更"}).click();
  await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("批量改名布局").first()).toBeVisible();await expect(page.getByText("清除并重建布局").first()).toBeVisible();await expect(page.getByText("无需 CAD 操作",{exact:true}).first()).toBeVisible();await expect(page.getByText("未提供 CAD 操作",{exact:true})).toBeVisible();await expect(page.getByText("未知 CAD 操作：legacy",{exact:true})).toBeVisible();await expect(page.getByText("数量变化前沿：第 2 个子集")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("source-sha-256",{exact:true})).toBeVisible();await expect(page.getByText("布局来源验证")).toHaveCount(0);const affectedFiles=page.locator(".preview > section").filter({has:page.getByRole("heading",{name:"受影响文件"})});await expect(affectedFiles.getByText("C:\\project\\001-002.dwg",{exact:true})).toBeVisible();await expect(affectedFiles.getByText("C:\\project\\003-004.dwg",{exact:true})).toBeVisible();
  page.once("dialog",dialog=>dialog.accept());await page.locator(".preview button.primary").click();const jobDetail=page.locator(".job-detail");const renameRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\001-002.dwg"});const rebuildRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\003-004.dwg"});await expect(renameRow.getByText("批量改名布局",{exact:true})).toBeVisible();await expect(renameRow.getByText("2026-08-26T10:00:00Z",{exact:true})).toBeVisible();await expect(renameRow.getByText("2026-08-26T10:00:02Z",{exact:true})).toBeVisible();await expect(renameRow.getByText("2000 ms",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("清除并重建布局",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("2026-08-26T10:00:03Z",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("2026-08-26T10:00:08Z",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("5000 ms",{exact:true})).toBeVisible();
});

function deferred(){let resolve!:()=>void;const promise=new Promise<void>(done=>{resolve=done});return {promise,resolve}}

const workspace={
  id:"workspace-1",revision_id:"revision-1",sheet_set:{name:"测试图纸集",sheet_count:2,subset_count:2,custom_properties:{项目号:"P-001"},property_definitions:[{type:"sheetset",name:"项目号",default_value:"P-001"},{type:"sheet",name:"比例",default_value:""}],subsets:[
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

test("草稿按动作持久化并支持 A→B→C 撤销恢复 B、重做和批量原子撤销",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"draft-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  const name=page.locator(".summary input");
  for(const value of ["A","B","C"]){await name.fill(value);await page.getByRole("button",{name:"更新图纸集"}).click()}
  await expect(page.getByText("动作 3/3")).toBeVisible();
  await page.getByRole("button",{name:"撤销"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await expect(name).toHaveValue("B");
  expect(previewBodies.at(-1).commands).toEqual([{type:"update_sheet_set",name:"B",custom_properties:{项目号:"P-001"}}]);
  await page.getByRole("button",{name:"重做"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await expect(name).toHaveValue("C");
  expect(previewBodies.at(-1).commands[0].name).toBe("C");
  await page.getByRole("button",{name:"全选当前结果"}).click();await page.getByLabel("既有图纸属性").selectOption("比例");await page.getByLabel("批量值").fill("1:200");await page.getByRole("button",{name:"批量加入草稿"}).click();
  await expect(page.getByText("批量更新 比例（2 张） · 2 条命令")).toBeVisible();
  await page.getByRole("button",{name:"撤销"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies.at(-1).commands).toHaveLength(1);expect(previewBodies.at(-1).commands[0].name).toBe("C");
  await page.reload();await selectDst(page,"C:\\project\\test.dst");
  await expect(page.getByText("动作 3/4")).toBeVisible();
  await expect(page.locator(".summary input")).toHaveValue("C");
});

test("移除 active 动作不会激活 redo 区命令",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"remove-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{sheet_set:[],structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  const name=page.locator(".summary input");
  for(const value of ["A","B","C"]){await name.fill(value);await page.getByRole("button",{name:"更新图纸集"}).click()}
  await page.getByRole("button",{name:"撤销"}).click();
  const actions=page.locator(".draft-actions li");
  await actions.nth(0).getByRole("button",{name:"移除"}).click();
  await expect(page.getByText("动作 1/2")).toBeVisible();
  await expect(name).toHaveValue("B");
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
  const name=page.locator(".summary input");await name.fill("A");await page.getByRole("button",{name:"更新图纸集"}).click();await firstPutStarted.promise;await name.fill("B");await page.getByRole("button",{name:"更新图纸集"}).click();
  // 关闭 A：存在未发布改动 → 确认放弃 → discardDraft 先等待在途草稿保存全部完成再删除
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"关闭"}).click();
  releaseFirstPut.resolve();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await selectDst(page,"C:\\B.dst");await expect(page.locator(".summary input")).toHaveValue("工作区 B");
  expect(putCount).toBe(2);expect(deleted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();await selectDst(page,"C:\\A.dst");await expect(page.locator(".summary input")).toHaveValue("测试图纸集");await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("草稿网络保存失败会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:500,json:{code:"DRAFT_SAVE_FAILED",message:"保存失败"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");const name=page.locator(".summary input");await name.fill("未保存名称");await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByText(/保存失败/)).toBeVisible();
  page.once("dialog",dialog=>dialog.dismiss());await page.getByRole("button",{name:"关闭"}).click();
  await expect(name).toHaveValue("未保存名称");await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
});

test("草稿版本冲突会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:409,json:{code:"DRAFT_CONFLICT",message:"版本冲突"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");const name=page.locator(".summary input");await name.fill("冲突名称");await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByText(/其他窗口更新/)).toBeVisible();
  page.once("dialog",dialog=>dialog.dismiss());await page.getByRole("button",{name:"关闭"}).click();
  await expect(name).toHaveValue("冲突名称");await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
  page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"放弃本地冲突动作并重新加载"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("过期草稿只展示旧意图、阻断预览且可明确丢弃",async({page})=>{
  let deleted=false;await page.unroute("**/api/workspaces/*/draft");await page.route("**/api/workspaces/*/draft",async route=>{if(route.request().method()==="DELETE"){deleted=true;return route.fulfill({json:{deleted:true}})}return route.fulfill({json:{corrupted:false,stale:true,stale_reasons:["BASE_REVISION_CHANGED"],draft:{schema_version:1,workspace_id:"workspace-1",base_revision_id:"old-revision",repair_status:"VALID",version:3,cursor:1,actions:[{id:"old-action",kind:"command_batch",label:"旧图纸集名称",commands:[{type:"update_sheet_set",name:"旧值",custom_properties:{项目号:"P-001"}}]}]}}})});
  await openWorkspace(page);await expect(page.getByText(/草稿已过期（BASE_REVISION_CHANGED）/)).toBeVisible();await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();await expect(page.getByText("旧图纸集名称 · 1 条命令")).toBeVisible();await page.getByRole("button",{name:"丢弃过期草稿"}).click();expect(deleted).toBe(true);await expect(page.getByText(/草稿已过期/)).toHaveCount(0);
});

test("三级导航可按 DWG 路径筛选、多选批量修改并确认删除整个子集",async({page})=>{
  let previewCommands:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewCommands=(await route.request().postDataJSON()).commands;return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"delete-digest",executable:true,requires_cad:true,changes:[],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\001-002 第一册.dwg"],semantic_diff:{structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:{groups:[],deleted_subsets:[]}}})});
  await openWorkspace(page);
  await page.getByLabel("搜索图纸").fill("001-002 第一册.DWG");await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(2);
  const subsetSelect=page.locator(".filter-grid select").nth(0);await subsetSelect.selectOption("subset-2");await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(0);await subsetSelect.selectOption("subset-1");
  await page.getByRole("button",{name:"全选当前结果"}).click();await expect(page.getByText("已选 2")).toBeVisible();
  await page.getByLabel("既有图纸属性").selectOption("比例");await page.getByLabel("批量值").fill("1:50");await page.getByRole("button",{name:"批量加入草稿"}).click();await page.getByRole("button",{name:"清空"}).click();
  page.once("dialog",dialog=>{expect(dialog.message()).toContain("系统不会证明工程外部引用");dialog.accept()});await page.getByRole("button",{name:"删除整个子集"}).click();await page.getByRole("button",{name:"预览变更"}).click();
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
    return route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"number_range_changed",before:"001-002",after:"001-004"}],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\003-004 新分册.dwg"],execution_intent:{cad_validation_deferred:true,cardinality_frontier:{index:2,subset_id:"subset-new"},subset_operations:[{subset_id:"subset-1",cad_operation:"none",target_file:"C:\\project\\001-002 第一册.dwg",in_cardinality_scope:false},{subset_id:"subset-2",cad_operation:"none",target_file:"C:\\project\\002-003 第二册.dwg",in_cardinality_scope:false},{subset_id:"subset-new",cad_operation:"rebuild",target_file:"C:\\project\\003-004 新分册.dwg",in_cardinality_scope:true}],derived_document:{subsets:[{acsm_id:"subset-new",number_range:"003-004",display_name:"003-004 新分册",title:"新分册"}]},groups:[
      {subset_id:"subset-new",operation:"create",cad_operation:"rebuild",subset_name:"003-004 新分册",target_file:"C:\\project\\003-004 新分册.dwg",layouts:[{number:"003",title:"新分册 (一)",target_layout:"003 新分册 (一)"},{number:"004",title:"新分册 (二)",target_layout:"004 新分册 (二)"}]},
    ]}}});
  });
  await openWorkspace(page);
  await page.getByLabel("属性作用域").selectOption("sheet");await page.getByLabel("属性名称").fill("专业");await page.getByLabel("默认值").fill("燃气");await page.getByRole("button",{name:"加入属性定义"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[0]).toEqual([{type:"add_custom_property",property_type:"sheet",name:"专业",default_value:"燃气"}]);
  await page.getByRole("button",{name:"清空"}).click();await page.getByRole("button",{name:"删除 比例"}).click();await page.getByRole("button",{name:"预览变更"}).click();expect(previewRequests[1]).toEqual([{type:"delete_custom_property",property_type:"sheet",name:"比例"}]);
  await page.getByLabel("子集序号").fill("2");await page.getByLabel("子集方向").selectOption("after");await page.getByLabel("子集标题",{exact:true}).fill("新分册");await page.getByLabel("初始图纸数").fill("2");await page.getByLabel("模板文件",{exact:true}).fill("C:\\template.dwt");await page.getByLabel("模板布局",{exact:true}).fill("A1模板");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("属性定义与结构变更必须分批预览和执行")).toBeVisible();
  await page.getByRole("button",{name:"清空"}).click();await page.getByRole("button",{name:"新建子集"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[2]).toEqual([{type:"insert_subset",ordinal:2,placement:"after",title:"新分册",initial_sheet_count:2,source:{type:"template_layout",file:"C:\\template.dwt",layout:"A1模板"}}]);expect(previewRequests[2][0]).not.toHaveProperty("number");
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
  await openWorkspace(page);await page.getByLabel("AutoCAD 版本").selectOption("2016");await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies[0].cad_version).toBe("2016");await expect(page.getByText("前后有序结构")).toBeVisible();await expect(page.getByRole("columnheader",{name:"受影响图纸"})).toBeVisible();await expect(page.getByText("DWG 与布局差异")).toBeVisible();await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("abc123",{exact:true})).toBeVisible();await expect(page.getByText("A1模板",{exact:true}).first()).toBeVisible();await expect(page.getByText("[object Object]",{exact:true})).toHaveCount(0);
  page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();expect(executeBody.cad_version).toBe("2016");expect(executeBody.preview_digest).toBe("digest-2016");
  await page.getByRole("button",{name:"预览变更"}).click();await expect(page.getByText("完整变更预览")).toBeVisible();await page.getByLabel("AutoCAD 版本").selectOption("2020");await expect(page.getByText("完整变更预览")).toHaveCount(0);
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
  await openWorkspace(page,"C:\\A.dst");
  await expect(page.locator(".summary input")).toHaveValue("工作区 A");
  await page.getByRole("button",{name:"关闭"}).click();
  const switching=selectDst(page,"C:\\B.dst");
  await expect.poll(()=>openCalls).toBe(2);
  const loadingWasVisible=await page.getByText("正在加载工作区…",{exact:true}).isVisible();
  const editorWasVisible=await page.locator(".editor").isVisible();
  openB.resolve();await switching;await expect(page.locator(".summary input")).toHaveValue("工作区 B");
  await expect(page.getByRole("button",{name:"确认并执行"})).toHaveCount(0);await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  expect(loadingWasVisible).toBe(true);expect(editorWasVisible).toBe(false);expect(executeCalls).toBe(0);expect(importCalls).toBe(0);
});

test("多次打开及刷新与打开竞争时仅最新工作区生效",async({page})=>{
  const openA=deferred(),openB=deferred(),openC=deferred(),refreshC=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst")){await openA.promise;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")})}if(path.endsWith("B.dst")){await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})}if(path.endsWith("C.dst")){await openC.promise;return route.fulfill({json:workspaceVersion("workspace-C","工作区 C","revision-C")})}return route.fulfill({json:workspaceVersion("workspace-D","工作区 D","revision-D")})});
  await page.route("**/api/workspaces/workspace-C/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"C-preview"}],diagnostics:[],affected_files:["C.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-C/changes/execute",route=>route.fulfill({json:{id:"job-C",status:"SUCCEEDED",progress:100,files:[]}}));await page.route("**/api/workspaces/workspace-C",async route=>{refreshStarted=true;await refreshC.promise;await route.fulfill({json:workspaceVersion("workspace-C","工作区 C 刷新","revision-C2")})});
  await page.goto("/");
  await selectDst(page,"C:\\A.dst");await selectDst(page,"C:\\B.dst");await selectDst(page,"C:\\C.dst");
  openC.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 C");openB.resolve();openA.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 C");
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect.poll(()=>refreshStarted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\D.dst");await expect(page.locator(".summary input")).toHaveValue("工作区 D");refreshC.resolve();await page.waitForTimeout(100);await expect(page.locator(".summary input")).toHaveValue("工作区 D");
});

test("切换工作区会关闭旧任务监控且忽略迟到终态",async({page})=>{
  await installMockEventSource(page);const openB=deferred();let refreshACalls=0,openBStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst"))return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});openBStarted=true;await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"A-command"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-A/changes/execute",route=>route.fulfill({json:{id:"job-A",workspace_id:"workspace-A",status:"QUEUED",progress:0,attempt:0,files:[]}}));await page.route("**/api/workspaces/workspace-A",route=>{refreshACalls++;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A 被旧任务刷新","revision-A2")})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect(page.getByText("任务 job-A")).toBeVisible();
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"关闭"}).click();
  const switching=selectDst(page,"C:\\B.dst");await expect.poll(()=>openBStarted).toBe(true);await page.evaluate(()=>(window as any).__emitJob({id:"job-A",workspace_id:"workspace-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}));openB.resolve();await switching;await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);
  expect(refreshACalls).toBe(0);await expect(page.getByText("任务 job-A")).toHaveCount(0);expect(await page.evaluate(()=>(window as any).__closedEventSources())).toBe(1);
});

test("工作区切换会丢弃迟到的修订列表和恢复预览",async({page})=>{
  const revisionList=deferred(),restorePreviewGate=deferred();let revisionCalls=0,restoreCalls=0;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.endsWith("A.dst")?workspaceVersion("workspace-A","工作区 A","revision-A"):workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/revisions?workspace_id=workspace-A",async route=>{revisionCalls++;if(revisionCalls===1)await revisionList.promise;return route.fulfill({json:[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",async route=>{await restorePreviewGate.promise;return route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}})});await page.route("**/api/workspaces/**/revisions/revision-A-old/restore",route=>{restoreCalls++;return route.fulfill({json:{id:"wrong-restore",status:"SUCCEEDED",progress:100,files:[]}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("button",{name:"修订历史"}).click();await expect.poll(()=>revisionCalls).toBe(1);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\B.dst");revisionList.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);await expect(page.getByText("revision-A-old")).toHaveCount(0);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\A.dst");await page.getByRole("button",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\B.dst");restorePreviewGate.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 B");await page.waitForTimeout(100);const restoreButton=page.getByRole("button",{name:"恢复为新修订"});if(await restoreButton.isVisible()){page.once("dialog",dialog=>dialog.accept());await restoreButton.click()}expect(restoreCalls).toBe(0);await expect(page.getByText("恢复确认")).toHaveCount(0);
});

test("恢复写入期间阻断冲突入口并在成功后刷新工作区与修订",async({page})=>{
  const restorePost=deferred();let openCalls=0,revisionCalls=0,previewCalls=0,restoreCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",async route=>{openCalls++;const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.endsWith("B.dst")?workspaceVersion("workspace-B","工作区 B","revision-B"):workspaceVersion("workspace-A","工作区 A","revision-A")})});await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:revisionCalls===1?[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]:[{id:"revision-A-new",created_at:"2026-08-13T00:00:00Z",before_hash:"bbbbbbbb",result_hash:"cccccccc"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>{previewCalls++;return route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreCalls++;restoreStarted=true;await restorePost.promise;return route.fulfill({json:{id:"restore-job-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}})});await page.route("**/api/workspaces/workspace-A",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A 已恢复","revision-A2")}));
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("button",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"恢复为新修订"}).click();await expect.poll(()=>restoreStarted).toBe(true);
  const restoringWasVisible=await page.getByText("正在恢复修订…",{exact:true}).isVisible();const closeWasDisabled=await page.getByRole("button",{name:"关闭"}).isDisabled();const historyWasDisabled=await page.getByRole("button",{name:"修订历史"}).isDisabled();const previewButton=page.getByRole("button",{name:"恢复预览"});const previewWasDisabled=await previewButton.isDisabled();const confirmWasDisabled=await page.getByRole("button",{name:"恢复为新修订"}).isDisabled();if(!historyWasDisabled)await page.getByRole("button",{name:"修订历史"}).click();if(!previewWasDisabled)await previewButton.click();
  restorePost.resolve();await expect(page.locator(".summary input")).toHaveValue("工作区 A 已恢复");await expect(page.getByText("revision-A-new")).toBeVisible();await expect(page.getByText("任务 restore-job-A")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);
  expect(restoringWasVisible).toBe(true);expect(closeWasDisabled).toBe(true);expect(historyWasDisabled).toBe(true);expect(previewWasDisabled).toBe(true);expect(confirmWasDisabled).toBe(true);expect(openCalls).toBe(1);expect(revisionCalls).toBe(2);expect(previewCalls).toBe(1);expect(restoreCalls).toBe(1);
});

test("恢复写入错误会显示消息并解除入口锁定",async({page})=>{
  const restorePost=deferred();let revisionCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")}));await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreStarted=true;await restorePost.promise;return route.fulfill({status:500,json:{message:"恢复失败"}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("button",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"恢复为新修订"}).click();await expect.poll(()=>restoreStarted).toBe(true);await expect(page.getByText("正在恢复修订…",{exact:true})).toBeVisible();restorePost.resolve();await expect(page.getByText("恢复失败")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭"})).toBeEnabled();await expect(page.getByRole("button",{name:"修订历史"})).toBeEnabled();await page.getByRole("button",{name:"修订历史"}).click();expect(revisionCalls).toBe(2);await expect(page.locator(".editor")).toBeVisible();
});

test("旧编辑入口已移除且图号标题只读",async({page})=>{
  await openWorkspace(page);await expect(page.getByRole("button",{name:"子集↑"})).toHaveCount(0);await expect(page.getByRole("button",{name:"子集↓"})).toHaveCount(0);await expect(page.getByText("移动到",{exact:true})).toHaveCount(0);const sheetRow=page.locator(".subset-editor tbody tr").filter({has:page.getByText("001",{exact:true})});await expect(sheetRow.locator("td").nth(0).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(1).locator("input,textarea,select")).toHaveCount(0);await expect(sheetRow.locator("td").nth(0)).toHaveText("001");await expect(sheetRow.locator("td").nth(1)).toHaveText("第一册 (一)");
});

test("批量新增图纸校验位置数量和布局来源",async({page})=>{
  let previewCommands:any[]=[];await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewCommands=(await route.request().postDataJSON()).commands;await route.fulfill({json:{executable:true,requires_cad:true,changes:[],diagnostics:[],affected_files:[],execution_intent:{groups:[]}}})});await page.route("**/api/layout-names",route=>route.fulfill({json:{layouts:["A1","A2"],cached:false,file_hash:"x"}}));await openWorkspace(page);
  await page.getByLabel("图纸序号").fill("3");await page.getByLabel("新增图纸数量").fill("0");await page.getByRole("button",{name:"批量新增图纸"}).click();await expect(page.getByText("图纸序号必须在 1 到 2 之间")).toBeVisible();expect(previewCommands).toHaveLength(0);
  await page.getByLabel("图纸序号").fill("2");await page.getByLabel("新增图纸数量").fill("2");await page.getByRole("button",{name:"批量新增图纸"}).click();await expect(page.getByText("来源文件和来源布局不能为空")).toBeVisible();await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\source.dwg"});await page.getByRole("button",{name:"选择模板文件"}).click();await page.getByLabel("来源布局").selectOption("A1");await page.getByLabel("图纸方向").selectOption("before");await page.getByRole("button",{name:"批量新增图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewCommands).toEqual([{type:"insert_sheet",target_subset_id:"subset-1",ordinal:2,placement:"before",count:2,source:{type:"template_layout",file:"C:\\source.dwg",layout:"A1"}}]);expect(previewCommands[0]).not.toHaveProperty("number");expect(previewCommands[0]).not.toHaveProperty("title");
});

test("选择来源文件后加载布局下拉",async({page})=>{
  await page.route("**/api/layout-names",(route)=>route.fulfill({json:{layouts:["A-01","A-02"],cached:false,file_hash:"abc"}}));
  await openWorkspace(page);
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/tpl/frame.dwg"});
  await page.getByRole("button",{name:"选择模板文件"}).click();
  await expect(page.getByRole("combobox",{name:/来源布局/})).toBeEnabled();
  await expect(page.getByRole("combobox",{name:/来源布局/})).toContainText("A-01");
});

test("布局读取失败回退手动输入",async({page})=>{
  await page.route("**/api/layout-names",(route)=>route.fulfill({status:502,json:{code:"LAYOUT_READ_FAILED",message:"读取布局失败"}}));
  await openWorkspace(page);
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/tpl/frame.dwg"});
  await page.getByRole("button",{name:"选择模板文件"}).click();
  await expect(page.getByText("读取布局失败")).toBeVisible();
  await expect(page.getByRole("textbox",{name:/来源布局/})).toBeVisible();
});

test("空图纸集首个子集只能用序号一且必须提供模板",async({page})=>{
  const empty={...workspace,sheet_set:{...workspace.sheet_set,sheet_count:0,subset_count:0,subsets:[]}};let previewCalls=0;await page.route("**/api/workspaces/open",route=>route.fulfill({json:empty}));await page.route("**/api/workspaces/workspace-1/changes/preview",route=>{previewCalls++;return route.fulfill({json:{executable:true,changes:[],diagnostics:[]}})});await openWorkspace(page);await page.getByLabel("子集序号").fill("2");await page.getByLabel("子集标题",{exact:true}).fill("首册");await page.getByLabel("初始图纸数").fill("1");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("空图纸集的首个子集序号必须为 1")).toBeVisible();await page.getByLabel("子集序号").fill("1");await page.getByRole("button",{name:"新建子集"}).click();await expect(page.getByText("模板文件和模板布局不能为空")).toBeVisible();expect(previewCalls).toBe(0);
});

test("属性命令与结构命令分批并支持 CSV 行级预览导入",async({page})=>{
  let importedCsv="";await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{importedCsv=(await route.request().postDataJSON()).csv;await route.fulfill({json:{executable:false,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[{line:3,severity:"error",code:"CUSTOM_PROPERTY_NAME_EMPTY",message:"名称不能为空"}],affected_files:["test.dst"],execution_intent:null}})});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:"csv-job",status:"SUCCEEDED",progress:100,files:[]}}));await openWorkspace(page);
  await expect(page.getByRole("link",{name:"下载 CSV 模板"})).toHaveAttribute("href","/api/custom-properties/template");await expect(page.getByRole("link",{name:"导出当前属性"})).toHaveAttribute("href","/api/workspaces/workspace-1/custom-properties/export");await page.getByLabel("属性 CSV 文件").setInputFiles({name:"properties.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,专业,燃气\nsheet,,\n","utf8")});await page.getByRole("button",{name:"预览 CSV 导入"}).click();expect(importedCsv).toContain("sheet,专业,燃气");await expect(page.getByText("第 3 行")).toBeVisible();await expect(page.getByText("CUSTOM_PROPERTY_NAME_EMPTY")).toBeVisible();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  await page.unroute("**/api/workspaces/workspace-1/custom-properties/import/preview");await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.getByRole("button",{name:"预览 CSV 导入"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认导入"}).click();await expect(page.getByText("任务 csv-job")).toBeVisible();
});

test("失败任务显示逐 DWG 详情并可安全重试",async({page})=>{
  await installMockEventSource(page);await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,duration_ms:600000,error_code:"CAD_TIMEOUT"}]}}));await page.route("**/api/jobs/job-failed/retry",route=>route.fulfill({json:{id:"job-failed",status:"QUEUED",progress:0,attempt:1,files:[]}}));await openWorkspace(page);await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();await expect(page.getByText("A.dwg")).toBeVisible();await expect(page.getByText("检查 CAD 日志")).toBeVisible();await page.getByRole("button",{name:"安全重试"}).click();await expect(page.getByText(/QUEUED/)).toBeVisible();
});

test("修订恢复先预览再确认为新修订",async({page})=>{
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-1",status:"SUCCEEDED",progress:100,attempt:0,files:[]}}));await openWorkspace(page);await page.getByRole("button",{name:"修订历史"}).click();await page.getByRole("button",{name:"恢复预览"}).click();await expect(page.getByText("replace test.dst")).toBeVisible();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"恢复为新修订"}).click();await expect(page.locator(".summary input")).toHaveValue("测试图纸集");
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
  await expect(page.getByText("DST 修复状态：已修复（待确认）")).toBeVisible();
  await page.getByText("修复明细（1）").click();
  await expect(page.getByText("REPAIR_ATTR_MISSING")).toBeVisible();
  // 确认前普通编辑发布被禁用
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();
  await page.getByRole("button",{name:"预览并确认修复"}).click();
  await expect(page.getByText(/修复 1 项 · 摘要 digest-12345678/)).toBeVisible();
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"确认发布修复修订"}).click();
  await expect(page.getByText("任务 repair-job")).toBeVisible();
  // 修复成功后刷新为 VALID，修复面板消失且普通编辑恢复
  await expect(page.getByText("已修复（待确认）")).toHaveCount(0);
  await expect(page.getByText("DST 修复状态")).toHaveCount(0);
  await page.getByRole("button",{name:"更新图纸集"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeEnabled();
});

test("未打开态只有文件选择区，不显示修订历史",async({page})=>{
  await page.goto("/");
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.getByRole("button",{name:"修订历史"})).toHaveCount(0);
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
  await page.getByRole("button",{name:"更新图纸集"}).click();
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
  page.once("dialog",dialog=>dialog.accept());
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
});

test("关闭后迟到的刷新响应不会复活工作区",async({page})=>{
  const refreshGate=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")}));
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"A-preview"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-A/changes/execute",route=>route.fulfill({json:{id:"job-refresh",status:"SUCCEEDED",progress:100,files:[]}}));
  await page.route("**/api/workspaces/workspace-A",async route=>{refreshStarted=true;await refreshGate.promise;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A 已刷新","revision-A2")})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("button",{name:"预览变更"}).click();page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"确认并执行"}).click();
  await expect.poll(()=>refreshStarted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  refreshGate.resolve();await page.waitForTimeout(100);
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.locator(".summary input")).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭"})).toHaveCount(0);
});
