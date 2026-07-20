# Medi 医学知识数据说明

本目录保存 Medi 医疗健康 RAG 系统使用的处理后知识数据。

## 目录结构

- `processed/knowledge_chunks.jsonl`
- `processed/knowledge_embeddings.npz`
- `processed/embedding_manifest.json`

## 数据文件说明

### knowledge_chunks.jsonl

类型：JSON Lines 文本文件。

用途：保存经过 OCR、清洗和切分后的医学知识块，每行对应一个知识块。

主要字段包括：

- `chunk_id`：知识块唯一标识
- `document_id`：来源文档标识
- `pdf_page`：原始 PDF 页码
- `chunk_index`：页面内知识块序号
- `article_title`：文档标题
- `section_title`：章节标题
- `source_url`：原文定位地址
- `category`：知识分类
- `content`：知识块正文
- `tags`：知识标签
- `content_hash`：正文哈希

当前共包含 4003 个知识块，导入 PostgreSQL 的 `msd_knowledge_chunks` 表，用于保存正文和元数据。

### knowledge_embeddings.npz

类型：NumPy 压缩二进制文件。

用途：保存所有知识块对应的向量，用于导入 Milvus 并执行语义检索。

向量信息：

- 模型：`BAAI/bge-small-zh-v1.5`
- 向量数量：4003
- 向量维度：512
- 数据类型：`float32`
- 向量已进行 L2 归一化

文件内部包含：

- `embeddings`：向量矩阵
- `chunk_ids`：对应的知识块 ID
- `content_hashes`：正文哈希
- `pdf_pages`：对应的 PDF 页码

### embedding_manifest.json

类型：JSON 校验文件。

用途：记录 Embedding 模型、向量维度、知识块数量和生成范围，并在导入数据时校验 JSONL 与 NPZ 是否属于同一版本。

三个文件必须配套使用，不能只修改其中一个文件。

## 数据导入方法

进入后端目录：

    cd backend

启动 PostgreSQL 和 Milvus：

    docker compose -f docker-compose.knowledge.yml up -d

设置环境变量：

    $env:DATABASE_URL="postgresql://medi:medi@localhost:5432/medi"
    $env:MILVUS_URI="http://localhost:19530"
    $env:MILVUS_COLLECTION="medical_chunks"

执行导入：

    python scripts/import_knowledge_data.py

导入完成后：

- PostgreSQL 保存知识块正文和元数据
- Milvus 保存知识块向量
- 两个数据库通过 `chunk_id` 一一对应

## 在线检索流程

用户问题首先通过本地 `BAAI/bge-small-zh-v1.5` 模型生成查询向量，随后在 Milvus 中检索相关知识块，再根据 `chunk_id` 从 PostgreSQL 回查完整正文、标题和 PDF 页码，最后将结果交给 RAG 回答模块。

## 未提交的数据

以下内容不属于项目运行所需的最小正式数据包，因此不提交：

- 原始 MSD PDF
- 页面级 OCR 中间结果 `msd_pages.jsonl`
- OCR 临时文件
- PostgreSQL 本地数据文件
- Milvus、MinIO 和 etcd 数据卷
- SQLite 用户与会话数据库
- 用户上传的报告
- 日志和测试输出

## 注意事项

1. 处理后的数据仅供 Medi 项目内部开发、测试及授权场景使用。
2. 原始医学资料和用户数据不得上传至公开仓库。
3. 更新知识块后，必须重新生成对应向量和 Manifest。
4. 不要手工修改 `knowledge_embeddings.npz`。
