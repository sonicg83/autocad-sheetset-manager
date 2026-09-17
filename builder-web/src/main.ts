// 启动入口：加载语义令牌与基础样式，按系统偏好设置主题（浅/深只映射令牌，
// 业务样式不写主题分支），随后挂载向导应用。
import "./styles/tokens.css";
import "./styles/app.css";
import {createApp} from "vue";
import App from "./App.vue";

const themeMedia = window.matchMedia("(prefers-color-scheme: dark)");
function applyTheme(dark: boolean): void {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
applyTheme(themeMedia.matches);
themeMedia.addEventListener("change", (event) => applyTheme(event.matches));

createApp(App).mount("#app");
