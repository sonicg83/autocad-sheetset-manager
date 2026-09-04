// 打开图纸集所在文件夹与可信上下文桥（PLAN-DM-015 任务 2）e2e。
// 覆盖：无壳禁用并解释、新桥点击传当前 workspace_id 且成功不报错、旧桥缺新方法
// 降级提示、关闭工作区后清空服务端上下文且按钮消失。桥目标路径由服务端可信
// 上下文解析，浏览器只传 workspace_id；此处只用虚构路径。
import {expect,test,type Page} from "@playwright/test";

const workspace={
  id:"workspace-1",revision_id:"revision-1",dst_path:"C:\\虚构工程\\图纸集.dst",
  sheet_set:{name:"虚构图纸集",sheet_count:1,subset_count:1,custom_properties:{},property_definitions:[],
    subsets:[{id:"subset-1",name:"1 平面图",title:"平面图",number_range:"1",display_name:"1 平面图",
      sheets:[{id:"sheet-1",number:"001",title:"图纸 1",custom_properties:{},layout:{file_name:"C:\\虚构工程\\分册.dwg",relative_file_name:".\\分册.dwg",resolved_path:"C:\\虚构工程\\分册.dwg",layout_name:"001 图纸 1",handle:"1"}}]}]},
  diagnostics:[],
};

const FOLDER_BTN="打开图纸集所在文件夹";

async function installRoutes(page:Page){
  await page.route("**/api/workspaces/open",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/workspace-1",route=>route.fulfill({json:workspace}));
  await page.route("**/api/workspaces/*/draft",route=>route.fulfill({json:{draft:null,corrupted:false,stale:false,stale_reasons:[]}}));
}

// 新桥：open_workspace_folder / clear_workspace_context 记录调用，返回成功
async function installNewShell(page:Page){
  await page.addInitScript(()=>{
    (window as any).__folderCalls=[];
    (window as any).__clearCalls=[];
    (window as any).pywebview={api:{
      select_file:async()=>(window as any).__fakeSelectResult??null,
      on_files_dropped:async()=>{},
      open_workspace_folder:async(workspaceId:string)=>{(window as any).__folderCalls.push(workspaceId);return {ok:true,value:null}},
      clear_workspace_context:async(workspaceId:string)=>{(window as any).__clearCalls.push(workspaceId);return {ok:true,value:null}},
    }};
    window.dispatchEvent(new Event("pywebviewready"));
  });
}

// 旧桥：只暴露 select_file/on_files_dropped，缺新方法（降级路径）
async function installOldShell(page:Page){
  await page.addInitScript(()=>{
    (window as any).pywebview={api:{
      select_file:async()=>(window as any).__fakeSelectResult??null,
      on_files_dropped:async()=>{},
    }};
    window.dispatchEvent(new Event("pywebviewready"));
  });
}

async function openWorkspaceWithShell(page:Page){
  await page.goto("/");
  await page.evaluate(()=>{(window as any).__fakeSelectResult="C:\\虚构工程\\图纸集.dst"});
  await page.getByRole("button",{name:"选择 DST 文件"}).click();
  await expect(page.getByRole("button",{name:"关闭"})).toBeVisible();
}

test("无壳时文件夹按钮禁用并解释原因",async({page})=>{
  await installRoutes(page);
  await page.goto("/");
  await page.locator(".no-shell input").fill("C:\\虚构工程\\图纸集.dst");
  await page.locator(".no-shell button").click();
  await expect(page.getByRole("button",{name:"关闭"})).toBeVisible();
  const button=page.getByRole("button",{name:FOLDER_BTN});
  await expect(button).toBeVisible();
  await expect(button).toBeDisabled();
  await expect(button).toHaveAttribute("title","桌面壳未就绪，无法打开图纸集所在文件夹");
});

test("点击文件夹按钮经桥传当前 workspace_id 且成功不报错",async({page})=>{
  await installRoutes(page);
  await installNewShell(page);
  await openWorkspaceWithShell(page);
  await page.getByRole("button",{name:FOLDER_BTN}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__folderCalls)).toEqual(["workspace-1"]);
  await expect(page.locator(".error.notice")).toHaveCount(0);
});

test("旧桥缺新方法时降级提示且不调用",async({page})=>{
  await installRoutes(page);
  await installOldShell(page);
  await openWorkspaceWithShell(page);
  await page.getByRole("button",{name:FOLDER_BTN}).click();
  await expect(page.getByText("当前桌面壳不支持打开图纸集所在文件夹")).toBeVisible();
});

test("关闭工作区后清空服务端上下文且按钮消失",async({page})=>{
  await installRoutes(page);
  await installNewShell(page);
  await openWorkspaceWithShell(page);
  await expect(page.getByRole("button",{name:FOLDER_BTN})).toBeVisible();
  await page.getByRole("button",{name:"关闭"}).click();
  await expect(page.getByRole("button",{name:FOLDER_BTN})).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>(window as any).__clearCalls)).toEqual(["workspace-1"]);
});
