# MSD 文本清洗需要保留的标签

MSD 大众版页面的特点是“医学主题页面”为基本单位：每个 URI 通常对应一个疾病、症状、检查、急救或医学知识主题，内容按章节组织，并带有作者、审核人员、修订时间和版本信息。因此爬虫和清洗阶段建议按下面几层保存。

## 1. 页面级标签

每个 URI 一条页面记录：

| 字段 | 说明 |
| --- | --- |
| `page_id` | 后端生成的稳定 ID，可由 URI hash 得到 |
| `source_url` | MSD 原文 URI |
| `canonical_url` | 规范化后的 URI，去掉无意义 query |
| `topic_type` | `disease`、`symptom`、`test`、`first_aid`、`drug`、`special_population`、`medical_knowledge`、`quiz` |
| `title` | 页面标题 |
| `subtitle` | 副标题或页面说明，没有则为空 |
| `category_path` | 栏目树，如 `家庭版/急救/创伤` |
| `summary` | 页面导语或摘要 |
| `authors` | 作者列表 |
| `reviewers` | 审核/医学审阅人员 |
| `revised_at` | 修订时间 |
| `version_label` | 页面版本或更新标识 |
| `language` | `zh-CN` |
| `license_scope` | 授权范围：展示、缓存、离线、媒体等 |
| `content_hash` | 页面正文 hash，用于增量更新 |
| `crawled_at` | 抓取时间 |
| `published_status` | `draft`、`approved`、`deprecated`、`offline` |

## 2. 章节级标签

每个页面按标题层级拆成章节：

| 字段 | 说明 |
| --- | --- |
| `section_id` | 章节 ID |
| `page_id` | 所属页面 |
| `heading_path` | 多级标题路径，如 `概述 > 症状` |
| `section_title` | 当前章节标题 |
| `section_order` | 页面内顺序 |
| `section_type` | `overview`、`symptoms`、`causes`、`diagnosis`、`tests`、`treatment`、`first_aid_steps`、`when_to_seek_care`、`prevention`、`normal_values`、`quiz` |
| `plain_text` | 去除导航和广告后的正文 |
| `html_snapshot` | 授权允许时保存原始预览 HTML |
| `citation_anchor` | 前端跳转到原文或章节的锚点 |

## 3. 知识块级标签

Milvus 和 RAG 使用知识块，不直接用整页：

| 字段 | 说明 |
| --- | --- |
| `chunk_id` | 知识块 ID |
| `page_id` / `section_id` | 来源定位 |
| `chunk_index` | 章节内序号 |
| `chunk_text` | 适合 embedding 的文本，建议 300-800 中文字 |
| `keywords` | 疾病、症状、检查、药物、人群等关键词 |
| `entity_tags` | 结构化实体标签，如 `symptom_dizziness`、`lab_hemoglobin` |
| `risk_flags` | 红旗风险，如 `chest_pain`、`dyspnea`、`loss_of_consciousness` |
| `population_tags` | `adult`、`child`、`newborn`、`pregnancy`、`older_adult` |
| `source_url` | 原文链接 |
| `article_title` | 页面标题 |
| `section_title` | 章节标题 |
| `version_label` | 所属页面版本 |
| `content_hash` | 块级 hash |
| `embedding_model` | 向量模型名称 |
| `embedding_vector_id` | Milvus 主键 |

## 4. 多媒体标签

MSD 页面包含图片、视频、动画、3D 和测验时单独保存：

| 字段 | 说明 |
| --- | --- |
| `media_id` | 媒体 ID |
| `page_id` / `section_id` | 所属内容 |
| `media_type` | `image`、`video`、`animation`、`3d`、`quiz` |
| `title` | 媒体标题 |
| `caption` | 图注或说明 |
| `alt_text` | 无障碍描述 |
| `source_url` | MSD 原始媒体地址 |
| `storage_url` | 授权缓存后的对象存储地址 |
| `license_scope` | 媒体授权范围 |

## 5. 化验指标标签

报告解读需要把参考值页面清洗成指标库：

| 字段 | 说明 |
| --- | --- |
| `indicator_id` | 指标 ID |
| `name` | 中文名称，如 `血红蛋白` |
| `aliases` | 英文名、缩写，如 `hemoglobin`、`Hb` |
| `unit` | 标准单位 |
| `reference_low` / `reference_high` | 参考区间 |
| `sex_at_birth` | 适用性别 |
| `age_min` / `age_max` | 适用年龄范围 |
| `population_note` | 孕妇、新生儿、老人等特殊说明 |
| `source_chunk_id` | 来源知识块 |

第一阶段最低必需字段是：`source_url`、`topic_type`、`title`、`category_path`、`section_title`、`plain_text/chunk_text`、`authors`、`reviewers`、`revised_at`、`version_label`、`content_hash`、`citation_anchor`。有了这些，后端才能做到去重、版本更新、引用追溯和“无依据拒答”。
