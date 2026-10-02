"""Planner: LLM plan (strict tool-calling) with an offline heuristic fallback.

The LLM never executes anything; it may only emit a Plan DAG whose steps name
tools from a manifest and pass args that satisfy the manifest JSON Schema.
Refs: https://developers.openai.com/api/docs/guides/function-calling
      https://developers.openai.com/api/docs/guides/structured-outputs
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..contracts.tools import RISK_TIERS, ToolManifest, validate_args

RISK_ORDER = list(RISK_TIERS)

PLAN_TOOL_NAME = "submit_plan"
_MODEL = os.environ.get("CENTRALIGN_MODEL", "gpt-4.1-mini")


class PlannerError(RuntimeError):
    pass


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Short unique id within the plan, e.g. s1")
    tool: str = Field(description="Tool name exactly as it appears in the manifest; nothing else is dispatchable")
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime-populated. The LLM submits it empty (strict mode cannot express a free-form map); "
        "the planner fills it from one forced tool call against the step's own manifest.",
    )
    depends_on: list[str] = Field(default_factory=list, description="Step ids that must have succeeded first")
    intent: str = Field(description="Why this step exists, one line")
    success_criterion: str = Field(description="Observable claim the Verify stage can check")


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    goal: str
    steps: list[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_dag(self) -> Plan:
        ids = [s.id for s in self.steps]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate step ids: {sorted(dupes)}")
        known = set(ids)
        for s in self.steps:
            missing = [d for d in s.depends_on if d not in known]
            if missing:
                raise ValueError(f"step {s.id} depends on unknown step(s) {missing}")
            if s.id in s.depends_on:
                raise ValueError(f"step {s.id} depends on itself")
        self.topo_order()  # raises on cycles
        return self

    def topo_order(self) -> list[Step]:
        """Kahn topological order; raises PlannerError on a cycle."""
        by_id = {s.id: s for s in self.steps}
        indeg = {s.id: len(set(s.depends_on)) for s in self.steps}
        ready = sorted(s.id for s in self.steps if indeg[s.id] == 0)
        order: list[Step] = []
        while ready:
            cur = ready.pop(0)
            order.append(by_id[cur])
            for sid, step in by_id.items():
                if cur in step.depends_on:
                    indeg[sid] -= 1
                    if indeg[sid] == 0:
                        ready.append(sid)
                        ready.sort()
        if len(order) != len(self.steps):
            raise PlannerError(f"plan has a dependency cycle: {[s.id for s in self.steps if s not in order]}")
        return order

    def to_contract(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ---------------------------------------------------------------- strict schema
def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """model_json_schema() -> OpenAI strict schema (additionalProperties:false, all keys required)."""
    schema = model.model_json_schema()

    def fix(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                props = node.setdefault("properties", {})
                node["additionalProperties"] = False
                node["required"] = sorted(props)
                for v in list(node.values()):
                    fix(v)
            elif "anyOf" in node:
                for v in node["anyOf"]:
                    fix(v)
            else:
                for v in node.values():
                    fix(v)
        elif isinstance(node, list):
            for v in node:
                fix(v)

    fix(schema)
    return schema


# ---------------------------------------------------------------- offline path
_VALUE_HINTS: dict[str, str] = {
    "url": "url",
    "query": "text",
    "text": "text",
    "note": "text",
    "message": "text",
    "message_body": "text",
    "body": "text",
    "company": "company",
    "company_name": "company",
    "vendor": "company",
    "path": "path",
    "file": "path",
    "path_or_url": "path",
}
_URL_RE = re.compile(r"https?://\S+")
_MONEY_RE = re.compile(r"(?:[$€£]\s?)?(\d[\d,]*(?:\.\d+)?)")
_QUOTED_RE = re.compile(r"[\"'“]([^\"'”]{2,})[\"'”]")
# Stops at the first clause boundary, so "from Company X and post it to the ERP" mines "Company X"
# and not the whole task tail (the greedy version filled every arg with the leftovers).
_AFTER_RE = re.compile(
    r"\b(?:for|of|from|about)\s+(?:the\s+)?([^,;]+?)(?=\s+(?:and|then|but|so)\b|[,;.]|$)",
    re.IGNORECASE,
)
_COMPANY_RE = re.compile(r"\bCompany\s+[A-Za-z0-9]+")


_STOPWORDS = frozenset(
    """a an and are as at be by for from in into is it its of on or that the to when with within
    under over each every all any this these those if then than so such not no""".split()
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def _company(task: str) -> str:
    """The company the task names: a quoted name, else `Company X`. Empty when it names none.

    Deliberately narrow. Mining "the company" out of an arbitrary tail is how the offline planner
    used to post one company another's invoice.
    """
    quoted = _QUOTED_RE.search(task)
    if quoted:
        return quoted.group(1).strip()
    named = _COMPANY_RE.search(task)
    return named.group(0) if named else ""


def _tokens_from_task(task: str) -> dict[str, Any]:
    """Values a heuristic step can use, mined once from the task text."""
    url = _URL_RE.search(task)
    money = _MONEY_RE.search(task)
    after = _AFTER_RE.search(task)
    tail = after.group(1).strip().rstrip(".") if after else task
    return {
        "url": url.group(0) if url else "",
        "text": tail,
        "company": _company(task) or tail,
        "path": url.group(0) if url else "",
        "number": float(money.group(1).replace(",", "")) if money else 0.0,
        "integer": int(float(money.group(1).replace(",", ""))) if money else 0,
        "boolean": True,
        "array": [],
        "object": {},
    }


def fill_args(manifest: ToolManifest, task: str) -> dict[str, Any]:
    """Fill every required arg of a manifest from the task text. Deterministic, no LLM."""
    values = _tokens_from_task(task)
    args: dict[str, Any] = {}
    props: dict[str, Any] = manifest.parameters.get("properties", {})
    for key in manifest.parameters.get("required") or []:
        spec = props.get(key) or {}
        if "default" in spec:
            args[key] = spec["default"]
        elif "enum" in spec and spec["enum"]:
            args[key] = spec["enum"][0]
        elif "const" in spec:
            args[key] = spec["const"]
        elif key in ("company", "company_name"):
            company = _company(task)
            if company:
                args[key] = company
            # no company named -> omit the arg, so the step is skipped with a reason, not posted blind
        else:
            hint = _VALUE_HINTS.get(key, spec.get("type", "string"))
            args[key] = values.get(hint, values.get("text"))
    return args


# ------------------------------------------------------------- templated intake flow
# The one multi-step flow worth templating offline: find the invoice, then post what was found.
# Every post arg is a {{step.field}} reference into the find result (resolved by the executor
# before the schema check), so no payload value is invented from the task text.
_INTAKE_FIND = "invoice_find_latest"
_INTAKE_POST = "erp_post_invoice"
_INTAKE_DIR = "seed/invoices"  # tool paths are relative to the data/ sandbox
_INTAKE_PATTERN = "*.pdf"
_INTAKE_WRITE_RE = re.compile(r"\b(post|enter|upload|submit)\b|\berp\b", re.IGNORECASE)
_INTAKE_POST_ARGS: dict[str, Any] = {
    "action": "post",
    "vendor": "{{s1.latest.vendor}}",
    "company": "{{s1.latest.company}}",
    "amount": "{{s1.latest.amount}}",
    "invoice_number": "{{s1.latest.invoice_number}}",
    "currency": "{{s1.latest.currency}}",
    "due_date": "{{s1.latest.due}}",
    "source_file": "{{s1.latest.file}}",
    "base_url": "",  # tool default: $ERP_URL
    "idempotency_key": "",  # tool default: hash of the payload
}


def intake_plan(task: str, manifests: Mapping[str, ToolManifest]) -> Plan | None:
    """`find latest invoice for <company>` -> `post it to the ERP`, or None if the task is not that."""
    if _INTAKE_FIND not in manifests or _INTAKE_POST not in manifests:
        return None
    if "invoice" not in _tokens(task) or not _INTAKE_WRITE_RE.search(task):
        return None
    company = _company(task)  # omitted, never guessed, when the task names no company
    find_args = {k: v for k, v in (("company", company), ("dir", _INTAKE_DIR),
                                    ("pattern", _INTAKE_PATTERN)) if v}
    return Plan(
        goal=task,
        steps=[
            Step(
                id="s1",
                tool=_INTAKE_FIND,
                args=find_args,
                intent="find the latest invoice for the company",
                success_criterion="a parseable invoice for that company comes back",
            ),
            Step(
                id="s2",
                tool=_INTAKE_POST,
                args=dict(_INTAKE_POST_ARGS),
                depends_on=["s1"],
                intent="post the invoice the find step returned to the ERP",
                success_criterion="the ERP accepts the posted invoice",
            ),
        ],
    )


def heuristic_plan(task: str, manifests: Mapping[str, ToolManifest]) -> Plan:
    """Offline planner: the templated intake flow, else keyword overlap with read-before-write order.

    ponytail: template for the reference flow, keyword overlap + name-keyed arg filling for
    everything else. A task outside that shape needs the LLM path (Phase 04 adds replan).
    """
    if not task.strip():
        return Plan(goal=task)  # nothing was asked, so nothing is planned (verify blocks the run)
    template = intake_plan(task, manifests)
    if template is not None:
        return template

    task_tokens = _tokens(task)
    ranked: list[tuple[int, int, str]] = []
    for name, m in manifests.items():
        name_tokens = set(re.split(r"[._\-\s]+", name.lower()))
        overlap = len(name_tokens & task_tokens)
        desc_tokens = _tokens(m.description) & task_tokens
        ranked.append((overlap, len(desc_tokens), name))
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))

    # name overlap wins; a description that shares 2+ content words is enough on its own
    chosen: list[str] = [r[2] for r in ranked if r[0] > 0 or r[1] >= 2]
    fallback = not chosen
    if fallback:
        # Nothing in the task names a tool: do the lowest-risk thing available, and say so in
        # the evidence rather than pretending the task asked for it.
        by_risk = sorted(manifests.values(), key=lambda m: RISK_ORDER.index(m.risk))
        if by_risk:
            chosen.append(by_risk[0].name)
    chosen = chosen[:4]
    # reads before writes: a write step can only consume what a read step produced. Stable sort,
    # so ranking decides within a risk tier.
    chosen.sort(key=lambda n: RISK_ORDER.index(manifests[n].risk))

    steps: list[Step] = []
    prev: str | None = None
    for i, name in enumerate(chosen, start=1):
        m = manifests[name]
        sid = f"s{i}"
        steps.append(
            Step(
                id=sid,
                tool=name,
                args=fill_args(m, task),
                depends_on=[prev] if prev else [],
                intent=("heuristic fallback: no tool matched the task, running the lowest-risk tool"
                        if fallback else f"heuristic: {name} matches task"),
                success_criterion=f"{name} returns without error",
            )
        )
        prev = sid
    return Plan(goal=task, steps=steps)


# ---------------------------------------------------------------- LLM path
_SYSTEM = (
    "You are the planner of a contract-bound AI operator. Plan only; never execute. "
    "For the plan, emit exactly one tool call: submit_plan, using only tool names present in the manifest, "
    "the fewest steps that accomplish the goal, and depends_on forming a DAG. Leave every step's args empty. "
    "When asked for one step's arguments, emit exactly one tool call to that step's tool with concrete values."
)


def plan_schema_prompt(manifests: Mapping[str, ToolManifest]) -> str:
    tools = [m.to_contract() for m in manifests.values()]
    return "Available tool manifests (JSON):\n" + repr(tools)


def _plan_submit_tool() -> dict[str, Any]:
    """submit_plan with strict:true. `args` is pinned to {} — see Step.args."""
    schema = strict_schema(Plan)
    step_schema = schema.get("$defs", {}).get("Step") or schema["properties"]["steps"]["items"]
    step_schema["properties"]["args"] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
        "description": "Leave empty. The planner fills arguments from the tool manifest.",
    }
    return {
        "type": "function",
        "function": {
            "name": PLAN_TOOL_NAME,
            "description": "Return the plan DAG for the operator to execute.",
            "parameters": schema,
            "strict": True,
        },
    }


def _step_args(
    client: Any,
    model: str,
    manifest: ToolManifest,
    *,
    goal: str,
    intent: str,
    upstream: dict[str, Any],
) -> dict[str, Any]:
    """One forced strict tool call against the step's own manifest = that step's arguments.

    Strict mode already constrains key names/types; validate_args is the runtime re-check
    (no silent mock autonomy: an invalid arg set is a PlannerError, never a guess).
    """
    ctx = f"Goal: {goal}\nStep intent: {intent}\n"
    if upstream:
        ctx += "Results of earlier steps (use these values verbatim):\n" + repr(upstream) + "\n"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": ctx},
        ],
        tools=[manifest.openai_tool()],
        tool_choice=manifest.tool_choice(),
        parallel_tool_calls=False,
    )
    calls = resp.choices[0].message.tool_calls or []
    if not calls:
        raise PlannerError(f"no tool call for step args of {manifest.name}")
    args = json.loads(calls[0].function.arguments or "{}")
    errors = validate_args(manifest, args)
    if errors:
        raise PlannerError(f"step args violate {manifest.name} schema: {errors}")
    return args


def llm_plan(
    task: str,
    manifests: Mapping[str, ToolManifest],
    *,
    client: Any | None = None,
    model: str = _MODEL,
    memory: str = "",
) -> Plan:
    """Two strict tool-calling phases: submit_plan, then one forced call per step for args.

    The client is the multi-key router (`src/llm/router.py`): every key in the environment is
    used round-robin, and a 429/5xx cools one key and fails over to the next. It is a drop-in
    for an OpenAI client, and it replaces the `model=` below with the endpoint's own model id
    — a GPT model name cannot call Gemini.

    Raises PlannerError on any contract violation; the caller falls back to the heuristic.
    """
    from ..llm.router import router  # noqa: PLC0415 - keeps the CLI banner instant

    client = client if client is not None else router()
    submit = _plan_submit_tool()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Goal: {task}\n\n{plan_schema_prompt(manifests)}\n\nCompany memory:\n{memory or '(none)'}"},
        ],
        tools=[submit],
        tool_choice={"type": "function", "function": {"name": PLAN_TOOL_NAME}},
        parallel_tool_calls=False,
    )
    calls = resp.choices[0].message.tool_calls or []
    if not calls:
        raise PlannerError("LLM returned no tool call")
    try:
        plan = Plan.model_validate_json(calls[0].function.arguments)
    except Exception as exc:
        raise PlannerError(f"LLM plan failed contract validation: {exc}") from exc

    # The API only sees sanitized names (erp_post_invoice); map back to the real manifest name.
    by_api = {m.api_name(): name for name, m in manifests.items()}
    for step in plan.steps:
        step.tool = by_api.get(step.tool, step.tool)

    unknown = sorted({s.tool for s in plan.steps} - set(manifests))
    if unknown:
        raise PlannerError(f"LLM invented tools not in the manifest: {unknown}")

    results: dict[str, Any] = {}
    for step in plan.topo_order():
        upstream = {d: results.get(d) for d in step.depends_on}
        step.args = _step_args(
            client, model, manifests[step.tool], goal=task, intent=step.intent, upstream=upstream
        )
        results[step.id] = step.args
    return plan


def make_plan(
    task: str,
    manifests: Mapping[str, ToolManifest],
    *,
    offline: bool = False,
    client: Any | None = None,
    memory: str = "",
) -> tuple[Plan, str]:
    """Return (plan, source) where source is 'llm' | 'heuristic'. Never raises for the demo path."""
    if offline:
        return heuristic_plan(task, manifests), "heuristic"
    try:
        return llm_plan(task, manifests, client=client, memory=memory), "llm"
    except Exception as exc:  # noqa: BLE001 - any LLM/transport failure degrades to offline
        return heuristic_plan(task, manifests), f"heuristic(fallback: {type(exc).__name__}: {exc})"


def describe(plan: Plan) -> str:
    return " -> ".join(f"{s.id}:{s.tool}" for s in plan.topo_order()) or "(no steps)"
