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
-