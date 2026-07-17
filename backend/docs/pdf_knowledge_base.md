# PDF 知识库启动指南

本流程消费 MinerU 已完成的本地解析结果，将文本块写入 PostgreSQL、向量写入 Milvus。原始 PDF 不会上传到 Qwen；只有待嵌入的文本块和查询/候选块会调用 Qwen API。

## 1. 启动依赖

```powershell
cd backend
Copy-Item .env.example .env
docker compose -f docker-compose.knowledge.yml up -d
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

填写 `.env` 中的 `DASHSCOPE_API_KEY` 和已获准使用的 `QWEN_RERANK_URL`。不要将密钥提交到 Git。

## 2. 使用 MinerU 解析

在本地完成 MinerU 解析，并确认输出目录内有结构化 JSON，优先使用 `content_list.json`。本项目不自动下载或安装 MinerU 模型。

```powershell
# 示意：按你安装的 MinerU 版本运行其本地解析命令
# 输出目录应包含 content_list.json 或等价结构化 JSON
<mineru-command> "..\默克家庭医学手册.pdf" --output "data\parsed\merck-manual"
```

## 3. 构建知识库

```powershell
python scripts\build_knowledge_base.py `
  --pdf "..\默克家庭医学手册.pdf" `
  --parsed-dir "data\parsed\merck-manual" `
  --title "默克家庭医学手册"
```

重复执行是幂等的：内容哈希未变化的向量会命中 PostgreSQL 嵌入缓存。中断后重新运行即可继续写入；Milvus 会按稳定 chunk ID upsert。

## 4. 启动 API

```powershell
uvicorn app.main:app --reload
```

Swagger 位于 `http://127.0.0.1:8000/docs`。登录后，聊天引用将返回 `/api/v1/content/citations/{chunk_id}`；页面预览端点为 `/api/v1/content/documents/{document_id}/pages/{page_no}/preview`。

## 常见问题

- `No MinerU content-list JSON`: 指定的目录不是 MinerU 的结构化输出目录，或需要导出 content-list JSON。
- `DATABASE_URL and MILVUS_URI`: 检查 `.env` 并确认 Docker 服务已启动。
- 嵌入调用失败：检查模型名、DashScope Key、网络及账户权限；不要打印 Key 或原始医学内容。
- 重排失败：系统会自动退回 RRF 排序；设置 `QWEN_RERANK_URL` 后才会实际调用 Qwen3 Rerank。
- 页面预览失败：确认 `KNOWLEDGE_PDF_PATH` 对 API 进程可读，并已安装 `PyMuPDF`。
