# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec：DST Builder 绿色分发包（PLAN-DB-001 Task 11）。

运行约定：仓库根执行 `uv run pyinstaller --noconfirm packaging/dst-builder.spec`，
前置条件 builder-web/dist 已构建（npm --prefix builder-web run build）。
产物 `dist/DSTBuilder/`，datas 落在 _internal（= 运行期 sys._MEIPASS），
路径均相对 spec 所在目录（packaging/），PyInstaller 执行 spec 前会 chdir 到该目录。

与 Manager（packaging/dst-manager.spec）刻意隔离：不捆 Manager 前端 web/dist、
不捆 sample/；随包资源为 Builder 前端、builder_migrations、builder_alembic.ini
与共享 XSD（dst_platform/acsm/schema）。2016/2020 双版本 Builder 插件 DLL 由
scripts/build_builder_release.ps1 复制到 exe 同级 autocad{2016,2020}/（运行期
dst_builder.infrastructure.autocad.capabilities._default_plugin 按
sys.executable 同级发现，frozen 态免配置）。
"""

a = Analysis(
    ["builder_entry.py"],
    pathex=["..\\src"],
    binaries=[],
    datas=[
        ("..\\builder-web\\dist", "builder-web/dist"),
        ("..\\builder_alembic.ini", "."),
        ("..\\builder_migrations", "builder_migrations"),
        # 版本兜底（Task 11 评审）：frozen 态 importlib.metadata 必 miss，
        # runtime.app_version 回退读本文件 [project].version 写入成果包
        # builder_version provenance（对齐 dst-manager.spec 的版本兜底模式）
        ("..\\pyproject.toml", "."),
        # 共享 XSD（dst_platform.acsm.contract._load_schema 经 __file__ 定位）：
        # frozen 态必须随包打入，且目标目录与 contract.pyc 同级
        ("..\\src\\dst_platform\\acsm\\schema", "dst_platform/acsm/schema"),
    ],
    hiddenimports=[
        # uvicorn 运行期动态导入的协议/事件循环实现
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        # pywebview Windows 后端（WebView2 走 pythonnet/clr）
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        # SQLAlchemy SQLite 方言按 URL 动态加载
        "sqlalchemy.dialects.sqlite",
    ],
    excludes=[
        "tavily_cli",  # 生产依赖里的开发工具，禁止进包
        "pytest",
        "pytest_cov",
        "playwright",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dst-builder",
    console=False,  # 去终端黑窗：壳输出经 builder_entry.py 重定向到 %LOCALAPPDATA%/dst-builder/logs/
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DSTBuilder",
)
