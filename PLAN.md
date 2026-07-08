# 数码竞品监测 RAG 一期实施方案（Docker 封装）

## Summary
一期系统按 `FastAPI + Next.js + PostgreSQL + ChromaDB + LangChain + DashScope` 落地，并统一用 Docker 封装。目标是做一个面向内部团队的、`SKU/型号级` 的竞品监测与问答平台，既支持参数/价格/时间线的结构化对比，也支持评测/社区口碑的 RAG 问答，且所有结论可追溯到来源页面与抓取时间。

部署形态固定为 `Docker Compose` 多容器方案，适合作为本地开发、一体化测试和一期内网部署基线。

## Implementation Changes
### 1. 容器与服务拆分
- `frontend`：Next.js 容器，负责列表、详情、对比、问答、任务页。
- `api`：FastAPI 容器，负责产品查询、对比、问答、证据查看、任务管理接口。
- `worker`：采集与入库容器，负责抓取、清洗、抽取、标准化、分块、向量化。
- `scheduler`：定时任务容器，负责周期性抓取和重试编排。
- `postgres`：PostgreSQL 容器，存业务真值、历史快照、任务、问答元数据。
- `chromadb`：ChromaDB 容器，存非结构化 chunk 向量。
- 可选 `nginx`：如需要统一反向代理、静态入口和跨域收敛时再加；一期默认可不加。

### 2. Docker 封装规则
- 为 `frontend`、`api`、`worker` 各写独立 `Dockerfile`。
- 根目录提供 `docker-compose.yml`，统一编排网络、依赖、环境变量、健康检查、volume。
- 目录内提供 `.env.example`，不提交真实密钥。
- 真实 `DASHSCOPE_API_KEY` 只通过宿主环境变量或 Compose 覆盖注入，不写入镜像。
- 镜像构建采用分层缓存：
  - Python 服务先装依赖，再复制源码
  - Next.js 使用多阶段构建，区分 build 和 runtime
- 所有服务统一时区、日志输出格式、重启策略。

### 3. 数据与持久化边界
- PostgreSQL 持久化 volume：保存结构化真值与历史，不允许容器重建导致数据丢失。
- ChromaDB 持久化 volume：保存 embeddings 和 metadata。
- 原始抓取页面与清洗结果建议单独挂载 `data/raw` 与 `data/processed` volume，便于排查解析问题和重放。
- 日志默认走容器 stdout/stderr；如后续要做审计，可追加日志采集容器，但一期不强依赖。

### 4. PostgreSQL 与 ChromaDB 分工
- PostgreSQL 存：
  - `brand`
  - `product_series`
  - `product_sku`
  - `source_site`
  - `source_document`
  - `crawl_job`
  - `price_snapshot`
  - `spec_snapshot`
  - `promotion_snapshot`
  - `selling_point_snapshot`
  - `timeline_event`
- ChromaDB 存：
  - `chunk_id`
  - `source_document_id`
  - `sku_id`
  - `source_type`
  - `published_at`
  - `crawled_at`
  - `embedding_dim=1024`
- 结构化字段以 PostgreSQL 为唯一真值来源；ChromaDB 只用于非结构化检索。

### 5. 数据采集与标准化流程
- 一期只做定向采集，不做全网自动发现。
- 首批 source 类型固定为：
  - `official`
  - `ecommerce`
  - `review`
  - `community`
- 统一 pipeline：
  - 抓取原始页面
  - 存 HTML/正文快照
  - 清洗正文
  - 抽取字段
  - SKU 归一与字段标准化
  - 写入 PostgreSQL 快照
  - 文本分块并写入 ChromaDB
- 同一 SKU 的不同别名和写法必须映射到统一主档。
- 每次抓取写入新快照，不覆盖旧记录。

### 6. 问答与检索编排
- LangChain 只做编排，不做业务真值存储。
- 查询分类固定为：
  - `structured`
  - `unstructured`
  - `hybrid`
- `structured`：
  - 走 SQL 模板查询
  - 输出价格、参数、卖点、变更历史
- `unstructured`：
  - 用 `text-embedding-v4` 检索 ChromaDB
  - 用 `qwen3-rerank` 重排
  - 交给 `qwen3.6-plus` 生成总结
- `hybrid`：
  - 并行查 PostgreSQL 与 ChromaDB
  - 合并证据后生成最终回答
- 输出 JSON schema 固定为：
  - `answer_text`
  - `citations`
  - `compare_table`
  - `timeline_events`
  - `related_skus`
  - `missing_fields`
  - `generated_at`

### 7. 前端形态
- `Next.js` 页面固定为：
  - SKU 列表页
  - SKU 详情页
  - 竞品对比页
  - 问答页
  - 任务监控页
- 问答页默认展示：
  - 文本回答
  - 引用来源卡片
  - 对比表
  - 时间线事件
- 前端只消费结构化 JSON，不做模型自由文本解析。

## Public APIs / Interfaces
- 环境变量固定：
  - `DASHSCOPE_API_KEY`
  - `DASHSCOPE_BASE_URL`
  - `CHAT_MODEL`
  - `EMBEDDING_MODEL`
  - `EMBEDDING_DIM`
  - `RERANK_MODEL`
  - `POSTGRES_URL`
  - `CHROMA_HOST`
  - `CHROMA_PORT`
- 你当前给定的模型配置固定使用：
  - `CHAT_MODEL=qwen3.6-plus`
  - `EMBEDDING_MODEL=text-embedding-v4`
  - `EMBEDDING_DIM=1024`
  - `RERANK_MODEL=qwen3-rerank`
  - `DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`
- 核心接口固定：
  - `POST /ingestion/jobs`
  - `GET /ingestion/jobs/{id}`
  - `GET /products`
  - `GET /products/{sku_id}`
  - `GET /products/{sku_id}/timeline`
  - `POST /compare`
  - `POST /chat`
  - `GET /sources/{document_id}`

## Test Plan
- `docker compose up` 后，`frontend`、`api`、`worker`、`postgres`、`chromadb` 都能通过健康检查。
- PostgreSQL 与 ChromaDB 重启后数据仍保留，volume 生效。
- 官网、电商、评测、社区样本都能完成抓取、抽取、入库、向量化。
- 同一 SKU 多次抓取后，价格、参数、卖点能形成完整历史快照。
- 参数/价格问题只走 SQL 也能答；口碑总结问题能走向量检索并返回 citation。
- 混合问题能同时返回文本、引用、对比表、时间线。
- Chroma 检索失败、rerank 超时、字段缺失时，API 能降级返回而不是整条失败。
- 前端在容器环境下能正确连通 API，不依赖本机裸端口硬编码。

## Assumptions
- 一期部署基线为 `Docker Compose`，不是 Kubernetes。
- 一期为单团队内部使用，不做多租户。
- 以中文内容为主。
- 以 SKU/型号级分析为主，品牌/产品线级作为汇总视图。
- 默认保留全量历史快照。
- 默认回答形态为“文本 + 引用 + 对比表 + 时间线”。
- 你贴出的 `DASHSCOPE_API_KEY` 已暴露，正式实施前默认先轮换，再写入 Docker 运行环境。
