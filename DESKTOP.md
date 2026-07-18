# OpenXFlow 桌面端指南

OpenXFlow Desktop 使用 Electron 承载现有 React 前端，并在本机启动现有 FastAPI / Python 运行时。桌面端不复制业务代码，Web、Windows 和 macOS 共用同一套前端、后端、工作流和组件实现。

## 支持平台

| 平台 | 架构 | 开发运行 | 安装包 |
| --- | --- | --- | --- |
| Windows 10 / 11 | x64 | 支持 | NSIS `.exe` |
| macOS | Apple Silicon arm64 | 支持 | `.dmg` |
| macOS | Intel x64 | 支持 | `.dmg` |

> Python 虚拟环境包含平台和架构相关的原生依赖，不能在 Windows、macOS、Linux、WSL 或不同 CPU 架构之间复制使用。

## 架构说明

```text
Electron 主进程
├── 创建和管理窗口
├── 分配 127.0.0.1 随机端口
├── 启动和停止 Python 后端
├── 管理原生文件选择器与系统能力
└── 加载本机 FastAPI 提