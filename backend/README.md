# Medi 后端说明

本目录按 `第一阶段.docx` 和 `PLAN(1).md` 搭建了第一阶段后端骨架：用户注册登录、健康画像与标签、医学知识检索、带引用的 RAG 问答、体检/化验单上传与解读结果查询。

## 快速运行

```powershell
cd C:\Users\pointzu\Desktop\placement\new\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

启动后访问：

- Swagger: `http://127.0.0.1:8000/docs`
- 健康检查: `GET http://127.0.0.1:8000/api/v1/health`

## 后端架构

```text
backend/
  app/
    api/            FastAPI 路由与登录鉴权依赖
    core/           配置、安全、统一响应和异常处理
    models/         Pydantic 请求/返回模型
    services/       业务服务：认证、画像、RAG、报告、知识检索
    data/           示例知识块，真实部署时替换为 MSD 授权入库内容
  contracts/        给前端联调使用的 TypeScript 接口类型
  docs/             接口契约和 MSD 文本标签说明
```

当前实现用 SQLite 做本地开发存储，方便前后端先联调。生产设计仍按计划替换为 PostgreSQL + Milvus：

- PostgreSQL: 用户、画像、报告、MSD 页面元数据、章节、审计日志。
- Milvus: 章节级或知识块级 embedding 向量索引。
- Qwen API: 问答生成、查询改写、重排、报告解释。
- OCR: 体检报告字段、单位、参考区间、采样时间提取。

## 已实现接口

- `POST /api/v1/auth/register`: 注册并返回 access token。
- `POST /api/v1/auth/login`: 登录并返回 access token。
- `PUT /api/v1/profile`: 保存个人健康信息并生成标签。
- `GET /api/v1/profile`: 获取个人健康信息和标签。
- `GET /api/v1/knowledge/search`: 关键词检索知识块。
- `POST /api/v1/chat/query`: 使用画像标签 + 知识块生成带引用的医学科普回答。
- `POST /api/v1/reports/analyze`: 上传 JPG/JPEG/PNG/PDF 报告，保存文件并返回结构化解读占位结果。
- `GET /api/v1/reports/{report_id}`: 查询报告解读结果。

## 安全边界

回答只基于检索到的知识块组织内容；没有证据时明确说明无法给出医学判断。红旗症状规则独立于 LLM，命中胸痛、呼吸困难、意识障碍、严重外伤、大出血、过敏性休克等关键词时，直接输出高风险急诊提示。

`app/data/seed_knowledge.json` 只是联调示例，不是正式 MSD 内容。真实上线前应先完成 MSD 授权、内容清洗、版本化索引、医学审核和引用校验。
