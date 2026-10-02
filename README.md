# swagger-migrate

Swagger 2.0 → OpenAPI 3.0.3 请求契约迁移库。由上层导入流程调用，将本地
Swagger 2.0 JSON 文件转换为 OpenAPI 3.0.3 JSON 文件，仅迁移请求侧
（路径、方法、参数、请求体、模型），不包含接口层与服务端配置。

## 使用

```python
from swagger_migrate import migrate, migrate_file

# 文件到文件
migrate_file("swagger.json", "openapi.json")

# 已解析的字典到字典
openapi_doc = migrate(swagger_doc)
```

运行测试：

```bash
python3 -m pytest tests/ -q
```

## 迁移规则

- **参数身份**：路径级与操作级参数按 `(in, name)` 确定身份，操作级覆盖
  同身份的路径级参数；同名不同位置的参数同时保留。`$ref` 参数以目标
  参数的身份参与覆盖。
- **consumes**：操作级 `consumes` 存在时完全覆盖根级；共享 body 参数在
  不同操作中各自使用本操作的有效媒体类型。
- **body**：保持原模型与必填性，不额外包裹参数名；`formData` 转为对象
  请求体，各字段必填性分别保留，请求体必填当且仅当至少一个字段必填；
  `type: file` 转为 `{type: string, format: binary}`。
- **普通参数**：标量与标量数组保留默认值、枚举、数值及长度约束；
  `collectionFormat` 缺省按 `csv` 处理；`csv/ssv/pipes/multi` 映射为
  OAS3 的 `style`/`explode`；路径与请求头中的数组仅支持 `csv`。
- **模型**：支持嵌套、`allOf`、共享与循环引用；引用按 URI 片段及
  JSON Pointer 规则解释，模型名可含斜杠、波浪号、百分号与非 ASCII
  字符，统一编码为合法的 OAS 3.0.3 组件名且互不混淆；
  `example`/`default`/`x-*` 内部的 `$ref` 作为数据原样保留。
- **范围**：仅迁移请求侧。`responses`、`produces`、`schemes` 等响应侧
  与服务端字段不写入输出。

## 输入约束

- 合法 Swagger 2.0 JSON；请求模型不含 XML 与 discriminator。
- `formData` 不含数组；文件表单仅使用 `multipart/form-data`。
- 仅支持指向根级 `parameters` 或 `definitions` 条目的本地引用。
- 有请求体的操作能取得非空 `consumes`。

## 模块结构

- `swagger_migrate/refs.py`：本地引用解析、JSON Pointer 解码、组件名编码。
- `swagger_migrate/schemas.py`：模型转换（约束、allOf、循环引用）。
- `swagger_migrate/parameters.py`：参数与请求体转换。
- `swagger_migrate/operations.py`：操作级参数合并与 consumes 生效。
- `swagger_migrate/converter.py`：顶层编排与文件入口。
