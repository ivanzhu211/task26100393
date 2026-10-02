# swagger2to3

Swagger 2.0 → OpenAPI 3.0.3 请求契约迁移库（仅迁移请求侧），由上层导入流程以库方式调用，将本地 Swagger 2.0 JSON 文件转换为 OpenAPI 3.0.3 JSON 文件。无接口层、无第三方依赖。

## 使用

```python
from swagger2to3 import migrate, migrate_file

# 方式一：文件到文件
migrate_file("swagger.json", "openapi.json")

# 方式二：已解析的 dict -> dict
openapi_doc = migrate(swagger_doc)
```

## 迁移规则

- 保留路径与 HTTP 方法；路径级与操作级参数按 `(in, name)` 确定身份，操作级覆盖同身份的路径级参数；同名不同位置的参数同时保留。`$ref` 参数以目标参数的身份参与覆盖。
- 操作级 `consumes` 存在时完全覆盖根级；共享 body 参数在各操作中使用该操作自己的有效媒体类型。
- `body` 参数转为 `requestBody`，模型原样引用，不额外包裹参数名；`formData` 转为对象请求体，字段必填性分别保留，请求体必填当且仅当至少一个字段必填；`type: file` 转为 `string + format: binary`。
- 普通参数支持标量与标量数组，`default`、`enum`、数值与长度约束移入 `schema`。`collectionFormat` 缺省按 `csv`：`csv/ssv/pipes/multi` 分别映射为 `form+explode=false`、`spaceDelimited`、`pipeDelimited`、`form+explode=true`；path/header 数组仅支持 `csv`（`simple`）。
- 模型支持嵌套、`allOf`、共享与循环引用；引用按 URI 片段 + JSON Pointer（RFC 6901）规则解析，模型名可含 `/`、`~`、`%` 及非 ASCII 字符，清洗为合法的 OpenAPI 3.0.3 组件名且互不冲突，循环关系完整保留。`example`、`default`、`x-` 扩展内部的 `$ref` 作为数据原样保留。
- 响应侧不迁移，仅保留各响应的 `description` 占位，保证输出为合法的 OpenAPI 3.0.3 文档。

## 输入约束

合法 Swagger 2.0 JSON；请求模型不含 XML 与 discriminator；formData 不含数组；文件表单仅用于 `multipart/form-data`；仅支持指向根级 `parameters` 或 `definitions` 条目的本地引用；有请求体的操作能取得非空 `consumes`。

## 测试

```bash
python3 -m pytest tests/ -q
```
