"""Operation conversion: parameter merging, consumes, requestBody assembly."""

from typing import Any, Dict, List, Tuple

from .parameters import ParameterConverter
from .refs import RefResolver

# Operation fields carried over verbatim (request-relevant metadata only).
_PASSTHROUGH_KEYS = (
    "tags", "summary", "description", "operationId", "deprecated", "security",
)


class OperationConverter:
    def __init__(self, resolver: RefResolver, params: ParameterConverter) -> None:
        self.resolver = resolver
        self.params = params

    def _resolve(self, param: Dict[str, Any]) -> Dict[str, Any]:
        if "$ref" in param:
            return self.resolver.resolve(param["$ref"])
        return param

    @staticmethod
    def _identity(param: Dict[str, Any]) -> Tuple[str, str]:
        return (param["in"], param["name"])

    def _merge_parameters(
        self,
        path_parameters: List[Dict[str, Any]],
        operation_parameters: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for param in path_parameters + operation_parameters:
            resolved = self._resolve(param)
            merged[self._identity(resolved)] = resolved
        return list(merged.values())

    def convert_operation(
        self,
        operation: Dict[str, Any],
        path_parameters: List[Dict[str, Any]],
        root_consumes: List[str],
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key in _PASSTHROUGH_KEYS:
            if key in operation:
                out[key] = operation[key]
        for key, value in operation.items():
            if key.startswith("x-"):
                out[key] = value
        consumes = operation.get("consumes", root_consumes)
        merged = self._merge_parameters(
            path_parameters, operation.get("parameters", [])
        )
        regular = [
            p for p in merged if p["in"] in ("query", "header", "path", "cookie")
        ]
        body_params = [p for p in merged if p["in"] in ("body", "formData")]
        if regular:
            out["parameters"] = [
                self.params.convert_parameter(p) for p in regular
            ]
        request_body = self.params.build_request_body(body_params, consumes)
        if request_body is not None:
            out["requestBody"] = request_body
        return out
