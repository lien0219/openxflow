# OpenXFlow Desktop

OpenXFlow Desktop 是现有 React 前端和 FastAPI/Python 运行时的 Electron 桌面外壳，不复制业务代码。

完整安装、启动、打包、Windows/macOS 测试、数据目录和常见问题说明请查看：

- [OpenXFlow 桌面端指南](../DESKTOP.md)

## 常用命令

在仓库根目录执行：

```bash
npm --prefix desktop install
npm --prefix desktop run dev:setup
```

首次初始化完成后：

```bash
npm --prefix desktop run dev
```

质量检查：

```bash
npm --prefix desktop run typecheck
npm --prefix desktop run lint
npm --prefix desktop test
npm --prefix desktop run build
```

打包测试：

```bash
npm --prefix desktop run pack
```

完整运行时和安装包：

```bash
npm --prefix desktop run frontend:prepare
npm --prefix desktop run runtime:build
npm --prefix desktop run runtime:verify
npm --prefix desktop run dist
```

## 平台环境

```text
Windows  .venv-win\Scripts\python.exe
macOS    .venv/bin/python
Linux    .venv/bin/python
```

桌面命令不会改变 `make run_cli`、`make backend` 或 `make frontend` 等 Web 端命令。