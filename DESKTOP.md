# OpenXFlow 桌面端指南

OpenXFlow Desktop 使用 Electron 承载现有 React 前端，并在本机启动现有 FastAPI/Python 后端。Web、Windows 和 macOS 共用业务源码，桌面端只负责窗口、进程、原生能力和安装包。

## 支持平台

| 平台 | 架构 | 安装包 |
| --- | --- | --- |
| Windows 10/11 | x64 | NSIS `.exe` |
| macOS | Apple Silicon arm64 | `.dmg` |
| macOS | Intel x64 | `.dmg` |

Python 环境包含平台和架构相关依赖，不能在 Windows、macOS、Linux、WSL 或不同 CPU 架构之间复制使用。

## 环境要求

- Node.js `>=20.19.0`，推荐 22.12 LTS
- npm 10+
- `uv`
- Git
- macOS 打包需要 Xcode Command Line Tools

检查环境：

```bash
node --version
npm --version
uv --version
git --version
```

## 首次安装并启动

在项目根目录安装桌面工程依赖：

```bash
npm --prefix desktop install
```

一键准备 Python、后端依赖、前端资源并启动桌面端：

```bash
npm --prefix desktop run dev:setup
```

开发环境目录：

```text
Windows  .venv-win\Scripts\python.exe
macOS    .venv/bin/python
Linux    .venv/bin/python
```

`.venv-win/` 已加入 `.gitignore`。Windows 可以保留原有 WSL `.venv`，Windows 桌面端会优先使用 `.venv-win`。

初始化完成后，日常启动使用：

```bash
npm --prefix desktop run dev
```

只初始化、不启动：

```bash
npm --prefix desktop run setup:dev
```

## 与 Web 端的关系

桌面端不会替换或修改 Web 端启动方式。以下命令继续保持不变：

```bash
make run_cli
make run_clic
make backend
make frontend
```

桌面后端监听 `127.0.0.1` 的随机端口，通常不会与 Web 默认端口 `7860` 冲突。

## 质量检查

```bash
npm --prefix desktop run typecheck
npm --prefix desktop run lint
npm --prefix desktop test
npm --prefix desktop run build
```

全部通过后再进行安装包测试。

## 打包命令

生成未安装版应用，用于本地烟雾测试：

```bash
npm --prefix desktop run pack
```

产物位于：

```text
desktop/release/
```

完整安装包需要先构建共享前端和平台原生 Python Runtime：

```bash
npm --prefix desktop run frontend:prepare
npm --prefix desktop run runtime:build
npm --prefix desktop run runtime:verify
npm --prefix desktop run test:ci
```

Windows x64：

```bash
npm --prefix desktop run dist -- --x64 --publish never
```

macOS Apple Silicon：

```bash
npm --prefix desktop run dist -- --arm64 --publish never
```

macOS Intel：

```bash
npm --prefix desktop run dist -- --x64 --publish never
```

Python Runtime 必须在目标操作系统和目标架构上原生构建，不能跨平台打包。

## Windows 本地测试

重点验证：

- 首次一键初始化和后续快速启动
- 新建、保存和运行工作流
- 文件与目录选择器
- 关闭应用后无残留 Python 进程
- 重启后数据库、配置和工作流数据仍然存在
- `desktop/release/win-unpacked/OpenXFlow.exe` 可以启动
- NSIS 安装、卸载和重新安装流程

## macOS 本地测试

确认当前架构：

```bash
uname -m
```

`arm64` 为 Apple Silicon，`x86_64` 为 Intel。

重点验证：

- 窗口左上角关闭后可通过 Dock 恢复
- `Command+Q` 可以完全退出
- 活动监视器中无残留 Python 进程
- 文件和目录选择器正常
- 工作流保存和重启后数据持久化
- `.app` 和 `.dmg` 均可启动

首次运行未签名应用时，可在 Finder 中右键应用并选择“打开”。正式发布需要 Developer ID、Notarization 和 Stapling。

## 用户数据目录

Windows：

```text
%APPDATA%\OpenXFlow\
```

macOS：

```text
~/Library/Application Support/OpenXFlow/
```

目录包含：

```text
config/
database/
files/
components/
plugins/
logs/
cache/
backups/
```

卸载应用默认不会删除用户数据。

## 常见问题

### 找不到 Python Runtime

Windows 检查 `.venv-win\Scripts\python.exe`，macOS 检查 `.venv/bin/python`。重新初始化：

```bash
npm --prefix desktop run setup:dev
```

### Electron 下载失败或 `ECONNRESET`

打包脚本会自动重试临时下载错误。Windows CMD 可临时设置镜像：

```bat
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm --prefix desktop run pack
```

### 查看日志

应用错误页可以直接打开日志目录，也可以查看用户数据目录下的 `logs/`。

## 发布说明

GitHub Actions 分别构建 Windows x64、macOS arm64 和 macOS x64。正式发布前必须完成双平台功能验收，并在 CI 中配置 Windows 签名证书、Apple Developer ID 和 Apple 公证凭据。