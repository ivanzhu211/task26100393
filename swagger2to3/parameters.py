"""Parameter conversion: shared/operation parameters, formData, body."""

from typing import Any, Callable

from swagger2to3.schemas import convert_schema

# Swagger 2.0 parameter-level fields that become OpenAPI 3.0.3 schema fields.
_SCHEMA_KEYS = (
    "type",
    "format",
    "items",
    "default",
    "enum",
    "maximum",
    "minimum",
    "multipleOf",
    "maxLength",
    "minLength",
    "pattern",
    "maxItems",
    "minItems",
    "uniqueItems",
)

_QUERY_ARRAY_STYLES = {
    "csv": ("form", False),
    "ssv": ("spaceDelimited", False),
    "pipes": ("pipeDelimited", False),
    "multi": ("form", True),
}


def _schema_from_param(param: dict, name_mapper: Callable[[str], str]) -> dict:
    schema = {}
    for key in _SCHEMA_KEYS:
        if key in param:
            schema[key] = param[key]
    if param.get("exclusiveMaximum") is True and "maximum" in schema:
        schema["exclusiveMaximum"] = schema.pop("maximum")
    if param.get("exclusiveMinimum") is True and "minimum" in schema:
        schema["exclusiveMinimum"] = schema.pop("minimum")
    return convert_schema(schema, name_mapper)


def _array_serialization(location: str, collection_format: str) -> tuple:
    """Return (style, explode) preserving the Swagger 2.0 wire meaning."""
    if location in ("path", "header"):
        # Arrays in path/header only support csv.
        return ("simple", False)
    return _QUERY_ARRAY_STYLES[collection_format]


def convert_non_body_parameter(param: dict, name_mapper: Callable[[str], str]) -> dict:
    """Convert a Swagger 2.0 query/header/path parameter to OpenAPI 3.0.3."""
    location = param["in"]
    out: dict = {"name": param["name"], "in": location}
    for key in ("description", "deprecated"):
        if key in param:
            out[key] = param[key]
    if location == "path":
        out["required"] = True
    elif param.get("required"):
        out["required"] = True
    if location == "query" and "allowEmptyValue" in param:
        out["allowEmptyValue"] = param["allowEmptyValue"]

    schema = _schema_from_param(param, name_mapper)
    if schema.get("type") == "array":
        style, explode = _array_serialization(
            location, param.get("collectionFormat", "csv")
        )
        out["style"] = style
        out["explode"] = explode
    out["schema"] = schema
    return out


def _form_field_schema(field: dict, name_mapper: Callable[[str], str]) -> dict:
    if field.get("type") == "file":
        return {"type": "string", "format": "binary"}
    return _schema_from_param(field, name_mapper)


def build_form_request_body(
    fields: list, consumes: list, name_mapper: Callable[[str], str]
) -> dict:
    """Build an OpenAPI 3.0.3 requestBody from Swagger 2.0 formData fields."""
    properties: dict = {}
    required_names = []
    for field in fields:
        properties[field["name"]] = _form_field_schema(field, name_mapper)
        if field.get("description"):
            properties[field["name"]]["description"] = field["description"]
        if field.get("required"):
            required_names.append(field["name"])
    schema: dict = {"type": "object", "properties": properties}
    if required_names:
        schema["required"] = required_names

    body: dict = {"content": {}}
    for media_type in consumes:
        body["content"][media_type] = {"schema": dict(schema)}
    if required_names:
        body["required"] = True
    return body


def build_body_request_body(
    param: dict, consumes: list, name_mapper: Callable[[str], str]
) -> dict:
    """Build an OpenAPI 3.0.3 requestBody from a Swagger 2.0 body parameter.

    The original model schema is used as-is (no wrapper object keyed by the
    parameter name).
    """
    schema = convert_schema(param.get("schema", {}), name_mapper)
    body: dict = {"content": {}}
    for media_type in consumes:
        body["content"][media_type] = {"schema": schema}
    if param.get("required"):
        body["required"] = True
    if param.get("description"):
        body["description"] = param["description"]
    return body
