"""Local $ref resolution and OpenAPI 3.0.3 compatible component naming."""

from typing import Any, Dict, List
from urllib.parse import unquote

# OpenAPI 3.0.3 requires component keys to match ^[a-zA-Z0-9.\-_]+$.
_SAFE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
)


def pointer_segments(ref: str) -> List[str]:
    """Split a local ref into decoded JSON Pointer segments.

    Applies URI fragment percent-decoding first, then JSON Pointer
    unescaping (~1 -> '/', then ~0 -> '~') per RFC 6901.
    """
    if not ref.startswith("#/"):
        raise ValueError(f"only local refs are supported: {ref!r}")
    fragment = unquote(ref[2:])
    segments = fragment.split("/")
    return [seg.replace("~1", "/").replace("~0", "~") for seg in segments]


def encode_component_name(key: str) -> str:
    """Encode an arbitrary definition key into a valid OAS 3.0.3 name.

    '_' is doubled; any other unsafe character becomes '_x{hex}_'.
    The mapping is injective, so distinct keys never collide.
    """
    out = []
    for ch in key:
        if ch == "_":
            out.append("__")
        elif ch in _SAFE_CHARS:
            out.append(ch)
        else:
            out.append("_x{:X}_".format(ord(ch)))
    return "".join(out) or "_x0_"


class RefResolver:
    """Resolves local JSON references and maps definition keys to safe names."""

    def __init__(self, document: Dict[str, Any]) -> None:
        self.document = document
        self._name_cache: Dict[str, str] = {}

    def resolve(self, ref: str) -> Any:
        node: Any = self.document
        for segment in pointer_segments(ref):
            if not isinstance(node, dict) or segment not in node:
                raise KeyError(f"unresolvable ref: {ref!r}")
            node = node[segment]
        return node

    def component_name(self, ref: str) -> str:
        if ref not in self._name_cache:
            key = pointer_segments(ref)[-1]
            self._name_cache[ref] = encode_component_name(key)
        return self._name_cache[ref]

    def rewrite_ref(self, ref: str) -> str:
        segments = pointer_segments(ref)
        if len(segments) == 2 and segments[0] == "definitions":
            return "#/components/schemas/{}".format(self.component_name(ref))
        raise ValueError(f"unsupported schema ref: {ref!r}")
