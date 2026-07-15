# 第一阶段前后端接口契约

统一响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误响应：

```json
{
  "code": 40001,
  "message": "错误说明",
  "data": null
}
```

除注册、登录、健康检查外，其余接口需要请求头：

```text
Authorization: Bearer <access_token>
```

## 用户注册

`POST /api/v1/auth/register`

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

## 用户登录

`POST /api/v1/auth/login`

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

## 填写或修改用户画像

`PUT /api/v1/profile`

```json
{
  "nickname": "用户A",
  "birth_date": "2003-05-20",
  "sex_at_birth": "female",
  "height_cm": 165,
  "weight_kg": 52,
  "pregnancy_status": "not_applicable",
  "chronic_conditions": ["过敏性鼻炎"],
  "allergies": ["青霉素"],
  "current_medications": ["氯雷他定"]
}
```

返回 `profile` 和后端生成的 `tags`，例如：

```json
{
  "profile": {},
  "tags": ["age_adult", "sex_female", "allergy_penicillin"]
}
```

## 获取用户画像

`GET /api/v1/profile`

## 医学问题提交

`POST /api/v1/chat/query`

```json
{
  "question": "最近经常头晕，可能是什么原因？",
  "use_profile": true
}
```

返回字段：

- `question`: 原始问题。
- `answer`: AI 科普解读。
- `risk_level`: `low`、`medium`、`high` 或 `unknown`。
- `suggestions`: 非诊疗行动建议。
- `profile_tags_used`: 本次使用的用户标签。
- `citations`: 证据来源知识块，前端应展示来源标题、章节和原文链接。

## 上传并分析体检报告

`POST /api/v1/reports/analyze`

`multipart/form-data` 字段：

- `file`: JPG、JPEG、PNG 或 PDF。
- `report_type`: `physical_exam`、`blood_test` 或 `other`。

返回 `report_id`、`summary`、结构化指标 `items` 和引用 `citations`。

## 获取报告结果

`GET /api/v1/reports/{report_id}`

## 知识检索

`GET /api/v1/knowledge/search?q=贫血&limit=5`

第一阶段给问答和报告模块复用，前端也可以用于搜索页。
