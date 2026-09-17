<p align="center">
  <img src="web/src/assets/brand/dst-manager-logo-512.png" alt="DST Manager logo" width="128" />
</p>

<h1 align="center">DST Manager — AutoCAD Sheet Set Management Tool</h1>

<p align="center">
  <a href="README.md">简体中文</a> · <a href="#readme">English</a>
</p>

DST Manager targets real-world engineering work on a single workstation. It provides **auditable, recoverable** inspection, controlled editing, and safe publishing for AutoCAD Sheet Sets (DST/DWG): every structural change comes with an understandable preview, an explicit execution boundary, and a traceable result. Edits first go into persisted drafts; no engineering files are touched until an explicit publish, and a failed publish is rolled back to the pre-publish state of the whole batch.

## Key Features

- **Controlled editing**: DST changes strictly follow the `DST → XML DOM → DST` pipeline, never dropping unknown nodes, attributes, or original node order; every write is previewed before it is published.
- **Drafts & publish transactions**: edits are persisted as a draft stack with undo/redo; formal writes keep a permanent before-snapshot, and a multi-file publish failure restores the entire batch to its pre-publish state.
- **Safe CAD execution**: AutoCAD work runs through a version-matched Core Console + Worker plugin with fixed commands only; user input is never concatenated into SCR/Shell/path commands.
- **Unified naming rules**: sheet numbers, ranges, titles, suffixes, and file/layout names are all derived from controlled rules, with support for "unnumbered subset keywords".
- **Sheet single-table workspace**: tree-plus-table navigation, column configuration, paged buffered editing, and batch operations.
- **Sectioned property editing**: view and edit sheet set / subset / sheet properties by section.
- **Sheet catalog XLSX export**: a built-in extension with field references, number format codes, and output-sheet filtering.
- **Revision history & restore**: every publish keeps a full revision record; previous revisions can be previewed and restored.
- **Settings center**: 13 persistent options including UI language (Chinese/English), AutoCAD version (2016/2020), UI theme (light/dark), and numbering rules, effective across processes.
- **Desktop shell**: a pywebview/WebView2 single-window desktop app that launches with a double click and enforces single-instance.

## Quick Start

### End users (portable, no installation)

1. Obtain the `dst-manager-v<version>-win64.zip` distribution and extract it to any folder.
2. Run `setup.bat` in the program folder: it searches the local AutoCAD installation (registry + default install paths) for `accoreconsole.exe` and writes `.env` (2015–2019 → 2016 bucket, 2020–2024 → 2020 bucket; 2025+ not yet supported). It is idempotent and never overwrites existing configuration.
3. Double-click `dst-manager.exe` to launch the desktop app, then open a `.dst` file to start a workspace.

Data and drafts live in `%LOCALAPPDATA%\dst-manager\`; updating the zip never overwrites user data. Run `dst-manager.exe doctor` for a self-check.

See the **[user guide](docs/dst-manager/guides/GUIDE-DM-006-user-guide.md)** (Chinese) for day-to-day operation.

### Developers (run from source)

Requirements: Windows 11, Python ≥ 3.12 (managed with UV), Node.js (web frontend), and a local AutoCAD 2016/2020 install (required for structural CAD operations).

```powershell
# One-click start: initialize environment, sync dependencies, build the web app,
# upgrade the database, and launch the API plus the CAD Worker
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1
```

When the services are ready, `http://127.0.0.1:8000` opens automatically. Repeated starts reuse existing dependencies and builds.

```powershell
.\scripts\start.ps1 -Action Status   # Show status
.\scripts\start.ps1 -Action Logs     # Tail the UTF-8 logs of the current instance
.\scripts\start.ps1 -Action Stop     # Stop the API and Worker
.\scripts\start.ps1 -SkipSync -SkipWebBuild   # Fast start
.\scripts\start.ps1 -NoWorker -NoBrowser      # Web/API only
```

Each start creates a unique `run_id`; runtime logs go to `.dst-manager-data/runtime/<run-id>/`. Health checks verify the `run_id` so a stale instance on the same port is never mistaken for a new one; running `Start` again reuses the current instance.

For first-time setup you can also run the environment bootstrap (idempotent, fills in only missing items):

```powershell
. .\scripts\setup-env.ps1   # Create .env from .env.example, detect local AutoCAD, configure UV cache
uv sync
uv run dst-manager doctor
uv run dst-manager serve    # Manual mode: run Web/API and Worker in two terminals
uv run dst-manager worker
```

