"""Parameter conversion: query/header/path params, body and formData."""

from typing import Any, Dict, List, Optional

from .refs import RefResolver
from .schemas import SchemaConverter

# Param-level keys that become schema keys in OpenAPI 3.
_SCHEMA_KEYS = (
    "type", "format", "items", "default", "enum",
    "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum",
    "maxLength", "minLength", "pattern",
    "maxItems", "minItems", "uniqueItems", "multipleOf",
)

# collectionFormat -> (style, explode) for query parameters.
_QUERY_ARRAY_STYLES = {
    "csv": ("form", False),
    "ssv": ("spaceDelimited", False),
    "pipes": ("pipeDelimited", False),
    "multi": ("form", True),
}


class ParameterConverter:
    def __init__(self, resolver: RefResolver, schemas: SchemaConverter) -> None:
        self.resolver = resolver
        self.schemas = schemas

    def _schema_from_param(self, param: Dict[str, Any]) -> Dict[str, Any]:
        schema = {k: param[k] for k in _SCHEMA_KEYS if k in param}
        return self.schemas.convert(schema)

    def convert_parameter(self, param: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a non-body, non-formData parameter."""
        location = param["in"]
        out: Dict[str, Any] = {"name": param["name"], "in": location}
        if location == "path":
            out["required"] = True
        elif param.get("required"):
            out["required"] = True
        for key in ("description", "allowEmptyValue"):
            if key in param:
                out[key] = param[key]
        for key, value in param.items():
            if key.startswith("x-"):
                out[key] = value
        schema = self._schema_from_param(param)
        if schema.get("type") == "array":
            collection = param.get("collectionFormat", "csv")
            if location == "query":
                style, explode = _QUERY_ARRAY_STYLES[collection]
            else:
                if collection != "csv":
                    raise ValueError(
                        f"parameter {param['name']!r} in {location}: only 'csv' "
                        f"collectionFormat is supported, got {collection!r}"
                    )
                style, explode = "simple", False
            out["style"] = style
            out["explode"] = explode
        out["schema"] = schema
        return out

    def _form_field_schema(self, param: Dict[str, Any]) -> Dict[str, Any]:
        if param.get("type") == "file":
            schema: Dict[str, Any] = {"type": "string", "format": "binary"}
        else:
            schema = self._schema_from_param(param)
        if "description" in param:
            schema["description"] = param["description"]
        for key, value in param.items():
            if key.startswith("x-"):
                schema[key] = value
        return schema

    def build_request_body(
        self, params: List[Dict[str, Any]], consumes: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Build requestBody from body and/or formData parameters."""
        body_param = next((p for p in params if p.get("in") == "body"), None)
        form_params = [p for p in params if p.get("in") == "formData"]
        if body_param is None and not form_params:
            return None
        request_body: Dict[str, Any] = {}
        if body_param is not None:
            if "description" in body_param:
                request_body["description"] = body_param["description"]
            for key, value in body_param.items():
                if key.startswith("x-"):
                    request_body[key] = value
            if body_param.get("required"):
                request_body["required"] = True
            schema = self.schemas.convert(body_param.get("schema", {}))
            request_body["content"] = {
                media: {"schema": schema} for media in consumes
            }
            return request_body
        properties: Dict[str, Any] = {}
        required_fields: List[str] = []
        for param in form_params:
            properties[param["name"]] = self._form_field_schema(param)
            if param.get("required"):
                required_fields.append(param["name"])
        form_schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required_fields:
            form_schema["required"] = required_fields
            request_body["required"] = True
        request_body["content"] = {
            media: {"schema": form_schema} for media in consumes
        }
        return request_body
