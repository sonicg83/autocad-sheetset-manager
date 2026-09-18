import {expect,test,type Page,type TestInfo} from "@playwright/test";
import {writeFileSync} from "node:fs";
import {buildPreviewFromBase, installSheetsFixture} from "./fixtures/sheets";
import {installPreferenceSnapshot,openSettingsDialog} from "./fixtures/settings";

test.beforeEach(async({page})=>{
  await page.addInitScript(() => {
    // 真实 pywebview 在页面加载后才异步注入 window.pywebview 并派发 pywebviewready；
    // ?late-bridge 模拟该时序（load 后 30ms 才注入），验证前端不把"晚到的桥"当成无壳浏览器
    const inject = () => {
      (window as any).__selectFileCalls = [];
      (window as any).pywebview = {
        api: {
          // PLAN-DM-021 Task 4：select_file(file_kind, localizedDescription)——记录调用以断言
          // 固定种类与本地化描述；白名单由壳侧按 kind 拼接，前端不再传过滤器字符串
          select_file: async (fileKind: string, description: string) => {
            (window as any).__selectFileCalls.push({fileKind, description});
            return (window as any).__fakeSelectResult ?? null;
          },
          on_files_dropped: async () => {},
        },
      };
      window.dispatchEvent(new Event("pywebviewready"));
    };
    // I18N 批次起 bootstrap 先取设置再挂载（I18N-04），首帧可能晚于 load+30ms；
    // 必须等 Vue 已挂载（#app 有子节点，即降级界面已渲染）再注入，否则"降级态→文件选择区"
    // 的切换无从观察（注入早于首帧时应用直接以有壳态起步，同样符合预期行为）
    if (new URLSearchParams(window.location.search).has("late-bridge")) {
      const injectWhenMounted = () => {
        if (document.querySelector("#app")?.hasChildNodes()) { setTimeout(inject, 30); return; }
        setTimeout(injectWhenMounted, 10);
      };
      window.addEventListener("load", injectWhenMounted);
    } else {
      inject();
    }
  });
  // 扩展页面贡献不在本 spec 范围（Task 10 专属 spec 覆盖）：按无扩展呈现，标签世界与既有用例一致
  await page.route("**/api/extensions",route=>route.fulfill({json:[]}));
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
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("批量改名布局").first()).toBeVisible();await expect(page.getByText("清除并重建布局").first()).toBeVisible();await expect(page.getByText("无需 CAD 操作",{exact:true}).first()).toBeVisible();await expect(page.getByText("未提供 CAD 操作",{exact:true})).toBeVisible();await expect(page.getByText("未知 CAD 操作：legacy",{exact:true})).toBeVisible();await expect(page.getByText("数量变化前沿：第 2 个子集")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("source-sha-256",{exact:true})).toBeVisible();await expect(page.getByText("布局来源验证")).toHaveCount(0);const affectedFiles=page.locator(".preview > section").filter({has:page.getByRole("heading",{name:"受影响文件"})});await expect(affectedFiles.getByText("C:\\project\\001-002.dwg",{exact:true})).toBeVisible();await expect(affectedFiles.getByText("C:\\project\\003-004.dwg",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // 任务详情迁入任务浮层实施进度页签：预览已展开浮层，切到实施进度页签再断言逐文件行
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("tab",{name:"实施进度"}).click();
  const jobDetail=overlay.locator(".job-detail");const renameRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\001-002.dwg"});const rebuildRow=jobDetail.locator("tbody tr").filter({hasText:"C:\\project\\003-004.dwg"});await expect(renameRow.getByText("批量改名布局",{exact:true})).toBeVisible();await expect(renameRow.getByText("2000 ms",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("清除并重建布局",{exact:true})).toBeVisible();await expect(rebuildRow.getByText("5000 ms",{exact:true})).toBeVisible();
  // PLAN-DM-021 Task 8：任务起止时间经 Intl 按生效语言（zh-CN 基线）格式化
  const zhFormatter=new Intl.DateTimeFormat("zh-CN",{dateStyle:"medium",timeStyle:"medium"});await expect(renameRow.getByText(zhFormatter.format(new Date("2026-08-26T10:00:00Z")),{exact:true})).toBeVisible();await expect(renameRow.getByText(zhFormatter.format(new Date("2026-08-26T10:00:02Z")),{exact:true})).toBeVisible();await expect(rebuildRow.getByText(zhFormatter.format(new Date("2026-08-26T10:00:03Z")),{exact:true})).toBeVisible();await expect(rebuildRow.getByText(zhFormatter.format(new Date("2026-08-26T10:00:08Z")),{exact:true})).toBeVisible();
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

// Task 5 起外壳双语：按钮可访问名随生效语言变化，name 参数允许英文用例传入英文名
function selectDst(page:Page,dst:string,name="选择 DST 文件"){return page.evaluate(p=>{(window as any).__fakeSelectResult=p},dst).then(()=>page.getByRole("button",{name}).click())}

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
// PLAN-DM-034（SPEC-DM-015 §5.1/§5.2）：clean 态「更新图纸集」为可聚焦语义禁用（aria-disabled），
// 空保存由提交守卫阻断（旧「clean 仍可执行空保存」例外已删除）。需要产生草稿动作的用例
// 先修改图纸集名称制造真实差异再保存；同会话多次保存必须传不同 value（保存后基准随之更新）。
async function saveSheetSetDraft(page:Page,value:string){
  await page.getByLabel("图纸集名称", {exact: true}).fill(value);
  await page.getByRole("button",{name:"更新图纸集"}).click();
}
// 草稿栈浮窗（Task 5）：点计数芯片展开 / Esc 关闭（§7.2 抽屉模型，焦点归还芯片）
// 用 .draft-chip 类精确定位：/草稿/ 名称正则会误中"批量加入草稿"按钮
async function openDraftPop(page:Page){await page.locator(".draft-chip").click()}
async function closeDraftPop(page:Page){await page.keyboard.press("Escape")}

async function expectActionAppearance(page: Page, selector: string) {
  await expect(page.locator(selector).first()).toBeVisible();
  for (const control of await page.locator(selector).all()) {
    const style = await control.evaluate(el => {
      const css = getComputedStyle(el);
      return {height: el.getBoundingClientRect().height, padding: parseFloat(css.paddingLeft), border: parseFloat(css.borderTopWidth)};
    });
    expect.soft(style.height).toBeGreaterThanOrEqual(36);
    expect.soft(style.padding).toBeGreaterThanOrEqual(8);
    expect.soft(style.border).toBeGreaterThan(0);
  }
}

test("草稿按动作持久化并支持 A→B→C 撤销恢复 B、重做和批量原子撤销",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"draft-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.getByLabel("图纸集名称", {exact: true});
  for(const value of ["A","B","C"]){await name.fill(value);await page.getByRole("button",{name:"更新图纸集"}).click()}
  await page.getByRole("tab",{name:"图纸"}).click();
  await openDraftPop(page);
  await expect(page.getByText("动作 3/3")).toBeVisible();
  await expectActionAppearance(page, "#draft-pop button");
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
  await page.getByRole("button",{name:"收起任务浮层"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();
  // 任务 3 起选择后出现吸顶选择条，批量输入经「批量修改属性」展开
  await page.getByRole("checkbox",{name:"全选当前结果"}).check();await page.getByRole("button",{name:"批量修改属性"}).click();await page.getByLabel("既有图纸属性").selectOption("比例");await page.getByLabel("批量值").fill("1:200");await page.getByRole("button",{name:"批量加入草稿"}).click();
  await openDraftPop(page);
  await expect(page.getByText("批量更新 比例（2 张） · 2 条命令")).toBeVisible();
  await closeDraftPop(page);
  await page.getByRole("button",{name:"撤销"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies.at(-1).commands).toHaveLength(1);expect(previewBodies.at(-1).commands[0].name).toBe("C");
  await page.reload();await selectDst(page,"C:\\project\\test.dst");
  await openDraftPop(page);
  await expect(page.getByText("动作 3/4")).toBeVisible();
  await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("C");
});

test("草稿浮层使用宽布局，工具栏文字不拆分且动作按钮右对齐",async({page})=>{
  await page.setViewportSize({width:1280,height:720});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.getByLabel("图纸集名称",{exact:true});
  for(const value of ["草稿名称 A","草稿名称 B"]){
    await name.fill(value);
    await page.getByRole("button",{name:"更新图纸集"}).click();
  }
  await page.getByRole("tab",{name:"图纸"}).click();
  await openDraftPop(page);

  const layout=await page.locator("#draft-pop").evaluate(pop=>{
    const popRect=pop.getBoundingClientRect();
    const toolbar=pop.querySelector<HTMLElement>(".toolbar")!;
    const toolbarButtons=Array.from(toolbar.querySelectorAll<HTMLElement>("button"));
    const firstRemove=pop.querySelector<HTMLElement>(".draft-actions li button")!;
    return {
      popWidth:popRect.width,
      buttonTops:toolbarButtons.map(button=>Math.round(button.getBoundingClientRect().top)),
      buttonWhiteSpaces:toolbarButtons.map(button=>getComputedStyle(button).whiteSpace),
      removeRightGap:popRect.right-firstRemove.getBoundingClientRect().right,
    };
  });
  expect(layout.popWidth,"桌面视口下应给摘要、四个操作和动作列表留出舒展宽度").toBeGreaterThanOrEqual(540);
  expect(new Set(layout.buttonTops).size,"四个工具栏按钮应位于同一行").toBe(1);
  expect(layout.buttonWhiteSpaces,"按钮标签不得拆字或换行").toEqual(["nowrap","nowrap","nowrap","nowrap"]);
  expect(layout.removeRightGap,"动作移除按钮应贴近列表右侧对齐").toBeLessThanOrEqual(28);
});

test("移除 active 动作不会激活 redo 区命令",async({page})=>{
  const previewBodies:any[]=[];
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());return route.fulfill({json:{workspace_id:"workspace-1",base_revision_id:"revision-1",cad_version:"2020",preview_digest:"remove-digest",executable:true,requires_cad:false,changes:[],diagnostics:[],affected_files:[],semantic_diff:{sheet_set:[],structure:{before:[],after:[]},properties:[],dwgs:[]},execution_intent:null}})});
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  const name=page.getByLabel("图纸集名称", {exact: true});
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
  const name=page.getByLabel("图纸集名称", {exact: true});await name.fill("A");await page.getByRole("button",{name:"更新图纸集"}).click();await firstPutStarted.promise;await name.fill("B");await page.getByRole("button",{name:"更新图纸集"}).click();
  // 关闭 A：存在未发布改动 → 确认放弃 → discardDraft 先等待在途草稿保存全部完成再删除
  await page.getByRole("button",{name:"关闭"}).click();
  await confirmModal(page,/确定关闭并放弃当前改动/);
  releaseFirstPut.resolve();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await selectDst(page,"C:\\B.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 B");
  expect(putCount).toBe(2);expect(deleted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();await selectDst(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("测试图纸集");await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText("动作 0/0")).toBeVisible();
});

test("草稿网络保存失败会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:500,json:{code:"DRAFT_SAVE_FAILED",message:"保存失败"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();const name=page.getByLabel("图纸集名称", {exact: true});await name.fill("未保存名称");await page.getByRole("button",{name:"更新图纸集"}).click();await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText(/保存失败/)).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();await cancelModal(page);
  await page.getByRole("tab",{name:"属性"}).click();await expect(name).toHaveValue("未保存名称");await page.getByRole("tab",{name:"图纸"}).click();await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
});

test("草稿版本冲突会中止工作区切换并保留编辑",async({page})=>{
  await page.unroute("**/api/workspaces/*/draft");
  await page.route("**/api/workspaces/*/draft",route=>route.request().method()==="GET"?route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}):route.fulfill({status:409,json:{code:"DRAFT_CONFLICT",message:"版本冲突"}}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await openWorkspace(page,"C:\\A.dst");await page.getByRole("tab",{name:"属性"}).click();const name=page.getByLabel("图纸集名称", {exact: true});await name.fill("冲突名称");await page.getByRole("button",{name:"更新图纸集"}).click();await expect(page.getByText(/其他窗口更新/)).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();await cancelModal(page);
  await expect(name).toHaveValue("冲突名称");await page.getByRole("tab",{name:"图纸"}).click();await openDraftPop(page);await expect(page.getByText("动作 1/1")).toBeVisible();await expect(page.getByRole("status")).toHaveCount(0);
  await page.getByRole("button",{name:"放弃本地冲突动作并重新加载"}).click();await confirmModal(page,/确定放弃冲突动作并重新加载/);await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("测试图纸集");await page.getByRole("tab",{name:"图纸"}).click();await expect(page.getByText("动作 0/0")).toBeVisible();
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
  await page.getByRole("checkbox",{name:"全选当前结果"}).check();await expect(page.getByText("已选 2")).toBeVisible();
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
  await page.getByRole("button",{name:/继续加载/}).click();await expect(page.locator(".sheet-table-window tbody tr")).toHaveCount(100);await page.locator(".sheet-table-window").focus();await page.keyboard.press("Tab");await expect(page.getByLabel("全选当前结果")).toBeFocused();await page.keyboard.press("Tab");await expect(page.getByLabel("选择图纸 003")).toBeFocused();
  await page.getByRole("checkbox",{name:"全选当前结果"}).check();await expect(page.getByText(/已选 \d+/)).toBeVisible();
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
  await page.getByRole("button",{name:"展开属性字段定义"}).click();await page.getByRole("button",{name:"新增字段"}).click();
  await page.getByLabel("属性作用域").selectOption("sheet");await page.getByLabel("属性名称").fill("专业");await page.getByLabel("默认值").fill("燃气");await page.getByRole("button",{name:"加入草稿"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewRequests[0]).toEqual([{type:"add_custom_property",property_type:"sheet",name:"专业",default_value:"燃气"}]);
  await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);
  await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByRole("button",{name:"收起属性字段定义"})).toBeVisible();await expect(page.getByRole("button",{name:"新增字段"})).toBeVisible();
  await page.getByRole("button",{name:"删除 图纸 属性 比例"}).click();await page.getByRole("dialog",{name:"删除属性定义"}).getByRole("button",{name:"加入删除草稿"}).click();
  await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();expect(previewRequests[1]).toEqual([{type:"delete_custom_property",property_type:"sheet",name:"比例"}]);
  // 任务 6 起新建子集表单选择参照子集而非手填序号：参照子集 2 + 之后 → ordinal 2
  await page.getByRole("button",{name:"收起任务浮层"}).click();
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
  await installPreferenceSnapshot(page,"light","2016");
  const previewBodies:any[]=[];let executeBody:any=null;
  const semantic={
    structure:{before:[{position:1,id:"subset-1",title:"第一册",number_range:"001-002",display_name:"001-002 第一册",dwg_file:"C:\\project\\A.dwg",sheets:[{position:1,id:"sheet-1",number:"001",title:"第一册 (一)",suffix:"一",dwg_file:"C:\\project\\A.dwg",layout_name:"001 第一册 (一)"}]}],after:[{position:1,id:"subset-1",title:"第一册",number_range:"001-003",display_name:"001-003 第一册",dwg_file:"C:\\project\\A.dwg",sheets:[{position:1,id:"sheet-1",number:"001",title:"第一册 (一)",suffix:"一",dwg_file:"C:\\project\\A.dwg",layout_name:"001 第一册 (一)"}]}]},
    properties:[{action:"add",type:"sheet",name:"专业",before:null,after:{name:"专业",default_value:"燃气"},affected_sheet_count:2}],
    dwgs:[{action:"rebuild",subset_id:"subset-1",before:{file:"C:\\project\\A.dwg",layouts:["001 第一册 (一)"]},after:{file:"C:\\project\\A.dwg",layouts:["001 第一册 (一)","003 第一册 (三)"]}}],
  };
  const inspection={path:"C:\\project\\template.dwt",sha256:"abc123",cad_version:"2016",layouts:["A1模板"],requested_layouts:["A1模板"]};
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{previewBodies.push(await route.request().postDataJSON());await route.fulfill({json:{executable:true,requires_cad:true,preview_digest:"digest-2016",changes:[{type:"add_custom_property",affected_sheet_count:2}],diagnostics:[],affected_files:["C:\\project\\test.dst"],semantic_diff:semantic,execution_intent:{cad_validation_deferred:true,source_baselines:[{path:inspection.path,sha256:inspection.sha256,identity:["source-id"],source_types:["template_layout"],requested_layouts:inspection.requested_layouts}],derived_document:{subsets:[]},groups:[]}}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",async route=>{executeBody=await route.request().postDataJSON();await route.fulfill({json:{id:"job-version",status:"FAILED",progress:0,attempt:1,files:[]}})});
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
  expect(previewBodies[0].cad_version).toBe("2016");await expect(page.getByText("前后有序结构")).toBeVisible();await expect(page.getByRole("columnheader",{name:"受影响图纸"})).toBeVisible();await expect(page.getByText("DWG 与布局差异")).toBeVisible();await expect(page.getByText("CAD 布局校验将在确认后执行")).toBeVisible();await expect(page.getByText("来源基准")).toBeVisible();await expect(page.getByText("abc123",{exact:true})).toBeVisible();await expect(page.getByText("A1模板",{exact:true}).first()).toBeVisible();await expect(page.getByText("[object Object]",{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);expect(executeBody.cad_version).toBe("2016");expect(executeBody.preview_digest).toBe("digest-2016");
  await page.getByRole("button",{name:"预览变更"}).click();await expect(page.getByText("完整变更预览")).toBeVisible();await expect(page.getByRole("banner").getByRole("combobox")).toHaveCount(0);
});

test("普通预览丢弃乱序响应并只执行冻结命令",async({page})=>{
  const gates=[deferred(),deferred(),deferred(),deferred()];const previewBodies:any[]=[];let executeBody:any=null;
  await page.route("**/api/workspaces/workspace-1/changes/preview",async route=>{const index=previewBodies.length;previewBodies.push(await route.request().postDataJSON());await gates[index].promise;await route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:`preview-${index+1}`}],diagnostics:[],affected_files:[`preview-${index+1}.dst`],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/changes/execute",async route=>{executeBody=await route.request().postDataJSON();await route.fulfill({json:{id:"job-race",status:"FAILED",progress:0,attempt:1,files:[]}})});
  // PLAN-DM-034：多次保存改为留在属性页签完成（预览经全局操作栏，两页签均可触发），
  // 规避「属性→图纸→属性」往返与预览浮层收展开的异步时序耦合（clean 空保存已由守卫阻断）
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"乱序A");
  await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(2);
  gates[1].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();gates[0].resolve();await expect(page.getByText("preview-2",{exact:true})).toBeVisible();await expect(page.getByText("preview-1",{exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"收起任务浮层"}).click();
  await saveSheetSetDraft(page,"乱序B");await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(3);await openDraftPop(page);await page.getByRole("button",{name:"清空"}).click();await closeDraftPop(page);gates[2].resolve();await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();
  await saveSheetSetDraft(page,"乱序C");await page.getByRole("button",{name:"预览变更"}).click();await expect.poll(()=>previewBodies.length).toBe(4);gates[3].resolve();await expect(page.getByText("preview-4",{exact:true})).toBeVisible();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect.poll(()=>executeBody).not.toBeNull();expect(executeBody.base_revision_id).toBe(previewBodies[3].base_revision_id);expect(executeBody.commands).toEqual(previewBodies[3].commands);expect(executeBody.commands).not.toBe(previewBodies[3].commands);
});

test("CSV 预览丢弃换文件和乱序响应并只导入冻结文本",async({page})=>{
  const gates=[deferred(),deferred(),deferred()];const previewBodies:any[]=[];let importBody:any=null;
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{const index=previewBodies.length;const body=await route.request().postDataJSON();previewBodies.push(body);const name=body.csv.match(/sheet,([^,]+)/)?.[1]??`属性${index}`;await gates[index].promise;await route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name,default_value:""}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}})});
  await page.route("**/api/workspaces/workspace-1/custom-properties/import",async route=>{importBody=await route.request().postDataJSON();await route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}})});
  await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"导入 CSV"}).click();const csvInput=page.getByLabel("属性 CSV 文件");const csv=(name:string)=>({name:`${name}.csv`,mimeType:"text/csv",buffer:Buffer.from(`type,name,default_value\nsheet,${name},\n`,"utf8")});
  await csvInput.setInputFiles(csv("A属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(1);await csvInput.setInputFiles(csv("B属性"));gates[0].resolve();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();await expect(page.locator(".csv-preview").getByText("A属性")).toHaveCount(0);
  await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(2);await csvInput.setInputFiles(csv("C属性"));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await expect.poll(()=>previewBodies.length).toBe(3);gates[2].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();gates[1].resolve();await expect(page.locator(".csv-preview").getByText("C属性")).toBeVisible();await expect(page.locator(".csv-preview").getByText("B属性")).toHaveCount(0);
  await page.getByRole("button",{name:"确认导入"}).click();await confirmModal(page,/确认导入/);await expect.poll(()=>importBody).not.toBeNull();expect(importBody).toEqual(previewBodies[2]);
});

