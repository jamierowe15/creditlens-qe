"""Contract testing: every response must match a JSON Schema in /schemas.
If a developer renames or removes a field, these tests fail before the Angular app breaks."""
import json
from functools import lru_cache

from jsonschema import Draft202012Validator

from config.settings import ROOT


@lru_cache
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))
    registry_dir = ROOT / "schemas"
    # Resolve "$ref": "reason.schema.json" style references from the same folder.
    from referencing import Registry, Resource
    resources = []
    for f in registry_dir.glob("*.schema.json"):
        resources.append((f.name, Resource.from_contents(json.loads(f.read_text(encoding="utf-8")))))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources))


def assert_matches(name: str, payload) -> None:
    errors = sorted(_validator(name).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        lines = [f"  at {'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:10]]
        raise AssertionError(f"Response does not match contract '{name}':\n" + "\n".join(lines))
