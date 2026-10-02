import json

from swagger_migrate import migrate, migrate_file


def _base_doc():
    return {
        "swagger": "2.0",
        "info": {"title": "Legacy API", "version": "1.0.0"},
        "paths": {},
    }


def test_ref_operation_param_overrides_path_param_and_keeps_other_location():
    doc = _base_doc()
    doc["parameters"] = {
        "ResourceId": {
            "name": "id",
            "in": "path",
            "required": True,
            "type": "string",
            "pattern": "^[a-z]+$",
        }
    }
    doc["paths"] = {
        "/things/{id}": {
            "parameters": [
                {"name": "id", "in": "path", "required": True, "type": "integer"},
                {"name": "id", "in": "query", "type": "string"},
            ],
            "get": {
                "operationId": "getThing",
                "parameters": [{"$ref": "#/parameters/ResourceId"}],
                "responses": {"200": {"description": "ok"}},
            },
        }
    }
    out = migrate(doc)
    params = out["paths"]["/things/{id}"]["get"]["parameters"]
    by_identity = {(p["in"], p["name"]): p for p in params}
    assert set(by_identity) == {("path", "id"), ("query", "id")}
    # The referenced operation parameter wins for (path, id).
    assert by_identity[("path", "id")]["schema"] == {
        "type": "string",
        "pattern": "^[a-z]+$",
    }
    assert by_identity[("path", "id")]["required"] is True
    # Same name in a different location is preserved untouched.
    assert by_identity[("query", "id")]["schema"] == {"type": "string"}
    assert "required" not in by_identity[("query", "id")]


def test_shared_body_param_with_different_consumes_and_default_array_csv():
    doc = _base_doc()
    doc["consumes"] = ["application/json"]
    doc["definitions"] = {
        "Widget": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
    }
    doc["paths"] = {
        "/widgets": {
            "post": {
                "operationId": "createWidget",
                "consumes": ["application/vnd.widget+json"],
                "parameters": [
                    {"name": "payload", "in": "body", "required": True,
                     "schema": {"$ref": "#/definitions/Widget"}},
                    {"name": "flags", "in": "query", "type": "array",
                     "items": {"type": "string"}, "default": ["a", "b"]},
                ],
                "responses": {"200": {"description": "ok"}},
            },
            "put": {
                "operationId": "replaceWidget",
                "parameters": [
                    {"name": "payload", "in": "body", "required": True,
                     "schema": {"$ref": "#/definitions/Widget"}},
                ],
                "responses": {"200": {"description": "ok"}},
            },
        }
    }
    out = migrate(doc)
    post = out["paths"]["/widgets"]["post"]
    put = out["paths"]["/widgets"]["put"]
    # Operation-level consumes fully overrides the root-level value.
    assert set(post["requestBody"]["content"]) == {"application/vnd.widget+json"}
    # The sibling operation falls back to the root-level consumes.
    assert set(put["requestBody"]["content"]) == {"application/json"}
    # Both share the same body schema and requiredness, with no name wrapper.
    for op in (post, put):
        body = op["requestBody"]
        assert body["required"] is True
        for media in body["content"].values():
            assert media["schema"] == {
                "$ref": "#/components/schemas/Widget"
            }
    # Array query parameter without collectionFormat defaults to csv.
    flags = post["parameters"][0]
    assert flags["name"] == "flags"
    assert flags["style"] == "form"
    assert flags["explode"] is False
    assert flags["schema"] == {
        "type": "array",
        "items": {"type": "string"},
        "default": ["a", "b"],
    }


