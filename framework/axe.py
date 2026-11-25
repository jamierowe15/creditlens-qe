"""Accessibility scanning with axe-core (the engine behind most a11y tools, e.g. Lighthouse).
axe-core is installed by `npm install` into node_modules; we inject it into the page and run it."""
from __future__ import annotations

import json
import re

from config.settings import REPORTS, ROOT

AXE_JS = ROOT / "node_modules" / "axe-core" / "axe.min.js"
WCAG_AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
BLOCKING = {"serious", "critical"}

# Known, logged defects (docs/DEFECTS.md). They are excluded from the per-screen gate so new
# problems still fail the build, and each one has its own strict-xfail test that turns red
# (XPASS) the day the fix lands, reminding us to delete the entry.
KNOWN_ISSUES = {
    ("label-content-name-mismatch", ".brand"): "DEF-002",
}


def scan(page, name: str, include: str | None = None) -> dict:
    if not AXE_JS.exists():
        raise RuntimeError("axe-core missing: run `npm install` in the creditlens-qe folder")
    page.add_script_tag(path=str(AXE_JS))
    context = include or "document"
    result = page.evaluate(
        "async ([ctx, tags]) => await axe.run(ctx === 'document' ? document : ctx, {runOnly: {type: 'tag', values: tags}})",
        [context, WCAG_AA])
    out = REPORTS / "a11y"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{re.sub(r'[^a-z0-9]+', '-', name.lower())}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def _known(rule: str, node: dict) -> bool:
    return (rule, " ".join(node["target"])) in KNOWN_ISSUES


def blocking(result: dict, include_known: bool = False) -> list[dict]:
    out = []
    for v in result["violations"]:
        if v["impact"] not in BLOCKING:
            continue
        nodes = v["nodes"] if include_known else [n for n in v["nodes"] if not _known(v["id"], n)]
        if nodes:
            out.append({**v, "nodes": nodes})
    return out


def describe(violations: list[dict]) -> str:
    lines = []
    for v in violations:
        targets = ", ".join(" ".join(n["target"]) for n in v["nodes"][:4])
        lines.append(f"[{v['impact']}] {v['id']}: {v['help']} ({len(v['nodes'])} element(s): {targets})\n    {v['helpUrl']}")
    return "\n".join(lines)
