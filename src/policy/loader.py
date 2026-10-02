"""Load + validate the versioned YAML context, and apply PII redaction.

Deny-by-default: anything missing, mistyped or out of allowlist is a hard error
here rather than a silent default at exec time. Risk tiers come from the frozen
contract (src/contracts/tools.py) so this file never re-declares them.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from src.contracts.tools import RISK_TIERS

ROOT = Path(__file__).resolve().parents[2]
CONTEXT_DIR = ROOT / "context"
FILES = ("company.yaml", "policies.yaml", "tools.yaml")


class PolicyError(ValueError):
    """Context file missing, malformed, or fails validation."""


def _need(doc: dict[str, Any], path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise PolicyError(f"missing required key: {path}")
        cur = cur[part]
    return cur


def _num(doc: dict[str, Any], path: str) -> float:
    value = _need(doc, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{path} must be a number, got {value!r}")
    if value < 0:
        raise PolicyError(f"{path} must be >= 0, got {value}")
    return float(value)


def _stamp(doc: dict[str, Any], name: str) -> None:
    if not isinstance(_need(doc, "version"), int):
        raise PolicyError(f"{name}: version must be an int")
    try:
        dt.date.fromisoformat(str(_need(doc, "updated")))
    except ValueError as exc:
        raise PolicyError(f"{name}: updated must be YYYY-MM-DD ({exc})") from exc


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PolicyError(f"missing context file: {path}")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise PolicyError(f"{path}: expected a YAML mapping")
    return doc


def _validate_company(doc: dict[str, Any]) -> None:
    _stamp(doc, "company.yaml")
    if not str(_need(doc, "company.id")).strip():
        raise PolicyError("company.id must be non-empty")
    _need(doc, "erp.endpoint")
    ceiling = _num(doc, "approval.amount_ceiling")
    queue = str(_need(doc, "approval.queue"))
    # The queue path is written to by the gate: keep it inside the repo, never absolute.
    if Path(queue).is_absolute() or ".." in Path(queue).parts:
        raise PolicyError(f"approval.queue must be a relative path inside the repo, got {queue!r}")
    if ceiling <= 0:
        raise PolicyError(f"approval.amount_ceiling must be > 0, got {ceiling}")


def _validate_policies(doc: dict[str, Any]) -> list[dict[str, str]]:
    _stamp(doc, "policies.yaml")
    domains = _need(doc, "allowlist_domains")
    if not isinstance(domains, list) or not domains:
        raise PolicyError("allowlist_domains must be a non-empty list")
    for domain in domains:
        if not isinstance(domain, str) or domain != domain.lower().strip() or not domain:
            raise PolicyError(f"allowlist domain must be lowercase text, got {domain!r}")
    _num(doc, "max_amount_auto_post")
    rules = _need(doc, "pii_redact")
    if not isinstance(rules, list):
        raise PolicyError("pii_redact must be a list")
    for rule in rules:
        name, pattern = _need(rule, "name"), _need(rule, "pattern")
        try:
            re.compile(str(pattern))
        except re.error as exc:
            raise PolicyError(f"pii_redact {name}: bad regex ({exc})") from exc
    return rules


def _validate_tools(doc: dict[str, Any]) -> None:
    _stamp(doc, "tools.yaml")
    tools = _need(doc, "tools")
    if not isinstance(tools, dict) or not tools:
        raise PolicyError("tools must be a non-empty mapping")
    for name, spec in tools.items():
        risk = _need(spec, "risk")
        if risk not in RISK_TIERS:
            raise PolicyError(f"tool {name}: risk {risk!r} not in contract RISK_TIERS {RISK_TIERS}")


def redact(text: str, rules: list[dict[str, str]]) -> tuple[str, list[str]]:
    """Replace every PII match with [REDACTED:<name>]. Returns (text, names hit)."""
    hits: list[str] = []
    for rule in rules:
        pattern = re.compile(str(rule["pattern"]), re.I)
        if pattern.search(text):
            hits.append(str(rule["name"]))
        text = pattern.sub(f"[REDACTED:{rule['name']}]", text)
    return text, hits


def load_context(context_dir: Path | str | None = None) -> dict[str, Any]:
    """Return {company, policies, tools, redactor} after validating all three files."""
    base = Path(context_dir or CONTEXT_DIR)
    company = _read(base / "company.yaml")
    policies = _read(base / "policies.yaml")
    tools = _read(base / "tools.yaml")
    _validate_company(company)
    rules = _validate_policies(policies)
    _validate_tools(tools)
    redactor: Callable[[str], tuple[str, list[str]]] = lambda text: redact(text, rules)
    return {"company": company, "policies": policies, "tools": tools, "redactor": redactor}