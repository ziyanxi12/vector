# Vector Service

统一的向量化与搜索服务，为上游业务提供简单的 RESTful API，隐藏 Elasticsearch 和 TextToVec 的复杂性。

---

## 核心价值

### 为什么需要这个服务？

直接让上游服务连接 ES 和 TextToVec 看起来更简单，但这个服务提供了以下价值：

| 功能 | 如果上游直连 | 使用本服务 |
|------|-------------|-----------|
| **向量化逻辑** | ❌ 每个上游都要实现批量编码、并发控制、错误处理 | ✅ 统一封装，上游只需传文本 |
| **Hybrid 搜索融合** | ❌ 需要实现分数归一化、权重融合算法 | ✅ 开箱即用，一个参数开启 |
| **ES knn 查询** | ⚠️ 需要了解 ES 8.x 的 knn 语法 | ✅ 简单的 JSON 请求体 |
| **索引管理** | ❌ 需要手动创建索引、管理模板 | ✅ 自动处理 |
| **metadata 管理** | ❌ 每个上游自己定义结构 | ✅ 完全透传，上游自治 |

### 适用场景

- ✅ 有多个上游服务需要向量化能力
- ✅ 需要 hybrid 搜索（向量 + 全文融合）
- ✅ 不想深入学习 ES knn 查询语法
- ✅ metadata 结构频繁变化，不想维护验证逻辑

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     上游业务服务                              │
│         (组件库、图标库、模板库、插画库 ...)                    │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST API
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Vector Service                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Ingest API  │  │  Search API  │  │  Update API  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘      │
│         │                 │                                  │
│         │    ┌────────────┴────────────┐                   │
│         │    │  Search Modes           │                   │
│         │    │  - vector (knn)         │                   │
│         │    │  - text (BM25)          │                   │
│         │    │  - hybrid (融合)         │                   │
│         │    └─────────────────────────┘                   │
│         │                                                  │
└─────────┼──────────────────────────────────────────────────┘
          │
          ├──────────────────────┬──────────────────────────┐
          ▼                      ▼                          ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  TextToVec 服务   │   │ Elasticsearch 8  │   │  未来扩展...      │
│  (文本转向量)      │   │  (向量 + 全文)    │   │                  │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

---

## 核心功能

### 1. 向量化代理

- 调用 TextToVec API 批量编码
- 自动分批、并发控制
- 错误处理与部分失败返回

### 2. 三种搜索模式

| 模式 | 原理 | 适用场景 |
|------|------|----------|
| **vector** | ES knn 语义向量相似度 | 模糊语义匹配，如"蓝色的按钮" |
| **text** | ES match 全文检索 (BM25) | 关键词精确匹配，如"PrimaryButton" |
| **hybrid** | 向量 + 文本分数融合 | 兼顾语义和关键词 |

**Hybrid 融合算法**：
```
final_score = hybrid_weight × vector_score + (1 - hybrid_weight) × text_score
```
- `vector_score`: cosine similarity (已归一化 0~1)
- `text_score`: BM25 分数经 min-max 归一化到 0~1

### 3. Filters 筛选

支持对 metadata 字段进行精确筛选：

```json
{
  "filters": {
    "group_id": 4,           // 数字类型：直接匹配
    "category": "navigation" // 字符串类型：精确匹配
  }
}
```

**智能类型处理**：
- 字符串字段 → 使用 `metadata.{field}.keyword`
- 数字/布尔字段 → 直接使用 `metadata.{field}`

### 4. Metadata 完全透传

- **不做字段验证**：上游传入什么就存储什么
- **支持动态类型**：通过 `allow_dynamic_type=true` 支持任意 `type`
- **上游自治**：metadata 结构完全由上游定义

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp vector_service/.env.example vector_service/.env
```

编辑 `.env`：

```bash
# TextToVec 服务
TEXTTOVEC_BASE_URL=http://localhost:8099
TEXTTOVEC_DIMENSION=128

# Elasticsearch（可选，默认使用内存 mock）
ES_MOCK=true
# ES_MOCK=false
# ES_URL=http://localhost:9200
# ES_USERNAME=
# ES_PASSWORD=

# 动态类型支持
ALLOW_DYNAMIC_TYPE=true
```

### 3. 启动服务

```bash
uvicorn vector_service.main:app --reload --port 8000
```

---

## API 文档

详细 API 文档见 [api.md](./api.md)

### 核心接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/ingest` | POST | 批量入库 |
| `/api/v1/search` | POST | 单次搜索 |
| `/api/v1/search/batch` | POST | 批量搜索 |
| `/api/v1/update` | PUT | 更新数据 |
| `/api/v1/item` | GET | 精确查询 |
| `/api/v1/item` | DELETE | 删除数据 |

---

## 使用示例

### 入库

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "type": "icon",
    "items": [
      {
        "data_id": "icon_001",
        "text": "首页导航图标，房子形状",
        "metadata": {
          "name": "首页",
          "category": "navigation",
          "group_id": 1,
          "any_field": "any_value"
        }
      }
    ]
  }'
```

### 搜索（带筛选）

```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "type": "icon",
    "query": "首页",
    "mode": "hybrid",
    "top_k": 10,
    "filters": {
      "group_id": 1,
      "category": "navigation"
    }
  }'
```

### 批量搜索

```bash
curl -X POST http://localhost:8000/api/v1/search/batch \
  -H "Content-Type: application/json" \
  -d '{
    "type": "icon",
    "queries": ["首页", "设置", "通知"],
    "mode": "vector",
    "top_k": 5,
    "filters": {"group_id": 1}
  }'
```

---

## 设计理念

### Metadata 透传的设计决策

**为什么不做字段验证？**

1. **业务自治**：不同上游有不同的 metadata 结构，统一验证会增加维护成本
2. **快速迭代**：上游新增字段无需通知向量服务，无需修改代码
3. **减少耦合**：metadata 结构变化不影响向量服务稳定性

**如果需要验证怎么办？**

可以在上游服务入库前自行验证，向量服务只负责存储和检索。

### 动态类型支持

设置 `ALLOW_DYNAMIC_TYPE=true` 后，可以传入任意 `type` 值，服务会自动创建对应的索引：

```json
{"type": "new_type", "items": [...]}  // 自动创建 vec_new_type 索引
```

---

## 配置说明

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| TEXTTOVEC_BASE_URL | `http://localhost:8099` | TextToVec 服务地址 |
| TEXTTOVEC_DIMENSION | `128` | 向量维度 |
| ES_MOCK | `true` | 是否使用内存 mock |
| ES_URL | `http://localhost:9200` | ES 地址 |
| ES_USERNAME | `` | ES 用户名 |
| ES_PASSWORD | `` | ES 密码 |
| ES_INDEX_PREFIX | `vec_` | 索引名前缀 |
| ALLOW_DYNAMIC_TYPE | `true` | 是否允许动态类型 |

---

## License

MIT