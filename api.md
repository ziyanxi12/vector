# Vector Management Service — API 文档

Base URL: `http://{host}:{port}`

---

## 通用说明

- 所有请求 Content-Type: `application/json`
- `type` 当前支持：`component`、`icon`
- 错误响应格式：`{ "detail": "错误描述" }`

---

## 1. 批量入库

**POST** `/api/v1/ingest`

将数据向量化后写入库中。`data_id` 已存在则覆盖。

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 数据类型 |
| items | array | 是 | 入库数据列表，至少 1 条 |
| items[].data_id | string | 是 | 业务唯一 ID，由调用方保证唯一 |
| items[].text | string | 是 | 用于向量化的文本，不能为空 |
| items[].metadata | object | 是 | 业务字段，各 type 定义见下方 |

```json
{
  "type": "component",
  "items": [
    {
      "data_id": "comp_001",
      "text": "蓝色主按钮",
      "metadata": {
        "name": "主按钮",
        "canvas_name": "Button",
        "component_name": "PrimaryButton",
        "domain": "basic"
      }
    }
  ]
}
```

### 响应 `200`

| 字段 | 类型 | 说明 |
|------|------|------|
| succeeded | array[string] | 成功的 data_id 列表 |
| failed | array[object] | 失败的条目，含 data_id 和 error |

```json
{
  "succeeded": ["comp_001"],
  "failed": []
}
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 422 | 请求参数校验失败（text 为空、items 为空等） |

---

## 2. 更新

**PUT** `/api/v1/update`

更新已有数据。`text` 和 `metadata` 至少传一个。

- 传了 `text` → 重新生成向量
- 只传 `metadata` → 保留原向量，只更新业务字段

### 请求

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 数据类型 |
| data_id | string | 是 | 要更新的 ID |
| text | string | 否 | 新文本，传入则重新向量化 |
| metadata | object | 否 | 新 metadata，整体替换 |

```json
{
  "type": "component",
  "data_id": "comp_001",
  "text": "红色危险按钮",
  "metadata": {
    "name": "危险按钮",
    "canvas_name": "Button",
    "component_name": "DangerButton",
    "domain": "basic"
  }
}
```

### 响应 `200`

```json
{ "status": "ok" }
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 404 | data_id 不存在 |
| 422 | text 和 metadata 均未传 |

---

## 3. 搜索

**POST** `/api/v1/search`

支持三种搜索模式。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| type | string | 是 | — | 数据类型 |
| query | string | 是 | — | 搜索文本 |
| mode | string | 否 | `vector` | `vector` / `text` / `hybrid` |
| top_k | integer | 否 | `10` | 返回条数 |
| filters | object | 否 | `{}` | 精确过滤条件，支持 metadata 子字段 |
| hybrid_weight | float | 否 | `0.7` | hybrid 模式下向量分数权重（0~1） |

```json
{
  "type": "component",
  "query": "蓝色按钮",
  "mode": "hybrid",
  "top_k": 5,
  "filters": { "metadata.domain": "basic" },
  "hybrid_weight": 0.7
}
```

#### 搜索模式说明

| mode | 原理 | 适用场景 |
|------|------|----------|
| `vector` | 语义向量相似度（knn） | 模糊语义匹配 |
| `text` | 全文检索（BM25） | 关键词精确匹配 |
| `hybrid` | 向量 + 文本分数加权融合 | 兼顾语义和关键词 |

### 响应 `200`

| 字段 | 类型 | 说明 |
|------|------|------|
| results | array | 按相似度降序排列 |
| results[].data_id | string | 业务 ID |
| results[].text | string | 原始文本 |
| results[].score | float | 相似度分数 |
| results[].metadata | object | 业务字段 |

