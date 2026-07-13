# XiangFlow AI 二次开发与上游同步指南

本文档用于帮助开发者理解翔域智流（XiangFlow AI）与 Langflow 官方仓库的关系，并统一二次开发、上游同步、版本升级、冲突处理和发布流程。

- **产品中文名：** 翔域智流
- **产品英文名：** XiangFlow AI
- **GitHub 仓库名：** `xiangflow-ai`
- **上游项目：** [Langflow](https://github.com/langflow-ai/langflow)
- **上游默认分支：** `upstream/main`

> [!IMPORTANT]
> 本文档描述 XiangFlow AI 的下游维护规范。Langflow 官方仓库自身的贡献与发布流程仍以 [CONTRIBUTING.md](./CONTRIBUTING.md)、[DEVELOPMENT.md](./DEVELOPMENT.md) 和 [RELEASE.md](./RELEASE.md) 为准。

## 目录

1. [项目与上游关系](#1-项目与上游关系)
2. [Git 远程仓库说明](#2-git-远程仓库说明)
3. [分支职责](#3-分支职责)
4. [首次初始化流程](#4-首次初始化流程)
5. [日常功能开发流程](#5-日常功能开发流程)
6. [同步 Langflow 官方代码](#6-同步-langflow-官方代码)
7. [将官方更新合入二开项目](#7-将官方更新合入二开项目)
8. [按官方版本标签升级](#8-按官方版本标签升级)
9. [冲突处理规范](#9-冲突处理规范)
10. [二开改动边界](#10-二开改动边界)
11. [自定义改动记录](#11-自定义改动记录)
12. [提交信息规范](#12-提交信息规范)
13. [发布流程](#13-发布流程)
14. [分支保护建议](#14-分支保护建议)
15. [禁止事项](#15-禁止事项)
16. [快速命令清单](#16-快速命令清单)

## 1. 项目与上游关系

XiangFlow AI 是基于 Langflow 官方开源仓库持续维护的二次开发项目。项目既需要吸收 Langflow 的功能、安全修复和架构改进，也需要稳定承载 XiangFlow AI 的品牌、业务和企业能力。

长期维护遵循以下原则：

- `official` 应尽可能与 `upstream/main` 保持一致，只用于保存官方代码的同步结果。
- `official` 不得提交 XiangFlow AI 自定义业务代码。
- `main` 和 `develop` 才允许存在 XiangFlow AI 二开代码。
- `main` 是稳定发布分支，不用于日常开发。
- `develop` 是日常开发和升级结果的集成分支。
- 上游更新不能直接推入或合入 `main`。
- 上游更新必须先进入 `upgrade/*` 分支，完成冲突处理和测试后，再通过 Pull Request 合入 `develop`。

该隔离方式让官方代码基线、二开集成状态和稳定发布状态可以分别追踪，降低升级时误覆盖自定义功能的风险。

## 2. Git 远程仓库说明

| 名称 | 地址 | 用途 |
| --- | --- | --- |
| `origin` | XiangFlow AI 仓库 | 推送二开代码、分支和发布标签 |
| `upstream` | Langflow 官方仓库 | 获取 Langflow 官方分支和版本标签 |

检查当前远程配置：

```bash
git remote -v
```

正确输出示例：

```text
origin  git@github.com:lien0219/xiangflow-ai.git (fetch)
origin  git@github.com:lien0219/xiangflow-ai.git (push)
upstream  https://github.com/langflow-ai/langflow.git (fetch)
upstream  https://github.com/langflow-ai/langflow.git (push)
```

如果名称、地址或用途与上表不一致，应先修正远程配置，再进行同步或推送操作。

## 3. 分支职责

| 分支 | 来源分支 | 合并目标 | 允许直接提交 | 允许强制推送 | 主要用途 |
| --- | --- | --- | --- | --- | --- |
| `official` | `upstream/main` | `upgrade/*` 获取其更新 | 仅允许受控同步，不允许功能提交 | 仅该长期分支允许受控使用 `force-with-lease` | 镜像 Langflow 官方代码 |
| `main` | 经验证的 `release/*` | 稳定发布分支，不作为日常合并来源 | 否 | 否 | 保存 XiangFlow AI 可发布的稳定代码 |
| `develop` | `main` 或初始化时的 `official` | `release/*`，并接收功能、修复和升级 PR | 否，建议全部通过 Pull Request | 否 | 日常开发集成 |
| `feature/*` | `develop` | `develop` | 是 | 否 | 开发新功能 |
| `fix/*` | `develop` | `develop` | 是 | 否 | 修复普通缺陷 |
| `hotfix/*` | `main` | `main` 和 `develop` | 是 | 否 | 修复线上紧急问题 |
| `upgrade/*` | `develop` | `develop` | 是 | 否 | 合入并验证 `official` 或官方版本标签的更新 |
| `release/*` | `develop` | `main` | 仅允许发布准备和必要修复 | 否 | 版本冻结、验证和发布准备 |

核心规则：

- `official` 只同步 `upstream/main`，不得承载二开功能。
- `main` 禁止直接开发或直接提交。
- `develop` 是日常集成分支。
- `feature/*` 从 `develop` 创建，并通过 Pull Request 合回 `develop`。
- `fix/*` 从 `develop` 创建，并通过 Pull Request 合回 `develop`。
- `hotfix/*` 从 `main` 创建，修复后必须同时合回 `main` 和 `develop`，避免后续版本丢失修复。
- `upgrade/*` 从 `develop` 创建，并在该分支中合入 `official` 的更新或指定 Langflow 标签。
- `release/*` 从 `develop` 创建，验证完成后通过 Pull Request 合入 `main`。

> [!NOTE]
> “允许直接提交”表示开发者可以在对应临时分支上创建提交，不代表可以绕过 Pull Request 直接修改长期分支。

## 4. 首次初始化流程

以下流程适用于从 Langflow 官方仓库首次建立 XiangFlow AI 仓库。执行前应确认目标目录不存在，且当前账号具备 XiangFlow AI 仓库的推送权限。

```bash
git clone https://github.com/langflow-ai/langflow.git xiangflow-ai
cd xiangflow-ai
git remote rename origin upstream
git remote add origin git@github.com:lien0219/xiangflow-ai.git
git branch -m official
git branch --set-upstream-to=upstream/main official
git push origin official
git switch -c main
git push -u origin main
git switch -c develop
git push -u origin develop
```

初始化完成后的跟踪关系应为：

- `official` 跟踪 `upstream/main`，用于获取官方更新。
- `main` 跟踪 `origin/main`。
- `develop` 跟踪 `origin/develop`。

可使用以下命令检查分支跟踪关系：

```bash
git branch -vv
```

## 5. 日常功能开发流程

以开发 Skills 管理功能为例，先从最新的 `develop` 创建功能分支：

```bash
git switch develop
git pull origin develop
git switch -c feature/skills-manager
```

开发完成并验证后提交、推送功能分支：

```bash
git add .
git commit -m "feat: add skills manager"
git push -u origin feature/skills-manager
```

然后创建 Pull Request：

```text
feature/skills-manager -> develop
```

Pull Request 应说明功能目的、主要改动、测试方式、数据库或 API 影响以及回滚方式。功能代码禁止直接提交到 `main` 或 `official`。

## 6. 同步 Langflow 官方代码

同步前先切换到 `official` 并确认工作区状态：

```bash
git switch official
git status
git fetch upstream --prune --tags
git reset --hard upstream/main
git push origin official --force-with-lease
```

> [!WARNING]
> 执行 `reset --hard` 前，必须确认当前分支确实是 `official`，并确认工作区干净。该操作会丢弃 `official` 上未提交的本地修改和未推送的自定义提交。

同步规则：

- `official` 不允许保存任何 XiangFlow AI 自定义提交。
- `official` 应精确反映当前选定的 `upstream/main` 状态。
- `official` 是唯一允许使用 `force-with-lease` 的长期分支。
- 对 `official` 的强制更新必须由管理员或受控同步流程执行。
- `main` 和 `develop` 禁止任何形式的强制推送。
- 如果 `official` 出现无法丢弃的提交，应停止同步并先确认提交归属，不得直接覆盖。

## 7. 将官方更新合入二开项目

完成 `official` 同步后，从最新的 `develop` 创建升级分支。不得将上游更新直接合入 `main`：

```bash
git switch develop
git pull origin develop
git switch -c upgrade/langflow-latest
git merge --no-ff official
```

升级分支必须依次完成：

1. 理解并解决全部合并冲突。
2. 按项目规范安装或同步依赖。
3. 执行前端格式化、静态检查和类型检查。
4. 执行后端格式化、静态检查和类型检查。
5. 执行前端与后端单元测试。
6. 执行完整构建测试。
7. 检查数据库迁移的顺序、依赖和兼容性。
8. 检查新增、删除或语义变化的环境变量。
9. 检查工作流数据结构和节点序列化格式变化。
10. 检查 XiangFlow AI 自定义组件与官方组件基类的兼容性。
11. 提交升级和冲突处理结果。
12. 创建 Pull Request 合入 `develop`，完成代码审查和 CI 验证。

可根据改动范围执行项目现有检查命令，例如：

```bash
make format
make lint
make test_frontend
make unit_tests
make run_cli
```

提交并推送升级分支：

```bash
git add .
git commit -m "chore: merge latest Langflow upstream"
git push -u origin upgrade/langflow-latest
```

然后创建 Pull Request：

```text
upgrade/langflow-latest -> develop
```

升级 Pull Request 中应记录合入的上游提交、冲突文件、兼容性结论、迁移要求和测试结果。

## 8. 按官方版本标签升级

生产项目更推荐按 Langflow 稳定版本标签升级，而不是始终追随快速变化的 `upstream/main`。版本标签可提供明确、可复现的升级基线，也便于回滚和审计。

先获取并查看官方标签：

```bash
git fetch upstream --tags
git tag --sort=-version:refname
```

确认目标标签后，从最新的 `develop` 创建升级分支并合入该标签：

```bash
git switch develop
git pull origin develop
git switch -c upgrade/langflow-vX.Y.Z
git merge --no-ff vX.Y.Z
```

如果某个标签无法直接作为合并目标，或本地存在同名标签，应先确认标签名称、来源和对应提交：

```bash
git show vX.Y.Z
git log -1 vX.Y.Z
```

确认标签属于 Langflow 官方发布且提交正确后，再继续冲突处理、测试和 Pull Request 流程。XiangFlow AI 自身发布标签与 Langflow 标签可能同名，因此长期维护时应在发布记录中同时保存上游版本和上游提交哈希，避免仅依赖标签名称判断基线。

## 9. 冲突处理规范

发生合并冲突后，先查看冲突范围：

```bash
git status
```

处理原则：

- 先理解 Langflow 官方改动的目的、上下文和兼容性要求。
- 再确认 XiangFlow AI 自定义改动的业务目的和不可丢失的行为。
- 不允许在未理解双方改动的情况下直接选择 Accept Current 或 Accept Incoming。
- 工作流核心执行引擎优先兼容官方实现，再通过扩展点恢复二开能力。
- 品牌、Skills、MCP、租户和自定义业务模块应保留 XiangFlow AI 的二开实现，同时适配新的官方接口。
- 数据库迁移文件不能随意删除、覆盖、重排或复用版本标识。
- `package-lock.json`、`uv.lock` 等依赖锁文件应重新生成，或严格按照项目现有依赖管理规范处理，不应手工拼接冲突内容。
- 解决冲突后必须完成与改动范围匹配的格式化、静态检查、单元测试、构建和人工验证。

逐个解决冲突后标记文件并完成合并提交：

```bash
git add <resolved-files>
git commit
```

如果无法安全解决，或发现升级方向错误，应取消本次合并：

```bash
git merge --abort
```

取消后应记录阻塞原因，并在明确处理方案后重新发起升级，不得以删除冲突代码或跳过测试的方式强行完成合并。

## 10. 二开改动边界

推荐扩展区域：

- 品牌与 UI
- Skills 管理
- MCP 管理
- 自定义组件
- 模型供应商扩展
- 企业知识库
- 项目管理
- 用户与租户
- RBAC
- 审计日志
- 用量统计
- API 网关
- 工作流市场
- 工作流版本管理

慎重修改区域：

- 工作流核心数据结构
- Langflow 执行器核心
- 官方组件基类
- 数据库历史迁移
- API 基础协议
- 节点序列化格式
- 官方鉴权底层
- 官方插件加载机制

新增二开能力时，按以下优先级选择实现方式：

1. 新增模块。
2. 扩展接口。
3. 自定义组件。
4. 配置覆盖。
5. 适配器模式。

应尽量避免直接修改官方核心文件。确需修改时，必须保持改动集中、边界清晰、测试完整，并在自定义改动记录中说明原因、影响和后续升级策略。

## 11. 自定义改动记录

建议后续按需建立以下文档目录。本指南仅定义结构，不要求创建无内容文件：

```text
docs/customization/
├── architecture.md
├── branding.md
├── database-changes.md
├── api-changes.md
├── custom-components.md
├── upstream-upgrade.md
└── breaking-changes.md
```

每一次重要二开都应记录：

- 修改原因和业务背景。
- 修改文件和主要符号。
- 对上游代码及后续同步的影响。
- 数据库结构、数据迁移和回滚影响。
- API 路径、请求、响应和兼容性影响。
- 是否可能造成上游升级冲突，以及预期冲突区域。
- 回滚方法和必要的数据恢复步骤。
- 自动化测试与人工验证方式。

每次上游升级还应在 `upstream-upgrade.md` 中记录 Langflow 版本、上游提交、升级日期、负责人、冲突摘要和验证结果。

## 12. 提交信息规范

项目采用 [Conventional Commits](https://www.conventionalcommits.org/)。提交信息应简洁描述改动目的，并保持一个提交只承担一个清晰职责。

示例：

```text
feat: add skills registry
fix: resolve workflow execution error
docs: add customization guide
refactor: isolate tenant service
chore: sync Langflow upstream
build: update frontend dependencies
test: add workflow runtime tests
perf: optimize component loading
revert: revert workflow schema change
```

上游同步推荐使用：

```text
chore: sync Langflow upstream to <commit-or-version>
```

如提交包含不兼容变更，应按 Conventional Commits 规范标记 breaking change，并在发布说明和 `breaking-changes.md` 中记录迁移方法。

## 13. 发布流程

推荐发布路径：

```text
develop
  -> release/vX.Y.Z
  -> main
  -> Git tag
  -> release
```

从已验证的 `develop` 创建发布准备分支：

```bash
git switch develop
git pull origin develop
git switch -c release/v0.1.0
git push -u origin release/v0.1.0
```

在 `release/*` 上仅允许版本准备、发布说明、必要缺陷修复和最终验证，不再接收普通新功能。验证完成后，通过 Pull Request 将 `release/v0.1.0` 合入 `main`。

合入并确认 CI 通过后创建发布标签：

```bash
git switch main
git pull origin main
git tag -a v0.1.0 -m "XiangFlow AI v0.1.0"
git push origin v0.1.0
```

每个 XiangFlow AI 版本必须分别记录自身版本和上游基线，例如：

- **XiangFlow AI：** `v0.1.0`
- **Based on Langflow：** `vX.Y.Z`
- **Upstream commit：** `<commit hash>`

发布后，应确认对应 GitHub Release、构建产物、数据库迁移说明、环境变量变化和回滚方案完整可用。

## 14. 分支保护建议

建议在 GitHub 中为长期分支配置以下保护规则。

### `main`

- 禁止直接推送。
- 禁止强制推送。
- 禁止删除。
- 必须通过 Pull Request。
- 必须通过要求的状态检查。
- 必须解决所有讨论后才能合并。

### `develop`

- 建议所有改动通过 Pull Request。
- 禁止强制推送。
- 禁止删除。
- 建议要求核心检查通过后才能合并。

### `official`

- 禁止功能开发。
- 只允许管理员或受控同步流程更新。
- 允许受控的 `force-with-lease`。
- 不接受任何 XiangFlow AI 二开功能 Pull Request。
- 建议限制可推送人员，并保留同步日志。

## 15. 禁止事项

- 禁止在 `official` 开发二开功能。
- 禁止直接向 `main` 开发和提交。
- 禁止对 `main` 执行 force push。
- 禁止将 `upstream` 直接覆盖 `develop` 或 `main`。
- 禁止未经测试直接合入官方升级。
- 禁止随意修改、删除、覆盖或重排数据库迁移历史。
- 禁止将密钥、Token、密码或其他敏感信息提交到仓库。
- 禁止把二开逻辑散落到大量官方核心文件中。
- 禁止在未记录的情况下改变工作流数据协议。
- 禁止使用普通 force push 替代 `force-with-lease`。
- 禁止在分支和工作区状态不明确时执行破坏性 Git 操作。

## 16. 快速命令清单

### 查看当前分支

```bash
git branch --show-current
```

### 查看分支跟踪关系

```bash
git branch -vv
```

### 查看远程

```bash
git remote -v
```

### 同步官方

```bash
git switch official
git status
git fetch upstream --prune --tags
git reset --hard upstream/main
git push origin official --force-with-lease
```

### 创建功能分支

```bash
git switch develop
git pull origin develop
git switch -c feature/<name>
```

### 创建升级分支

```bash
git switch develop
git pull origin develop
git switch -c upgrade/langflow-<version>
git merge --no-ff official
```

### 检查当前修改

```bash
git status
git diff
git diff --staged
```

### 查看当前上游版本

```bash
git describe --tags --always
git rev-parse HEAD
```

执行任何同步、升级或发布操作前，都应先确认当前分支、工作区状态和远程跟踪关系，避免基于错误分支或过期代码执行维护流程。
