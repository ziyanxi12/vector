# 统一向量库管理服务 — 方案设计

## 一、整体架构

```
┌──────────────────────────────────────────────────────────┐
│                   Vector Management Service               │
│                                                          │
│   POST /ingest   PUT /update   POST /search   DELETE /item│
│        │              │              │              │     │
│  ┌─────▼──────────────▼──────────────▼──────────────▼──┐ │
│  │             DataType Handler Registry                 │ │
│  │   ComponentHandler │ IconHandler │ [扩展 Handler ...]  │ │
│  └──────────────┬──────────────────────────┬────────────┘ │
│                 │                          │              │
│   ┌─────────────▼──────────┐  ┌───────────▼────────────┐ │
│   │   TextToVec Client     │  │    ES Client (8.15)    │ │
│   │   mock_ip:mock_port    │  │    Free tier           │ │
│   └────────────────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 二、技术选型

| 模块 | 选型 |
|------|------|
| 框架 | Python + FastAPI |
| ES 客户端 | elasticsearch-py 8.x |
| HTTP 客户端 | httpx（支持异步并发） |
| 数据校验 | Pydantic v2 |
| Mock | pytest + respx（mock HTTP）+ pytest-elasticsearch 或内存 dict |
| 配置管理 | pydantic-settings + .env |

---

## 三、ES 索引设计

### 3.1 索引隔离原则

**每种 type 对应一个独立的 ES 索引**，命名规则：`vec_{type}`。

```
vec_component   ← 组件数据
vec_icon        ← 图标数据
vec_{type}      ← 未来扩展的数据类型
```

隔离的好处：
- 各 type 的 `metadata` 字段完全独立，mapping 不会相互污染
- 可以按 type 单独调整分片、副本等索引参数
- 搜索时无需额外加 `type` 过滤条件，天然隔离

### 3.2 统一 Mapping 模板

所有索引共享同一套 mapping 模板（通过 ES Index Template 管理，匹配 `vec_*`），**服务启动时自动按模板创建各索引**。

```json
// Index Template: vec_template（匹配 vec_*）
{
  "mappings": {
    "properties": {
      "data_id":  { "type": "keyword" },
      "text":     { "type": "text" },
      "vector":   { "type": "dense_vector", "dims": 128,
                    "index": true, "similarity": "cosine" },
      "metadata": { "type": "object", "dynamic": true }
    }
  },
  "settings": {
    "number_of_shards": 1,
    "number_of_replicas": 0
  }
}
```

### 3.3 metadata 字段如何做到各索引独立

模板只定义了所有 type 共用的骨架字段（data_id / text / vector 等）。  
`metadata` 设置了 `dynamic: true`，其子字段由 ES **在第一次写入时动态生成**，而不是在模板里预定义。

由于每个 type 有自己的独立索引，动态生成的子字段只存在于当前索引的 mapping 中：

```
vec_component 写入 metadata.category   → 只出现在 vec_component 的 mapping 里
vec_icon      写入 metadata.tags       → 只出现在 vec_icon 的 mapping 里
两个索引的 metadata 字段互相不感知
```

如果改成单索引，所有 type 的 metadata 子字段会堆在同一个 mapping 里，组件的 `category` 和图标的 `tags` 混在一起，随着 type 增多 mapping 会越来越臃肿。

---

## 四、API 接口设计

`type` 统一作为 body 参数，URL 保持扁平。

### 4.1 入库（批量）

```
POST /api/v1/ingest
{
  "type": "component",
  "items": [
    {
      "data_id": "comp_001",
      "text": "蓝色主按钮",
      "metadata": { "category": "button", "framework": "react" }
    }
  ]
}

Response:
{
  "succeeded": ["comp_001"],
  "failed": []
}
```

### 4.2 更新

```
PUT /api/v1/update
{
  "type": "component",
  "data_id": "comp_001",
  "text": "更新后的文本",
  "metadata": { "category": "button" }
}
```

### 4.3 查询（精确）

```
GET /api/v1/item?type=component&data_id=comp_001
```

### 4.4 搜索

```
POST /api/v1/search
{
  "type": "component",
  "query": "蓝色按钮",
  "mode": "vector",       // vector | text | hybrid
  "top_k": 10,
  "filters": { "metadata.category": "button" },
  "hybrid_weight": 0.7    // hybrid 模式下向量分数权重，默认 0.7
}

