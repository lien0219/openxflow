# OpenXFlow Desktop

OpenXFlow Desktop is a thin Electron shell around the existing OpenXFlow React frontend and FastAPI runtime. It does not duplicate application business logic.

## Architecture

- Electron main process owns application lifecycle, local port allocation, native dialogs and the Python child process.
- The existing OpenXFlow frontend is loaded from the local FastAPI server.
- Mutable data is stored under Electron's `userData` directory, never under the installation directory.
- The renderer has no Node.js access. Native capabilities are exposed through a small, typed preload bridge.
- The backend listens on `127.0.0.1` with one worker and never binds to the LAN in desktop mode.

## Requirements

- Node.js 22.12 or newer
- npm
- `uv`
- A built OpenXFlow frontend

## Development

From the repository root, initialize OpenXFlow normally and build the frontend. Then:

```bash
cd desktop
npm install
npm run test:ci
```

The desktop launcher resolves the development runtime from the repository `.venv`. You can override both paths explicitly:

```bash
OPENXFLOW_DESKTOP_PYTHON=/absolute/path/to/python \
OPENXFLOW_DESKTOP_FRONTEND=/absolute/path/to/frontend \
npm run dev
```

On Windows, set the same values using PowerShell environment variables.

## Embedded runtime

Build a platform-specific Python 3.12 runtime and copy the frontend assets:

```bash
npm run runtime:build
npm run runtime:verify
```

Runtime artifacts are generated under `desktop/resources/runtime` and must be built independently on each target operating system and architecture.

## Packaging

Unsigned local smoke package:

```bash
npm run pack
```

Installer/disk image:

```bash
npm run dist
```

The packaging wrapper retries transient Electron download failures three times. Override retry behavior with:

```bash
OPENXFLOW_DESKTOP_BUILD_ATTEMPTS=5 \
OPENXFLOW_DESKTOP_BUILD_RETRY_DELAY_MS=10000 \
npm run pack
```

If Electron downloads are unstable in your region, configure a mirror before packaging.

Windows CMD:

```bat
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm run pack
```

PowerShell:

```powershell
$env:ELECTRON_MIRROR="https://npmmirror.com/mirrors/electron/"
npm run pack
```

Release signing is intentionally supplied through CI secrets:

- Windows Authenticode certificate
- Apple Developer ID Application certificate
- Apple notarization credentials

## Data locations

Electron supplies the platform `userData` directory. The application creates:

```text
OpenXFlow/
├── config/
├── database/
├── files/
├── components/
├── plugins/
├── logs/
├── cache/
└── backups/
```

Uninstalling the application does not delete this directory by default.

## Quality gates

Every desktop pull request targeting `develop` runs on Windows and macOS:

- strict TypeScript type checking
- Biome linting and formatting checks
- unit tests
- production TypeScript build
- unsigned unpacked package smoke build

A desktop change must not be merged while any required check is failing.