test("非法 UTF-8 CSV 在本地阻断且不请求 API",async({page})=>{
  let previewCalls=0,importCalls=0;await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>{previewCalls++;return route.abort()});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>{importCalls++;return route.abort()});await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await page.getByRole("button",{name:"导入 CSV"}).click();
  await page.getByLabel("属性 CSV 文件").setInputFiles({name:"invalid.csv",mimeType:"text/csv",buffer:Buffer.from([0x74,0x79,0x70,0x65,0x0a,0xc3,0x28])});await expect(page.getByText("CSV 必须使用 UTF-8 编码",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"预览 CSV 导入"})).toBeHidden();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();expect(previewCalls).toBe(0);expect(importCalls).toBe(0);
});

test("CSV 导入确认模态为强确认：未勾选时确认按钮禁用",async({page})=>{
  // SPEC-DM-006 §6.2/§10.3：CSV 不得走弱确认旁路，与 §9.1 全部正式写入共用同一危险确认（danger+requireCheckbox+impactLines）
  await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"比例",default_value:"1:100",affected_sheet_count:2},{line:3,action:"skip",type:"sheet",name:"专业",default_value:"建筑",affected_sheet_count:0}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:null,status:"SUCCEEDED",progress:100,no_op:true,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByRole("button",{name:"导入 CSV"}).click();
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
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 A");
  await page.getByRole("button",{name:"关闭"}).click();
  const switching=selectDst(page,"C:\\B.dst");
  await expect.poll(()=>openCalls).toBe(2);
  const loadingWasVisible=await page.getByText("正在加载工作区…",{exact:true}).isVisible();
  // 任务 3 起旧编辑器区改名为左树右表工作区容器
  const editorWasVisible=await page.locator(".sheets-workspace").isVisible();
  openB.resolve();await switching;await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 B");await page.getByRole("button",{name:"导入 CSV"}).click();
  await expect(page.getByRole("button",{name:"确认写入"})).toBeDisabled();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  expect(loadingWasVisible).toBe(true);expect(editorWasVisible).toBe(false);expect(executeCalls).toBe(0);expect(importCalls).toBe(0);
});

test("多次打开及刷新与打开竞争时仅最新工作区生效",async({page})=>{
  const openA=deferred(),openB=deferred(),openC=deferred(),refreshC=deferred();let refreshStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst")){await openA.promise;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")})}if(path.endsWith("B.dst")){await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})}if(path.endsWith("C.dst")){await openC.promise;return route.fulfill({json:workspaceVersion("workspace-C","工作区 C","revision-C")})}return route.fulfill({json:workspaceVersion("workspace-D","工作区 D","revision-D")})});
  await page.route("**/api/workspaces/workspace-C/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{type:"C-preview"}],diagnostics:[],affected_files:["C.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-C/changes/execute",route=>route.fulfill({json:{id:"job-C",status:"SUCCEEDED",progress:100,files:[]}}));await page.route("**/api/workspaces/workspace-C",async route=>{refreshStarted=true;await refreshC.promise;await route.fulfill({json:workspaceVersion("workspace-C","工作区 C 刷新","revision-C2")})});
  await page.goto("/");
  await selectDst(page,"C:\\A.dst");await selectDst(page,"C:\\B.dst");await selectDst(page,"C:\\C.dst");
  openC.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 C");openB.resolve();openA.resolve();await page.waitForTimeout(100);await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 C");
  await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect.poll(()=>refreshStarted).toBe(true);
  // 执行成功已 discardDraft，此处关闭无未发布改动，不弹确认模态
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\D.dst");await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 D");refreshC.resolve();await page.waitForTimeout(100);await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 D");
});

test("切换工作区会关闭旧任务监控且忽略迟到终态",async({page})=>{
  await installMockEventSource(page);const openB=deferred();let refreshACalls=0,openBStarted=false;
  await page.route("**/api/workspaces/open",async route=>{const path=(await route.request().postDataJSON()).dst_path;if(path.endsWith("A.dst"))return route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")});openBStarted=true;await openB.promise;return route.fulfill({json:workspaceVersion("workspace-B","工作区 B","revision-B")})});
  await page.route("**/api/workspaces/workspace-A/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"A-command"}],diagnostics:[],affected_files:["A.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-A/changes/execute",route=>route.fulfill({json:{id:"job-A",workspace_id:"workspace-A",status:"QUEUED",progress:0,attempt:0,files:[]}}));await page.route("**/api/workspaces/workspace-A",route=>{refreshACalls++;return route.fulfill({json:workspaceVersion("workspace-A","工作区 A 被旧任务刷新","revision-A2")})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);await expect(page.getByText("任务 job-A")).toBeVisible();
  // 任务仍在排队，草稿命令未发布成功：关闭会弹确认模态
  await page.getByRole("button",{name:"关闭"}).click();await confirmModal(page,/确定关闭并放弃当前改动/);
  const switching=selectDst(page,"C:\\B.dst");await expect.poll(()=>openBStarted).toBe(true);await page.evaluate(()=>(window as any).__emitJob({id:"job-A",workspace_id:"workspace-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}));openB.resolve();await switching;await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 B");await page.waitForTimeout(100);
  expect(refreshACalls).toBe(0);await expect(page.getByText("任务 job-A")).toHaveCount(0);expect(await page.evaluate(()=>(window as any).__closedEventSources())).toBe(1);
});

test("关闭工作区后停留在未打开态时任务与修订面板不残留",async({page})=>{
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-close",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-close-1234567890",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();
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
  await selectDst(page,"C:\\B.dst");revisionList.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 B");await page.waitForTimeout(100);await expect(page.getByText("revision-A-old")).toHaveCount(0);
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\A.dst");await page.getByRole("tab",{name:"修订历史"}).click();await expectActionAppearance(page, ".revisions-view button");await page.getByRole("button",{name:"恢复预览"}).click();
  await page.getByRole("button",{name:"关闭"}).click();
  await selectDst(page,"C:\\B.dst");restorePreviewGate.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 B");await page.waitForTimeout(100);const restoreButton=page.getByRole("button",{name:"恢复为新修订"});if(await restoreButton.isVisible()){await restoreButton.click()}expect(restoreCalls).toBe(0);await expect(page.getByText("恢复确认")).toHaveCount(0);
});

test("恢复写入期间阻断冲突入口并在成功后刷新工作区与修订",async({page})=>{
  const restorePost=deferred();let openCalls=0,revisionCalls=0,previewCalls=0,restoreCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",async route=>{openCalls++;const path=(await route.request().postDataJSON()).dst_path;return route.fulfill({json:path.endsWith("B.dst")?workspaceVersion("workspace-B","工作区 B","revision-B"):workspaceVersion("workspace-A","工作区 A","revision-A")})});await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:revisionCalls===1?[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]:[{id:"revision-A-new",created_at:"2026-08-13T00:00:00Z",before_hash:"bbbbbbbb",result_hash:"cccccccc"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>{previewCalls++;return route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreCalls++;restoreStarted=true;await restorePost.promise;return route.fulfill({json:{id:"restore-job-A",status:"SUCCEEDED",progress:100,attempt:0,files:[]}})});await page.route("**/api/workspaces/workspace-A",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A 已恢复","revision-A2")}));
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"修订历史"}).click();await expectActionAppearance(page, ".revisions-view button");await page.getByRole("button",{name:"恢复预览"}).click();await expectActionAppearance(page, ".revisions-view .primary");await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await expect.poll(()=>restoreStarted).toBe(true);
  const restoringWasVisible=await page.getByText("正在恢复修订…",{exact:true}).isVisible();const closeWasDisabled=await page.getByRole("button",{name:"关闭"}).isDisabled();const historyWasDisabled=await page.getByRole("tab",{name:"修订历史"}).isDisabled();const previewButton=page.getByRole("button",{name:"恢复预览"});const previewWasDisabled=await previewButton.isDisabled();const confirmWasDisabled=await page.getByRole("button",{name:"恢复为新修订"}).isDisabled();if(!historyWasDisabled)await page.getByRole("tab",{name:"修订历史"}).click();if(!previewWasDisabled)await previewButton.click();
  restorePost.resolve();await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("工作区 A 已恢复");await page.getByRole("tab",{name:"修订历史"}).click();await expect(page.getByText("revision-A-new")).toBeVisible();
  // 恢复任务详情迁入任务浮层实施进度页签：刷新复位后先展开浮层
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("button",{name:"展开任务浮层"}).click();await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("任务 restore-job-A")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);
  expect(restoringWasVisible).toBe(true);expect(closeWasDisabled).toBe(true);expect(historyWasDisabled).toBe(true);expect(previewWasDisabled).toBe(true);expect(confirmWasDisabled).toBe(true);expect(openCalls).toBe(1);expect(revisionCalls).toBe(3);expect(previewCalls).toBe(1);expect(restoreCalls).toBe(1); // 3 次 = 首次切标签① + 恢复成功后自动刷新 + 断言后切回标签③（沿用旧按钮每次点击即加载语义）
});

