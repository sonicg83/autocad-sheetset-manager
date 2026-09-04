# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec：DST Manager 绿色分发包（ARCH-DM-002 §3.3）。

运行约定：仓库根执行 `uv run pyinstaller --noconfirm packaging/dst-manager.spec`，
前置条件 web/dist 已构建、migrations/ 与 alembic.ini 在仓库根。
产物 `dist/DSTManager/`，datas 落在 _internal（= 运行期 sys._MEIPASS）。
路径均相对 spec 所在目录（packaging/），PyInstaller 执行 spec 前会 chdir 到该目录。
"""

a = Analysis(
    ["entry.py"],
    pathex=["..\\src"],
    binaries=[],
    datas=[
        ("..\\web\\dist", "web/dist"),
        ("..\\alembic.ini", "."),
        ("..\\migrations", "migrations"),
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
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dst-manager",
    console=True,  # 控制台保留：Worker 认领日志与启动警告必须可观察
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DSTManager",
)
