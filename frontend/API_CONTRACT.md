# Medi 前端对后端接口要求

> 本文档依据当前前端实现整理：`frontend/src/lib/api/types.ts`、`client.ts`、以及 Mock（`handlers.ts`）。  
> 联调时以后端实现这些约定为准；与早期 `PLAN/PLAN1.md` 示例不一致处，**以本文档为准**。

## 1. 通用约定

### 1.1 Base URL 与版本

| 项 | 约定 |
|---|---|
| API 前缀 | `/api/v1` |
| 前端环境变量 | `NEXT_PUBLIC_API_BASE_URL`（可为空；为空则请求同源 `/api/v1/...`） |
| Mock 模式 | `NEXT_PUBLIC_API_MODE=mock` 时由 MSW 拦截，不访问真实后端 |

### 1.2 认证与跨域

- 前端使用 `fetch(..., { credentials: "include" })`，期望后端通过 **Cookie 会话**（或等价的跨站凭证）维持登录态。
- 当前前端类型中的用户对象**不包含** `access_token`；若后端改用 JWT，需另行协商前端改动。
- 跨域部署时需配置 CORS：`Access-Control-Allow-Credentials: true`，并指定具体 `Origin`（不可为 `*`）。

### 1.3 统一响应信封

成功与业务失败均返回 JSON：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "uuid"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | number | `0` 表示成功；非 0 表示失败（前端当前也按 HTTP 非 2xx 判失败） |
| `message` | string | 可读说明，失败时会展示给用户 |
| `data` | T \| null | 成功时为业务数据；失败时可为 `null` |
| `request_id` | string | 请求追踪 ID |

失败时建议附加：

```json
{
  "code": 404,
  "message": "会话不存在",
  "data": null,
  "request_id": "uuid",
  "error": { "type": "not_found" }
}
```

前端识别的 `error.type` 示例：`not_found`、`validation_error`、`request_failed`。

前端判定成功条件：`response.ok && payload.code === 0`，然后只消费 `payload.data`。

### 1.4 内容类型

- JSON 接口：`Content-Type: application/json`
- 报告上传：`multipart/form-data`（不要手动设 JSON Content-Type）

### 1.5 时间与 ID

- 时间字段使用 ISO 8601 字符串（建议带时区，如 `2026-07-15T08:30:00+08:00`）
- 资源 ID 为字符串（UUID 或其它稳定标识均可）

---

## 2. 类型定义（前端契约）

### 2.1 User

```ts
{
  user_id: string;
  email: string;
  nickname: string;
}
```

### 2.2 Profile

```ts
{
  nickname: string;
  birth_date: string;                         // YYYY-MM-DD
  sex_at_birth: "female" | "male" | "other" | "unknown";
  height_cm?: number;
  weight_kg?: number;
  pregnancy_status: "not_applicable" | "pregnant" | "postpartum" | "unknown";
  chronic_conditions: string[];
  allergies: string[];
  current_medications: string[];
}
```

### 2.3 ProfileResponse

```ts
{
  profile: Profile | null;
  tags: string[];   // 后端按规则生成，如 age_adult、sex_female、allergy_*
}
```

### 2.4 Citation

```ts
{
  chunk_id: string;
  article_title: string;
  section_title: string;
  source_url: string;
}
```

### 2.5 Chat

```ts
type RiskLevel = "low" | "medium" | "high" | "unknown";

type Conversation = {
  conversation_id: string;
  title: string;
  updated_at: string;
  preview: string;
};

type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  risk_level?: RiskLevel;           // 助手消息常用
  suggestions?: string[];
  profile_tags_used?: string[];
  citations?: Citation[];
  evidence_available?: boolean;     // false 时前端提示“无足够依据”
};

type ConversationDetail = Conversation & {
  messages: ChatMessage[];
};
```

### 2.6 Report

