#!/usr/bin/env python3
"""Extract Gherkin .feature files from OpenSpec change specs.

OpenSpec already writes scenarios in Gherkin-flavored Markdown under
`openspec/changes/<change-id>/specs/<capability>/spec.md`:

    ### Requirement: <name>
    ...
    #### Scenario: <name>
    - **WHEN** <action>
    - **THEN** <outcome>

We parse those blocks and emit one `features/<capability>.feature` per capability,
merging scenarios from every change that touches that capability.

Why a build-time extraction instead of running OpenSpec markdown directly?
- behave / pytest-bdd need real .feature files for IDE + tooling support.
- Drift is prevented by re-running this on every CI / pre-commit invocation.

Usage:
    python scripts/extract_features.py              # emit features/*.feature
    python scripts/extract_features.py --check       # exit 1 if features are stale
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENSPEC_DIR = ROOT / "openspec" / "changes"
FEATURES_DIR = ROOT / "features"

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

REQ_HEADING_RE = re.compile(r"^###\s+Requirement:\s+(.+?)\s*$")
SCENARIO_HEADING_RE = re.compile(r"^####\s+Scenario:\s+(.+?)\s*$")
STEP_RE = re.compile(r"^\s*[-*]\s+\*\*(GIVEN|WHEN|THEN|AND)\*\*\s+(.+?)\s*$", re.IGNORECASE)


@dataclass
class Scenario:
    name: str
    steps: list[tuple[str, str]] = field(default_factory=list)  # (keyword, text)
    source_change: str = ""
    source_path: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Capability:
    name: str
    scenarios: list[Scenario] = field(default_factory=list)


def parse_spec_file(spec_path: Path, change_id: str) -> list[Scenario]:
    """Parse a single OpenSpec spec.md into a list of Scenario objects."""
    scenarios: list[Scenario] = []
    current: Scenario | None = None

    text = spec_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if SCENARIO_HEADING_RE.match(line):
            if current is not None and current.steps:
                scenarios.append(current)
            name = SCENARIO_HEADING_RE.match(line).group(1)  # type: ignore[union-attr]
            current = Scenario(
                name=name,
                source_change=change_id,
                source_path=str(spec_path.relative_to(ROOT)),
                tags=["fast"],  # default; override via convention below
            )
            continue
        if REQ_HEADING_RE.match(line):
            # Close out any pending scenario across requirement boundaries
            if current is not None and current.steps:
                scenarios.append(current)
                current = None
            continue
        m = STEP_RE.match(line)
        if m and current is not None:
            keyword = m.group(1).title()
            current.steps.append((keyword, m.group(2)))

    if current is not None and current.steps:
        scenarios.append(current)
    return scenarios


def collect_capabilities() -> dict[str, Capability]:
    """Walk openspec/changes/*/specs/<cap>/spec.md and group by capability."""
    caps: dict[str, Capability] = {}
    if not OPENSPEC_DIR.exists():
        return caps

    for change_dir in sorted(OPENSPEC_DIR.iterdir()):
        if not change_dir.is_dir() or change_dir.name == "archive":
            continue
        specs_dir = change_dir / "specs"
        if not specs_dir.is_dir():
            continue
        for cap_dir in sorted(specs_dir.iterdir()):
            if not cap_dir.is_dir():
                continue
            spec_file = cap_dir / "spec.md"
            if not spec_file.exists():
                continue
            scenarios = parse_spec_file(spec_file, change_dir.name)
            if not scenarios:
                continue
            cap = caps.setdefault(cap_dir.name, Capability(name=cap_dir.name))
            cap.scenarios.extend(scenarios)
    return caps


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

HEADER = """# AUTO-GENERATED from openspec/changes/**/specs/. DO NOT EDIT BY HAND.
# Regenerate with:  python scripts/extract_features.py
#
# Step definitions live in features/steps/. If a scenario is unimplemented,
# behave emits stub code you can paste into a steps file.
"""


def render_capability(cap: Capability) -> str:
    out: list[str] = [HEADER, f"Feature: {cap.name}", ""]
    by_change: dict[str, list[Scenario]] = defaultdict(list)
    for s in cap.scenarios:
        by_change[s.source_change].append(s)

    for change_id in sorted(by_change):
        out.append(f"  # source: {change_id}")
        for s in by_change[change_id]:
            tag_line = " ".join(f"@{t}" for t in s.tags)
            if tag_line:
                out.append(f"  {tag_line}")
            out.append(f"  Scenario: {s.name}")
            first = True
            for kw, text in s.steps:
                # behave wants Given/When/Then/And. Promote first GIVEN/WHEN/THEN; the
                # rest become And/But to keep things readable.
                if first:
                    out.append(f"    {kw} {text}")
                    first = False
                else:
                    out.append(f"    And {text}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if features/ would change (CI mode)",
    )
    args = parser.parse_args()

    FEATURES_DIR.mkdir(exist_ok=True)
    caps = collect_capabilities()

    if not caps:
        print("[extract-features] no scenarios found under openspec/changes/", file=sys.stderr)
        return 0

    drift = False
    seen: set[str] = set()
    for name, cap in sorted(caps.items()):
        target = FEATURES_DIR / f"{name}.feature"
        seen.add(target.name)
        rendered = render_capability(cap)
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        if existing == rendered:
            continue
        if args.check:
            drift = True
            print(f"[extract-features] STALE: {target.relative_to(ROOT)}", file=sys.stderr)
        else:
            target.write_text(rendered, encoding="utf-8")
            print(f"[extract-features] wrote {target.relative_to(ROOT)}")

    # Optionally warn about feature files with no matching capability (manual ones)
    for existing in sorted(FEATURES_DIR.glob("*.feature")):
        if existing.name not in seen:
            print(
                f"[extract-features] note: {existing.relative_to(ROOT)} has no matching openspec capability",
                file=sys.stderr,
            )

    if args.check and drift:
        print(
            "\n[extract-features] features/ is out of sync with OpenSpec. "
            "Run: python scripts/extract_features.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
