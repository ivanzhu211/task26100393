"""Schema conversion: types, constraints, allOf, shared and cyclic models."""

from typing import Any, Dict

from .refs import RefResolver, encode_component_name

# Keys whose values are example/default data or extensions: any "$ref"
# inside them is payload, not a reference, and must be preserved verbatim.
_DATA_KEYS = frozenset({"example", "default", "examples"})

# Keys holding nested schemas that need recursive conversion.
_SCHEMA_LIST_KEYS = ("allOf", "anyOf", "oneOf")


class SchemaConverter:
    def __init__(self, resolver: RefResolver) -> None:
        self.resolver = resolver

    def convert(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(schema, dict):
            return schema
        out: Dict[str, Any] = {}
        for key, value in schema.items():
            if key == "$ref":
                out["$ref"] = self.resolver.rewrite_ref(value)
            elif key in _DATA_KEYS or key.startswith("x-"):
                out[key] = value
            elif key == "properties" and isinstance(value, dict):
                out[key] = {k: self.convert(v) for k, v in value.items()}
            elif key in ("items", "additionalProperties", "not"):
                out[key] = self.convert(value) if isinstance(value, dict) else value
            elif key in _SCHEMA_LIST_KEYS and isinstance(value, list):
                out[key] = [self.convert(v) for v in value]
            else:
                out[key] = value
        self._convert_exclusive_bounds(out)
        return out

    @staticmethod
    def _convert_exclusive_bounds(schema: Dict[str, Any]) -> None:
        # Swagger 2.0 uses boolean exclusiveMinimum/Maximum alongside
        # minimum/maximum; OAS 3.0.3 uses numeric exclusive bounds.
        for bound, exclusive in (("minimum", "exclusiveMinimum"),
                                 ("maximum", "exclusiveMaximum")):
            flag = schema.pop(exclusive, None)
            if flag is True and bound in schema:
                schema[exclusive] = schema.pop(bound)

    def convert_definitions(self, definitions: Dict[str, Any]) -> Dict[str, Any]:
        return {
            encode_component_name(key): self.convert(schema)
            for key, schema in definitions.items()
        }