```ts
type ReportStatus =
  | "uploaded"
  | "ocr_processing"
  | "needs_confirmation"
  | "interpreting"
  | "completed"
  | "failed";

type ReportItem = {
  item_id: string;
  name: string;
  value: number | null;
  unit: string;
  reference_low: number | null;
  reference_high: number | null;
  status: "low" | "normal" | "high" | "unknown";
  explanation?: string;
  suggestions?: string[];
  citations?: Citation[];
};

type Report = {
  report_id: string;
  file_name: string;
  report_type: "physical_exam" | "blood_test" | "other";
  status: ReportStatus;
  created_at: string;
  summary?: string;
  profile_tags_used: string[];
  items: ReportItem[];
  error_message?: string;
};
```

### 2.7 分页

列表接口统一：

```ts
{
  items: T[];
  next_cursor: string | null;   // 暂无分页 UI，可恒为 null
}
```

---

## 3. 接口清单

### 3.1 认证

#### `POST /api/v1/auth/register`

**请求**

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**响应 `data`**：`User`  
**期望 HTTP**：`201`（Mock 使用 201；只要 `code === 0` 且 `data` 符合即可）  
**行为**：创建会话 Cookie；注册成功后前端跳转工作台。

#### `POST /api/v1/auth/login`

**请求**

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**响应 `data`**：`User`  
**行为**：建立会话 Cookie。

#### `POST /api/v1/auth/logout`

**请求体**：无  
**响应 `data`**：`null`  
**行为**：清除会话；前端跳转登录页。

#### `GET /api/v1/auth/me`

**响应 `data`**：`User`  
**用途**：受保护布局鉴权；失败（未登录）时前端跳转 `/login`。

---

### 3.2 健康画像

#### `GET /api/v1/profile`

**响应 `data`**：`ProfileResponse`  
- 未填写时：`profile` 可为 `null`，`tags` 为空数组。

#### `PUT /api/v1/profile`

**请求体**：完整 `Profile` 对象（见 2.2）  
**响应 `data`**：`ProfileResponse`  
**后端需**：保存画像 → 按固定规则生成标签 → 返回画像与标签。

---

### 3.3 健康咨询（会话式，非单次 `/chat/query`）

前端主页与咨询页按**会话**工作，需要以下四个接口。

#### `GET /api/v1/chat/conversations`

**响应 `data`**

```json
{
  "items": [ /* Conversation，不含 messages */ ],
  "next_cursor": null
}
```

#### `POST /api/v1/chat/conversations`

**请求体**：无（可忽略空对象）  
**响应 `data`**：`ConversationDetail`（新建时可 `messages: []`）  
**期望 HTTP**：`201`（可选）

#### `GET /api/v1/chat/conversations/{id}`

**响应 `data`**：`ConversationDetail`（含完整 `messages`）  
**失败**：`404`，`error.type = "not_found"`

#### `POST /api/v1/chat/conversations/{id}/messages`

**请求**

```json
{
  "question": "最近经常头晕，可能是什么原因？",
  "use_profile": true
}
```

**响应 `data`**：助手侧 `ChatMessage`（前端当前只把该对象当作本轮助手回复展示；用户消息由前端本地或再次拉取会话体现均可，Mock 会同时写入双方消息）

**后端处理建议**

1. 若 `use_profile === true`，读取当前用户画像与标签参与检索/生成  
2. 检索知识库（如 PostgreSQL + Milvus）  
3. 调用模型生成科普回复（非诊断）  
4. 红旗/高风险规则命中时设置 `risk_level: "high"`  
5. 返回引用 `citations`；无依据时可设 `evidence_available: false`  
6. 更新会话 `title` / `preview` / `updated_at`

---

### 3.4 报告解读（分步：上传 OCR → 确认 → 解读）

前端流程对应状态：

1. 上传 `analyze` → 期望 `status: "needs_confirmation"`（已得到 OCR 条目）  
2. 用户核对后 `PATCH .../items`  
3. 再 `POST .../interpret` → `status: "completed"`，填充 `summary` 与条目级 `explanation` / `citations`

