"""Top-level orchestration of the Swagger 2.0 -> OpenAPI 3.0.3 migration."""

import json
from typing import Any

from swagger2to3.parameters import (
    build_body_request_body,
    build_form_request_body,
    convert_non_body_parameter,
)
from swagger2to3.refs import resolve_ref, sanitize_schema_name
from swagger2to3.schemas import convert_schema

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch")


def _resolve_parameter(document: dict, param: dict) -> dict:
    if "$ref" in param:
        return resolve_ref(document, param["$ref"])
    return param


def _merge_parameters(document: dict, path_params: list, op_params: list) -> list:
    """Merge path-level and operation-level parameters.

    Identity is (in, name) of the resolved parameter; operation-level
    entries override path-level entries with the same identity. Same name
    at a different location is a different identity and is kept.
    """
    merged: dict = {}
    order: list = []
    for raw in list(path_params) + list(op_params):
        param = _resolve_parameter(document, raw)
        identity = (param["in"], param["name"])
        if identity not in merged:
            order.append(identity)
        merged[identity] = param
    return [merged[identity] for identity in order]


def _convert_operation(document: dict, operation: dict, path_params: list,
                       root_consumes: list, name_map: dict) -> dict:
    out: dict = {}
    for key in ("tags", "summary", "description", "operationId", "deprecated"):
        if key in operation:
            out[key] = operation[key]

    consumes = operation.get("consumes", root_consumes)
    params = _merge_parameters(
        document, path_params, operation.get("parameters", [])
    )

    plain_params = []
    form_fields = []
    body_param = None
    for param in params:
        location = param["in"]
        if location == "body":
            body_param = param
        elif location == "formData":
            form_fields.append(param)
        else:
            plain_params.append(param)

    if plain_params:
        out["parameters"] = [
            convert_non_body_parameter(p, name_map.get) for p in plain_params
        ]
    if body_param is not None:
        out["requestBody"] = build_body_request_body(
            body_param, consumes, name_map.get
        )
    elif form_fields:
        out["requestBody"] = build_form_request_body(
            form_fields, consumes, name_map.get
        )

    # Request-side migration only: keep response stubs so the output stays
    # a valid OpenAPI 3.0.3 document.
    responses = operation.get("responses", {})
    out["responses"] = {
        str(code): {"description": str(resp.get("description", ""))}
        if isinstance(resp, dict)
        else {"description": ""}
        for code, resp in responses.items()
    } or {"default": {"description": ""}}
    return out


def migrate(document: dict) -> dict:
    """Migrate a parsed Swagger 2.0 document to an OpenAPI 3.0.3 document."""
    if document.get("swagger") != "2.0":
        raise ValueError("input must be a Swagger 2.0 document")

    definitions = document.get("definitions", {})
    name_map = {key: sanitize_schema_name(key) for key in definitions}
    if len(set(name_map.values())) != len(name_map):
        raise ValueError("schema name collision after sanitization")

    out: dict = {"openapi": "3.0.3"}
    out["info"] = dict(document.get("info", {}))

    servers = _convert_servers(document)
    if servers:
        out["servers"] = servers
    if "tags" in document:
        out["tags"] = document["tags"]
    if "externalDocs" in document:
        out["externalDocs"] = document["externalDocs"]

    root_consumes = document.get("consumes", [])
    paths: dict = {}
    for path, path_item in document.get("paths", {}).items():
        path_params = path_item.get("parameters", [])
        new_item: dict = {}
        for method in _HTTP_METHODS:
            if method in path_item:
                new_item[method] = _convert_operation(
                    document, path_item[method], path_params,
                    root_consumes, name_map,
                )
        paths[path] = new_item
    out["paths"] = paths

    if definitions:
        out["components"] = {
            "schemas": {
                name_map[key]: convert_schema(schema, name_map.get)
                for key, schema in definitions.items()
            }
        }
    return out


def _convert_servers(document: dict) -> list:
    host = document.get("host")
    if not host:
        return []
    base_path = document.get("basePath", "")
    schemes = document.get("schemes") or ["https"]
    return [{"url": f"{scheme}://{host}{base_path}"} for scheme in schemes]


def migrate_file(input_path: str, output_path: str) -> dict:
    """Read a Swagger 2.0 JSON file and write an OpenAPI 3.0.3 JSON file."""
    with open(input_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    result = migrate(document)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result
