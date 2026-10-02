"""Tool registry: the single dispatch path.

Thin on purpose — `src.contracts.tools` (01, frozen) owns the ToolManifest shape, the risk
tiers and `validate_args`, so this module only loads manifests, maps names to callables and
gates destructive tools behind an explicit confirmation.

Tool ids match NAME_RE (`[a-zA-Z0-9_-]`), so they are underscore, not dotted. Phase 03's
policy files key on dotted ids (`erp.post`), so resolve() accepts either spelling.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from src.contracts.tools import RISK_TIERS, ToolManifest, validate_args

TOOLS: dict[str, tuple[str, str, str]] = {
    # tool id -> (module, manifest attr, handler attr); the handler takes one args dict.
    "files_list": ("src.tools.files_tool", "LIST_MANIFEST", "run_list"),
    "files_read": ("src.tools.files_tool", "MANIFEST", "run"),
    "invoice_parse": ("src.tools.invoice_tool", "MANIFEST", "run"),
    "invoice_find_latest": ("src.tools.invoice_tool", "FIND_MANIFEST", "run_find_latest"),
    "erp_post_invoice": ("src.tools.erp_tool", "MANIFEST", "run"),
    "browser_open": ("src.tools.browser_tool", "MANIFEST", "run"),
}
ALIASES = {"erp.post": "erp_post_invoice", "browser.fetch": "browser_open"}


def resolve(name: str) -> str:
    """Accept contract-legal `erp_post_invoice` or policy-style `erp.post`."""
    if name in TOOLS:
        return name
    dotted = name.replace(".", "_")
    for candidate in (ALIASES.get(name), dotted if dotted in TOOLS else None):
        if candidate:
            return candidate
    raise KeyError(f"unknown tool {name!r}; known: {sorted(TOOLS)}")


def _resolve(spec: str) -> Any:
    mod, _, attr = spec.partition(":")
    return getattr(importlib.import_module(mod), attr)


def _mod(name: str) -> Any:
    return importlib.import_module(TOOLS[name][0])


def manifest(name: str) -> ToolManifest:
    """Load a manifest and validate it against the frozen contract (raises if it drifts)."""
    _, man_attr, _ = TOOLS[resolve(name)]
    return ToolManifest.model_validate(dict(getattr(_mod(name), man_attr)))


def registry() -> dict[str, ToolManifest]:
    return {name: manifest(name) for name in TOOLS}


def callables() -> dict[str, Callable[..., Any]]:
    """Handlers as **kwargs callables, the shape 01's Executor expects (it calls fn(**args))."""
    return {n: _handler(_mod(n), TOOLS[n][2]) for n in TOOLS}


def _handler(mod: Any, attr: str) -> Callable[..., Any]:
    fn = getattr(mod, attr)
    return lambda **kw: fn(kw)


EMPTY: dict[str, Any] = {"string": "", "integer": 0, "number": 0, "boolean": False,
                         "array": [], "object": {}}


def defaults(name: str) -> dict[str, Any]:
    """Strict mode requires every property present *and* correctly typed, so fill optional
    args with type-correct empties: `{**defaults("invoice_find_latest"), "company": "X"}`."""
    props = manifest(name).parameters.get("properties", {})
    return {k: EMPTY.get(spec.get("type", "string")) for k, spec in props.items()}


def execute(name: str, args: dict[str, Any] | None = None, confirmed: bool = False) -> dict[str, Any]:
    """Dispatch by manifest only. Returns an evidence-friendly dict; never raises for tool errors."""
    args = args or {}
    try:
        name, man = resolve(name), manifest(name)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "tool": name, "error": f"manifest error: {e}"}
    env = {"ok": True, "tool": name, "risk": man.risk}
    if man.risk == "destructive" and not confirmed:
        return {**env, "ok": False, "status": "confirm_required",
                "error": f"{name} is destructive; re-run with confirmed=True after approval"}
    errors = validate_args(man, args)
    if errors:
        return {**env, "ok": False, "error": "manifest schema violation: " + "; ".join(errors)}
    try:
        return {**env, **(getattr(_mod(name), TOOLS[name][2])(args) or {})}
    except Exception as e:  # noqa: BLE001 - a tool failure is data, not a crash
        return {**env, "ok": False, "error": f"{type(e).__name__}: {e}"}


__all__ = ["EMPTY", "RISK_TIERS", "TOOLS", "callables", "defaults", "execute", "manifest",
           "registry", "resolve", "validate_args"]
