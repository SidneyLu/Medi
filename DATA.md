# 数码竞品监测 RAG 数据准备方案

## Summary
一期数据准备目标是建立一套可持续扩展的竞品数据底座，覆盖 `SKU 主档`、`结构化快照`、`非结构化 RAG 语料` 和 `评测/验收样本` 四类数据。准备顺序固定为：先建主档，再定来源，再抓商品真值，最后补评测和社区内容。这样可以优先支撑“参数/价格对比 + 可追溯问答”，避免一开始陷入全网抓取和脏数据治理。

最终要交付的不是一堆网页，而是 4 份可用资产：
- PostgreSQL 可入库的结构化数据
- ChromaDB 可入库的文本 chunk 数据
- 首批站点与 SKU 的种子清单
- 一套用于抽取和问答验收的小型标注集

## Key Changes
### 1. 数据域划分
- `SKU 主档数据`：定义系统里的“竞品对象”是谁，解决同款不同写法、同系列多版本、平台命名不一致的问题。
- `结构化监测数据`：记录价格、参数、促销、卖点等可以做 SQL 对比的真值字段。
- `非结构化证据数据`：记录官网文案、评测正文、社区帖子、评论摘录等用于 RAG 的文本证据。
- `评估样本数据`：记录人工校验过的抽取样本和问答样本，用于后续验收与回归。

### 2. 首批数据准备顺序
- 先准备 `source_registry`，列出首批高价值来源站点。
- 再准备 `product_sku_seed`，列出首批需要监测的产品型号。
- 再接入 `official + ecommerce` 两类来源，优先沉淀结构化真值。
- 之后补 `review + community`，增强 RAG 问答质量。
- 默认先覆盖 1 到 2 个数码品类，不要一开始做全品类。

### 3. 首批推荐范围
- 先选一个主品类作为一期，例如：
  - 手机
  - 平板
  - 笔记本
  - 耳机
- 每个品类首批只做 20 到 50 个 SKU。
- 每个 SKU 至少覆盖：
  - 1 个官网来源
  - 2 个电商来源
  - 1 个评测来源
  - 1 个社区来源
- 每个来源都要能映射回具体 `sku_id`，不接受“只存文本但找不到对应产品”的孤立内容。

### 4. PostgreSQL 结构化数据准备
- 必备种子表：
  - `brand`
  - `product_series`
  - `product_sku`
  - `product_alias`
  - `source_site`
- 必备业务表：
  - `source_document`
  - `crawl_job`
  - `price_snapshot`
  - `spec_snapshot`
  - `promotion_snapshot`
  - `selling_point_snapshot`
  - `timeline_event`
- `product_sku` 至少准备字段：
  - `sku_id`
  - `brand_name`
  - `series_name`
  - `model_name`
  - `normalized_model_name`
  - `category`
  - `launch_date`
  - `status`
- `product_alias` 至少准备字段：
  - `alias_text`
  - `sku_id`
  - `alias_type`
  - `source`
- `source_document` 至少准备字段：
  - `document_id`
  - `source_site_id`
  - `sku_id`
  - `source_type`
  - `url`
  - `title`
  - `published_at`
  - `crawled_at`
  - `raw_storage_path`
  - `clean_text_path`

### 5. 结构化字段字典
- 一期必须先维护一份 `spec_field_dictionary`，统一不同站点字段名。
- 手机类示例字段建议固定为：
  - `chipset`
  - `ram`
  - `storage`
  - `screen_size`
  - `resolution`
  - `refresh_rate`
  - `battery_capacity`
  - `charging_power`
  - `rear_camera_main`
  - `front_camera`
  - `weight`
  - `os`
- 销售字段建议固定为：
  - `current_price`
  - `original_price`
  - `promotion_text`
  - `platform`
  - `seller_type`
  - `stock_status`
- 所有抽取字段必须能映射到这份字典，不允许每个站点各用一套字段名。

### 6. 非结构化 RAG 语料准备
- 每篇原始内容都要保留：
  - 原始 HTML 或原文
  - 清洗后的正文
  - 标题
  - URL
  - 来源类型
  - 发布时间
  - 抓取时间
  - 关联 SKU
- chunk 入库前先做清洗：
  - 去导航、广告、推荐阅读、版权尾巴
  - 去重复段落
  - 保留小标题结构
- chunk metadata 固定包含：
  - `chunk_id`
  - `source_document_id`
  - `sku_id`
  - `site_name`
  - `source_type`
  - `title`
  - `published_at`
  - `crawled_at`
  - `url`
- 对评测文章按“标题段落”切分，对社区内容按“帖子正文/高质量评论”切分，不做纯长度切块。

### 7. 历史追踪数据准备
- 同一商品页的每次抓取都生成新的 `source_document` 记录。
- 每次抽取后的价格、参数、促销、卖点都写入对应 snapshot 表。
- 当快照值变化时，生成 `timeline_event`：
  - `field_name`
  - `old_value`
  - `new_value`
  - `observed_at`
  - `source_document_id`
- 默认保留全量历史，不覆盖旧值。

### 8. 首批 CSV / Excel 模板
- `source_registry.csv`
  - `site_name`
  - `source_type`
  - `base_url`
  - `priority`
  - `crawl_frequency`
  - `notes`
- `product_sku_seed.csv`
  - `brand_name`
  - `series_name`
  - `model_name`
  - `normalized_model_name`
  - `category`
  - `launch_date`
  - `official_url`
  - `competitor_group`
- `product_alias.csv`
  - `normalized_model_name`
  - `alias_text`
  - `alias_type`
  - `source`
- `manual_source_urls.csv`
  - `sku_model_name`
  - `source_type`
  - `site_name`
  - `url`
  - `priority`
- `extraction_goldens.csv`
  - `url`
  - `sku_model_name`
  - `field_name`
  - `expected_value`
  - `annotator`
- `qa_eval_set.csv`
  - `question`
  - `target_sku`
  - `comparison_skus`
  - `expected_key_points`
  - `expected_sources`

### 9. 数据验收标准
- 每个 SKU 至少能关联 1 条官网文档和 2 条电商文档。
- 首批 SKU 的主档别名映射准确，不出现重复建档。
- 结构化字段抽取准确率对核心字段要可人工验收：
  - 价格
  - 芯片
  - 存储
  - 屏幕
  - 电池
  - 快充
- 任意一个回答中引用的结论都能追溯到 `source_document` 和抓取时间。
- 同一 SKU 的多次抓取能正确形成历史快照。
- RAG 检索返回的 chunk 必须带完整 metadata，不能出现无来源文本。

## Test Plan
- 用 20 个首批 SKU 做端到端试运行，确认主档、快照、chunk、timeline 都能生成。
- 从官网、电商、评测、社区各抽 10 个样本页面，人工核对抽取字段。
- 使用 30 条真实业务问题验证问答输出是否能正确引用结构化与非结构化证据。
- 对 5 个 SKU 做二次抓取，确认价格或参数变化能写入历史快照和时间线。
- 随机抽查 20 条 chunk，确认清洗质量、SKU 归属和 metadata 完整性。

## Assumptions
- 一期先聚焦 1 到 2 个数码品类，不做全品类铺开。
- 一期先覆盖 20 到 50 个 SKU，追求数据质量而不是数量。
- PostgreSQL 是结构化真值源，ChromaDB 只负责非结构化检索。
- 首批种子数据允许人工整理为 CSV/Excel，再导入系统。
- 默认需要一份小型人工标注集，用于抽取和问答验收，否则后续很难判断系统质量变化。
