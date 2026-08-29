from __future__ import annotations

import math
from typing import Any


class PluginSchemaError(ValueError):
    pass


class PluginSchemaValidationError(ValueError):
    pass


_COMMON = {"type", "enum", "const", "description"}
_BY_TYPE = {
    "object": {"properties", "required", "additionalProperties"},
    "array": {"items", "minItems", "maxItems"},
    "string": {"minLength", "maxLength"},
    "integer": {"minimum", "maximum"},
    "number": {"minimum", "maximum"},
    "boolean": set(),
    "null": set(),
}


def validate_json_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    _validate_schema(schema, depth=0, require_object=True)
    return schema


def validate_json_instance(schema: dict[str, Any], value: Any) -> None:
    _validate_instance(schema, value, path="params")


def _validate_schema(schema: Any, *, depth: int, require_object: bool = False) -> None:
    if depth > 32 or not isinstance(schema, dict):
        raise PluginSchemaError("plugin bridge schema is invalid")
    value_type = schema.get("type")
    if value_type not in _BY_TYPE or (require_object and value_type != "object"):
        raise PluginSchemaError("plugin bridge schema uses an unsupported type")
    unknown = set(schema) - _COMMON - _BY_TYPE[value_type]
    if unknown:
        raise PluginSchemaError("plugin bridge schema uses unsupported keywords")
    if "description" in schema and not isinstance(schema["description"], str):
        raise PluginSchemaError("plugin bridge schema description must be text")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or not enum:
            raise PluginSchemaError("plugin bridge schema enum must be non-empty")
    if value_type == "object":
        properties = schema.get("properties")
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not all(isinstance(key, str) and key for key in properties):
            raise PluginSchemaError("plugin bridge object schema requires named properties")
        if not isinstance(schema.get("additionalProperties"), bool):
            raise PluginSchemaError("plugin bridge object schema must declare additionalProperties")
        if (
            not isinstance(required, list)
            or len(required) != len(set(required))
            or any(not isinstance(key, str) or key not in properties for key in required)
        ):
            raise PluginSchemaError("plugin bridge object schema has invalid required properties")
        for child in properties.values():
            _validate_schema(child, depth=depth + 1)
    elif value_type == "array":
        if "items" not in schema:
            raise PluginSchemaError("plugin bridge array schema requires items")
        _validate_schema(schema["items"], depth=depth + 1)
        _validate_non_negative_bounds(schema, "minItems", "maxItems")
    elif value_type == "string":
        _validate_non_negative_bounds(schema, "minLength", "maxLength")
    elif value_type in {"integer", "number"}:
        for name in ("minimum", "maximum"):
            if name in schema and (
                isinstance(schema[name], bool)
                or not isinstance(schema[name], (int, float))
                or not _is_finite_number(schema[name])
            ):
                raise PluginSchemaError("plugin bridge numeric bound is invalid")


def _validate_non_negative_bounds(schema: dict[str, Any], minimum: str, maximum: str) -> None:
    for name in (minimum, maximum):
        if name in schema and (isinstance(schema[name], bool) or not isinstance(schema[name], int) or schema[name] < 0):
            raise PluginSchemaError("plugin bridge size bound is invalid")
    if minimum in schema and maximum in schema and schema[minimum] > schema[maximum]:
        raise PluginSchemaError("plugin bridge size bounds are inconsistent")


def _validate_instance(schema: dict[str, Any], value: Any, *, path: str) -> None:
    value_type = schema["type"]
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool) and _is_finite_number(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[value_type]
    if not matches:
        raise PluginSchemaValidationError(f"{path} has the wrong type")
    if "const" in schema and value != schema["const"]:
        raise PluginSchemaValidationError(f"{path} does not match const")
    if "enum" in schema and value not in schema["enum"]:
        raise PluginSchemaValidationError(f"{path} is outside enum")
    if value_type == "object":
        properties = schema["properties"]
        missing = set(schema.get("required", ())) - set(value)
        if missing:
            raise PluginSchemaValidationError(f"{path} is missing required properties")
        if schema["additionalProperties"] is False and not set(value) <= set(properties):
            raise PluginSchemaValidationError(f"{path} contains unsupported properties")
        for key, child in properties.items():
            if key in value:
                _validate_instance(child, value[key], path=f"{path}.{key}")
    elif value_type == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            raise PluginSchemaValidationError(f"{path} has an invalid item count")
        for index, item in enumerate(value):
            _validate_instance(schema["items"], item, path=f"{path}[{index}]")
    elif value_type == "string":
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
            raise PluginSchemaValidationError(f"{path} has an invalid length")
    elif value_type in {"integer", "number"}:
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise PluginSchemaValidationError(f"{path} is outside numeric bounds")


def _is_finite_number(value: int | float) -> bool:
    return isinstance(value, int) or math.isfinite(value)


__all__ = [
    "PluginSchemaError",
    "PluginSchemaValidationError",
    "validate_json_instance",
    "validate_json_object_schema",
]