```json
{
  "results": [
    {
      "data_id": "comp_001",
      "text": "蓝色主按钮",
      "score": 0.92,
      "metadata": {
        "name": "主按钮",
        "canvas_name": "Button",
        "component_name": "PrimaryButton",
        "domain": "basic"
      }
    }
  ]
}
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 422 | 请求参数校验失败 |

---

## 4. 批量搜索

**POST** `/api/v1/search/batch`

供后端 API 调用，并发执行多个查询，返回二维结果。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| type | string | 是 | — | 数据类型 |
| queries | array[string] | 是 | — | 查询文本列表，至少 1 条 |
| mode | string | 否 | `vector` | `vector` / `text` / `hybrid` |
| top_k | integer | 否 | `10` | 每个 query 返回条数 |
| filters | object | 否 | `{}` | 精确过滤条件 |
| hybrid_weight | float | 否 | `0.7` | hybrid 模式向量分数权重 |

```json
{
  "type": "component",
  "queries": ["蓝色按钮", "输入框", "下拉菜单"],
  "mode": "vector",
  "top_k": 5
}
```

### 响应 `200`

`results` 为二维数组，顺序与 `queries` 一一对应。

```json
{
  "results": [
    [
      { "data_id": "comp_001", "text": "蓝色主按钮", "score": 0.92, "metadata": {} }
    ],
    [
      { "data_id": "comp_003", "text": "文本输入框", "score": 0.88, "metadata": {} }
    ],
    []
  ]
}
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 422 | queries 为空 |

---

## 5. 精确查询

**GET** `/api/v1/item`

按 data_id 查询单条数据。

### 请求参数（Query String）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 数据类型 |
| data_id | string | 是 | 业务 ID |

```
GET /api/v1/item?type=component&data_id=comp_001
```

### 响应 `200`

```json
{
  "data_id": "comp_001",
  "text": "蓝色主按钮",
  "metadata": {
    "name": "主按钮",
    "canvas_name": "Button",
    "component_name": "PrimaryButton",
    "domain": "basic"
  }
}
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 404 | data_id 不存在 |

---

## 6. 删除

**DELETE** `/api/v1/item`

### 请求

```json
{
  "type": "component",
  "data_id": "comp_001"
}
```

### 响应 `200`

```json
{ "status": "ok" }
```

### 错误

| 状态码 | 原因 |
|--------|------|
| 400 | 未知 type |
| 404 | data_id 不存在 |

---

## Metadata 字段定义

### component（组件集）

| 字段 | 类型 | 必填 |
|------|------|------|
| name | string | 是 |
| canvas_name | string | 是 |
| component_name | string | 是 |
| domain | string | 是 |

### icon（图标）

| 字段 | 类型 | 必填 |
|------|------|------|
| name | string | 是 |
| description | string | 是 |
| english_name | string | 是 |
| category | string | 是 |

---

## 配置说明

复制 `vector_service/.env.example` 为 `vector_service/.env` 后按需修改：

```bash
cp vector_service/.env.example vector_service/.env
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| TEXTTOVEC_BASE_URL | `http://localhost:8099` | TextToVec 服务地址 |
| TEXTTOVEC_DIMENSION | `128` | 向量维度，需与 TextToVec 服务保持一致 |
| ES_MOCK | `true` | `true` 使用内存 mock；`false` 连接真实 ES |
| ES_URL | `http://localhost:9200` | 真实 ES 地址，ES_MOCK=false 时生效 |
| ES_USERNAME | `` | ES 用户名，ES_MOCK=false 时生效 |
| ES_PASSWORD | `` | ES 密码，ES_MOCK=false 时生效 |

### 本地开发（默认配置）

无需任何额外服务，`ES_MOCK=true`，直接运行：

```bash
uvicorn vector_service.main:app --reload --port 8000
```

### 对接真实服务

```bash
# vector_service/.env
ES_MOCK=false
ES_URL=http://your-es-host:9200
ES_USERNAME=your_username
ES_PASSWORD=your_password
TEXTTOVEC_BASE_URL=http://your-texttovec-host:port
TEXTTOVEC_DIMENSION=128
```
