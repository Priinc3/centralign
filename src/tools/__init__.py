"""Tools: allowlisted browser, sandboxed files, invoice parser, sim-ERP client.

Entry point for the runtime (01's Executor wants both halves):
    from src.tools import registry, callables
    Executor(ledger, run_id, registry(), callables())
Standalone dispatch (tests, CLI, demo):
    from src.tools import execute, defaults
    execute("invoice_find_latest", {**defaults("invoice_find_latest"), "company": "Company X"})
"""

from .manifest_registry import (RISK_TIERS, TOOLS, callables, defaults, execute, manifest,
                                registry, resolve, validate_args)

__all__ = ["RISK_TIERS", "TOOLS", "callables", "defaults", "execute", "manifest", "registry",
           "resolve", "validate_args"]
