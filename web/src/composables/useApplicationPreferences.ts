import {ref} from "vue";
import type {Ref} from "vue";
import type {SettingsSnapshot,SettingsValue} from "../api/settings";
import {applyTheme,useTheme,type Theme} from "./useTheme";

export type CadVersion="2016"|"2020";

const cadVersion=ref<CadVersion>("2020");
let preferencesInitialized=false;

function valueOf(snapshot:SettingsSnapshot,key:string):SettingsValue|undefined{
  return snapshot.items.find(item=>item.key===key)?.value;
}

function readCadVersion(snapshot:SettingsSnapshot):CadVersion{
  return valueOf(snapshot,"cad_version")==="2016"?"2016":"2020";
}

function readTheme(snapshot:SettingsSnapshot):Theme{
  return valueOf(snapshot,"ui_theme")==="dark"?"dark":"light";
}

export function initializeApplicationPreferences(snapshot:SettingsSnapshot):void{
  cadVersion.value=readCadVersion(snapshot);
  applyTheme(readTheme(snapshot));
  preferencesInitialized=true;
}

export function initializeApplicationPreferencesIfNeeded(snapshot:SettingsSnapshot):boolean{
  if(preferencesInitialized)return false;
  initializeApplicationPreferences(snapshot);
  return true;
}

export function applySavedApplicationPreferences(snapshot:SettingsSnapshot,changedKeys:Set<string>):void{
  if(changedKeys.has("cad_version"))cadVersion.value=readCadVersion(snapshot);
  if(changedKeys.has("ui_theme"))applyTheme(readTheme(snapshot));
}

export function useApplicationPreferences():{
  cadVersion:Ref<CadVersion>;
  theme:Ref<Theme>;
  toggleTheme:()=>void;
}{
  const {theme,toggleTheme}=useTheme();
  return {cadVersion,theme,toggleTheme};
}
