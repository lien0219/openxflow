# 同机 Docker 单实例测试

这套配置在一台 Linux 测试服务器上运行一个 OpenXFlow 应用 worker，以及
PostgreSQL 16/pgvector、Redis 和 SeaweedFS S3 存储。应用沿用
`docker-compose.prod.yml` 和 `prod` 启动检查；基础服务由
`docker-compose.single-node-services.yml` 管理。

生产环境统一以 `production.env.example` 为基础。本方案只覆盖前期同机启动测试，
共享存储、Redis、认证和密钥策略沿用生产配置；后续多实例的配置约定与部署要求见
[生产部署说明](PRODUCTION_DEPLOYMENT.md#multiple-api-instances)。

| 文件 | 用途 |
| --- | --- |
| `docker-compose.prod.yml` | 运行一个应用 worker，由 `deploy-main.sh` 管理 |
| `docker-compose.single-node-services.yml` | 同机 PostgreSQL/pgvector、Redis、S3 |
| `production.env.example` | 生产应用基础配置 |
| `single-node.env.example` | 同机地址和 HTTP 测试覆盖项，追加在生产模板之后 |

本方案使用上面两份 Compose；`deploy/docker-compose.yml` 是另一套旧部署方案。
不要把基础服务合并进部署助手使用的应用 Compose；助手要求其中只有应用服务。

两份 Compose 使用同一个 `openxflow` 项目和 `openxflow_default` 网络，因此应用
可以通过 `postgres`、`redis`、`objectstore` 访问依赖。基础服务没有宿主机端口映射。
应用默认只发布 `127.0.0.1:7860`。这是单机测试拓扑，不提供跨主机容灾。
后续跨主机部署时，为依赖配置可达的私网地址或迁移到共享服务，并保留数据库、对象
存储数据及密钥；这里的 Docker 服务名仅在本机网络内有效。

需要 Docker Compose v2、Bash、OpenSSL，以及部署助手使用的 Python 3.10+。
以下命令均在仓库的 `deploy/` 目录执行。首次安装请使用独立测试服务器和空数据卷。

## 1. 创建环境配置

```bash
cd /path/to/openxflow/deploy
(umask 077; set -C; cat production.env.example single-node.env.example > .env)
```

命令在 `.env` 已存在时会拒绝覆盖。已有文件请按两份模板核对，不要重复追加覆盖项。
后面的同名配置覆盖前面的值，因此生成文件中的重复项是有意保留的。编辑 `.env`，
替换全部 `replace-*` 和 `example.invalid` 占位值，并把 `OPENXFLOW_IMAGE` 改成实际
可拉取的固定版本、完整 SHA 标签或 digest。被同机覆盖项替换的连接地址无需再填写。
模板中的镜像版本仅是示例。

可用下面的命令生成值，再分别填入配置。不要在后续重启时重新生成密钥或密码。

```bash
# 分别为 POSTGRES_PASSWORD、REDIS_PASSWORD 和管理员密码生成不同的值
openssl rand -hex 24

# LANGFLOW_SECRET_KEY：URL-safe base64 编码的 32 字节 Fernet 密钥
openssl rand -base64 32 | tr '+/' '-_'

# 分别为 LANGFLOW_CACHE_SIGNING_KEY、AWS_ACCESS_KEY_ID、AWS_SECRET_ACCESS_KEY 生成不同的值
openssl rand -hex 32
```

模板会将数据库和 Redis 密码插入连接 URL，使用十六进制密码可避免 URL 编码问题。
保留 `LANGFLOW_AUTO_LOGIN=false`，以 `LANGFLOW_SUPERUSER` 和
`LANGFLOW_SUPERUSER_PASSWORD` 配置的账号登录；公共注册默认关闭。

## 2. 准备应用目录并启动基础服务

应用以 UID 1000 运行。以下目录命令对应默认 `OPENXFLOW_DATA_DIR=./data`；如果改了
该变量，同步调整宿主机目录。将 S3 的 path-style 配置放入持久化目录，供应用内 AWS SDK 读取：

```bash
sudo install -d -o 1000 -g 0 -m 0700 data data/config
sudo install -o 1000 -g 0 -m 0600 aws-config.example data/config/aws-config

docker compose --env-file .env -f docker-compose.single-node-services.yml config --quiet
docker compose --env-file .env -f docker-compose.prod.yml config --quiet

docker compose --env-file .env -f docker-compose.single-node-services.yml up -d --wait --wait-timeout 240
```

PostgreSQL 在首次初始化空卷时创建 `vector` 扩展。SeaweedFS 根据环境变量创建测试
bucket 和 S3 凭据；其健康检查使用签名请求访问 bucket。Redis 启用密码认证及 AOF
持久化。三个基础服务都使用命名数据卷，应用配置保存在 `data/`。

`initdb/01-vector.sql` 只对新 PostgreSQL 卷执行。如果复用已有数据库，先确认它属于
本次测试，再按需执行：

```bash
docker compose --env-file .env -f docker-compose.single-node-services.yml exec -T postgres \
  psql -U openxflow -d openxflow -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

## 3. 检查镜像并部署应用

基础服务健康后，使用已有的生产部署助手部署应用。将下面的镜像替换为与 `.env`
一致、已发布的实际版本：

```bash
umask 077
IMAGE='ghcr.io/lien0219/openxflow:main-vX.Y.Z'
./deploy-main.sh "$IMAGE" --inspect > deployment-plan.json
```

按 [生产部署说明](PRODUCTION_DEPLOYMENT.md#upgrade-gate) 准备 `.upgrade-gate.json`。
镜像、配置和迁移字段取自 `deployment-plan.json`；备份和恢复演练字段填写实际完成的
记录。首次部署的 `previous_digest` 为 `null`，`approved_at` 使用带时区的当前时间，
有效期为 24 小时。设置文件权限后启动：

```bash
chmod 600 .upgrade-gate.json
./deploy-main.sh "$IMAGE"

docker compose --env-file .env -f docker-compose.prod.yml ps
curl -fsS http://127.0.0.1:7860/health_check
```

部署助手只管理应用服务，基础服务继续运行。应用启动会执行 Alembic 迁移；镜像回退
不会回退 PostgreSQL、Redis 或对象存储的数据。保留 `.deployed-image`，以后升级继续
使用部署助手。修改配置后重新生成检查结果和对应的升级门禁。

## 4. 访问、日志与停止

从开发电脑建立 SSH 隧道，然后在浏览器打开 `http://localhost:7860`：

```bash
ssh -L 7860:127.0.0.1:7860 用户@服务器IP
```

公网访问时，在服务器配置带 HTTPS 的反向代理，转发到 `127.0.0.1:7860`，并在 `.env`
启用下面两项，再重新生成部署检查结果和升级门禁：

```dotenv
LANGFLOW_ACCESS_SECURE=true
LANGFLOW_REFRESH_SECURE=true
```

HTTP SSH 隧道测试保持这两项为 `false`，否则浏览器无法通过 HTTP 正常发送认证 Cookie。
同时将 `LANGFLOW_CORS_ORIGINS` 从测试用 localhost 地址改为实际公网 HTTPS Origin。

```bash
# 应用与基础服务日志
docker compose --env-file .env -f docker-compose.prod.yml logs --tail 100 openxflow
docker compose --env-file .env -f docker-compose.single-node-services.yml logs --tail 100

# 停止测试：先停应用，再停基础服务，保留数据
docker compose --env-file .env -f docker-compose.prod.yml stop openxflow
docker compose --env-file .env -f docker-compose.single-node-services.yml stop
```

两份配置共同管理同一个项目，不要使用 `--remove-orphans`。保留命名卷、`data/` 和
`.env`，不要用 `down -v` 清理这套测试数据。修改 PostgreSQL 初始化密码或 S3 凭据前，
先完成对应服务内部的凭据变更；仅编辑 `.env` 不等于修改已有数据卷中的账号。

仓库检查可以验证 Compose 解析、环境变量映射和部署门禁。镜像实际启动、数据库迁移、
文件上传、知识库查询以及完整工作流执行，需要在目标测试服务器完成验收。