def test_collection_formats_and_header_path_arrays():
    doc = _base_doc()
    doc["paths"] = {
        "/search/{tags}": {
            "get": {
                "operationId": "search",
                "parameters": [
                    {"name": "tags", "in": "path", "required": True,
                     "type": "array", "items": {"type": "string"}},
                    {"name": "a", "in": "query", "type": "array",
                     "items": {"type": "integer"}, "collectionFormat": "ssv"},
                    {"name": "b", "in": "query", "type": "array",
                     "items": {"type": "integer"}, "collectionFormat": "pipes"},
                    {"name": "c", "in": "query", "type": "array",
                     "items": {"type": "integer"}, "collectionFormat": "multi"},
                    {"name": "X-Ids", "in": "header", "type": "array",
                     "items": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    params = {p["name"]: p for p in
              migrate(doc)["paths"]["/search/{tags}"]["get"]["parameters"]}
    assert (params["tags"]["style"], params["tags"]["explode"]) == ("simple", False)
    assert (params["a"]["style"], params["a"]["explode"]) == ("spaceDelimited", False)
    assert (params["b"]["style"], params["b"]["explode"]) == ("pipeDelimited", False)
    assert (params["c"]["style"], params["c"]["explode"]) == ("form", True)
    assert (params["X-Ids"]["style"], params["X-Ids"]["explode"]) == ("simple", False)


def test_formdata_fields_file_and_requiredness():
    doc = _base_doc()
    doc["paths"] = {
        "/upload": {
            "post": {
                "operationId": "upload",
                "consumes": ["multipart/form-data"],
                "parameters": [
                    {"name": "title", "in": "formData", "type": "string",
                     "required": True, "maxLength": 80},
                    {"name": "note", "in": "formData", "type": "string"},
                    {"name": "attachment", "in": "formData", "type": "file"},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    body = migrate(doc)["paths"]["/upload"]["post"]["requestBody"]
    assert body["required"] is True
    schema = body["content"]["multipart/form-data"]["schema"]
    assert schema["type"] == "object"
    assert schema["required"] == ["title"]
    assert schema["properties"]["title"] == {"type": "string", "maxLength": 80}
    assert schema["properties"]["note"] == {"type": "string"}
    assert schema["properties"]["attachment"] == {
        "type": "string",
        "format": "binary",
    }


def test_optional_form_makes_optional_request_body():
    doc = _base_doc()
    doc["paths"] = {
        "/submit": {
            "post": {
                "operationId": "submit",
                "consumes": ["application/x-www-form-urlencoded"],
                "parameters": [
                    {"name": "a", "in": "formData", "type": "string"},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    body = migrate(doc)["paths"]["/submit"]["post"]["requestBody"]
    assert "required" not in body
    schema = body["content"]["application/x-www-form-urlencoded"]["schema"]
    assert "required" not in schema


def test_cyclic_models_allof_and_unusual_names():
    doc = _base_doc()
    doc["definitions"] = {
        "tree/node": {
            "type": "object",
            "properties": {
                "parent": {"$ref": "#/definitions/tree~1node"},
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/tree~1node"},
                },
            },
        },
        "100%覆盖率~v2": {
            "allOf": [
                {"$ref": "#/definitions/tree~1node"},
                {"type": "object",
                 "properties": {"self": {"$ref": "#/definitions/100%25%E8%A6%86%E7%9B%96%E7%8E%87~0v2"}}},
            ]
        },
    }
    doc["paths"] = {
        "/nodes": {
            "post": {
                "operationId": "create",
                "consumes": ["application/json"],
                "parameters": [
                    {"name": "node", "in": "body",
                     "schema": {"$ref": "#/definitions/100%25%E8%A6%86%E7%9B%96%E7%8E%87~0v2"}}
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    out = migrate(doc)
    schemas = out["components"]["schemas"]
    node_name = "tree_x2F_node"
    weird_name = "100_x25__x8986__x76D6__x7387__x7E_v2"
    assert set(schemas) == {node_name, weird_name}
    node = schemas[node_name]
    assert node["properties"]["parent"] == {
        "$ref": "#/components/schemas/" + node_name
    }
    assert node["properties"]["children"]["items"] == {
        "$ref": "#/components/schemas/" + node_name
    }
    weird = schemas[weird_name]
    assert weird["allOf"][0] == {"$ref": "#/components/schemas/" + node_name}
    assert weird["allOf"][1]["properties"]["self"] == {
        "$ref": "#/components/schemas/" + weird_name
    }
    body = out["paths"]["/nodes"]["post"]["requestBody"]
    assert body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/" + weird_name
    }


def test_refs_inside_example_default_and_extensions_are_data():
    doc = _base_doc()
    doc["definitions"] = {
        "Pet": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "default": {"$ref": "#/definitions/Pet"},
                    "example": {"$ref": "#/definitions/Pet"},
                    "x-sample": {"$ref": "#/definitions/Pet"},
                }
            },
        }
    }
    doc["paths"] = {}
    out = migrate(doc)
    prop = out["components"]["schemas"]["Pet"]["properties"]["name"]
    assert prop["default"] == {"$ref": "#/definitions/Pet"}
    assert prop["example"] == {"$ref": "#/definitions/Pet"}
    assert prop["x-sample"] == {"$ref": "#/definitions/Pet"}


def test_parameter_constraints_preserved():
    doc = _base_doc()
    doc["paths"] = {
        "/items": {
            "get": {
                "operationId": "list",
                "parameters": [
                    {"name": "limit", "in": "query", "type": "integer",
                     "default": 20, "minimum": 1, "maximum": 100,
                     "exclusiveMaximum": True, "multipleOf": 5},
                    {"name": "prefix", "in": "query", "type": "string",
                     "minLength": 2, "maxLength": 10, "pattern": "^[a-z]+",
                     "enum": ["ab", "abc"]},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    params = {p["name"]: p for p in
              migrate(doc)["paths"]["/items"]["get"]["parameters"]}
    assert params["limit"]["schema"] == {
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "exclusiveMaximum": 100,
        "multipleOf": 5,
    }
    assert params["prefix"]["schema"] == {
        "type": "string",
        "minLength": 2,
        "maxLength": 10,
        "pattern": "^[a-z]+",
        "enum": ["ab", "abc"],
    }


def test_migrate_file_roundtrip(tmp_path):
    doc = _base_doc()
    doc["paths"] = {
        "/ping": {
            "get": {
                "operationId": "ping",
                "parameters": [
                    {"name": "q", "in": "query", "type": "string"}
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    src = tmp_path / "swagger.json"
    dst = tmp_path / "openapi.json"
    src.write_text(json.dumps(doc), encoding="utf-8")
    result = migrate_file(str(src), str(dst))
    on_disk = json.loads(dst.read_text(encoding="utf-8"))
    assert result == on_disk
    assert on_disk["openapi"] == "3.0.3"
    assert on_disk["paths"]["/ping"]["get"]["parameters"][0]["schema"] == {
        "type": "string"
    }
