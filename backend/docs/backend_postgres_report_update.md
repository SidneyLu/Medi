# 后端更新说明：PostgreSQL、报告指标提取与历史记录

本文记录本次提交围绕“第一阶段问题”中 1、4、5 三项完成的后端改造。

## 1. 用户登录注册改为 PostgreSQL

此前注册用户、个人画像、聊天历史、报告记录主要写入本地 SQLite。现在应用业务数据统一写入 PostgreSQL。

新增文件：

- `backend/app/services/application_repository.py`
- `backend/sql/application_schema.sql`

新增 PostgreSQL 表：

- `medi_users`：注册用户、邮箱、密码哈希、创建时间。
- `medi_profiles`：用户画像 JSON 和画像标签。
- `medi_conversations`：聊天历史、消息 JSON、标题、预览、更新时间。
- `medi_reports`：上传报告、提取出的指标、原始文本、状态和错误信息。
- `medi_audit_logs`：登录注册、画像、聊天、报告相关审计日志。

涉及服务调整：

- `AuthService` 使用 `ApplicationRepository` 创建用户、登录校验和读取用户信息。
- `ProfileService` 使用 `ApplicationRepository` 保存/读取画像。
- `get_current_user()` 从 PostgreSQL 读取当前用户，确保 Bearer token 对应的用户仍存在。

SQLite 的 `Store` 仍保留，但只作为本地 seed knowledge fallback，不再承担用户和历史业务数据。

## 2. 前端历史记录的数据端支持

聊天历史现在由 PostgreSQL 的 `medi_conversations` 表支持：

- `POST /api/v1/chat/conversations` 创建会话。
- `GET /api/v1/chat/conversations` 读取当前用户历史会话列表。
- `GET /api/v1/chat/conversations/{id}` 读取指定会话消息。
- `POST /api/v1/chat/conversations/{id}/messages` 写入用户问题和助手回复。

报告历史现在由 PostgreSQL 的 `medi_reports` 表支持：

- `POST /api/v1/reports/analyze` 保存上传报告和提取指标。
- `GET /api/v1/reports` 返回当前用户报告历史。
- `GET /api/v1/reports/{id}` 返回报告详情。
- `PATCH /api/v1/reports/{id}/items` 保存用户修正后的指标。
- `DELETE /api/v1/reports/{id}` 删除报告。

## 3. 体检报告指标提取

新增文件：

- `backend/app/services/report_indicator_extractor.py`

能力：

- PDF：使用 PyMuPDF 读取文字层。
- 图片：预留 PaddleOCR 路径；未安装 OCR 时返回明确错误信息，避免接口 500。
- 文本解析：解析常见体检报告行，提取 `name/value/unit/reference_low/reference_high/status`。

示例输入：

```text
WBC 6.28 10^9/L 3.5-9.5
HGB 168 g/L 130-175
GLU 7.2 mmol/L 3.9-6.1
```

提取结果：

```text
白细胞计数 6.28 10^9/L normal
血红蛋白 168.0 g/L normal
葡萄糖 7.2 mmol/L high
```

后续医学知识匹配可以直接基于 `ReportItem.name`、`ReportItem.status` 和参考范围继续实现。

## 4. 配置和启动

后端现在会自动读取 `backend/.env`：

- `backend/app/core/config.py` 使用 `python-dotenv` 加载 `.env`。
- `backend/requirements.txt` 增加 `python-dotenv`。

`start-dev.ps1` 会在启动前检查 PostgreSQL 是否可达。如果数据库未启动，会提示先启动 PostgreSQL。

本机已通过 winget 安装 PostgreSQL 16，并创建项目库：

- database: `medi`
- user: `medi`
- password: 随机强密码，保存在 `backend/storage/postgres-local-secrets.json`

`backend/storage/` 已被 `.gitignore` 忽略，因此不会提交本地数据库密码、日志或上传文件。

## 5. 验证结果

已完成后端和前端入口联调：

```text
api register 201 0
api me 200
api conversation 201
api report 202
frontend login 200
db users 1
db conversations 1
db reports 1
```

说明：

- 注册用户已写入 PostgreSQL。
- 聊天历史已写入 PostgreSQL。
- 上传报告已写入 PostgreSQL，并能提取指标。
- 前端 `/login` 页面能通过 `http://127.0.0.1:3000/login` 正常访问。

