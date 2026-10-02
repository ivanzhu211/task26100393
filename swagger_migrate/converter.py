"""Top-level orchestration of the Swagger 2.0 -> OpenAPI 3.0.3 migration."""

import json
from typing import Any, Dict

from .operations import OperationConverter
from .parameters import ParameterConverter
from .refs import RefResolver
from .schemas import SchemaConverter

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch")


def migrate(document: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a parsed Swagger 2.0 document to an OpenAPI 3.0.3 document."""
    resolver = RefResolver(document)
    schemas = SchemaConverter(resolver)
    operations = OperationConverter(resolver, ParameterConverter(resolver, schemas))

    root_consumes = document.get("consumes", [])
    out: Dict[str, Any] = {"openapi": "3.0.3", "info": document.get("info", {})}
    for key in ("tags", "externalDocs"):
        if key in document:
            out[key] = document[key]
    for key, value in document.items():
        if key.startswith("x-"):
            out[key] = value

    paths: Dict[str, Any] = {}
    for path, path_item in document.get("paths", {}).items():
        item: Dict[str, Any] = {}
        path_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method == "parameters" or method.startswith("x-"):
                continue
            if method not in _HTTP_METHODS:
                continue
            item[method] = operations.convert_operation(
                operation, path_parameters, root_consumes
            )
        for key, value in path_item.items():
            if key.startswith("x-"):
                item[key] = value
        paths[path] = item
    out["paths"] = paths

    definitions = document.get("definitions", {})
    if definitions:
        out["components"] = {
            "schemas": schemas.convert_definitions(definitions)
        }
    return out


def migrate_file(input_path: str, output_path: str) -> Dict[str, Any]:
    """Read a Swagger 2.0 JSON file and write an OpenAPI 3.0.3 JSON file."""
    with open(input_path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    result = migrate(document)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result
