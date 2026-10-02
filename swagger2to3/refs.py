"""JSON Pointer / $ref resolution and schema-name sanitization helpers."""

import re
from typing import Any
from urllib.parse import unquote

# OpenAPI 3.0.3 requires component keys to match ^[a-zA-Z0-9.\-_]+$
_SAFE_CHAR = re.compile(r"[a-zA-Z0-9.\-_]")
_ENCODED_CHAR = re.compile(r"_u([0-9A-F]+)_")


def unescape_pointer_token(token: str) -> str:
    """Unescape a single JSON Pointer token (RFC 6901)."""
    return token.replace("~1", "/").replace("~0", "~")


def resolve_ref(document: dict, ref: str) -> Any:
    """Resolve a local ``#/...`` reference against ``document``.

    The fragment is first percent-decoded per URI fragment rules, then
    interpreted as a JSON Pointer per RFC 6901.
    """
    if not ref.startswith("#/"):
        raise ValueError(f"only local references are supported: {ref!r}")
    node: Any = document
    for raw_token in ref[2:].split("/"):
        token = unescape_pointer_token(unquote(raw_token))
        if isinstance(node, list):
            node = node[int(token)]
        else:
            node = node[token]
    return node


def sanitize_schema_name(name: str) -> str:
    """Map an arbitrary Swagger definition key to a valid OpenAPI 3.0.3
    component schema name.

    Injective encoding: ``_`` becomes ``__``; any other disallowed
    character becomes ``_u<HEX>_`` using its Unicode code point. Two
    distinct original names therefore never map to the same result.
    """
    out = []
    for char in name:
        if char == "_":
            out.append("__")
        elif _SAFE_CHAR.match(char):
            out.append(char)
        else:
            out.append(f"_u{ord(char):X}_")
    return "".join(out) or "_u0_"


def restore_schema_name(sanitized: str) -> str:
    """Inverse of :func:`sanitize_schema_name` (used by tests/tools)."""
    out = []
    index = 0
    while index < len(sanitized):
        if sanitized.startswith("__", index):
            out.append("_")
            index += 2
            continue
        match = _ENCODED_CHAR.match(sanitized, index)
        if match:
            out.append(chr(int(match.group(1), 16)))
            index = match.end()
            continue
        out.append(sanitized[index])
        index += 1
    return "".join(out)
