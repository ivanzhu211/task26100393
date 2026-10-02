"""Schema (model) conversion: definitions, $ref rewriting, allOf, cycles."""

from typing import Any, Callable
from urllib.parse import unquote

from swagger2to3.refs import unescape_pointer_token

_DEFINITIONS_PREFIX = "#/definitions/"
_COMPONENTS_PREFIX = "#/components/schemas/"
_PASSTHROUGH_KEYS = ("example", "default")


def _rewrite_ref(ref: str, name_mapper: Callable[[str], str]) -> str:
    if ref.startswith(_DEFINITIONS_PREFIX):
        token = unescape_pointer_token(unquote(ref[len(_DEFINITIONS_PREFIX):]))
        return _COMPONENTS_PREFIX + name_mapper(token)
    return ref


def convert_schema(schema: Any, name_mapper: Callable[[str], str]) -> Any:
    """Convert a Swagger 2.0 schema to an OpenAPI 3.0.3 schema.

    ``name_mapper`` maps original definition keys to sanitized component
    names. ``$ref`` values inside ``example``/``default``/``x-`` extensions
    are treated as data and left untouched. Cycles are safe: they exist
    only as ``$ref`` strings, never as object graphs.
    """
    if isinstance(schema, list):
        return [convert_schema(item, name_mapper) for item in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key == "$ref" and isinstance(value, str):
            out[key] = _rewrite_ref(value, name_mapper)
        elif key in _PASSTHROUGH_KEYS or key.startswith("x-"):
            out[key] = value
        else:
            out[key] = convert_schema(value, name_mapper)
    return out
