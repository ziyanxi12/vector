这是一个统一的向量库管理服务。可以支撑组件数据的入库、更新、查询， 图标数据的入库、更新、查询，以及未来可能扩展的数据。

现在有 文本转向量 api：
mock_ip:mock_port/textToVec
参数是 "dimenison":128, "text_value":[{"text":"aaa", "text_id":"sss"}]
返回结果 {"vectors":[{"vector":[], "text_id":"sss"}]}

ES服务，ES都mock一下，ES版本是8.15

扩展一下方案