test("恢复写入错误会显示消息并解除入口锁定",async({page})=>{
  const restorePost=deferred();let revisionCalls=0,restoreStarted=false;
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspaceVersion("workspace-A","工作区 A","revision-A")}));await page.route("**/api/revisions?workspace_id=workspace-A",route=>{revisionCalls++;return route.fulfill({json:[{id:"revision-A-old",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]})});await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore-preview",route=>route.fulfill({json:{revision_id:"revision-A-old",executable:true,files:[{path:"A.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-A/revisions/revision-A-old/restore",async route=>{restoreStarted=true;await restorePost.promise;return route.fulfill({status:500,json:{message:"恢复失败"}})});
  await openWorkspace(page,"C:\\A.dst");
  await page.getByRole("tab",{name:"修订历史"}).click();await expectActionAppearance(page, ".revisions-view button");await page.getByRole("button",{name:"恢复预览"}).click();await expectActionAppearance(page, ".revisions-view .primary");await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await expect.poll(()=>restoreStarted).toBe(true);await expect(page.getByText("正在恢复修订…",{exact:true})).toBeVisible();restorePost.resolve();// PLAN-DM-021 Task 9（I18N-11）：无 message_key 的错误按未知错误呈现——本地化摘要为主提示，原文在诊断详情
  await expect(page.locator("p.error.notice")).toContainText("操作失败，发生未知错误");await expect(page.locator("details.error.notice").getByText("恢复失败")).toBeHidden();await page.locator("details.error.notice").getByText("原始错误详情").click();await expect(page.locator("details.error.notice").getByText("恢复失败")).toBeVisible();await expect(page.getByText("正在恢复修订…",{exact:true})).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭"})).toBeEnabled();await expect(page.getByRole("tab",{name:"修订历史"})).toBeEnabled();await page.getByRole("tab",{name:"修订历史"}).click();expect(revisionCalls).toBe(2);await page.getByRole("tab",{name:"图纸"}).click();await expect(page.locator(".sheets-workspace")).toBeVisible();
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
  // PLAN-DM-021 Task 9：模拟后端统一错误结构（已知 code 携带 message_key）
  await page.route("**/api/layout-names",(route)=>route.fulfill({status:502,json:{code:"LAYOUT_READ_FAILED",message_key:"errors.layout.readFailed",params:{},message:"读取布局失败"}}));
  await openWorkspace(page);
  await page.getByRole("button",{name:"新增图纸"}).click();
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:/tpl/frame.dwg"});
  await page.getByRole("button",{name:"选择模板文件"}).click();
  await expect(page.getByText("读取布局失败，DWG 可能正被占用或 CAD 环境不可用")).toBeVisible();
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
  await installPreferenceSnapshot(page,"light","2016");
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
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\source2.dwg"});await page.getByRole("button",{name:"选择模板文件"}).click();
  expect(layoutBodies.at(-1).cad_version).toBe("2016");
});

