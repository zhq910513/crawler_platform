# API 契约

- 路径采用 RESTful 风格复数名词。
- JSON 字段统一 camelCase。
- 响应统一为 `{ "code": 200, "message": "success", "data": ... }`。
- HTTP 状态码只使用 200、400、401、403、404、500。
- 数据库表和字段使用 snake_case。
- 后端 Controller 只负责参数和响应，业务逻辑在 Service，查询在 Repository。
