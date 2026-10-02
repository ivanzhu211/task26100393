"""Contract tests for the Swagger 2.0 -> OpenAPI 3.0.3 request migration."""

import json

import pytest

from swagger2to3.migrate import migrate, migrate_file
from swagger2to3.refs import sanitize_schema_name


def base_doc(**overrides):
    doc = {
        "swagger": "2.0",
        "info": {"title": "svc", "version": "1.0"},
        "paths": {},
    }
    doc.update(overrides)
    return doc


# --- Scenario 1: referenced operation parameter overrides path parameter ---

def test_referenced_operation_parameter_overrides_path_parameter():
    doc = base_doc(
        parameters={
            "VerboseQuery": {
                "name": "verbose",
                "in": "query",
                "type": "boolean",
                "default": True,
            }
        },
        paths={
            "/things": {
                "parameters": [
                    {"name": "verbose", "in": "query", "type": "string"},
                    {"name": "verbose", "in": "header", "type": "string"},
                ],
                "get": {
                    "parameters": [{"$ref": "#/parameters/VerboseQuery"}],
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    )
    out = migrate(doc)
    params = out["paths"]["/things"]["get"]["parameters"]
    by_location = {(p["in"], p["name"]): p for p in params}

    # Referenced operation parameter wins the (query, verbose) identity.
    assert by_location[("query", "verbose")]["schema"] == {
        "type": "boolean",
        "default": True,
    }
    # Same name at a different location is a different identity: kept.
    assert by_location[("header", "verbose")]["schema"] == {"type": "string"}
    assert len(params) == 2


# --- Scenario 2: shared body parameter with per-operation consumes ---

def test_shared_body_parameter_uses_each_operations_consumes():
    doc = base_doc(
        consumes=["application/json"],
        parameters={
            "PetBody": {
                "name": "pet",
                "in": "body",
                "required": True,
                "schema": {"$ref": "#/definitions/Pet"},
            }
        },
        definitions={
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        },
        paths={
            "/json": {
                "post": {
                    "consumes": ["application/json"],
                    "parameters": [
                        {"$ref": "#/parameters/PetBody"},
                        {
                            "name": "ids",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "integer", "format": "int64"},
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/vendor": {
                "post": {
                    "consumes": ["application/vnd.pet+json"],
                    "parameters": [{"$ref": "#/parameters/PetBody"}],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    )
    out = migrate(doc)

    json_body = out["paths"]["/json"]["post"]["requestBody"]
    assert list(json_body["content"]) == ["application/json"]
    assert json_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Pet"
    }
    assert json_body["required"] is True

    vendor_body = out["paths"]["/vendor"]["post"]["requestBody"]
    assert list(vendor_body["content"]) == ["application/vnd.pet+json"]
    assert vendor_body["content"]["application/vnd.pet+json"]["schema"] == {
        "$ref": "#/components/schemas/Pet"
    }

    # The shared model is not wrapped in an object keyed by the param name.
    assert "pet" not in json_body["content"]["application/json"]["schema"]

    # Array query parameter without collectionFormat defaults to csv.
    ids = out["paths"]["/json"]["post"]["parameters"][0]
    assert ids["name"] == "ids"
    assert ids["style"] == "form"
    assert ids["explode"] is False
    assert ids["schema"] == {
        "type": "array",
        "items": {"type": "integer", "format": "int64"},
    }


def test_operation_consumes_fully_override_root_consumes():
    doc = base_doc(
        consumes=["application/json", "application/xml"],
        paths={
            "/x": {
                "post": {
                    "consumes": ["text/csv"],
                    "parameters": [
                        {"name": "b", "in": "body", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    body = migrate(doc)["paths"]["/x"]["post"]["requestBody"]
    assert list(body["content"]) == ["text/csv"]


# --- formData conversion ---

def test_form_data_becomes_object_request_body():
    doc = base_doc(
        paths={
            "/upload": {
                "post": {
                    "consumes": ["multipart/form-data"],
                    "parameters": [
                        {
                            "name": "file",
                            "in": "formData",
                            "type": "file",
                            "required": True,
                            "description": "the file",
                        },
                        {"name": "note", "in": "formData", "type": "string",
                         "maxLength": 20, "default": "n/a"},
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    body = migrate(doc)["paths"]["/upload"]["post"]["requestBody"]
    schema = body["content"]["multipart/form-data"]["schema"]

    assert schema["type"] == "object"
    assert schema["properties"]["file"] == {
        "type": "string",
        "format": "binary",
        "description": "the file",
    }
    assert schema["properties"]["note"]["maxLength"] == 20
    assert schema["properties"]["note"]["default"] == "n/a"
    assert schema["required"] == ["file"]
    assert body["required"] is True


def test_form_data_without_required_fields_is_optional():
    doc = base_doc(
        paths={
            "/f": {
                "post": {
                    "consumes": ["application/x-www-form-urlencoded"],
                    "parameters": [
                        {"name": "a", "in": "formData", "type": "integer"}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    body = migrate(doc)["paths"]["/f"]["post"]["requestBody"]
    assert "required" not in body
    assert "required" not in body["content"][
        "application/x-www-form-urlencoded"
    ]["schema"]


# --- collectionFormat wire semantics ---

@pytest.mark.parametrize(
    "fmt,style,explode",
    [
        ("csv", "form", False),
        ("ssv", "spaceDelimited", False),
        ("pipes", "pipeDelimited", False),
        ("multi", "form", True),
    ],
)
def test_collection_format_mapping(fmt, style, explode):
    doc = base_doc(
        paths={
            "/q": {
                "get": {
                    "parameters": [
                        {
                            "name": "v",
                            "in": "query",
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": fmt,
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    param = migrate(doc)["paths"]["/q"]["get"]["parameters"][0]
    assert param["style"] == style
    assert param["explode"] == explode


@pytest.mark.parametrize("location", ["path", "header"])
def test_path_and_header_arrays_are_csv_only(location):
    doc = base_doc(
        paths={
            "/q": {
                "get": {
                    "parameters": [
                        {
                            "name": "v",
                            "in": location,
                            "required": True,
                            "type": "array",
                            "items": {"type": "string"},
                            "collectionFormat": "multi",
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    param = migrate(doc)["paths"]["/q"]["get"]["parameters"][0]
    assert param["style"] == "simple"
    assert param["explode"] is False


def test_scalar_constraints_and_defaults_are_preserved():
    doc = base_doc(
        paths={
            "/q": {
                "get": {
                    "parameters": [
                        {
                            "name": "n",
                            "in": "query",
                            "type": "number",
                            "maximum": 10,
                            "exclusiveMaximum": True,
                            "minimum": 1,
                            "multipleOf": 0.5,
                            "enum": [1, 2, 3],
                            "default": 2,
                        },
                        {
                            "name": "s",
                            "in": "query",
                            "type": "string",
                            "minLength": 2,
                            "maxLength": 8,
                            "pattern": "^[a-z]+$",
                        },
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    params = migrate(doc)["paths"]["/q"]["get"]["parameters"]
    number, string = params
    assert number["schema"] == {
        "type": "number",
        "exclusiveMaximum": 10,
        "minimum": 1,
        "multipleOf": 0.5,
        "enum": [1, 2, 3],
        "default": 2,
    }
    assert string["schema"] == {
        "type": "string",
        "minLength": 2,
        "maxLength": 8,
        "pattern": "^[a-z]+$",
    }


# --- models: nesting, allOf, cycles, exotic names ---

def test_circular_allof_and_exotic_model_names():
    doc = base_doc(
        definitions={
            "Node": {
                "type": "object",
                "properties": {
                    "child": {"$ref": "#/definitions/Node"},
                    "meta": {"$ref": "#/definitions/a~1b~0c%25d"},
                },
            },
            "a/b~c%d": {
                "allOf": [
                    {"$ref": "#/definitions/Node"},
                    {"type": "object"},
                ]
            },
            "中文模型": {
                "type": "object",
                "properties": {"n": {"$ref": "#/definitions/Node"}},
            },
        },
        paths={
            "/n": {
                "post": {
                    "consumes": ["application/json"],
                    "parameters": [
                        {
                            "name": "payload",
                            "in": "body",
                            "schema": {"$ref": "#/definitions/%E4%B8%AD%E6%96%87%E6%A8%A1%E5%9E%8B"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    )
    out = migrate(doc)
    schemas = out["components"]["schemas"]

    node_name = sanitize_schema_name("Node")
    exotic_name = sanitize_schema_name("a/b~c%d")
    cjk_name = sanitize_schema_name("中文模型")
    assert {node_name, exotic_name, cjk_name} == set(schemas)
    assert len({node_name, exotic_name, cjk_name}) == 3

    # Full cycle preserved through sanitized component names.
    node = schemas[node_name]
    assert node["properties"]["child"]["$ref"] == (
        f"#/components/schemas/{node_name}"
    )
    assert node["properties"]["meta"]["$ref"] == (
        f"#/components/schemas/{exotic_name}"
    )
    assert schemas[exotic_name]["allOf"][0]["$ref"] == (
        f"#/components/schemas/{node_name}"
    )
    assert schemas[cjk_name]["properties"]["n"]["$ref"] == (
        f"#/components/schemas/{node_name}"
    )

    # Percent-encoded URI fragment in the body $ref resolves to 中文模型.
    body = out["paths"]["/n"]["post"]["requestBody"]
    assert body["content"]["application/json"]["schema"] == {
        "$ref": f"#/components/schemas/{cjk_name}"
    }


def test_ref_like_data_in_example_default_and_extensions_is_untouched():
    doc = base_doc(
        definitions={
            "Thing": {
                "type": "object",
                "example": {"$ref": "#/definitions/Other"},
                "default": {"$ref": "#/definitions/Other"},
                "x-source": {"$ref": "#/definitions/Other"},
            }
        },
        paths={},
    )
    thing = migrate(doc)["components"]["schemas"]["Thing"]
    assert thing["example"] == {"$ref": "#/definitions/Other"}
    assert thing["default"] == {"$ref": "#/definitions/Other"}
    assert thing["x-source"] == {"$ref": "#/definitions/Other"}


# --- end-to-end file migration ---

def test_migrate_file_round_trip(tmp_path):
    doc = base_doc(
        host="api.example.com",
        basePath="/v1",
        schemes=["https"],
        paths={
            "/ping": {
                "get": {"responses": {"200": {"description": "pong"}}}
            }
        },
    )
    src = tmp_path / "swagger.json"
    dst = tmp_path / "openapi.json"
    src.write_text(json.dumps(doc), encoding="utf-8")

    result = migrate_file(str(src), str(dst))
    on_disk = json.loads(dst.read_text(encoding="utf-8"))

    assert result == on_disk
    assert on_disk["openapi"] == "3.0.3"
    assert on_disk["servers"] == [{"url": "https://api.example.com/v1"}]
    assert on_disk["paths"]["/ping"]["get"]["responses"] == {
        "200": {"description": "pong"}
    }
