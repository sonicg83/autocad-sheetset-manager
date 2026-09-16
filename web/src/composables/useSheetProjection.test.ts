import {describe,expect,it,vi} from "vitest";
import {ref} from "vue";
import type {ChangeCommand,Preview,Workspace} from "../api/contracts";

const {requestMock}=vi.hoisted(()=>({requestMock:vi.fn()}));
vi.mock("../api/client",()=>({request:requestMock}));
vi.mock("vue-i18n",()=>({useI18n:()=>({t:(key:string)=>key})}));
vi.mock("../i18n",()=>({i18n:{global:{t:(key:string)=>key}}}));

function deferred<T>(){
  let resolve!:(value:T)=>void;
  const promise=new Promise<T>(done=>{resolve=done});
  return {promise,resolve};
}

const workspace={id:"workspace-1",revision_id:"revision-1",sheet_set:{subsets:[]}} as unknown as Workspace;
const command={type:"insert_subset",ordinal:1,placement:"after",title:"新分册",initial_sheet_count:0,base_template_file:null} as unknown as ChangeCommand;
const preview={executable:true,execution_intent:{derived_document:{subsets:[]}}} as unknown as Preview;

describe("useSheetProjection",()=>{
  it("CAD 版本变化后丢弃旧版本在途响应",async()=>{
    vi.stubGlobal("window",{addEventListener:vi.fn()});
    const {useSheetProjection}=await import("./useSheetProjection");
    const gate=deferred<Preview>();
    requestMock.mockReturnValueOnce(gate.promise);
    const cadVersion=ref("2016");
    const state=useSheetProjection({workspace:ref(workspace),baseWorkspace:ref(workspace),commands:ref([command]),cadVersion});
    const pending=state.refresh();
    cadVersion.value="2020";
    gate.resolve(preview);
    await pending;
    expect(state.projection.value).toBeNull();
    expect(state.stamp.value).toBeNull();
  });
});
