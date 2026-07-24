# Setting up an OpenXFlow Development Environment

This document explains how to install dependencies, start the frontend and backend, and work on OpenXFlow locally.

## Base Requirements

- Git
- Python managed through `uv`
- Node.js `>=20.19.0` and npm
- An IDE such as [Visual Studio Code](https://code.visualstudio.com/)

The cross-platform helper scripts use Python 3.12 by default because it is the version used for the channel gateway development workflow. You can override the version when needed.

GNU Make is still supported for the traditional workflow, but it is not required when using the new Windows or macOS/Linux helper scripts.

## Clone the Repository

```bash
git clone https://github.com/lien0219/openxflow.git
cd openxflow
git switch feature/channel-gateway
```

If you work from a fork, add the upstream repository as usual:

```bash
git remote add upstream https://github.com/lien0219/openxflow.git
git remote set-url --push upstream no_push
```

> [!TIP]
> Windows and WSL users can avoid file-mode-only changes with `git config core.filemode false`.

## Recommended: Cross-platform One-command Development

The repository contains native development helpers for Windows and macOS/Linux. They install project dependencies and start the backend and frontend together while preserving every existing Makefile command.

### What the helpers do

The default `all` action:

1. Verifies that `uv`, Node.js, and npm are available.
2. Installs Python 3.12 through `uv` when it is not already available.
3. Creates `.env` from `.env.example` when `.env` does not exist.
4. Installs the locked backend dependencies with the PostgreSQL extra.
5. Installs frontend dependencies with `npm ci`.
6. Installs pre-commit hooks when Git is available.
7. Starts the backend on `http://localhost:7860`.
8. Starts the frontend on `http://localhost:3000` and proxies API requests to the backend.

The helpers never replace or remove the traditional commands described later in this document.

### Windows PowerShell

From the repository root:

```powershell
.\dev.ps1
```

You can also double-click `dev.cmd` in File Explorer. The default action installs dependencies and then opens separate PowerShell windows for the backend and frontend.

Available actions:

```powershell
# Install dependencies only
.\dev.ps1 install

# Start both services without reinstalling
.\dev.ps1 start

# Install and start both services
.\dev.ps1 all

# Display help
.\dev.ps1 help
```

Common options:

```powershell
.\dev.ps1 start `
  -PythonVersion 3.12 `
  -BackendPort 7860 `
  -FrontendPort 3000 `
  -ListenHost 0.0.0.0 `
  -NoBrowser
```

The Windows helper detects a `.venv` created by WSL, Linux, or macOS and recreates it as a native Windows virtual environment. A virtual environment cannot be shared between Windows and WSL.

If PowerShell blocks local scripts, either use `dev.cmd` or allow locally created scripts for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### macOS and Linux

From the repository root:

```bash
bash ./dev.sh
```

Available actions:

```bash
# Install dependencies only
bash ./dev.sh install

# Start both services without reinstalling
bash ./dev.sh start

# Install and start both services
bash ./dev.sh all

# Display help
bash ./dev.sh help
```

The macOS/Linux helper runs both services in the current terminal. Press `Ctrl+C` to stop both processes.

Optional environment variables:

```bash
OPENXFLOW_PYTHON_VERSION=3.12 \
OPENXFLOW_BACKEND_PORT=7860 \
OPENXFLOW_FRONTEND_PORT=3000 \
OPENXFLOW_HOST=0.0.0.0 \
OPENXFLOW_NO_BROWSER=1 \
bash ./dev.sh start
```

Additional variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENXFLOW_PYTHON_VERSION` | `3.12` | Python version installed and selected by `uv` |
| `OPENXFLOW_BACKEND_PORT` | `7860` | FastAPI/Uvicorn port |
| `OPENXFLOW_FRONTEND_PORT` | `3000` | Vite development port |
| `OPENXFLOW_HOST` | `0.0.0.0` | Backend and frontend listen address |
| `OPENXFLOW_PROXY_TARGET` | `http://127.0.0.1:7860` | Frontend API proxy target |
| `OPENXFLOW_SKIP_PRE_COMMIT` | `0` | Set to `1` to skip pre-commit installation |
| `OPENXFLOW_NO_BROWSER` | `0` | Set to `1` to avoid opening the browser |

### Local network access

The frontend listens on `0.0.0.0` by default. Devices on the same network can use:

```text
http://<your-computer-ip>:3000
```

On Windows, allow inbound TCP port 3000 when the firewall prompts you. You can also add the rule manually from an elevated PowerShell terminal:

```powershell
New-NetFirewallRule `
  -DisplayName "OpenXFlow Frontend 3000" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 3000 `
  -Action Allow
```

A private LAN address is suitable for testing from a phone on the same network, but external providers such as Feishu, WeCom, DingTalk, and Telegram still require a public HTTPS callback URL.

## Traditional Makefile Workflow

The existing workflow remains fully supported.

### Prerequisites

- macOS, Linux, WSL, or a Dev Container
- GNU Make
- `uv >=0.4`
- Node.js `>=20.19.0` and npm

### Initial environment validation

```bash
make init
```

This installs backend dependencies, frontend dependencies, and pre-commit hooks.

To build the frontend and run the packaged web application in one terminal:

```bash
make run_cli
```

To clear the frontend build cache before rebuilding and starting:

```bash
make run_clic
```

### Start the backend and frontend separately

Backend terminal:

```bash
make backend
```

Frontend terminal:

```bash
make frontend
```

The backend listens on `http://localhost:7860` and the frontend development server listens on `http://localhost:3000`.

### Component development mode

By default, OpenXFlow uses the prebuilt component index for fast startup. Enable dynamic component loading while actively modifying components:

```bash
LFX_DEV=1 make backend
```

Or load selected component modules:

```bash
LFX_DEV=mistral,openai,anthropic make backend
```

Without `LFX_DEV`, rebuild the component index after component changes:

```bash
uv run python scripts/build_component_index.py
```

## Manual Native Commands

The helper scripts are wrappers around the standard project commands. You can still run the services manually.

### Backend

```bash
uv sync --python 3.12 --frozen --extra postgresql
uv run uvicorn \
  --factory langflow.main:create_app \
  --host 0.0.0.0 \
  --port 7860 \
  --reload \
  --env-file .env \
  --loop asyncio
```

Windows PowerShell uses the same arguments:

```powershell
uv sync --python 3.12 --frozen --extra postgresql
uv run uvicorn `
  --factory langflow.main:create_app `
  --host 0.0.0.0 `
  --port 7860 `
  --reload `
  --env-file .env `
  --loop asyncio
```

### Frontend

```bash
cd src/frontend
npm ci
npm run start
```

The frontend Vite configuration reads these optional values:

```env
VITE_HOST=0.0.0.0
VITE_PORT=3000
VITE_PROXY_TARGET=http://localhost:7860
```

## Dev Container

A preconfigured `.devcontainer` is included in the repository. In Visual Studio Code, install the Dev Containers extension and run **Dev Containers: Reopen in Container** from the Command Palette.

The Makefile workflow and `bash ./dev.sh` are both available inside the container when the required tools are present.

## Troubleshooting

### Python 3.10 and `StrEnum`

The channel gateway uses standard-library features available in Python 3.11 and newer. Use Python 3.12 for this branch:

```bash
uv python install 3.12
uv sync --python 3.12 --frozen --extra postgresql
```

### Switching between WSL and Windows

Do not share the same `.venv` or `node_modules` between Windows and WSL. Recreate them in the active environment:

```powershell
# Windows
Remove-Item -Recurse -Force .venv, src\frontend\node_modules
.\dev.ps1 install
```

```bash
# WSL/macOS/Linux
rm -rf .venv src/frontend/node_modules
bash ./dev.sh install
```

### `uv` hardlink warning on `/mnt/c` or `/mnt/d`

When a repository is stored on a Windows-mounted drive, `uv` may fall back from hardlinks to copies. This is safe but slower. Suppress the warning in WSL with:

```bash
export UV_LINK_MODE=copy
```

### Port already in use

Windows:

```powershell
Get-NetTCPConnection -LocalPort 3000,7860 -State Listen
```

macOS/Linux:

```bash
lsof -i :3000
lsof -i :7860
```

Use the script options or environment variables to select other ports.

### Frontend build problems

For the traditional Makefile workflow:

```bash
make run_clic
```

For the cross-platform helper workflow:

```bash
rm -rf src/frontend/node_modules
bash ./dev.sh install
```

On Windows:

```powershell
Remove-Item -Recurse -Force src\frontend\node_modules
.\dev.ps1 install
```

## Optional Pre-commit Hooks

The install helpers and `make init` install pre-commit hooks by default. To install them manually:

```bash
uv sync
uv run pre-commit install
```

Skip hook installation in the helper scripts with `-SkipPreCommit` on Windows or `OPENXFLOW_SKIP_PRE_COMMIT=1` on macOS/Linux.

## Build and Display Documentation

From the project root:

```bash
cd docs
npm install
npm run start
```

The documentation site normally runs on `http://localhost:3001` when port 3000 is occupied by the frontend.

## Adding or Modifying a Component

Components reside below `src/backend/base/langflow`, with unit tests below the corresponding backend test directories.

When developing components, run the backend with `LFX_DEV=1` so changes are loaded dynamically. Add or update unit tests where practical. The component index is refreshed by CI for pull requests and can be rebuilt locally with:

```bash
uv run python scripts/build_component_index.py
```

## Building and Testing Changes

Useful validation commands include:

```bash
make lint
make format_backend
make format_frontend
make unit_tests
```

Channel gateway-specific checks are also run by the repository's GitHub Actions workflows.

## Committing, Pushing, and Pull Requests

Before committing, inspect the working tree and run the checks relevant to your changes. If pre-commit hooks are installed through the Python environment, use:

```bash
uv run git commit
```

Then push the branch and update or open the pull request as usual.

## Files That May Change

- Files under `src/backend/base/langflow/initial_setup/starter_projects` can be regenerated when the application starts.
- `uv.lock` and `src/frontend/package-lock.json` can change when dependency commands are run. Do not commit unintended lock-file changes.

You can temporarily hide expected local lock-file changes with:

```bash
git update-index --assume-unchanged uv.lock src/frontend/package-lock.json
```

Restore normal tracking with:

```bash
git update-index --no-assume-unchanged uv.lock src/frontend/package-lock.json
```