#### `GET /api/v1/reports`

**响应 `data`**：`{ items: Report[]; next_cursor: null }`

#### `POST /api/v1/reports/analyze`

**Content-Type**：`multipart/form-data`

| 字段 | 说明 |
|---|---|
| `file` | 文件（前端提示 JPG / JPEG / PNG / PDF，单文件 ≤ 15MB） |
| `report_type` | `physical_exam` \| `blood_test` \| `other` |

**响应 `data`**：`Report`  
**期望 HTTP**：`202`（Mock 使用；表示已受理并返回 OCR 待确认结果）  
**此时建议**：`status = "needs_confirmation"`，`items` 已有 OCR 字段；`explanation` / `summary` 可暂缺。

**失败示例**：无文件 → `422`，`error.type = "validation_error"`

#### `GET /api/v1/reports/{id}`

**响应 `data`**：`Report`  
**失败**：`404`，`not_found`

#### `PATCH /api/v1/reports/{id}/items`

**请求**

```json
{
  "items": [ /* ReportItem[]，用户校正后的整表 */ ]
}
```

**响应 `data`**：更新后的 `Report`  
**行为**：保存校正结果；状态可回到 / 保持 `needs_confirmation`。

#### `POST /api/v1/reports/{id}/interpret`

**请求体**：无  
**响应 `data`**：`Report`（`status: "completed"`，含 `summary`，各 `items` 带科普解释与引用）  
**说明**：解读仅做健康科普，不输出诊断/处方结论。

#### `DELETE /api/v1/reports/{id}`

**响应 `data`**：`null`

---

## 4. 接口一览表

| 方法 | 路径 | 前端用途 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册 |
| POST | `/api/v1/auth/login` | 登录 |
| POST | `/api/v1/auth/logout` | 退出 |
| GET | `/api/v1/auth/me` | 会话校验 / 顶栏用户 |
| GET | `/api/v1/profile` | 读取画像 |
| PUT | `/api/v1/profile` | 保存画像并拿标签 |
| GET | `/api/v1/chat/conversations` | 会话列表 |
| POST | `/api/v1/chat/conversations` | 新建会话 |
| GET | `/api/v1/chat/conversations/{id}` | 会话详情与消息 |
| POST | `/api/v1/chat/conversations/{id}/messages` | 发送问题并拿助手回复 |
| GET | `/api/v1/reports` | 报告列表 |
| POST | `/api/v1/reports/analyze` | 上传并 OCR |
| GET | `/api/v1/reports/{id}` | 报告详情 |
| PATCH | `/api/v1/reports/{id}/items` | 确认/校正 OCR |
| POST | `/api/v1/reports/{id}/interpret` | 生成科普解读 |
| DELETE | `/api/v1/reports/{id}` | 删除报告 |

---

## 5. 与 PLAN1 示例的主要差异

| 主题 | PLAN1 示例 | 当前前端实际要求 |
|---|---|---|
| 登录返回 | 含 `access_token` / `token_type` | `User` + Cookie 会话 |
| 医学问答 | 单次 `POST /api/v1/chat/query` | 会话 CRUD + `.../messages` |
| 报告分析 | 一次返回完整解读 | 先 OCR 确认，再 `interpret` |

后端若需兼容旧示例，至少仍须满足本文档路径与响应形状，否则前端页面无法联调。

---

## 6. 源码索引

| 文件 | 内容 |
|---|---|
| `frontend/src/lib/api/types.ts` | TypeScript 契约与 `ApiError` |
| `frontend/src/lib/api/client.ts` | 统一请求与全部调用函数 |
| `frontend/src/lib/api/handlers.ts` | MSW Mock（联调前行为参考） |
| `frontend/.env.local` | `NEXT_PUBLIC_API_MODE` / `NEXT_PUBLIC_API_BASE_URL` |

文档版本与前端 Mock 日期对齐：2026-07-15。
