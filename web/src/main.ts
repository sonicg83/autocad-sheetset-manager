// 启动只负责引导：语言与挂载顺序由 i18n/bootstrap 决定（先定语言再挂载，I18N-04）。
import "./style.css";
import {bootstrap} from "./i18n";

void bootstrap();
