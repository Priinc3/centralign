"""Frozen contract: tool manifest (OpenAI strict tool-calling shape).

Phase 02 (tools) and Phase 03 (policy) read this file; nobody edits it after
freeze. Any change goes through a HELP post in prompts/parallel-G1/COMM.md.

Refs:
- https://developers.openai.com/api/docs/guides/function-calling  (strict mode)
- https://developers.openai.com/api/docs/guides/structured-outputs
"""

from __future__ import annotations

import copy
import re
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

Risk = Literal["read", "write", "destructive"]
RISK_TIERS: tuple[Risk, ...] = ("read", "write", "destructive")

# Internal names may be dotted (`erp.post_invoice`); OpenAI function names may not.
# api_name() sanitizes at the API boundary, so nobody has to rename their tools.
NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
INTERNAL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ToolManifest(BaseModel):
    """One tool as declared to the LLM and enforced by the executor."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(description="Tool name, dotted or not, e.g. erp.post_invoice")
    description: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        validation_alias=AliasChoices("parameters", "input_schema"),
        description="JSON Schema object; strict mode requires additionalProperties:false and every key in required.",
    )
    risk: Risk = "read"
    idempotent: bool = True
    requires_approval: bool = False
    side_effect_free: bool = True

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        if not INTERNAL_NAME_RE.match(v):
            raise ValueError(f"tool name {v!r} must match {INTERNAL_NAME_RE.pattern}")
        return v

    @model_validator(mode="after")
    def _strict_schema(self) -> ToolManifest:
        """OpenAI strict mode: object schema, additionalProperties:false, required == all keys."""
        p = self.parameters
        if p.get("type") != "object":
            raise ValueError(f"{self.name}: parameters.type must be 'object' (strict mode)")
        if p.get("additionalProperties") is not False:
            raise ValueError(f"{self.name}: parameters.additionalProperties must be False (strict mode)")
        props = p.get("properties")
        if not isinstance(props, dict):
            raise ValueError(f"{self.name}: parameters.properties must be an object")
        return self

    def api_name(self) -> str:
        """Function name sent to the API: OpenAI allows only [a-zA-Z0-9_-]."""
        return self.name.replace(".", "_")

    def strict_parameters(self) -> dict[str, Any]:
        """Strict-mode parameters: every key required, optional args become nullable.

        This is how OpenAI expresses an optional argument; the manifest keeps it optional.
        """
        schema = copy.deepcopy(self.parameters)
        props = schema.get("properties", {})
        required = set(schema.get("required") or [])
        for key, spec in props.items():
            if key in required:
                continue
            required.add(key)
            kind = spec.get("type")
            if isinstance(kind, str):
                spec["type"] = [kind, "null"]
        schema["required"] = sorted(required)
        return schema

    def openai_tool(self) -> dict[str, Any]:
        """Tool spec for chat.completions tools=[...] with strict tool-calling."""
        return {
            "type": "function",
            "function": {
                "name": self.api_name(),
                "description": self.description,
                "parameters": self.strict_parameters(),
                "strict": True,
            },
        }

    def tool_choice(self) -> dict[str, Any]:
        return {"type": "function", "function": {"name": self.api_name()}}

    def to_contract(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def validate_args(manifest: ToolManifest, args: dict[str, Any]) -> list[str]:
    """Return list of contract violations ([] == args ok). Trust boundary: never exec on violations.

    ponytail: covers object/string/number/integer/boolean/array/object + enum + required only,
    which is all strict-mode tool schemas use. Swap for `jsonschema` if a richer schema lands.
    """
    schema = manifest.parameters
    errors: list[str] = []
    if not isinstance(args, dict):
        return [f"{manifest.name}: args must be object, got {type(args).__name__}"]
    props: dict[str, Any] = schema.get("properties", {})
    for key in schema.get("required") or []:
        if key not in args:
            errors.append(f"{manifest.name}: missing required arg {key!r}")
    if schema.get("additionalProperties") is False:
        for key in args:
            if key not in props:
                errors.append(f"{manifest.name}: unexpected arg {key!r} (additionalProperties:false)")
    for key, value in args.items():
        spec = props.get(key)
        if not isinstance(spec, dict):
            continue
        expected = _JSON_TYPES.get(spec.get("type", ""))
        if expected is not None:
            if expected is not bool and isinstance(value, bool):
                errors.append(f"{manifest.name}: arg {key!r} must be {spec['type']}, got boolean")
            elif not isinstance(value, expected):
                errors.append(f"{manifest.name}: arg {key!r} must be {spec['type']}, got {type(value).__name__}")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{manifest.name}: arg {key!r} not in enum {spec['enum']}")
    return errors
