import {defineConfig} from "vite"; import vue from "@vitejs/plugin-vue";
// API 代理目标可用 DST_MANAGER_API_TARGET 覆盖（默认 127.0.0.1:8000）：
// e2e 全局 setup 需在非 8000 端口启动真实后端——Windows 的 WinNAT 端口排除
// 区间可能覆盖 8000（绑定报 WinError 10013），测试用 9001 并经此变量注入。
const apiTarget=process.env.DST_MANAGER_API_TARGET??"http://127.0.0.1:8000";
export default defineConfig({plugins:[vue()],server:{proxy:{"/api":apiTarget}}});