See `.env.example` at the repository root for the `.env` / `DST_MANAGER_*` variable reference.

## Startup & Log Troubleshooting

- If `Status` reports an invalid status file, `Stop` cleans up only this project's managed process tree (by normalized project root and exact command line); unrelated programs are never killed.
- If the port is taken by an unrelated program, `Start` fails and reports the occupying PID; use `-Port` to pick another one.
- If stale or duplicate workers are detected, run `Stop` first and make sure `Status` reports both API and Worker as stopped before starting again.
- Runtime logs are kept per instance; when there are more than 20 stopped instances or the total exceeds 512 MiB, only the oldest stopped instances are cleaned up.
- Startup verifies the Alembic revision and key physical tables/columns. On `DATABASE_SCHEMA_DRIFT`, a test database can be reset by deleting `.dst-manager-data/dst-manager.db` and starting again; never modify a published migration — add a new revision instead.

## Packaging & Release

Internal distribution uses a portable, installation-free package; the development environment does not need the steps below.

```powershell
# Build the distribution (version defaults to pyproject.toml)
.\scripts\build_release.ps1                # Run without -SkipPlugins the first time or after plugin changes
.\scripts\build_release.ps1 -SkipPlugins   # Reuse existing plugin DLLs when unchanged

# One-click release: pre-checks + Ruff/pytest gates + build + local tag
.\scripts\release.ps1 -Version 0.3.4       # Update pyproject.toml version and changelog manually first
```

The artifact is `dist/releases/dst-manager-v<version>-win64.zip`. Tags are created locally only; pushing and distribution are done manually. See [ARCH-DM-002](docs/dst-manager/architecture/ARCH-DM-002-windows-release-packaging.md) and [ARCH-DM-003](docs/dst-manager/architecture/ARCH-DM-003-versioning-and-release.md) (Chinese).

## Common Verification Commands

```powershell
# Python baseline
$env:UV_LINK_MODE = "copy"
uv sync --dev
uv run ruff check .
uv run pytest -q
uv lock --check
uv run alembic upgrade head    # Database migrations

# Web
cd web
npm ci
npm run build
npm run test:e2e

# Dual-version plugins
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_plugins.ps1
```

Real AutoCAD system tests must be explicitly enabled and require the matching Core Console, plugin, and private samples on the machine:

```powershell
$env:DST_MANAGER_RUN_AUTOCAD = "1"
uv run pytest tests/system_autocad -q
```

## Repository Layout

| Path | Description |
| --- | --- |
| `src/dst_manager/domain/` | Domain models and deterministic planning (no FastAPI/filesystem/AutoCAD dependencies) |
| `src/dst_manager/application/` | Orchestrates workspaces, change previews, tasks, and CAD execution |
| `src/dst_manager/infrastructure/` | DST/AcSm, AutoCAD, SQLite, file locking, publish transaction adapters |
| `src/dst_manager/interfaces/` | FastAPI and Typer entry points |
| `web/` | Vue 3 + TypeScript + Vite local UI |
| `plugins/src/DstManager.AutoCAD/` | AutoCAD 2016/2020 Worker plugin source (.NET Framework 4.8) |
| `migrations/` | Alembic database migrations |
| `scripts/` | Startup, environment bootstrap, plugin and distribution build scripts |
| `docs/` | Documentation entry point |
| `sample/`, `legacy/` | Private samples and the legacy tool; local-only, never published |

## Safety Boundaries (Important)

- Read-only workspace access never creates `.dst-manager/`, never modifies DST/DWG, and never updates file timestamps.
- Never bypass the publisher to overwrite original files; never modify DST XML via string replacement.
- The web service binds to `127.0.0.1` only during the MVP phase.
- Local private directories such as `legacy/` and `sample/` must never be pushed to the public repository.

## Documentation

- [User guide (for end users, Chinese)](docs/dst-manager/guides/GUIDE-DM-006-user-guide.md)
- [Full documentation index](docs/README.md) (Chinese)
- [DST Builder product docs](docs/dst-builder/README.md) (Chinese)
- [DST Manager product docs](docs/dst-manager/README.md) (Chinese)
- [MVP architecture & acceptance baseline (ARCH-DM-001)](docs/dst-manager/architecture/ARCH-DM-001-dst-manager-mvp-baseline.md) (Chinese)
- [Shared AutoCAD/DST capabilities](docs/shared/README.md) (Chinese)
- [Cross-project integration](docs/integration/README.md) (Chinese)

## License

This project is licensed under the [MIT License](LICENSE).
