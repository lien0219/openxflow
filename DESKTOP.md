# OpenXFlow 桌面端指南

OpenXFlow Desktop 使用 Electron 承载现有 React 前端，并在本机启动现有 FastAPI/Python 后端。Web、Windows 和 macOS 共用业务源码，桌面端只负责窗口、进程、原生能力和安装包。

## 支持平台

| 平台 | 架构 | 安装包 |
| --- | --- | --- |
| Windows 10/11 | x64 | NSIS `.exe` |
| macOS | Apple Silicon arm64 | `.dmg` |
| macOS | Intel x64 | `.dmg` |

Python 环境不能跨 Windows、macOS、Linux、WSL 或不同 CPU 架构复制使用。

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

## 获取桌面端分支

```bash
git fetch origin
git switch feature/desktop-app
git pull --ff-only origin feature/desktop-app
```

本地没有该分支时：

```bash
git switch -c feature/desktop-app --track origin/feature/desktop-app
```

## 首次安装并启动

先安装 Electron 工程依赖：

```bash
npm --prefix desktop install
```

然后一键准备 Python、后端依赖、前端资源并启动：

```bash
npm --prefix desktop run dev:setup
```

环境目录：

```text
Windows  .venv-win\Scripts\python.exe
macOS    .venv/bin/python
Linux    .venv/bin/python
```

`.venv-win/` 已加入 `.gitignore`。Windows 可以保留原有 WSL `.venv`，桌面端会优先使用 `.venv-win`。

初始化完成后，日常启动只需：

```bash
npm --prefix desktop run dev
```

只初始化、不启动：

```bash
npm --prefix desktop run setup:dev
```

## 与 Web 端的关系

桌面端命令不会替换或修改原 Web 启动方式。以下命令继续保持不变：

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

全部通过后再进行打包测试。

## 打包命令

未安装版烟雾测试：

```bash
npm --prefix desktop run pack
```

生成目录：

```text
desktop/release/
```

完整安装包需要先构建前端和内置 Python Runtime：

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

运行时必须在目标操作系统和目标架构上原生构建。

## macOS 本地测试

确认架构：

```bash
uname -m
```

`arm64` 为 Apple Silicon，`x86_64` 为 Intel。首次运行未签名应用时，可在 Finder 中右键应用并选择“打开”。正式发布需要 Developer ID、Notarization 和 Stapling。

重点验证：窗口关闭与 Dock 恢复、`Command+Q` 完全退出、文件选择器、工作流保存和重启后数据持久化，以及活动监视器中无残留 Python 进程。

## 用户数据目录

Windows：

```text
%APPDATA%\OpenXFlow\
```

macOS：

```text
~/Library/Application Support/OpenXFlow/
```

目录包含 `config`、`database`、`files`、`components`、`plugins`、`logs`、`cache` 和 `backups`。卸载应用默认不会删除用户数据。

## 常见问题

### `spawn EINVAL`

先拉取最新分支代码。Windows 的 npm 子进程必须通过兼容的启动方式执行，相关脚本已处理该差异。

### 找不到 Python Runtime

Windows 检查 `.venv-win\Scripts\python.exe`，macOS 检查 `.venv/bin/python`。可重新运行：

```bash
npm --prefix desktop run setup:dev
```

### Electron 下载失败或 `ECONNRESET`

Windows CMD 可临时设置镜像：

```bat
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
npm --prefix desktop run pack
```

打包脚本会自动重试临时下载错误。

### 日志位置

应用错误页可打开日志目录。也可直接查看用户数据目录下的 `logs/`。

## 发布说明

GitHub Actions 会分别构建 Windows x64、macOS arm64 和 macOS x64。正式发布前必须完成双平台功能验收，并在 CI 中配置 Windows 签名证书、Apple Developer ID 和公证凭据。