test("属性命令与结构命令分批并支持 CSV 行级预览导入",async({page})=>{
  let importedCsv="";await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",async route=>{importedCsv=(await route.request().postDataJSON()).csv;await route.fulfill({json:{executable:false,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[{line:3,severity:"error",code:"CUSTOM_PROPERTY_NAME_EMPTY",message:"名称不能为空"}],affected_files:["test.dst"],execution_intent:null}})});await page.route("**/api/workspaces/workspace-1/custom-properties/import",route=>route.fulfill({json:{id:"csv-job",status:"SUCCEEDED",progress:100,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.getByRole("link",{name:"下载 CSV 模板"})).toHaveAttribute("href","/api/custom-properties/template");await expect(page.getByRole("link",{name:"导出当前属性"})).toHaveAttribute("href","/api/workspaces/workspace-1/custom-properties/export");await page.getByRole("button",{name:"导入 CSV"}).click();await page.getByLabel("属性 CSV 文件").setInputFiles({name:"properties.csv",mimeType:"text/csv",buffer:Buffer.from("type,name,default_value\nsheet,专业,燃气\nsheet,,\n","utf8")});await page.getByRole("button",{name:"预览 CSV 导入"}).click();expect(importedCsv).toContain("sheet,专业,燃气");await expect(page.getByText("第 3 行")).toBeVisible();await expect(page.getByText("CUSTOM_PROPERTY_NAME_EMPTY")).toBeVisible();await expect(page.getByRole("button",{name:"确认导入"})).toBeDisabled();
  await page.unroute("**/api/workspaces/workspace-1/custom-properties/import/preview");await page.route("**/api/workspaces/workspace-1/custom-properties/import/preview",route=>route.fulfill({json:{executable:true,changes:[{line:2,action:"add",type:"sheet",name:"专业",default_value:"燃气"}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.getByRole("button",{name:"预览 CSV 导入"}).click();await page.getByRole("button",{name:"确认导入"}).click();await confirmModal(page,/确认导入/);
  // CSV 导入任务迁入任务浮层实施进度页签：刷新复位后先展开浮层
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("button",{name:"展开任务浮层"}).click();await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("任务 csv-job")).toBeVisible();
});

test("失败任务显示逐 DWG 详情并可安全重试",async({page})=>{
  await installMockEventSource(page);await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,duration_ms:600000,error_code:"CAD_TIMEOUT"}]}}));await page.route("**/api/jobs/job-failed/retry",route=>route.fulfill({json:{id:"job-failed",status:"QUEUED",progress:0,attempt:1,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  // 失败任务详情迁入任务浮层实施进度页签：预览已展开浮层，切到实施进度页签再断言逐 DWG 详情
  const overlay=page.getByRole("complementary",{name:"任务浮层"});await overlay.getByRole("tab",{name:"实施进度"}).click();await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();await expect(page.getByText("A.dwg")).toBeVisible();await expect(page.getByText("检查 CAD 日志")).toBeVisible();await expectActionAppearance(page, ".job-detail button");await page.getByRole("button",{name:"安全重试"}).click();await expect(page.getByText(/已排队 · 0% · 第 1 次/)).toBeVisible();
  // 第 N 次跟随 payload attempt 原值渲染（I18N-12：任务域不加工数据，与下方 SSE 用例第 1 次口径一致）
});

test("修订恢复先预览再确认为新修订",async({page})=>{
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-1",status:"SUCCEEDED",progress:100,attempt:0,files:[]}}));await openWorkspace(page);await page.getByRole("tab",{name:"修订历史"}).click();await expectActionAppearance(page, ".revisions-view button");await page.getByRole("button",{name:"恢复预览"}).click();await expect(page.getByText("replace test.dst")).toBeVisible();await expectActionAppearance(page, ".revisions-view .primary");await page.getByRole("button",{name:"恢复为新修订"}).click();await confirmModal(page,/确认恢复/);await page.getByRole("tab",{name:"属性"}).click();await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("测试图纸集");
});

test("恢复直返终态 FAILED 时任务浮层自动展开到实施进度页签",async({page})=>{
  // fix round 1 回归：后端 restore 为同步发布可直返终态 FAILED（不设 error），任务详情不得再藏进折叠浮层——setJob 收到任何状态均展开浮层到实施进度页签
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore",route=>route.fulfill({json:{id:"restore-failed",status:"FAILED",progress:40,attempt:1,error_code:"RESTORE_FAILED",suggestion:"检查原文件",files:[{target_path:"test.dst",status:"FAILED",progress:0,error_code:"RESTORE_FAILED"}]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"修订历史"}).click();
  await expectActionAppearance(page, ".revisions-view button");await page.getByRole("button",{name:"恢复预览"}).click();
  await expect(page.getByText("replace test.dst")).toBeVisible();
  await expectActionAppearance(page, ".revisions-view .primary");await page.getByRole("button",{name:"恢复为新修订"}).click();
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
  // 确认前普通编辑发布被禁用；浮层展开覆盖属性面板，先收起再继续属性编辑。
  // PLAN-DM-034：等草稿投影基准加载完成后再制造真实差异并保存（clean 空保存已由守卫阻断）；
  // 修复门禁下草稿缓冲保存仍允许，但「预览变更」保持禁用——这是修复门禁语义，不是 clean 语义禁用
  await page.getByRole("button",{name:"收起任务浮层"}).click();await page.getByRole("tab",{name:"属性"}).click();
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveValue("测试图纸集");
  await saveSheetSetDraft(page,"草稿名");
  await page.getByRole("tab",{name:"图纸"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeDisabled();
  await overlay.getByRole("button",{name:"展开任务浮层"}).click();await overlay.getByRole("tab",{name:"诊断"}).click();
  await page.getByRole("button",{name:"预览并确认修复"}).click();
  await expect(page.getByText(/修复 1 项 · 摘要 digest-12345678/)).toBeVisible();
  await page.getByRole("button",{name:"确认发布修复修订"}).click();
  await confirmModal(page,/确认把内存修复发布/);
  // 修复直接返回 SUCCEEDED 且刷新后浮层复位（overlayOpen=false）：重新展开到实施进度页签查看任务
  await overlay.getByRole("button",{name:"展开任务浮层"}).click();
  await overlay.getByRole("tab",{name:"实施进度"}).click();
  await expect(page.getByText("任务 repair-job")).toBeVisible();
  // 修复成功后刷新为 VALID，修复面板消失且普通编辑恢复。
  // PLAN-DM-034：首次保存的「草稿名」仍是草稿投影基准，二次保存须用新值制造真实差异
  await expect(page.getByText("已修复（待确认）")).toHaveCount(0);
  await expect(page.getByText("DST 修复状态")).toHaveCount(0);
  await page.getByRole("button",{name:"收起任务浮层"}).click();await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名2");await page.getByRole("tab",{name:"图纸"}).click();
  await expect(page.getByRole("button",{name:"预览变更"})).toBeEnabled();
});

test("发布确认模态必须显式勾选后才可提交",async({page})=>{
  // 前置 mock 构造预览有效态（跟随既有发布流程用例）
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-gate",status:"FAILED",progress:0,attempt:1,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  // 先打开发布模态（requireCheckbox + impactLines + 不可逆）并取消
  await page.getByRole("button",{name:"确认写入"}).click();
  const gated=page.getByRole("dialog");
  await expect(gated.getByText("不可逆",{exact:true})).toBeVisible();
  await gated.getByRole("button",{name:"取消"}).click();
  await expect(gated).toHaveCount(0);
  // 再触发单张图纸删除（低风险：danger:false、无勾选）
  await page.getByRole("button",{name:"收起任务浮层"}).click();
  await page.locator(".sheet-table-window tbody tr").filter({has:page.getByText("001",{exact:true})}).getByRole("button",{name:"删除"}).click();
  const lowRisk=page.getByRole("dialog");
  await expect(lowRisk).toBeVisible();
  await expect(lowRisk.getByRole("checkbox")).toHaveCount(0);
  await expect(lowRisk.getByText("不可逆",{exact:true})).toHaveCount(0);
  await expect(lowRisk.locator(".modal-impact")).toHaveCount(0);
  await expect(lowRisk.getByRole("button",{name:/加入删除草稿/})).toBeEnabled();
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
  // PLAN-DM-021 Task 4：选择调用以固定种类 "dst" 发起，描述来自语言包（白名单由壳侧拼接）
  expect(await page.evaluate(() => (window as any).__selectFileCalls)).toEqual([
    {fileKind: "dst", description: "DST 文件"},
  ]);
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();await page.getByRole("button",{name:"预览变更"}).click();await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  await expect.poll(()=>refreshStarted).toBe(true);
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  refreshGate.resolve();await page.waitForTimeout(100);
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible();
  await expect(page.getByLabel("图纸集名称", {exact: true})).toHaveCount(0);await expect(page.getByRole("button",{name:"关闭工作区"})).toHaveCount(0);
});

test("壳桥延迟注入（pywebviewready）时初始界面切换为文件选择区",async({page})=>{
  await page.goto("/?late-bridge");
  // 注入前：无壳降级态（浏览器场景）
  await expect(page.getByRole("button",{name:"打开项目"})).toBeVisible();
  // load 后 30ms 注入桥并派发 pywebviewready：界面应切换，而非永远停留在降级态
  await expect(page.getByRole("button",{name:"选择 DST 文件"})).toBeVisible({timeout:5000});
  await expect(page.getByRole("button",{name:"打开项目"})).toHaveCount(0);
});

test("顶栏主题切换只在当前会话生效，刷新恢复配置中心主题",async({page})=>{
  await installPreferenceSnapshot(page,"light");
  await page.goto("/");
  await page.getByRole("button",{name:"切换主题"}).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme","light");
});

test("深色模式下中心视图区域随主题切换背景",async({page})=>{
  // 回归：旧单页样式块硬编码 background:white，中心区域不随 data-theme 切换
  await installPreferenceSnapshot(page,"dark");
  await openWorkspace(page);
  for(const [selector,token] of [[".sheets-workspace","--color-bg-canvas"],[".sheet-list-card","--color-bg-surface"]]) {
    const colors=await page.locator(selector).evaluate((el,name)=>{
      const probe=document.createElement("span");probe.style.color=`var(${name})`;el.append(probe);
      const expected=getComputedStyle(probe).color;probe.remove();
      return {actual:getComputedStyle(el).backgroundColor,expected};
    },token);
    expect(colors.actual).toBe(colors.expected);
  }
});

test("深色模式下文本输入框与下拉选单随主题切换背景",async({page})=>{
  // 回归：旧样式块只设 input/select 的 padding/border，背景落到 UA 默认白底且未声明 color-scheme
  await installPreferenceSnapshot(page,"dark");
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
  await saveSheetSetDraft(page,"草稿名");
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
  await page.getByLabel("图纸集名称", {exact: true}).fill("新名称");
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
  await saveSheetSetDraft(page,"草稿名");
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
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
  await saveSheetSetDraft(page,"草稿名");
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay).toBeVisible();
  await expect(overlay.getByRole("tab",{name:"修改预览"})).toHaveAttribute("aria-selected","true");
  await expect(overlay.getByRole("region",{name:"修改预览",exact:true})).toBeVisible();
  await expect(overlay.getByRole("button",{name:"修改预览",exact:true})).toHaveAttribute("aria-expanded","true");
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
  // 阻断红点已从 Unicode `●` 迁到 `UiIcon name="status-dot"`（Task 4 Step 2 的图形清单）：
  // 图标对读屏隐藏，因此按本仓自有钩子类断言可见性，而不是断言页签文本里含字形。
  await expect(overlay.getByRole("tab",{name:/诊断/}).locator(".ov-dot")).toBeVisible();
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
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
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
  // Task 4 迁移轮 2：关闭按钮由 `✕` 字形改为 `UiIconButton`（`.toast-actions .ui-icon-button`，
  // 尺寸由 `--icon-button-size` 给到 36×36），「查看」仍是有可见文案的描边按钮（`.toast-view`）。
  // 本用例原先只按可访问名定位，旧的裸 `<button class="toast-close">✕</button>` 同样能通过，
  // 所以补上结构与尺寸断言，作为提示宿主迁移的回归网。
  const closeBtn=toast.locator(".toast-actions .ui-icon-button");
  await expect(closeBtn).toHaveAttribute("aria-label","忽略通知");
  const closeBox=(await closeBtn.boundingBox())!;
  expect.soft(Math.round(closeBox.width),"toast 关闭按钮宽度").toBe(36);
  expect.soft(Math.round(closeBox.height),"toast 关闭按钮高度").toBe(36);
  await expect(toast.locator(".toast-actions .toast-view")).toHaveText("查看");
  await toast.getByRole("button",{name:"查看"}).click();
  await expect(page.getByRole("complementary",{name:"任务浮层"}).getByRole("tab",{name:"实施进度"})).toHaveAttribute("aria-selected","true");
  // Task 5 起关闭按钮带 aria-label（忽略通知），可访问名不再依赖 ✕ 字形
  await toast.getByRole("button",{name:"忽略通知"}).click();
  await expect(toast).toHaveCount(0);
});

test("发布回滚终态展示可读真因：toast 与实施进度面板均带 error_detail",async({page})=>{
  // 回归 2026-09-14：PUBLISH_ROLLED_BACK 只是终态结论（写盘中途失败、已整批回滚），
  // 界面若只显示错误码则无法排查；需把后端 error_detail 同时呈现到失败 toast 与实施进度面板
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-detail",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();await confirmModal(page,/确认发布/);
  const detail="发布日志写入失败（已按瞬时占用退避重试 5 次仍被拒绝）：[WinError 5] 拒绝访问";
  // 折叠浮层后 toast 抑制规则（overlayOpen&&overlayTab==="prog"）不命中
  await page.getByRole("complementary",{name:"任务浮层"}).getByRole("button",{name:"收起任务浮层"}).click();
  await page.evaluate(payload=>(window as any).__emitJob(payload),{id:"job-detail",workspace_id:"workspace-1",status:"ROLLED_BACK",progress:100,attempt:1,error_code:"PUBLISH_ROLLED_BACK",error_detail:detail,files:[]});
  // 失败 toast 常驻并带真因（而非仅错误码）
  const toast=page.getByRole("alert").filter({hasText:"任务失败"});
  await expect(toast).toContainText("PUBLISH_ROLLED_BACK，整批未发布");
  await expect(toast).toContainText(`原因：${detail}`);
  // 从 toast "查看"回到浮层实施进度页签：面板同样展示错误码与真因
  await toast.getByRole("button",{name:"查看"}).click();
  const overlay=page.getByRole("complementary",{name:"任务浮层"});
  await expect(overlay.getByRole("tab",{name:"实施进度"})).toHaveAttribute("aria-selected","true");
  await expect(overlay.getByText("PUBLISH_ROLLED_BACK")).toBeVisible();
  await expect(overlay.getByText(`原因：${detail}`)).toBeVisible();
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

// —— PLAN-DM-021 Task 5：共享外壳、通用组件与格式化双语（SPEC-DM-013 I18N-06/07/08）——
// 本节用 page 级路由提供语言来源（响应快照 ui_locale=en-US），不写全局 settings.json：
// 壳层用例只消费语言来源，并行 worker 下写共享配置文件会与既有中文基线用例串扰；
// 真实设置读写与保存切换事务已由 settings-dialog.spec 以真实后端承担。
// 切换不变量用例只拦截 PUT（GET 仍走真实后端 zh-CN 基线）：保存成功响应驱动前端
// applyLocale 事务，语言切换本身是前端行为，无需真实落盘。
const enSettingsSnapshot={
  schema_version:1,config_revision:1,diagnostics:[],schema_blocked:false,
  items:[{key:"ui_locale",control:"enum",value:"en-US",default:"system",source:"file",has_file_override:true,
    label_key:"settings.items.uiLocale",category_key:"settings.categories.interface",
    options:[{value:"system",text_key:"settings.locale.system"},{value:"zh-CN",text_key:"settings.locale.zhCN"},{value:"en-US",text_key:"settings.locale.enUS"}]}],
};

test("英文界面：欢迎区、顶栏、标签栏与操作栏双语渲染",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang","en-US");
  // 欢迎区（空状态）：标题、描述、主按钮与拖拽提示
  await expect(page.getByRole("region",{name:"Open Sheet Set"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Open Sheet Set"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Select DST File"})).toBeVisible();
  await expect(page.getByText("Or drag a .dst file into the window · drag and drop supported")).toBeVisible();
await selectDst(page,"C:\\project\\test.dst","Select DST File");
  // 顶栏：文件夹入口、关闭与主题/设置入口；AutoCAD 版本只在配置中心选择。
  // （2026-09-18 全量回归修正：v0.3 副标题 tagline 已在 95fe260 品牌标志改版中从顶栏移除，
  // 断言跟随现行 UI 删除；该失败先于 PLAN-DM-034 存在，非本轮行为变更引入。）
  await expect(page.getByRole("button",{name:"Open the folder containing the sheet set"})).toBeVisible();
  await expect(page.getByRole("banner").getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("button",{name:"Close"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Toggle theme"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Settings"})).toBeVisible();
  // 用户数据不翻译：图纸集名称原样显示（顶栏工作区名）
  await expect(page.locator(".workspace-name")).toHaveText("测试图纸集");
  // 标签栏：role=tablist 名称与三个页签（激活态保留在图纸页）
  await expect(page.getByRole("tablist",{name:"Sections"})).toBeVisible();
  await expect(page.getByRole("tab",{name:"Sheets"})).toHaveAttribute("aria-selected","true");
  await expect(page.getByRole("tab",{name:"Properties"})).toBeVisible();
  await expect(page.getByRole("tab",{name:"Revision History"})).toBeVisible();
  await expect(page.getByTitle("Reserved for future features: settings / plotting / sheet catalog generation")).toBeVisible();
  // 操作栏：草稿芯片（数字插值）、撤销/重做/预览/写入与禁用原因
  await expect(page.getByText("Draft 0/0")).toBeVisible();
  await expect(page.getByRole("button",{name:"Undo"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Redo"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Preview Changes"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Confirm Write"})).toBeVisible();
  await expect(page.getByText("No changes to publish")).toBeVisible();
});

test("英文界面：草稿恢复横幅计数、快捷键提示与任务浮层空状态",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  // 载入即恢复 1 条草稿动作：恢复横幅计数插值
  await page.route("**/api/workspaces/workspace-1/draft",async route=>{
    if(route.request().method()!=="GET")return route.fallback();
    return route.fulfill({json:{corrupted:false,stale:false,stale_reasons:[],draft:{schema_version:1,base_revision_id:"revision-1",repair_status:"VALID",expected_version:1,version:1,cursor:1,workspace_id:"workspace-1",actions:[{id:"a1",kind:"command_batch",label:"更新图纸集",commands:[{type:"update_sheet_set",name:"改名集",custom_properties:{项目号:"P-001"}}]}]}}});
  });
  await page.goto("/");
await selectDst(page,"C:\\project\\test.dst","Select DST File");
  // 恢复横幅（计数插值）与两个动作按钮
  await expect(page.getByText("Restored 1 unfinished change from the last session")).toBeVisible();
  await expect(page.getByRole("button",{name:"Resume"})).toBeVisible();
  await expect(page.getByRole("button",{name:"Start Over"})).toBeVisible();
  // 快捷键提示：Ctrl+O 在已打开工作区时给出英文关闭提示
  await page.keyboard.press("Control+o");
  await expect(page.locator(".error.notice")).toHaveText("Close the current workspace before opening a new DST file");
  // Ctrl+S 写入：存在未预览草稿命令时的英文禁用原因（快捷键提示走错误条，静态原因走 dock 内联文本）
  await page.keyboard.press("Control+s");
  await expect(page.locator(".error.notice")).toHaveText("Preview first");
  await expect(page.locator(".dock-reason")).toHaveText("Preview first");
  // 任务浮层：页签与空状态（无阻断诊断）
  await page.getByRole("complementary",{name:"Task overlay"}).getByRole("button",{name:"Implementation Progress"}).click();
  await expect(page.getByRole("region",{name:"Implementation Progress"})).toBeVisible();
  await expect(page.getByRole("tab",{name:"Diagnostics"})).toBeVisible();
  await page.getByRole("tab",{name:"Diagnostics"}).click();
  await expect(page.getByText("No blocking diagnostics")).toBeVisible();
  await expect(page.getByRole("button",{name:"Collapse task overlay"})).toBeVisible();
});

test("英文界面：删除确认框与 Toast 双语且图纸编号保持原样",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.goto("/");
await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("button",{name:"Delete",exact:true}).first().click();
  // 确认框：标题/正文/确认按钮双语，图纸编号（用户数据）原样
  const modal=page.locator('[role="dialog"][aria-modal="true"]');
  await expect(modal).toBeVisible();
  await expect(modal.getByRole("button",{name:"Add to Delete Draft"})).toBeVisible();
  await expect(modal.getByText("Delete sheet 001?")).toBeVisible();
  await modal.getByRole("button",{name:"Add to Delete Draft"}).click();
  // Toast：标题/正文双语且编号不翻译
  const toast=page.locator(".toast").first();
  await expect(toast).toBeVisible();
  await expect(toast.getByText("Added to Delete Draft")).toBeVisible();
  await expect(toast.getByText("Sheet 001 has been added to the delete draft; view or undo it in the draft stack.")).toBeVisible();
  await expect(toast.getByRole("button",{name:"Dismiss notification"})).toBeVisible();
});

test("英文界面：发布确认模态（不可逆标记与危险勾选）双语",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-en",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  // 批量属性流程入草稿（Task 6 起图纸页域控件随语言切换），随后走英文预览/写入门禁
  await page.getByRole("checkbox",{name:"Select all results"}).check();
  await page.getByRole("button",{name:"Batch Edit Properties"}).click();
  await page.getByLabel("Existing sheet property").selectOption("比例");
  await page.getByLabel("Batch value").fill("1:200");
  await page.getByRole("button",{name:"Add Batch to Draft"}).click();
  await page.getByRole("button",{name:"Preview Changes"}).click();
  await page.getByRole("button",{name:"Confirm Write"}).click();
  const modal=page.locator('[role="dialog"][aria-modal="true"]');
  await expect(modal.getByRole("heading",{name:"Confirm Publish"})).toBeVisible();
  await expect(modal.getByText("The original DST and affected DWGs will be backed up permanently.")).toBeVisible();
  await expect(modal.locator(".modal-irr")).toHaveText("Irreversible");
  await expect(modal.getByText("I understand this operation is Irreversible and have reviewed the list of affected content")).toBeVisible();
  await modal.getByRole("checkbox").check();
  await modal.getByRole("button",{name:"Confirm Publish (original DST and affected DWGs backed up permanently)"}).click();
  await expect(page.getByText("A task is running")).toBeVisible(); // execute 后任务进行中（英文禁用原因）
});

test("语言切换不变量：保存成功后 active tab、工作区与未提交输入保持",async({page})=>{
  // 只拦截 PUT：保存成功响应返回 en-US 快照，驱动前端 applyLocale；不落盘、GET 仍为 zh-CN 基线
  await page.route("**/api/settings",async route=>{
    if(route.request().method()!=="PUT")return route.fallback();
    return route.fulfill({json:{...enSettingsSnapshot,config_revision:2}});
  });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang","zh-CN");
  await selectDst(page,"C:\\project\\test.dst");
  // 背景：属性页签 + 更新图纸集表单未提交输入（PLAN-DM-034：clean 空保存已由守卫阻断，
  // 直接以图纸集名称输入作为未提交输入，不再先做一次无差异保存）
  await page.getByRole("tab",{name:"属性"}).click();
  // 语言容忍定位：切换 en-US 后该输入的可访问名合法变为 "Sheet set name"（label/for 关联
  // 由 fieldId(key) 稳定绑定，不受语言影响），故仅值不变量断言用双语 label 正则匹配
  const nameInput=page.getByLabel(/^(图纸集名称|Sheet set name)$/);
  await nameInput.fill("改名后的图纸集");
  // 设置中心保存切换 en-US
  await openSettingsDialog(page);
  await page.locator('input[data-key="ui_locale"][value="en-US"]').check();
  await page.getByRole("button",{name:"保存"}).click();
  await expect(page.locator("html")).toHaveAttribute("lang","en-US");
  await expect(page.getByTestId("settings-saved-pill")).toHaveText("Saved"); // 对话框保持 + 本地化成功反馈
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog",{name:"Settings"})).toBeHidden();
  // 不变量：active tab 不变、工作区未重建（名称仍为投影前名称、顶栏入口仍在）、输入值保留
  await expect(page.getByRole("tab",{name:"Properties"})).toHaveAttribute("aria-selected","true");
  await expect(page.getByText("测试图纸集")).toBeVisible();
  await expect(page.getByRole("button",{name:"Open the folder containing the sheet set"})).toBeVisible();
  await expect(nameInput).toHaveValue("改名后的图纸集");
});

// —— PLAN-DM-021 Task 8：修订、预览、修复、草稿与任务状态双语（I18N-07/08/12）——
// 语言来源沿用 page 级 enSettingsSnapshot 路由；断言 SSE/任务/草稿 payload 保持稳定 code，
// 状态在语言切换前后语义不变；草稿动作持久化 label_key（语言不得写入草稿），渲染期经语言包翻译。

// 语言切换辅助：只拦截 PUT 驱动前端 applyLocale，GET 仍为 zh-CN 基线（同 Task 5 不变量用例）
async function switchToEnglish(page:Page){
  await page.route("**/api/settings",async route=>{
    if(route.request().method()!=="PUT")return route.fallback();
    return route.fulfill({json:{...enSettingsSnapshot,config_revision:2}});
  });
  await openSettingsDialog(page);
  await page.locator('input[data-key="ui_locale"][value="en-US"]').check();
  await page.getByRole("button",{name:"保存"}).click();
  await expect(page.locator("html")).toHaveAttribute("lang","en-US");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog",{name:"Settings"})).toBeHidden();
}

test("草稿动作持久化 label_key 且动作栈渲染随语言切换",async({page})=>{
  const draftPuts:any[]=[];
  await page.route("**/api/workspaces/*/draft",async route=>{
    if(route.request().method()==="PUT")draftPuts.push(await route.request().postDataJSON());
    return route.fallback();
  });
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await page.getByLabel("图纸集名称",{exact:true}).fill("改名集");
  await page.getByRole("button",{name:"更新图纸集"}).click();
  // 绑定修复（I18N-12）：草稿只持久化稳定 label_key，不写创建时语言文本
  await expect.poll(()=>draftPuts.length).toBeGreaterThan(0);
  const action=draftPuts.at(-1).actions.at(-1);
  expect(action.label_key).toBe("shell.commands.updateSheetSet");
  expect(action.label).toBeUndefined();
  await openDraftPop(page);
  await expect(page.getByText("更新图纸集 · 1 条命令")).toBeVisible();
  // 批量动作：label_key + 命名参数（属性名与数量是用户数据参数，不是语言文本）
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("checkbox",{name:"全选当前结果"}).check();
  await page.getByRole("button",{name:"批量修改属性"}).click();
  await page.getByLabel("既有图纸属性").selectOption("比例");
  await page.getByLabel("批量值").fill("1:200");
  await page.getByRole("button",{name:"批量加入草稿"}).click();
  await expect.poll(()=>draftPuts.length).toBeGreaterThan(1);
  const bulk=draftPuts.at(-1).actions.at(-1);
  expect(bulk.label_key).toBe("shell.flows.bulk.setLabel");
  expect(bulk.params).toEqual({name:"比例",count:2});
  // 渲染期翻译：切换语言后同一存储键渲染为英文（语言不写入草稿）
  await switchToEnglish(page);
  await openDraftPop(page);
  await expect(page.getByText("Update Sheet Set · 1 command")).toBeVisible();
  await expect(page.getByText("Batch update 比例 (2 sheets) · 2 commands")).toBeVisible();
});

test("英文界面：完整变更预览双语且字段名与路径原样",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:true,changes:[{type:"number_range_changed",affected_sheet_count:2}],diagnostics:[],affected_files:["C:\\project\\test.dst","C:\\project\\001-002.dwg"],semantic_diff:{sheet_set:[{field:"name",before:"旧名称",after:"新名称"}],structure:{before:[],after:[]},properties:[{action:"update",type:"sheetset",name:"项目号",before:"P-001",after:"P-002",affected_sheet_count:2}],dwgs:[]},execution_intent:{cad_validation_deferred:true,cardinality_frontier:{index:1,subset_id:"subset-2"},estimate:{core_console_count:1,concurrency:2,duration_ms:{lower:1000,upper:2000},sources:[{cad_operation:"rename_only",source:"history",sample_count:1}]},subset_operations:[{subset_id:"subset-1",cad_operation:"rename_only",target_file:"C:\\project\\001-002.dwg",in_cardinality_scope:false}],source_baselines:[{path:"C:\\project\\001-002.dwg",sha256:"source-sha-256",identity:["source-id"],source_types:["existing_snapshot"],requested_layouts:["001 第一册(一)"]},],groups:[{subset_id:"subset-1",cad_operation:"rename_only",subset_name:"第一册",target_file:"C:\\project\\001-002.dwg",layouts:[]}]}}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("checkbox",{name:"Select all results"}).check();
  await page.getByRole("button",{name:"Batch Edit Properties"}).click();
  await page.getByLabel("Existing sheet property").selectOption("比例");
  await page.getByLabel("Batch value").fill("1:200");
  await page.getByRole("button",{name:"Add Batch to Draft"}).click();
  await page.getByRole("button",{name:"Preview Changes"}).click();
  // 标题与分节双语；CAD 操作码 → 语义键
  await expect(page.getByRole("heading",{name:"Full Change Preview"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Core Console Estimate"})).toBeVisible();
  await expect(page.getByText(/Estimated 1 task · concurrency \d+/)).toBeVisible();
  await expect(page.getByText("Batch rename layouts",{exact:true}).first()).toBeVisible();
  await expect(page.getByText("Cardinality frontier: subset 2")).toBeVisible();
  await expect(page.getByText("Source baselines")).toBeVisible();
  await expect(page.getByText("Sheet set field differences")).toBeVisible();
  await expect(page.getByText("Property differences")).toBeVisible();
  await expect(page.getByText("Affected sheets: 2")).toBeVisible();
  await expect(page.getByText("CAD layout validation will run after confirmation")).toBeVisible();
  await expect(page.getByText("Compatibility change list")).toBeVisible();
  await expect(page.getByText("CAD execution groups")).toBeVisible();
  await expect(page.getByText("No blocking diagnostics")).toBeVisible();
  // 用户数据与协议值原样：属性名、路径、哈希
  await expect(page.getByText("项目号",{exact:true})).toBeVisible();
  await expect(page.getByText("source-sha-256",{exact:true})).toBeVisible();
});

test("英文界面：任务状态双语、错误码原样且安全重试不变",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-en-failed",status:"FAILED",progress:40,attempt:1,error_code:"CAD_TIMEOUT",suggestion:"检查 CAD 日志",files:[{target_path:"A.dwg",status:"FAILED",progress:0,started_at:"2026-08-26T10:00:00Z",finished_at:"2026-08-26T10:00:05Z",duration_ms:5000,error_code:"CAD_TIMEOUT"}]}}));
  await page.route("**/api/jobs/job-en-failed/retry",route=>route.fulfill({json:{id:"job-en-failed",status:"QUEUED",progress:0,attempt:2,files:[]}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("tab",{name:"Properties"}).click();
  await page.getByLabel("Sheet set name",{exact:true}).fill("Renamed set"); // PLAN-DM-034：clean 空保存已由守卫阻断，先制造真实差异
  await page.getByRole("button",{name:"Update Sheet Set"}).click();
  await page.getByRole("tab",{name:"Sheets"}).click();
  await page.getByRole("button",{name:"Preview Changes"}).click();
  await page.getByRole("button",{name:"Confirm Write"}).click();
  await confirmModal(page,/Confirm Publish/);
  const overlay=page.getByRole("complementary",{name:"Task overlay"});
  await overlay.getByRole("tab",{name:"Implementation Progress"}).click();
  // 状态码 → 语义键（英文渲染）；错误码、DWG 名与后端消息保持原样
  await expect(page.getByText("Failed",{exact:true}).first()).toBeVisible();
  await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();
  await expect(page.getByText("A.dwg")).toBeVisible();
  await expect(page.getByText("检查 CAD 日志")).toBeVisible();
  // 日期本地化（en-US 日期时间格式）
  const expectedStarted=new Intl.DateTimeFormat("en-US",{dateStyle:"medium",timeStyle:"medium"}).format(new Date("2026-08-26T10:00:00Z"));
  await expect(page.getByText(expectedStarted,{exact:true})).toBeVisible();
  // 重试请求不携带语言：状态码 QUEUED 以英文语义键渲染
  await page.getByRole("button",{name:"Safe Retry"}).click();
  await expect(page.getByText(/Queued · 0% · Attempt 2/)).toBeVisible();
});

test("英文界面：NEEDS_REVIEW 锁定写入且重试禁止提示双语",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-review",status:"NEEDS_REVIEW",progress:100,attempt:1,error_code:"PUBLISH_INCOMPLETE",files:[]}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("tab",{name:"Properties"}).click();
  await page.getByLabel("Sheet set name",{exact:true}).fill("Renamed set"); // PLAN-DM-034：clean 空保存已由守卫阻断，先制造真实差异
  await page.getByRole("button",{name:"Update Sheet Set"}).click();
  await page.getByRole("tab",{name:"Sheets"}).click();
  await page.getByRole("button",{name:"Preview Changes"}).click();
  await page.getByRole("button",{name:"Confirm Write"}).click();
  await confirmModal(page,/Confirm Publish/);
  // NEEDS_REVIEW 语义在英文下保持：写入锁定 + 状态渲染 + 重试禁止提示（英文）
  await expect(page.getByText("Needs manual review; direct retry is disabled").first()).toBeVisible();
  await page.getByRole("button",{name:"Safe Retry"}).click();
  await expect(page.locator(".error.notice")).toHaveText("The publish state needs manual review; direct retry is disabled");
});

test("语言切换不变量：任务运行/失败/需人工检查状态与 SSE code 保持",async({page})=>{
  await installMockEventSource(page);
  await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
  await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-switch-1",status:"QUEUED",progress:0,attempt:0,files:[]}}));
  await page.route("**/api/jobs/job-switch-1/retry",route=>route.fulfill({json:{id:"job-switch-1",status:"NEEDS_REVIEW",progress:100,attempt:2,files:[]}}));
  await openWorkspace(page);
  await page.getByRole("tab",{name:"属性"}).click();
  await saveSheetSetDraft(page,"草稿名");
  await page.getByRole("tab",{name:"图纸"}).click();
  await page.getByRole("button",{name:"预览变更"}).click();
  await page.getByRole("button",{name:"确认写入"}).click();
  await confirmModal(page,/确认发布/);
  // SSE payload 保持稳定 code：事件 URL 不携带语言参数；状态码渲染为当前语言
  await expect.poll(()=>page.evaluate(()=>(window as any).__eventSources.map((s:any)=>s.url))).toContain("/api/jobs/job-switch-1/events");
  await expect(page.getByText(/已排队 · 0% · 第 0 次/)).toBeVisible();
  await page.evaluate(()=>{(window as any).__emitJob({id:"job-switch-1",status:"RUNNING",progress:60,attempt:1,files:[]})});
  await expect(page.getByText(/执行中 · 60% · 第 1 次/)).toBeVisible();
  // 断线（SSE onerror）：connectionMode 落到轮询 code，渲染为当前语言且任务状态不变
  await page.evaluate(()=>(window as any).__eventSources.filter((s:any)=>!s.closed).forEach((s:any)=>s.onerror?.()));
  await expect(page.getByText(/轮询/)).toBeVisible();
  await expect(page.getByText(/执行中 · 60% · 第 1 次/)).toBeVisible();
  // 语言切换：任务不重建，状态语义不变（同一 code 渲染为英文）
  await switchToEnglish(page);
  await expect(page.getByText(/Running · 60% · Attempt 1/)).toBeVisible();
  await expect(page.getByText(/Polling/)).toBeVisible(); // 断线状态跨切换保持（渲染随语言）
  // 终态 FAILED：断线后经轮询到达（GET /api/jobs/:id 不携带语言），code 原样、安全重试仍可用
  await page.route("**/api/jobs/job-switch-1",route=>route.fulfill({json:{id:"job-switch-1",status:"FAILED",progress:60,attempt:1,error_code:"CAD_TIMEOUT",files:[]}}));
  await expect(page.getByText(/Failed · 60% · Attempt 1/)).toBeVisible();
  await expect(page.getByText("CAD_TIMEOUT").first()).toBeVisible();
  await page.getByRole("button",{name:"Safe Retry"}).click();
  await expect(page.getByText(/Needs review · 100% · Attempt 2/)).toBeVisible();
});

test("英文界面：修订历史双语且日期本地化，恢复预览冲突提示英文",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
  await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:true}]}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("tab",{name:"Revision History"}).click();
  await expect(page.getByRole("heading",{name:"Permanent Revisions"})).toBeVisible();
  // 日期本地化（en-US 格式）；修订 ID 与哈希前缀（用户数据）原样
  const expected=new Intl.DateTimeFormat("en-US",{dateStyle:"medium",timeStyle:"medium"}).format(new Date("2026-08-12T00:00:00Z"));
  await expect(page.getByText(expected,{exact:true})).toBeVisible();
  await expect(page.getByText("aaaaaaaa → bbbbbbbb")).toBeVisible();
  await page.getByRole("button",{name:"Restore Preview"}).first().click();
  // 恢复确认块渲染在修订历史面板（主视图），浮层仅切到修改预览页签
  await expect(page.getByRole("heading",{name:"Restore Confirmation"})).toBeVisible();
  // 协议 action 与路径原样；冲突提示双语
  await expect(page.getByText("replace test.dst")).toBeVisible();
  await expect(page.getByText("(current file conflict)")).toBeVisible();
  await expect(page.getByRole("button",{name:"Restore as New Revision"})).toBeVisible();
});

test("英文界面：修订历史空状态双语",async({page})=>{
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[]}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  await page.getByRole("tab",{name:"Revision History"}).click();
  await expect(page.getByRole("heading",{name:"No revision history yet"})).toBeVisible();
  await expect(page.getByText("After you publish the first change, every recoverable revision is recorded here.")).toBeVisible();
  await expect(page.getByText("Go to the Sheets tab to make the first change; it can be restored here after publishing.")).toBeVisible();
});

test("英文界面：修复状态、修复明细与确认发布双语",async({page})=>{
  const repaired:any=workspaceVersion("workspace-1","测试图纸集","revision-1");
  repaired.dst_validation={status:"REPAIRED",actions:[{code:"REPAIR_ATTR_MISSING",node_path:"/AcSmDatabase/AcSmSheetSet[@ID=\"x\"]/AcSmSheet",object_id:null,confidence:"deterministic",before:{clsid:null},after:{clsid:"g16A07941-BC15-4D48-A880-9D5A211D5065"},message:"补齐 AcSmSheet 的 clsid"}],blocking_issues:[]};
  const valid:any=workspaceVersion("workspace-1","测试图纸集","revision-2");
  valid.dst_validation={status:"VALID",actions:[],blocking_issues:[]};
  await page.route("**/api/settings",route=>route.fulfill({json:enSettingsSnapshot}));
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:repaired}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:valid}));
  await page.route("**/api/workspaces/workspace-1/repairs/preview",route=>route.fulfill({json:{status:"REPAIRED",actions:repaired.dst_validation.actions,blocking_issues:[],preview_digest:"digest-1234567890abcdef",executable:true}}));
  await page.route("**/api/workspaces/workspace-1/repairs/execute",route=>route.fulfill({json:{id:"repair-job-en",status:"SUCCEEDED",progress:100,files:[]}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst","Select DST File");
  const overlay=page.getByRole("complementary",{name:"Task overlay"});
  await overlay.getByRole("button",{name:"Expand task overlay"}).click();
  await overlay.getByRole("tab",{name:"Diagnostics"}).click();
  await expect(page.getByText("DST repair status: Repaired (awaiting confirmation)")).toBeVisible();
  await page.getByText("Repair details (1)").click();
  // 修复码、节点路径与后端消息保持原样
  await expect(page.getByText("REPAIR_ATTR_MISSING")).toBeVisible();
  await expect(page.getByText("/AcSmDatabase/AcSmSheetSet[@ID=\"x\"]/AcSmSheet")).toBeVisible();
  await expect(page.getByText("补齐 AcSmSheet 的 clsid")).toBeVisible();
  await page.getByRole("button",{name:"Preview and Confirm Repair"}).click();
  await expect(page.getByText(/1 repair item · summary digest-12345678/)).toBeVisible();
  await expect(page.getByRole("button",{name:"Cancel Confirmation"})).toBeVisible();
  await page.getByRole("button",{name:"Confirm Repair Revision Publication"}).click();
  await confirmModal(page,/Confirm publishing the in-memory repair/);
  await overlay.getByRole("button",{name:"Expand task overlay"}).click();
  await overlay.getByRole("tab",{name:"Implementation Progress"}).click();
  await expect(page.getByText("Job repair-job-en")).toBeVisible();
  // 修复成功后刷新为 VALID：修复面板消失
  await expect(page.getByText("DST repair status")).toHaveCount(0);
});

// ---- PLAN-DM-021 Task 9：统一错误结构渲染（ARCH-DM-005 §6.2 / I18N-11） ----

test("已知 API 错误按 message_key 渲染并忽略兼容 message",async({page})=>{
  await page.route("**/api/workspaces/open",route=>route.fulfill({status:404,json:{code:"WORKSPACE_NOT_FOUND",message_key:"errors.workspace.notFound",params:{},message:"【兼容】旧中文文本不应进入主提示"}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst");
  const notice=page.locator("p.error.notice");
  await expect(notice).toContainText("工作区不存在，请重新打开图纸集");
  // 已知错误：兼容 message 不进主提示，也不进诊断详情
  await expect(page.getByText("【兼容】旧中文文本不应进入主提示")).toHaveCount(0);
  await expect(page.locator("details.error.notice")).toHaveCount(0);
});

test("未知 API 错误显示本地化摘要、原文只在可展开诊断详情",async({page})=>{
  await page.route("**/api/workspaces/open",route=>route.fulfill({status:500,json:{code:"DRAFT_SAVE_FAILED",message:"保存失败"}}));
  await page.goto("/");
  await selectDst(page,"C:\\project\\test.dst");
  const notice=page.locator("p.error.notice");
  await expect(notice).toContainText("操作失败，发生未知错误");
  await expect(notice).not.toContainText("保存失败");
  // 原始文本只在可展开诊断详情：折叠时不可见，展开后可读
  const diagnostics=page.locator("details.error.notice");
  await expect(diagnostics).toContainText("原始错误详情");
  await expect(diagnostics.getByText("保存失败")).toBeHidden();
  await diagnostics.getByText("原始错误详情").click();
  await expect(diagnostics.getByText("保存失败")).toBeVisible();
});

// —— Task 2 全局样式分层与字体、尺寸令牌（ARCH-DM-007 §4.1/§4.2）——
// 本节只断言根层级事实：正文排版、等宽令牌解析结果、字体资源本地化。
// 组件级控件的 36px/38px/34px 尺寸族由 Task 3 起的原语用例承担，此处不重复。

test("Task 2 根层级：正文 14px/21px 且表单控件继承同一字体栈",async({page})=>{
  await openWorkspace(page);
  const probe=await page.evaluate(()=>{
    const body=getComputedStyle(document.body);
    const controls=["button","input","select","textarea"].map(tag=>{
      const el=document.createElement(tag);
      if(tag==="input")el.setAttribute("type","text");
      document.body.append(el);
      const value=getComputedStyle(el);
      const result={tag,family:value.fontFamily,size:value.fontSize,lineHeight:value.lineHeight};
      el.remove();
      return result;
    });
    return {size:body.fontSize,lineHeight:body.lineHeight,family:body.fontFamily,controls};
  });
  expect(probe.size).toBe("14px"); // --font-body 的字号一半
  expect(probe.lineHeight).toBe("21px"); // 14px × 1.5
  expect(probe.family.split(",")[0].replace(/["']/g,"").trim()).toBe("Inter");
  expect(probe.family).toContain("Microsoft YaHei"); // 中文回落到系统雅黑，不打包 CJK
  for(const control of probe.controls){
    // 重置层必须让表单控件 font:inherit；否则 Chrome 默认 400 13.33px Arial 会盖掉正文排版
    expect.soft(control.family,`${control.tag} 应继承正文字体栈`).toBe(probe.family);
    expect.soft(control.size,`${control.tag} 应继承正文字号`).toBe("14px");
    // `<select>` 是 Chromium 的固定例外：UA 层把它的 line-height 叼成 normal，
    // `font:inherit` 与显式 `line-height:inherit` 实测都改不动（见 task-2-report.md）。
    // select 的高度契约由 Task 3 的控件原语定死，这里不把浏览器怪癖当回归看。
    if(control.tag!=="select")expect.soft(control.lineHeight,`${control.tag} 应继承正文行高`).toBe("21px");
  }
});

test("Task 2 等宽令牌：--font-mono 解析为 IBM Plex Mono 优先",async({page})=>{
  await openWorkspace(page);
  const probe=await page.evaluate(()=>{
    const el=document.createElement("span");
    el.textContent="001-002.dwg";
    el.style.fontFamily="var(--font-mono)";
    document.body.append(el);
    const resolved=getComputedStyle(el).fontFamily;
    el.remove();
    return {resolved,token:getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim()};
  });
  expect(probe.token).toContain("IBM Plex Mono");
  expect(probe.resolved.split(",")[0].replace(/["']/g,"").trim()).toBe("IBM Plex Mono");
});

test("Task 2 字体资源：两套本地 WOFF2 且不引用远程 URL",async({page})=>{
  await openWorkspace(page);
  const faces=await page.evaluate(()=>{
    const found:{family:string;text:string;unicodeRange:string}[]=[];
    for(const sheet of Array.from(document.styleSheets)){
      let rules:CSSRule[]=[];
      try{rules=Array.from(sheet.cssRules)}catch{continue} // 跨域工作表跳过：本地资源不应出现
      for(const rule of rules){
        if(rule.type!==CSSRule.FONT_FACE_RULE)continue;
        const font=rule as CSSFontFaceRule;
        found.push({
          family:font.style.getPropertyValue("font-family").replace(/["']/g,"").trim(),
          text:font.cssText,
          unicodeRange:font.style.getPropertyValue("unicode-range"),
        });
      }
    }
    return found;
  });
  const local=faces.filter(face=>face.family==="Inter"||face.family==="IBM Plex Mono");
  expect(local.map(face=>face.family).sort()).toEqual(["IBM Plex Mono","Inter"]);
  // CSSOM 会把 unicode-range 归一化（去前导零、十六进制大写），因此不比对字面串，
  // 而是拆成码位区间后判定真实需求：覆盖 Basic Latin、不打包 CJK。
  const ranges=(value:string)=>value.split(",").map(part=>part.trim()).filter(Boolean).map(part=>{
    const [start,end=start]=part.replace(/^u\+/i,"").split("-");
    return {from:parseInt(start,16),to:parseInt(end,16)};
  });
  const covers=(value:string,from:number,to:number)=>ranges(value).some(range=>range.from<=from&&range.to>=to);
  for(const face of local){
    expect(face.text).toContain(".woff2");
    expect(face.text).not.toMatch(/https?:\/\//); // 离线可用，禁止 CDN
    expect(face.text).toContain("font-display: swap");
    expect.soft(covers(face.unicodeRange,0x20,0x7e),`${face.family} 应覆盖 Basic Latin`).toBe(true);
    expect.soft(covers(face.unicodeRange,0x4e00,0x9fff),`${face.family} 不得打包 CJK`).toBe(false);
  }
});

// ===== PLAN-DM-029 Task 12 责任 A：字体"真实加载"的运行时证据 =====
// Task 2 的三条用例（以及上方那条）只断言 **CSSOM 声明层**：`@font-face` 规则文本、
// `getComputedStyle()` 字体栈与 `unicode-range` 区间语义；它们**不能**证明两套 WOFF2 在运行时
// 真被请求、也不排除远程字体。本节补上运行时证据（这是责任 A 的收口要求）。
//
// 路径口径说明（避免误判）：e2e 跑在 `npm run dev`（playwright.config.ts 的 webServer）上，
// 字体地址因此是 `/src/assets/fonts/*.woff2`；生产构建由 Vite 拷贝为 `/assets/<name>-<hash>.woff2`。
// 本节断言同时适配两者（本地同源 + `.woff2` + 资产名），而「生产产物确实落在 `/assets/`」
// 是对 `dist/` 产物的检查，见 task-12-report.md（与 `check:ui` 的字体资产规则互补）。
test("Task 12 责任 A：两套 WOFF2 在运行时被真实请求、本地同源且无远程字体访问",async({page})=>{
  const fontRequests:{url:string;pathname:string}[]=[];
  const fontResponses:{url:string;status:number}[]=[];
  const remoteFontRequests:string[]=[];
  // 监听器必须在 `goto` **之前**挂上：字体请求发生在首帧渲染期间。
  page.on("request",(request)=>{if(request.resourceType()!=="font")return;fontRequests.push({url:request.url(),pathname:new URL(request.url()).pathname});});
  page.on("response",(response)=>{if(response.request().resourceType()!=="font")return;fontResponses.push({url:response.url(),status:response.status()});});
  page.on("request",(request)=>{const {hostname,protocol}=new URL(request.url());if(protocol.startsWith("http")&&!["127.0.0.1","localhost"].includes(hostname)&&/\.(woff2?|ttf|otf|eot)(\?|$)/.test(request.url()))remoteFontRequests.push(request.url());});

  await page.goto("/");
  // 顶栏品牌名 `DST Sheet Set Manager`（i18n `app.title`，未翻译）是真实界面里的拉丁文本，
  // 它足以触发 Inter 的 Basic Latin 子集请求——不需要为了测试去伪造文本。
  await expect(page.locator(".topbar")).toBeVisible();
  // 第二套字体（等宽）只在图纸表格/目录页出现，欢迎页不渲染，故用探针触发一次请求：
  // 这里要证的是「产物可被真实请求并加载」，探针不改变这一性质（真实使用点仍由各页 e2e 覆盖）。
  await page.evaluate(()=>{
    const probe=document.createElement("span");
    probe.id="font-probe";
    probe.style.cssText="font-family:var(--font-mono);font-size:14px;position:absolute;left:-9999px;top:0";
    probe.textContent="ABCDEF0123456789";
    document.body.appendChild(probe);
  });
  const runtime=await page.evaluate(async()=>{
    await document.fonts.ready;
    return {
      faces:Array.from(document.fonts).map(face=>({family:face.family.replace(/["']/g,""),status:face.status})),
      inter:document.fonts.check("14px Inter"),
      mono:document.fonts.check('14px "IBM Plex Mono"'),
      loaded:Array.from(document.fonts).filter(face=>face.status==="loaded").map(face=>face.family.replace(/["']/g,"")),
    };
  });

  // ① 两套字体都真的进入 loaded（status==="loaded" 表示字体二进制已取回并可用）
  expect.soft(runtime.faces.map(face=>face.family).sort(),"声明的字体族").toEqual(["IBM Plex Mono","Inter"]);
  expect.soft(runtime.loaded.sort(),"运行时已加载的字体族").toEqual(["IBM Plex Mono","Inter"]);
  expect.soft(runtime.inter,"Inter 可渲染").toBe(true);
  expect.soft(runtime.mono,"IBM Plex Mono 可渲染").toBe(true);

  // ② 两套 WOFF2 都被真实请求，且都在本地同源、命中各自的资产文件名
  const basenames=fontRequests.map(request=>request.pathname.split("/").pop()??"");
  expect.soft(basenames.some(name=>name.startsWith("InterLatin")),`Inter 子集被请求，实测：${basenames.join(", ")}`).toBe(true);
  expect.soft(basenames.some(name=>name.startsWith("IBMPlexMonoLatin")),`Plex 子集被请求，实测：${basenames.join(", ")}`).toBe(true);
  for(const request of fontRequests){
    expect.soft(request.pathname.endsWith(".woff2"),`字体必须来自 WOFF2：${request.url}`).toBe(true);
    expect.soft(request.url.startsWith(new URL(page.url()).origin),`字体必须同源：${request.url}`).toBe(true);
  }
  // ③ 响应成功（被请求≠取回成功）
  for(const response of fontResponses) expect.soft(response.status,"字体响应状态 ".concat(response.url)).toBe(200);
  // ④ 全程无远程字体访问（离线可用是硬约束）
  expect(remoteFontRequests,"不得访问远程字体").toEqual([]);
});

// ===== PLAN-DM-029 Task 12（T11-2 Minor-2）：壳层布局搬迁后的几何关系 =====
// `WorkspaceShell.vue` 的三条布局规则是**逐字节**从 `App.vue` 搬来的（Task 11 Step 6），但搬迁后
// **没有任何自动化断言**覆盖它们（`check:ui` 只看规则合规，看不到布局；Task 11 也无截图门禁）。
// 评审因此把「这个搬迁的第一次真实验证」记在 Task 12 的截图/真实桌面证据上——本节把它先钉在
// **真实浏览器的几何结果**上，使后续截图/真实桌面只剩「与本节一致」这一点要核。
test("Task 12 壳层布局：shell-body/shell-main/sheets-active 三条搬迁规则的实际几何",async({page})=>{
  await openWorkspace(page);
  const readLayout=()=>page.evaluate(()=>{
    const body=document.querySelector<HTMLElement>(".shell-body")!;
    const main=document.querySelector<HTMLElement>(".shell-main")!;
    const overlay=document.querySelector<HTMLElement>(".shell-body > aside");
    const rect=(element:Element)=>{const r=element.getBoundingClientRect();return {left:Math.round(r.left),right:Math.round(r.right),width:Math.round(r.width),height:Math.round(r.height)};};
    const bodyStyle=getComputedStyle(body);
    const mainStyle=getComputedStyle(main);
    return {
      bodyDisplay:bodyStyle.display,
      bodyAlignItems:bodyStyle.alignItems,
      body:rect(body),
      mainDisplay:mainStyle.display,
      mainFlexDirection:mainStyle.flexDirection,
      mainFlexGrow:mainStyle.flexGrow,
      mainOverflow:mainStyle.overflow,
      main:rect(main),
      overlay:overlay?rect(overlay):null,
      sheetsActive:main.classList.contains("sheets-active"),
      viewportHeight:window.innerHeight,
      scrollWidth:document.documentElement.scrollWidth,
      clientWidth:document.documentElement.clientWidth,
    };
  });

  // 默认页签是**图纸页**（实测；打开工作区即 active==='sheets'）⇒ 先读 sheets-active 态。
  const sheetsState=await readLayout();
  // ③ `.shell-main.sheets-active{overflow:hidden}`：图纸页把纵向滚动交给表格
  expect.soft(sheetsState.sheetsActive,"图纸页应带 sheets-active").toBe(true);
  expect.soft(sheetsState.mainOverflow,"图纸页：主区自身不滚动（交给表格）").toBe("hidden");
  // ① `.shell-body{display:flex;align-items:stretch;height:calc(100vh - 104px);min-height:0}`
  expect.soft(sheetsState.bodyDisplay,".shell-body 是 flex 容器").toBe("flex");
  expect.soft(sheetsState.bodyAlignItems,".shell-body 拉伸子项（主区与浮层同高）").toBe("stretch");
  expect.soft(sheetsState.body.height,".shell-body 高度 = 100vh − 104px（顶栏＋操作栏）").toBe(sheetsState.viewportHeight-104);
  // ② `.shell-main{display:flex;flex-direction:column;flex:1;min-width:0;overflow:auto}`
  expect.soft(sheetsState.mainDisplay,".shell-main 是 flex 容器").toBe("flex");
  expect.soft(sheetsState.mainFlexDirection,".shell-main 纵向排列").toBe("column");
  expect.soft(sheetsState.mainFlexGrow,".shell-main 占满剩余宽度").toBe("1");
  // `flex:1` + `align-items:stretch` 的**几何结果**（不只是声明）：水平相邻、不重叠、同高
  if(sheetsState.overlay){
    expect.soft(sheetsState.main.right,"主区右缘不越过浮层左缘").toBeLessThanOrEqual(sheetsState.overlay.left+1);
    expect.soft(sheetsState.main.height,"主区与浮层同高（stretch）").toBe(sheetsState.overlay.height);
    expect.soft(sheetsState.main.width+sheetsState.overlay.width,"两者宽度之和 = 容器宽度（无重叠也无缝隙）").toBe(sheetsState.body.width);
  }

  // 切到属性页：`sheets-active` 必须移除、主区恢复自身滚动（反向分支，防只钉一个方向）
  await page.locator("#tab-properties").click();
  await expect(page.locator(".shell-main.sheets-active"),"属性页不应带 sheets-active").toHaveCount(0);
  const propertiesState=await readLayout();
  expect.soft(propertiesState.sheetsActive,"属性页不应带 sheets-active").toBe(false);
  expect.soft(propertiesState.mainOverflow,"属性页：主区自身纵向可滚动").toBe("auto");
  expect.soft(propertiesState.main.right,"切换页签不改变主区几何").toBe(sheetsState.main.right);
  expect.soft(propertiesState.scrollWidth,"无整页横向溢出").toBeLessThanOrEqual(propertiesState.clientWidth);
});

// ===== PLAN-DM-029 Task 4：壳层纵向验证 =====
// 尺寸必须在真实浏览器里量：happy-dom 不做布局，Task 3 只在源码与令牌链层面锁定了这组尺寸
// （`properties-definitions.spec.ts:344-346` 量的是 `.definition-panel` 的遗留控件）。
// 本节同时补齐 Task 3 无法在本地验证的真实可见性叠加（`display:none`，含祖先与自身）与
// 任务浮层的焦点语义（手写副本迁到 `useDialogFocus` 后必须保住的三条）以及 Step 5 要求的
// hover/focus/disabled 计算样式。注：**不拿 `[hidden]` 当隐藏形态**——壳层按钮位于 `<aside>` 内，
// `legacy.css:24` 的 `:where(#app) aside button{display:flex}` 是作者规则，按层叠直接覆盖
// UA 的 `[hidden]{display:none}`，`[hidden]` 按钮仍会产生盒子（实测可被 `focus()`）。

test("壳层已迁移控件：本地 SVG 图标、统一尺寸与可访问名称",async({page})=>{
  await openWorkspace(page);
  const topbar=page.locator(".topbar");
  const shell=page.locator(".topbar button, .tabbar button, .dock button");
  const heightOf=async(selector:string)=>Math.round((await page.locator(selector).first().boundingBox())!.height);

  // A：Unicode 字形不再充当结构图标，图标是本仓库的本地 SVG 且对读屏隐藏
  expect.soft(await topbar.textContent(),"顶栏不应再出现字形图标").not.toContain("◐");
  expect.soft(await topbar.textContent(),"顶栏不应再出现字形图标").not.toContain("⚙");
  expect.soft(await page.locator(".topbar svg.ui-icon[aria-hidden='true']").count(),"顶栏本地 SVG 图标").toBeGreaterThan(0);
  expect.soft(await page.locator(".dock svg.ui-icon[aria-hidden='true']").count(),"操作栏本地 SVG 图标").toBeGreaterThan(0);
  await expect(page.locator(".topbar svg.ui-icon").first()).toHaveAttribute("focusable","false");
  // 装饰图标不进可访问名称：顶栏两个入口的名称仍来自 i18n 的 aria-label
  await expect(page.getByRole("button",{name:"切换主题"})).toBeVisible();
  await expect(page.getByRole("button",{name:"设置"})).toBeVisible();
  await expect(page.getByRole("button",{name:"打开图纸集所在文件夹"})).toBeVisible();

  // B/E：输入类 38px、普通按钮 36px、图标按钮 36×36、紧凑动作 34px
  await expect.soft(topbar.getByRole("combobox"),"Topbar 不再包含 AutoCAD 版本选择框").toHaveCount(0);
  for(const selector of [".topbar .folder-btn",".topbar .close-btn",".topbar .settings-btn",".dock .draft-chip"]){
    expect.soft(await heightOf(selector),selector).toBe(36);
  }
  expect.soft(await page.locator(".topbar .ui-icon-button").count(),"顶栏图标按钮数量").toBeGreaterThan(0);
  const iconButton=(await page.locator(".topbar .ui-icon-button").first().boundingBox())??{width:0,height:0};
  expect.soft(Math.round(iconButton.width),"图标按钮宽度").toBe(36);
  expect.soft(Math.round(iconButton.height),"图标按钮高度").toBe(36);
  expect.soft(await heightOf(".dock .dock-btn"),"紧凑工具栏按钮").toBe(34);

  // 可点目标下限 32px（壳层所有按钮）
  for(const control of await shell.all()){
    const box=(await control.boundingBox())!;
    expect.soft(Math.round(box.height),`可点目标 ${await control.getAttribute("class")}`).toBeGreaterThanOrEqual(32);
  }
});

test("壳层交互态：键盘焦点环、悬停与禁用态的计算样式",async({page})=>{
  await openWorkspace(page);
  // 令牌解析：断言落在令牌真值上而不是硬编码 rgb
  const tokenColor=(name:string)=>page.evaluate(token=>{
    const probe=document.createElement("span");
    probe.style.color=`var(${token})`;
    document.body.appendChild(probe);
    const value=getComputedStyle(probe).color;
    probe.remove();
    return value;
  },name);

  // 键盘焦点（Step 1）：`:focus-visible` 的统一焦点环（`reset.css:34`）对壳层控件同样生效
  await page.locator(".topbar .theme-btn").focus();
  await page.keyboard.press("Tab");
  const settings=page.locator(".topbar .settings-btn");
  await expect(settings).toBeFocused();
  const ring=await settings.evaluate(el=>{const s=getComputedStyle(el);return {style:s.outlineStyle,width:s.outlineWidth,color:s.outlineColor}});
  expect.soft(ring.style,"键盘焦点环线型").toBe("solid");
  expect.soft(ring.width,"键盘焦点环线宽").toBe("2px");
  expect.soft(ring.color,"键盘焦点环颜色").toBe(await tokenColor("--color-focus"));

  // 悬停（Step 5）：`.settings-btn:hover` 命中 `--color-bg-muted`，且与常态不同
  const muted=await tokenColor("--color-bg-muted");
  const normalBg=await settings.evaluate(el=>getComputedStyle(el).backgroundColor);
  await settings.hover();
  const hoverBg=await settings.evaluate(el=>getComputedStyle(el).backgroundColor);
  expect.soft(normalBg,"悬停前背景与悬停态不同").not.toBe(muted);
  expect.soft(hoverBg,"悬停背景命中 --color-bg-muted").toBe(muted);

  // 禁用态（Step 5）：默认无草稿时撤销必然禁用（`cursor===0`），禁用样式由壳层自己声明
  const undo=page.locator(".dock .dock-btn.ghost").first();
  await expect(undo).toBeDisabled();
  const disabledStyle=await undo.evaluate(el=>{const s=getComputedStyle(el);return {opacity:s.opacity,cursor:s.cursor}});
  expect.soft(disabledStyle.opacity,"禁用态透明度").toBe("0.5");
  expect.soft(disabledStyle.cursor,"禁用态光标").toBe("not-allowed");
});

test("任务浮层焦点：展开后落在当前激活页签、关闭回焦当前激活入口、Tab 在首尾回绕",async({page})=>{
  await openWorkspace(page);
  const drawer=page.locator(".task-drawer");
  const activeId=()=>page.evaluate(()=>document.activeElement?.id??null);
  const activeEntry=()=>page.evaluate(()=>document.activeElement?.getAttribute("data-entry")??null);

  await page.getByRole("button",{name:"展开任务浮层"}).click();
  await expect(drawer).toBeVisible();
  // ② 关闭回焦：先在抽屉内切到「诊断」再收起，回焦的是**当前**激活入口（不是展开时那一个）
  await drawer.getByRole("tab",{name:/诊断/}).click();
  await page.getByRole("button",{name:"收起任务浮层"}).click();
  await expect(drawer).toBeHidden();
  await expect.poll(activeEntry).toBe("diag");
  // ① 展开后焦点必须落在当前激活页签（不是抽屉里第一个页签）。注：非激活页签带
  //    `tabindex="-1"`，迁移到 `useDialogFocus` 后 `focusables()[0]` 恒等于当前激活页签，
  //    因此这条断言**不是**「必须显式传 `initialFocus`」的回归网，只是行为冻结。
  await page.locator('.task-rail [data-entry="diag"]').click();
  await expect(drawer).toBeVisible();
  await expect.poll(activeId).toBe("ov-tab-diag");

  // ③ 隐藏形态的**端点级**验证：四种形态的探针都放在抽屉最前面（首端点侧）与最后面（尾端点侧），
  //    只要其中任何一个候选被算作停靠点，首/尾端点与回绕目标都会跟着变（Task 3 的 happy-dom
  //    用例只能验过滤结果，验不到真实布局与焦点可达性）。
  //    四种形态：属性 `[hidden]`、祖先 `display:none`、祖先 `inert`、自身 `visibility:hidden`。
  //    注意（控制器实测，`evidence/controller-task-4-probe-hidden.json`）：浮层内组件自己的元素有
  //    `.task-overlay [hidden]{display:none!important}` 兜底，但这里用 `createElement` 造的裸按钮会
  //    被 `legacy.css:24` 的 `:where(#app) aside button{display:flex}` 抢在 UA 的 `[hidden]{display:none}`
  //    之前，所以在 CSS 上仍然占位——本断言真正验证的是焦点工具**按属性**过滤。
  await page.evaluate(()=>{
    const drawerEl=document.querySelector(".task-drawer")!;
    const head=document.createElement("div");
    head.id="focus-probe-head";
    head.innerHTML=[
      '<button id="probe-head-hidden" hidden>属性隐藏</button>',
      '<div style="display:none"><button id="probe-head-display">祖先不显示</button></div>',
      '<div inert><button id="probe-head-inert">祖先惰性</button></div>',
      '<button id="probe-head-visibility" style="visibility:hidden">不可见</button>',
    ].join("");
    const tailNote=document.createElement("div");
    tailNote.id="focus-probe-tail";
    tailNote.style.display="none";
    tailNote.innerHTML='<button id="probe-tail-hidden">端点后不显示</button>';
    const tail=document.createElement("button");
    tail.id="probe-last";
    tail.textContent="真实最后";
    drawerEl.prepend(head);
    drawerEl.appendChild(tail);
    drawerEl.appendChild(tailNote);
  });
  // 非激活页签带 `tabindex="-1"`，不是停靠点 → 抽屉内**第一个真实停靠点**就是当前激活页签
  await page.locator("#probe-last").focus();
  await page.keyboard.press("Tab");
  await expect.poll(activeId).toBe("ov-tab-diag");
  // Shift+Tab 从第一个停靠点回绕到最后一个真实停靠点
  await page.locator("#ov-tab-diag").focus();
  await page.keyboard.press("Shift+Tab");
  await expect.poll(activeId).toBe("probe-last");

  // 0×0 候选：记录**迁移前后一致**的现有行为（原手写副本的 `getClientRects().length>0` 对
  // 零尺寸元素同样成立，故这不是本轮引入的缺口）；已知未覆盖，见计划 Task 12 收口责任 J。
  await page.evaluate(()=>{
    const zero=document.createElement("div");
    zero.style.cssText="width:0;height:0;overflow:hidden";
    zero.innerHTML='<button id="probe-zero">零尺寸</button>';
    document.querySelector(".task-drawer")!.appendChild(zero);
  });
  await page.locator("#probe-zero").focus();
  await page.keyboard.press("Tab");
  await expect.poll(activeId).toBe("ov-tab-diag");
});

// ===== PLAN-DM-029 Task 7：任务浮层内部控件（动作与状态） =====
// 背景：Task 4 把浮层控件迁到原语（`.ov-fold` 由 40×40 改为 UiIconButton 的 36×36）时，
// 它的尺寸断言循环 `shell = ".topbar button, .tabbar button, .dock button"` **不含浮层按钮**，
// 全仓也搜不到任何 `.ov-*` / `.diag-*` 元素的计算样式或几何断言 —— 即“补任务浮层动作与状态
// 控件断言”这一交付物此前是静默缺席的。本节补齐，并钉住可点下限与状态色来源。

// 令牌 → 当前主题下的计算色值（与「壳层交互态」用例同口径，不硬编码 rgb）
function tokenColorOf(page: Page, token: string) {
  return page.evaluate(name => {
    const probe = document.createElement("span");
    probe.style.color = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }, token);
}

// 读取令牌解析出的字号字符串（责任 K）。缺令牌时返回**空串**——
// 令牌自指断言（元素 vs 令牌）在令牌缺失时两侧同为 NaN 仍会通过，故必须先把令牌本身钉成具体值。
function tokenFontSizeOf(page: Page, token: string) {
  return page.evaluate(name => {
    const probe = document.createElement("span");
    probe.style.fontSize = `var(${name})`;
    document.body.appendChild(probe);
    const value = getComputedStyle(probe).fontSize;
    probe.remove();
    return value;
  }, token);
}

// 浮层内**所有**可点元素的可点高度必须 ≥32px（ARCH-DM-007 §4.1 全局最小可点下限）。
// 枚举口径：button / a / summary / [role=tab] / [data-entry]（默认态 7 个、有诊断态 10 个）。
// 刻意**不**缩小到“动作控件”：诊断行的 summary 与复制按钮正是在这里被发现低于下限的。
async function expectOverlayTapTargets(page: Page): Promise<void> {
  const rows = await page.evaluate(() => {
    const scope = document.querySelector(".task-overlay");
    if (!scope) return [];
    return Array.from(scope.querySelectorAll("button, a, summary, [role='tab'], [data-entry]")).map(element => {
      const rect = (element as HTMLElement).getBoundingClientRect();
      const style = getComputedStyle(element as HTMLElement);
      const cls = String((element as HTMLElement).className || "").split(" ").filter(Boolean).join(".");
      return {
        sel: `${element.tagName.toLowerCase()}${cls ? "." + cls : ""}`,
        h: Math.round(rect.height),
        visible: rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden",
      };
    });
  });
  const visible = rows.filter(row => row.visible);
  expect(visible.length, "应枚举到浮层内的可点元素").toBeGreaterThan(0);
  expect(visible.filter(row => row.h < 32).map(row => `${row.sel}=${row.h}px`), "浮层内所有可点元素都必须 ≥32px").toEqual([]);
}

test("任务浮层动作控件：折叠按钮 36×36、页签档位与可点下限",async({page})=>{
  await openWorkspace(page);
  await page.getByRole("button",{name:"展开任务浮层"}).click();
  const drawer=page.locator(".task-drawer");
  await expect(drawer).toBeVisible();

  // 折叠按钮：Task 4 把 40×40 改成 UiIconButton 的 36×36，此前无任何断言钉住（绝对值锚，
  // 不用令牌自指——令牌整体漂移时两侧同变会漏报，同责任 S 的教训）
  const fold=page.locator(".task-drawer .ov-fold");
  await expect(fold).toHaveCSS("width","36px");
  await expect(fold).toHaveCSS("height","36px");
  const foldBox=(await fold.boundingBox())!;
  expect(Math.round(foldBox.width),"折叠按钮宽度").toBe(36);
  expect(Math.round(foldBox.height),"折叠按钮高度").toBe(36);
  // 可访问名称来自 UiIconButton 的 label，而不是字形
  await expect(fold).toHaveAttribute("aria-label","收起任务浮层");

  // 页签：高度由 padding(10px)+行高决定（无固定档），字号取语义令牌
  const tab=page.locator(".task-drawer .ov-tab").first();
  await expect(tab).toHaveCSS("font-size","13px");
  const tabBox=(await tab.boundingBox())!;
  expect(Math.round(tabBox.height),"页签高度").toBe(42);

  // 空态（默认夹具无诊断）：状态文案字号取令牌；可点元素整体过下限
  await page.locator('.task-rail [data-entry="diag"]').click();
  const empty=page.locator(".ov-empty");
  await expect(empty).toBeVisible();
  await expect(empty).toHaveCSS("font-size","13px");
  await expectOverlayTapTargets(page);
});

test("任务浮层状态控件：状态色取语义令牌、诊断文本可读且过可点下限",async({page})=>{
  await installSheetsFixture(page,{dualStatus:true});
  await openWorkspace(page);
  await page.getByRole("button",{name:"展开任务浮层"}).click();
  const drawer=page.locator(".task-drawer");
  await expect(drawer).toBeVisible();
  await drawer.getByRole("tab",{name:/诊断/}).click();

  // 状态点（阻断诊断）颜色必须来自语义令牌，不硬编码 rgb
  const dot=page.locator(".task-drawer .ov-dot").first();
  await expect(dot).toBeVisible();
  expect(await dot.evaluate(element=>getComputedStyle(element).color),"状态点颜色应来自 --color-danger").toBe(await tokenColorOf(page,"--color-danger"));

  // 诊断文本：字号取语义令牌，且宽度必须 >0（回归守卫）——
  // 曾因 `legacy.css` 的 `:where(#app) aside button{...width:100%...}` 命中浮层的 `<aside>` 根，
  // `.diag-copy` 又带 `flex-shrink:0`，于是它独占整行、把 `.diag-text` 挤成 0 宽，
  // `word-break:break-word` 导致**每行只显示一个字符**（evidence/task-7-fix-diag-broken-drawer.png）
  await page.locator(".ov-diagnostics summary").click();
  const text=page.locator(".diag-text").first();
  await expect(text).toBeVisible();
  await expect(text).toHaveCSS("font-size","13px");
  const textBox=(await text.boundingBox())!;
  expect(Math.round(textBox.width),"诊断文本宽度（0 宽 = 每字一行、不可读）").toBeGreaterThan(50);

  // 复制按钮：达 ≥32px 下限，且按内容收缩（不得再被 width:100% 撑满整行）
  const copy=page.locator(".diag-copy").first();
  await expect(copy).toHaveCSS("min-height","32px");
  const copyBox=(await copy.boundingBox())!;
  const rowBox=(await page.locator(".diagnostics li").first().boundingBox())!;
  expect(Math.round(copyBox.height),"复制按钮高度").toBeGreaterThanOrEqual(32);
  expect(Math.round(copyBox.width),"复制按钮宽度必须小于整行（否则会挤掉诊断文本）").toBeLessThan(Math.round(rowBox.width)-10);

  // 该态下可点元素更多（含 summary 与复制按钮），整体再过一遍下限
  await expectOverlayTapTargets(page);
});

// ---------------------------------------------------------------------------
// PLAN-DM-029 Task 9：旧页面（欢迎/修订/草稿）控件视觉基础
// 契约：显式 type="button"、最小可点高度 ≥32px、非空可访问名称。
// 关键尺寸一律用**绝对值锚**（Task 7 的教训：用令牌断言令牌时，令牌整体漂移两侧同变仍会通过）。
async function expectLegacyControlContract(page: Page, selector: string): Promise<void> {
  // 先等首个命中可见：`.all()` 不等待，否则会在视图尚未渲染时得到 0 个而假红
  await expect(page.locator(selector).first()).toBeVisible();
  const controls = await page.locator(selector).all();
  expect(controls.length, `${selector} 至少命中一个控件`).toBeGreaterThan(0);
  for (const control of controls) {
    const info = await control.evaluate(el => ({
      type: el.getAttribute("type"),
      tag: el.tagName,
      height: Math.round(el.getBoundingClientRect().height),
      name: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim(),
    }));
    expect.soft(info.type, `${selector} <${info.tag}> 必须显式 type="button"`).toBe("button");
    expect.soft(info.height, `${selector} 可点高度`).toBeGreaterThanOrEqual(32);
    expect.soft(info.name.length, `${selector} 必须有可访问名称`).toBeGreaterThan(0);
  }
}

test.describe("旧页面控件视觉基础（PLAN-DM-029 Task 9）", () => {
  test("欢迎页：主操作为 38px 表单档，宽度上限 520px 逐字等值", async ({page}) => {
    await page.goto("/");
    const primary = page.locator(".welcome-card .primary");
    await expect(primary).toBeVisible();
    await expectLegacyControlContract(page, ".welcome-card .primary");
    expect(await primary.evaluate(el => Math.round(el.getBoundingClientRect().height)), "欢迎页主操作高度").toBe(38);
    expect(await page.locator(".welcome-card").evaluate(el => getComputedStyle(el).maxWidth), "欢迎卡宽度上限").toBe("520px");
    // 责任 K（已裁定）：20px 已升为语义档位 --font-page-title，值逐字等值
    expect(await tokenFontSizeOf(page, "--font-page-title"), "--font-page-title 必须解析为 20px").toBe("20px");
    await expect(page.locator(".welcome-title")).toHaveCSS("font-size", "20px");
  });

  test("修订页空态：标题字号取语义档位 --font-title（16px）", async ({page}) => {
    // 显式给空列表，落在空态而不是有列表态
    await page.route("**/api/revisions?workspace_id=workspace-1", route => route.fulfill({json: []}));
    await openWorkspace(page);
    await page.getByRole("tab", {name: "修订历史"}).click();
    const title = page.locator(".empty-title");
    await expect(title).toBeVisible();
    expect(await tokenFontSizeOf(page, "--font-title"), "--font-title 必须解析为 16px").toBe("16px");
    await expect(title).toHaveCSS("font-size", "16px");
  });

  test("欢迎页降级态：路径输入必须有可见 label 关联，按钮带显式 type", async ({page}) => {
    // 清掉壳桥后启动：稳定落在无壳降级态（不依赖 late-bridge 的 30ms 窗口）
    await page.addInitScript(() => { delete (window as any).pywebview; });
    await page.goto("/");
    const pathInput = page.locator(".no-shell input");
    await expect(pathInput).toBeVisible();
    const label = await pathInput.evaluate(el => {
      const associated = (el as HTMLInputElement).labels?.[0] ?? null;
      return associated ? (associated.textContent ?? "").trim() : null;
    });
    expect(label, "路径输入必须由可见 label 关联（仅 aria-label/placeholder 不算）").not.toBeNull();
    expect((label ?? "").length, "可见 label 文本不得为空").toBeGreaterThan(0);
    await expectLegacyControlContract(page, ".no-shell button");
    expect(await page.locator(".no-shell input").evaluate(el => Math.round(el.getBoundingClientRect().height)), "路径输入高度").toBe(36);
  });

  test("修订页：按钮契约 + 确认模态危险层级（文字色不得等于底色）", async ({page}) => {
    await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
    await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
    await openWorkspace(page);
    await page.getByRole("tab",{name:"修订历史"}).click();
    await expect(page.locator(".revisions-view")).toBeVisible();
    await expectLegacyControlContract(page, ".revisions-view button");
    expect(await page.locator(".revisions-view button").first().evaluate(el => Math.round(el.getBoundingClientRect().height)), "修订页按钮高度").toBe(36);
    await page.getByRole("button",{name:"恢复预览"}).click();
    await expect(page.getByText("replace test.dst")).toBeVisible();
    await page.getByRole("button",{name:"恢复为新修订"}).click();
    const modal = page.locator('[role="dialog"][aria-modal="true"]');
    const danger = modal.getByRole("button",{name:/确认恢复/});
    await expect(danger).toBeVisible();
    const colors = await danger.evaluate(el => { const css = getComputedStyle(el); return {color: css.color, background: css.backgroundColor}; });
    expect(colors.color, "危险确认按钮文字色不得与底色相同（否则不可见）").not.toBe(colors.background);
  });

  test("确认模态焦点归还：取消后焦点回到开启控件", async ({page}) => {
    await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
    await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
    await openWorkspace(page);
    await page.getByRole("tab",{name:"修订历史"}).click();
    await page.getByRole("button",{name:"恢复预览"}).click();
    await expect(page.getByText("replace test.dst")).toBeVisible();
    const opener = page.getByRole("button",{name:"恢复为新修订"});
    await expect(opener).toBeVisible();
    await opener.click();
    const modal = page.locator('[role="dialog"][aria-modal="true"]');
    await expect(modal).toBeVisible();
    // Tab 圈闭（Task 9 Step 3 起由 dialogFocus.ts 承担，替代原先手写的 button/input 过滤）：
    // 连续 Tab 必须始终留在对话框内。选 ConfirmModal 特有的 [role=dialog][aria-modal=true]
    // 作作用域：未保存闸门刻意不写这两个属性，所以对隐藏的闸门不会假通过。
    // 停靠点只有取消/确认两个，按 5 次足以触发两轮回绕。
    const focusInsideDialog = () => page.evaluate(() => document.activeElement?.closest('[role="dialog"][aria-modal="true"]') !== null);
    for (let step = 0; step < 5; step++) {
      await page.keyboard.press("Tab");
      expect(await focusInsideDialog(), `第 ${step + 1} 次 Tab 后焦点仍应在对话框内`).toBe(true);
    }
    await cancelModal(page);
    await expect(modal).toHaveCount(0);
    expect(await page.evaluate(() => (document.activeElement?.textContent ?? "").trim()), "取消后焦点应回到开启按钮").toContain("恢复为新修订");
  });

  test("草稿动作栈：按钮契约与 disabled 语义保持", async ({page}) => {
    await openWorkspace(page);
    await openDraftPop(page);
    const pop = page.locator("#draft-pop");
    await expect(pop).toBeVisible();
    await expectLegacyControlContract(page, "#draft-pop button");
    // 空草稿下撤销/重做/清空/预览均禁用（行为不变）
    await expect(pop.getByRole("button",{name:"撤销"})).toBeDisabled();
    await expect(pop.getByRole("button",{name:"重做"})).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// PLAN-DM-029 Task 9 Step 5：旧页面四张持久证据（依 T9-2 裁定）
// 落点：`docs/dst-manager/specs/assets/SPEC-DM-006/production/`（SPEC-DM-006 是桌面 UI/UX 的
// 总纲 Spec，旧页面归它；先例：T7-4 新建了 SPEC-DM-009 的资产目录）。
// 落盘方式与 `settings-extensions-production-evidence.spec.ts` 一致：截图**只作 testInfo 附件**，
// 验收时**显式复制**到资产目录——**刻意不加 env 开关自动写库**（目录页那套会无差别覆盖
// 其它 Spec 的既有验收资产，已登记为责任 T）。
// 证据组落在本文件（而不另建 `*-visual-evidence.spec.ts`）是 T9-2 的刻意裁定：四张图的
// 夹具流程（欢迎、修订、修复、任务事件）**已在本文件**，另建文件会重复不易写的夹具逻辑。
// 每张图都配**计算样式或几何断言**，并先断言被证对象已入视口，避免“有图无证据”与
// “拍到的不是该状态”（`toBeInViewport()` 默认 ratio 0 只要求任意相交）。
async function shootLegacyEvidence(page: Page, info: TestInfo, name: string): Promise<void> {
  const file = info.outputPath(name);
  await page.screenshot({path: file, animations: "disabled"});
  await info.attach(name, {path: file, contentType: "image/png"});
}

// 把语义令牌解析成当前主题下的计算色值（不能直接比 getPropertyValue 的原文）
async function resolveDangerToken(page: Page): Promise<string> {
  return page.evaluate(() => {
    const probe = document.createElement("span");
    probe.style.color = "var(--color-danger)";
    document.body.append(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  });
}

test.describe("旧页面持久证据（PLAN-DM-029 Task 9 Step 5）", () => {
  test("t9-01 欢迎默认：未打开态浅色（welcome-card）", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await page.goto("/");
    const card = page.locator(".welcome-card");
    await expect(card).toBeVisible();
    await expect(card).toBeInViewport();
    // 与断言轮同一口径：主操作 38px 表单档、卡片宽度上限 520px 逐字等值
    expect(await page.locator(".welcome-card .primary").evaluate(el => Math.round(el.getBoundingClientRect().height)), "欢迎页主操作高度").toBe(38);
    expect(await card.evaluate(el => getComputedStyle(el).maxWidth), "欢迎卡宽度上限").toBe("520px");
    await shootLegacyEvidence(page, info, "t9-01-welcome-default-1280x720-light.png");
  });

  test("t9-02 修订危险确认：确认模态危险层级浅色", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await page.route("**/api/revisions?workspace_id=workspace-1",route=>route.fulfill({json:[{id:"revision-1",created_at:"2026-08-12T00:00:00Z",before_hash:"aaaaaaaa",result_hash:"bbbbbbbb"}]}));
    await page.route("**/api/workspaces/workspace-1/revisions/revision-1/restore-preview",route=>route.fulfill({json:{revision_id:"revision-1",executable:true,files:[{path:"test.dst",action:"replace",conflict:false}]}}));
    await openWorkspace(page);
    await page.getByRole("tab",{name:"修订历史"}).click();
    await page.getByRole("button",{name:"恢复预览"}).click();
    await expect(page.getByText("replace test.dst")).toBeVisible();
    await page.getByRole("button",{name:"恢复为新修订"}).click();
    const modal = page.locator('[role="dialog"][aria-modal="true"]');
    await expect(modal).toBeVisible();
    await expect(modal).toBeInViewport();
    const danger = modal.getByRole("button",{name:/确认恢复/});
    await expect(danger).toBeVisible();
    // 勾选不可逆确认：让危险按钮处于**可用**态取景（禁用态带 opacity:.5，不能体现危险层级）
    await modal.getByRole("checkbox").check();
    await expect(danger).toBeEnabled();
    // Task 6 的红底红字回归守卫口径：危险按钮文字色不得等于底色
    const colors = await danger.evaluate(el => {const css = getComputedStyle(el); return {color: css.color, background: css.backgroundColor};});
    expect(colors.color, "危险确认按钮文字色不得与底色相同").not.toBe(colors.background);
    expect(colors.background, "危险按钮底色应取自 --color-danger").toBe(await resolveDangerToken(page));
    await shootLegacyEvidence(page, info, "t9-02-revision-danger-confirm-1280x720-light.png");
  });

  test("t9-03 修复错误：阻断问题只读态浅色", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    const blocked:any=workspaceVersion("workspace-1","测试图纸集","revision-1");
    blocked.dst_validation={status:"INVALID_REPAIR_REQUIRED",actions:[],blocking_issues:[{code:"REPAIR_UNSUPPORTED_ENCODING",message:"无法解析 DST 文件编码",severity:"error"}]};
    await page.route("**/api/workspaces/open",route=>route.fulfill({json:blocked}));
    await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:blocked}));
    await openWorkspace(page);
    // 修复面板在任务浮层的诊断页签（与 :608 的修复流程同一路径）
    const overlay=page.getByRole("complementary",{name:"任务浮层"});
    await overlay.getByRole("button",{name:"展开任务浮层"}).click();
    await overlay.getByRole("tab",{name:"诊断"}).click();
    const panel = page.locator(".repair");
    await expect(panel).toBeVisible();
    await expect(panel).toBeInViewport();
    await expect(page.getByText("DST 修复状态：需要人工修复")).toBeVisible();
    await expect(page.getByText(/存在阻断问题/)).toBeVisible();
    await expect(page.getByText("阻断原因（1）")).toBeVisible();
    await shootLegacyEvidence(page, info, "t9-03-repair-error-1280x720-light.png");
  });

  test("t9-04 深色任务状态：浮层实施进度同状态", async ({page}, info) => {
    await page.setViewportSize({width: 1280, height: 720});
    await installPreferenceSnapshot(page,"dark");
    await installMockEventSource(page);
    await page.route("**/api/workspaces/workspace-1/changes/preview",route=>route.fulfill({json:{executable:true,requires_cad:false,changes:[{}],diagnostics:[],affected_files:["test.dst"],execution_intent:null}}));
    await page.route("**/api/workspaces/workspace-1/changes/execute",route=>route.fulfill({json:{id:"job-evidence",status:"QUEUED",progress:0,attempt:0,files:[]}}));
    await openWorkspace(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme","dark");
    // 必须先由应用产生任务：对**未知**任务 id 的 SSE 事件会被忽略（既有用例均先经「确认写入」）
    await page.getByRole("tab",{name:"属性"}).click();await saveSheetSetDraft(page,"草稿名");await page.getByRole("tab",{name:"图纸"}).click();
    await page.getByRole("button",{name:"预览变更"}).click();
    await page.getByRole("button",{name:"确认写入"}).click();
    await confirmModal(page,/确认发布/);
    await expect(page.getByText("任务进行中")).toBeVisible();
    // 确认写入后浮层已被应用自动展开（既有用例随后即「收起」可证），因此这里不点「展开」；
    // 只在未停在进度页签时切换，避免因“已经展开”而找不到展开按钮。
    const overlay=page.getByRole("complementary",{name:"任务浮层"});
    const progTab=overlay.getByRole("tab",{name:"实施进度"});
    if ((await progTab.getAttribute("aria-selected")) !== "true") await progTab.click();
    await expect(progTab).toHaveAttribute("aria-selected","true");
    await page.evaluate(()=>(window as any).__emitJob({id:"job-evidence",workspace_id:"workspace-1",status:"ROLLED_BACK",progress:100,attempt:1,error_code:"PUBLISH_ROLLED_BACK",error_detail:"发布日志写入失败：[WinError 5] 拒绝访问",files:[]}));
    const job = page.locator(".job-detail");
    await expect(job).toBeVisible();
    await expect(job).toBeInViewport();
    await expect(page.getByText("任务 job-evidence")).toBeVisible();
    await expect(job.getByText("PUBLISH_ROLLED_BACK")).toBeVisible();
    // 计算样式断言：深色下抽屉底色必须取自当前主题的 --color-bg-surface（不得硬编码浅色）
    const drawerBg = await page.locator(".task-drawer").evaluate(el => {const probe=document.createElement("span");probe.style.color="var(--color-bg-surface)";el.append(probe);const expected=getComputedStyle(probe).color;probe.remove();return {actual:getComputedStyle(el).backgroundColor,expected};});
    expect(drawerBg.actual, "深色下抽屉底色应取自 --color-bg-surface").toBe(drawerBg.expected);
    await shootLegacyEvidence(page, info, "t9-04-task-status-1280x720-dark.png");
  });
});