Response:
{
  "results": [
    {
      "data_id": "comp_001",
      "text": "蓝色主按钮",
      "score": 0.92,
      "metadata": { ... }
    }
  ]
}
```

### 4.5 删除

```
DELETE /api/v1/item
{
  "type": "component",
  "data_id": "comp_001"
}
```

---

## 五、搜索模式详解

免费版 ES 不支持 RRF，hybrid 在应用层做分数融合。

### vector 模式

```
query_text → TextToVec API → query_vector
→ ES knn query（top_k）
→ 返回结果（含 cosine 相似度分数）
```

### text 模式

```
query_text
→ ES match query（BM25 全文检索）
→ 返回结果（含 BM25 分数）
```

### hybrid 模式（应用层融合）

```
并发执行：
  ├─ ES knn query   → vector_results（score 已归一化 0~1）
  └─ ES match query → text_results（score 需 min-max 归一化）

按 data_id 合并：
  final_score = hybrid_weight * vector_score
              + (1 - hybrid_weight) * text_score

按 final_score 排序，取 top_k 返回
```

分数归一化方式：
- vector：cosine similarity 本身在 0~1，直接使用
- text：`(score - min) / (max - min)` 归一化到 0~1

---

## 六、核心数据流

### 入库流程

```
收到 ingest 请求
  → Pydantic 校验（text 为空直接报错，不允许插入）
  → 按 type 路由到对应 Handler（校验 metadata 字段）
  → 分批（每批 ≤ 50 条）并发调用 TextToVec API
  → 拼装 ES 文档（text + vector + metadata）
  → ES bulk 写入（upsert，data_id 已存在则覆盖）
  → 返回 succeeded / failed 明细
```

`data_id` 由调用方传入，服务不生成，外部保证唯一性。

### 更新流程

```
收到 update 请求
  → 检查 data_id 是否存在（ES get），不存在则报错
  → 请求中包含 text 字段 → 重新调 TextToVec 生成新向量
  → 请求中只有 metadata → 跳过 TextToVec，保留原向量
  → ES update（partial update）
```

---

## 七、扩展新数据类型

新增 type 只需新建一个 Handler 类并注册：

```python
@handler_registry.register("material")
class MaterialHandler(BaseHandler):
    index_name = "vec_material"

    def validate_metadata(self, metadata: dict):
        # 自定义 metadata 校验逻辑
        ...
```

路由层、搜索层、入库层均无需修改。

---

## 八、Mock 设计

### TextToVec Mock（respx）

```python
# 返回固定随机 128 维向量，text_id 透传
respx.post("http://mock_ip:mock_port/textToVec").mock(
    return_value=httpx.Response(200, json={
        "vectors": [{"vector": [0.1]*128, "text_id": "sss"}]
    })
)
```

### ES Mock

- 单元测试：用内存 dict 实现 `EsRepository` 接口
- 集成测试：用 `testcontainers-python` 启动真实 ES 8.15 容器

---

## 九、项目结构

```
vector_service/
├── main.py                    # FastAPI app 入口
├── config.py                  # pydantic-settings 配置
├── api/
│   └── router.py              # 所有路由（ingest/update/search/delete）
├── handler/
│   ├── base.py                # BaseHandler 接口
│   ├── registry.py            # Handler 注册与路由
│   ├── component.py           # ComponentHandler
│   └── icon.py                # IconHandler
├── service/
│   ├── ingest.py              # 入库编排
│   ├── search.py              # 搜索编排（含 hybrid 融合逻辑）
│   └── update.py              # 更新编排
├── client/
│   ├── texttovec.py           # TextToVec HTTP client
│   └── es_repository.py       # ES 操作封装
├── model/
│   ├── request.py             # 所有请求 Pydantic 模型
│   └── response.py            # 所有响应 Pydantic 模型
└── tests/
    ├── mock_texttovec.py
    └── test_ingest.py / test_search.py
```

---

## 十、关键非功能设计

| 关注点 | 方案 |
|--------|------|
| 批量入库性能 | httpx 异步并发调 TextToVec，ES bulk 写入 |
| 向量维度扩展 | Handler 级别配置 `dimension`，维度变更需重建索引 |
| 部分失败处理 | bulk 入库返回 `failed` 列表，不整批回滚 |
| 索引不存在 | 服务启动时自动按模板创建各 type 索引 |
| text 为空 | 校验阶段直接报错，不允许写入 |
