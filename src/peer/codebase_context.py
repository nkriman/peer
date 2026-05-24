"""Slice 2 codebase-context gathering.

For a given PR's diff, extracts:
- modified_symbols: tree-sitter-extracted function/method/class definitions
  whose source spans overlap with diff hunks
- call_sites: where each modified symbol is referenced elsewhere in the repo
  (via ast-grep, with a ripgrep->Python fallback chain)
- related_tests: test files discovered by path convention
- untested_files: modified source files with no matching test
- unsupported_files / parse_failures: bookkeeping for graceful degradation

Per Decision 14: missing optional deps degrade gracefully (empty
CodebaseContext + WARNING) rather than blocking the review.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

import tiktoken

from .exceptions import CodebaseContextTooLarge
from .types import CallSite, CodebaseContext, Context, Symbol, SymbolKind, TestFile

logger = logging.getLogger(__name__)

DEFAULT_TEST_CONVENTIONS = [
    "tests/test_{stem}.py",
    "src/test_{stem}.py",
    "tests/{stem}_test.py",
    "test_{stem}.py",
]

CACHE_DIR = Path.home() / ".cache" / "peer" / "repos"
_ENCODER: tiktoken.Encoding | None = None


# -- Optional dependency detection (Decision 14) -----------------------------


def _have_tree_sitter() -> bool:
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_python  # noqa: F401

        return True
    except Exception as e:
        logger.error(
            "tree-sitter not importable (%s). Codebase context will be empty. "
            "Install via: pip install tree-sitter tree-sitter-python",
            e,
        )
        return False


def _have_ast_grep() -> bool:
    try:
        from ast_grep_py import SgRoot  # noqa: F401

        return True
    except Exception:
        return False


def _have_ripgrep() -> bool:
    return shutil.which("rg") is not None


# -- Repo checkout helper ----------------------------------------------------


def _ensure_repo_checkout(owner: str, repo: str, pr_number: int, sha: str) -> Path | None:
    """Clone (or update) the repo to ~/.cache/peer/repos and check out
    the PR head. Returns the checkout path, or None on failure."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    repo_path = CACHE_DIR / f"{owner}__{repo}"
    if not repo_path.exists():
        logger.info("Cloning %s/%s to %s (first use)", owner, repo, repo_path)
        result = subprocess.run(
            [
                "gh",
                "repo",
                "clone",
                f"{owner}/{repo}",
                str(repo_path),
                "--",
                "--depth=100",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.warning("Clone failed for %s/%s: %s", owner, repo, result.stderr.strip())
            return None

    # Try to check out the SHA directly first (cheap if already fetched)
    co = subprocess.run(
        ["git", "-C", str(repo_path), "checkout", "-q", sha],
        capture_output=True,
        text=True,
        check=False,
    )
    if co.returncode == 0:
        return repo_path

    # SHA not local — fetch the PR ref (handles fork PRs cleanly)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "fetch",
            "origin",
            f"pull/{pr_number}/head",
            "--depth=100",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    co = subprocess.run(
        ["git", "-C", str(repo_path), "checkout", "-q", sha],
        capture_output=True,
        text=True,
        check=False,
    )
    if co.returncode != 0:
        logger.warning(
            "Could not check out %s in %s: %s",
            sha,
            repo_path,
            co.stderr.strip(),
        )
        return None
    return repo_path


# -- Symbol extraction -------------------------------------------------------


def _extract_signature(node, source: bytes) -> str:
    """First line of the definition (up to the colon)."""
    text = source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    first_line = text.split("\n", 1)[0].strip()
    if not first_line.endswith(":") and ":" in first_line:
        first_line = first_line.split(":", 1)[0].strip() + ":"
    return first_line


def _walk_symbols(node, source: bytes, path: str, enclosing: str | None) -> list[Symbol]:
    """Recursively extract function/method/class definitions."""
    out: list[Symbol] = []
    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            name = source[name_node.start_byte : name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
            kind: SymbolKind = "method" if enclosing else "function"
            out.append(
                Symbol(
                    name=name,
                    path=path,
                    kind=kind,
                    signature=_extract_signature(node, source),
                    enclosing_qualifier=enclosing,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
        # Recurse for nested defs (rare but real)
        for child in node.children:
            out.extend(_walk_symbols(child, source, path, enclosing))
        return out
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        cls_name = None
        if name_node is not None:
            cls_name = source[name_node.start_byte : name_node.end_byte].decode(
                "utf-8", errors="replace"
            )
            out.append(
                Symbol(
                    name=cls_name,
                    path=path,
                    kind="class",
                    signature=_extract_signature(node, source),
                    enclosing_qualifier=enclosing,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                )
            )
        new_enclosing = (
            f"{enclosing}.{cls_name}" if (enclosing and cls_name) else cls_name
        ) or enclosing
        for child in node.children:
            out.extend(_walk_symbols(child, source, path, new_enclosing))
        return out
    for child in node.children:
        out.extend(_walk_symbols(child, source, path, enclosing))
    return out


def _extract_modified_symbols(repo_path: Path, ctx: Context, cc: CodebaseContext) -> None:
    """Populate cc.modified_symbols / unsupported_files / parse_failures."""
    import tree_sitter_python
    from tree_sitter import Language, Parser

    lang = Language(tree_sitter_python.language())
    parser = Parser(lang)

    by_path: dict[str, list[tuple[int, int]]] = {}
    for h in ctx.hunks:
        rng = (h.new_start, h.new_start + max(h.new_lines - 1, 0))
        by_path.setdefault(h.path, []).append(rng)

    for path, ranges in by_path.items():
        if not path.endswith(".py"):
            cc.unsupported_files.append(path)
            continue
        full = repo_path / path
        if not full.exists():
            # File deleted in PR — skip for now (deferred per spec)
            continue
        try:
            source = full.read_bytes()
            all_symbols = _walk_symbols(parser.parse(source).root_node, source, path, None)
        except Exception as e:
            logger.warning("Parse failure on %s: %s", path, e)
            cc.parse_failures.append(path)
            continue
        for sym in all_symbols:
            for r_start, r_end in ranges:
                if sym.start_line <= r_end and sym.end_line >= r_start:
                    cc.modified_symbols.append(sym)
                    break


# -- Call-site lookup --------------------------------------------------------


def _snippet(source_lines: list[str], line: int, n: int = 3) -> str:
    start = max(0, line - 1 - n)
    end = min(len(source_lines), line + n)
    return "\n".join(source_lines[start:end])


def _pattern_for(symbol: Symbol) -> str | None:
    if symbol.kind in ("function", "class"):
        return f"{symbol.name}($$$ARGS)"
    if symbol.kind == "method":
        return f"$RECV.{symbol.name}($$$ARGS)"
    return None


def _find_call_sites_ast_grep(
    repo_path: Path, symbols: list[Symbol], max_per_symbol: int
) -> tuple[list[CallSite], dict[str, int]]:
    from ast_grep_py import SgRoot

    out: list[CallSite] = []
    truncations: dict[str, int] = {}
    seen_per_symbol: dict[str, int] = {}

    # Files to skip (self-defs, no point flagging definition as a call site)
    self_paths = {s.path for s in symbols}

    patterns: list[tuple[Symbol, str]] = []
    for sym in symbols:
        pat = _pattern_for(sym)
        if pat:
            patterns.append((sym, pat))

    if not patterns:
        return out, truncations

    for py_file in repo_path.rglob("*.py"):
        rel = str(py_file.relative_to(repo_path))
        # Skip self-defining files
        if rel in self_paths:
            continue
        try:
            source = py_file.read_text(errors="ignore")
        except Exception:
            continue
        if not source:
            continue
        # Quick reject: at least one symbol's name must appear textually
        if not any(sym.name in source for sym, _ in patterns):
            continue
        try:
            root = SgRoot(source, "python")
        except Exception:
            continue
        source_lines = source.splitlines()
        for sym, pat in patterns:
            if seen_per_symbol.get(sym.name, 0) >= max_per_symbol:
                continue
            if sym.name not in source:
                continue
            try:
                matches = root.root().find_all(pattern=pat)
            except Exception:
                continue
            for m in matches:
                rng = m.range()
                line = rng.start.line + 1
                out.append(
                    CallSite(
                        symbol_name=sym.name,
                        path=rel,
                        line=line,
                        snippet=_snippet(source_lines, line, n=3),
                    )
                )
                seen_per_symbol[sym.name] = seen_per_symbol.get(sym.name, 0) + 1
                if seen_per_symbol[sym.name] >= max_per_symbol:
                    truncations[f"call_sites_{sym.name}"] = 1
                    break
    return out, truncations


# -- Test discovery ----------------------------------------------------------


def _source_to_module(source_rel: str) -> str | None:
    """Convert 'pydantic/_internal/_generate_schema.py' -> 'pydantic._internal._generate_schema'."""
    p = Path(source_rel)
    if p.suffix != ".py":
        return None
    parts = list(p.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    if not parts:
        return None
    return ".".join(parts)


def _find_tests_by_import(repo_path: Path, source_rel: str, max_results: int) -> list[str]:
    """Find test files in the repo that import from the source module."""
    module = _source_to_module(source_rel)
    if not module:
        return []
    if not _have_ripgrep():
        return []
    # Determine test roots
    test_roots: list[Path] = []
    for cand in ("tests", "test"):
        p = repo_path / cand
        if p.is_dir():
            test_roots.append(p)
    if not test_roots:
        # Fall back to whole-repo scan
        test_roots = [repo_path]

    patterns = [
        f"from {re.escape(module)} import",
        f"from {re.escape(module)}.",
        f"import {re.escape(module)}\\b",
    ]
    candidates: set[str] = set()
    for pat in patterns:
        for root in test_roots:
            result = subprocess.run(
                ["rg", "--type", "py", "-l", "--no-messages", pat, str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            for line in result.stdout.splitlines():
                try:
                    rel = Path(line).resolve().relative_to(repo_path.resolve())
                except ValueError:
                    continue
                # Require "test" in the path (filename or parent dir) to avoid
                # picking up the source module itself if it self-imports
                if "test" not in str(rel).lower():
                    continue
                # Skip the source file itself
                if str(rel) == source_rel:
                    continue
                candidates.add(str(rel))
    return sorted(candidates)[:max_results]


def _find_related_tests(
    repo_path: Path,
    modified_paths: list[str],
    conventions: list[str],
    max_chars: int,
    max_tests_per_source: int = 3,
) -> tuple[list[TestFile], list[str]]:
    """Discover tests related to each modified source file.

    Strategy:
      1. Try configurable path conventions (fast, deterministic)
      2. Fall back to import-graph discovery: ripgrep for files that
         `from <module> import` or `import <module>`, scoped to test dirs
    """
    found: list[TestFile] = []
    untested: list[str] = []
    seen_test_paths: set[str] = set()

    def _add_test_file(test_rel: str, source_rel: str) -> bool:
        if test_rel in seen_test_paths:
            return True
        candidate = repo_path / test_rel
        if not candidate.exists():
            return False
        try:
            content = candidate.read_text(errors="ignore")
        except Exception:
            return False
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... (truncated, {len(content) - max_chars} chars)"
            truncated = True
        found.append(
            TestFile(
                path=test_rel,
                source_file=source_rel,
                content=content,
                truncated=truncated,
            )
        )
        seen_test_paths.add(test_rel)
        return True

    for src in modified_paths:
        if not src.endswith(".py"):
            continue
        stem = Path(src).stem
        if stem.startswith("test_") or stem.endswith("_test"):
            continue
        name = Path(src).name

        # Strategy 1: convention-based
        matched = False
        for conv in conventions:
            try:
                test_rel = conv.format(stem=stem, name=name, path=src)
            except (KeyError, IndexError):
                continue
            if _add_test_file(test_rel, src):
                matched = True
                break

        # Strategy 2: import-graph fallback
        if not matched:
            for test_rel in _find_tests_by_import(repo_path, src, max_tests_per_source):
                if _add_test_file(test_rel, src):
                    matched = True

        if not matched:
            untested.append(src)
    return found, untested


# -- Token budget ------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text))


def _serialize_cc(cc: CodebaseContext) -> str:
    parts: list[str] = []
    for s in cc.modified_symbols:
        prefix = f"{s.enclosing_qualifier}." if s.enclosing_qualifier else ""
        parts.append(
            f"{s.kind} {prefix}{s.name} @ {s.path}:{s.start_line}-{s.end_line}\n{s.signature}"
        )
    for c in cc.call_sites:
        parts.append(f"call {c.symbol_name} @ {c.path}:{c.line}\n{c.snippet}")
    for t in cc.related_tests:
        parts.append(f"test {t.path} (for {t.source_file})\n{t.content}")
    return "\n\n".join(parts)


def _enforce_budget(cc: CodebaseContext, max_tokens: int) -> None:
    text = _serialize_cc(cc)
    cc.token_estimate = int(_estimate_tokens(text) * 1.3)  # Claude-conservative

    # Symbols-only floor check first
    if cc.token_estimate > max_tokens:
        symbols_only = CodebaseContext(modified_symbols=cc.modified_symbols)
        sym_tokens = int(_estimate_tokens(_serialize_cc(symbols_only)) * 1.3)
        if sym_tokens > max_tokens:
            raise CodebaseContextTooLarge(
                f"modified_symbols alone is ~{sym_tokens} tokens, exceeds budget {max_tokens}"
            )

        # Drop call sites until under budget
        while cc.token_estimate > max_tokens and cc.call_sites:
            cc.call_sites.pop()
            cc.truncations["call_sites_dropped"] = cc.truncations.get("call_sites_dropped", 0) + 1
            cc.token_estimate = int(_estimate_tokens(_serialize_cc(cc)) * 1.3)

        # Drop tests last
        while cc.token_estimate > max_tokens and cc.related_tests:
            cc.related_tests.pop()
            cc.truncations["related_tests_dropped"] = (
                cc.truncations.get("related_tests_dropped", 0) + 1
            )
            cc.token_estimate = int(_estimate_tokens(_serialize_cc(cc)) * 1.3)


# -- Top-level entry ---------------------------------------------------------


def gather_codebase_context(
    pr_context: Context,
    max_tokens: int = 30_000,
    max_call_sites_per_symbol: int = 5,
    max_test_file_chars: int = 5000,
    test_path_conventions: list[str] | None = None,
) -> CodebaseContext:
    """Assemble the CodebaseContext for a PR. Graceful: returns empty if
    optional deps are unavailable."""
    cc = CodebaseContext()

    if not _have_tree_sitter():
        return cc

    repo_path = _ensure_repo_checkout(
        pr_context.owner, pr_context.repo, pr_context.number, pr_context.head_sha
    )
    if repo_path is None:
        logger.warning(
            "Could not check out %s/%s @ %s — skipping codebase context",
            pr_context.owner,
            pr_context.repo,
            pr_context.head_sha,
        )
        return cc

    _extract_modified_symbols(repo_path, pr_context, cc)

    if cc.modified_symbols:
        if _have_ast_grep():
            sites, truncs = _find_call_sites_ast_grep(
                repo_path, cc.modified_symbols, max_call_sites_per_symbol
            )
            cc.call_sites = sites
            cc.truncations.update(truncs)
        else:
            logger.warning(
                "ast-grep-py not available — call-site lookup falls back to "
                "ripgrep + tree-sitter (not yet implemented in this slice). "
                "Continuing without call sites."
            )

    modified_paths = [h.path for h in pr_context.hunks]
    conv = test_path_conventions or DEFAULT_TEST_CONVENTIONS
    tests, untested = _find_related_tests(repo_path, modified_paths, conv, max_test_file_chars)
    cc.related_tests = tests
    cc.untested_files = untested

    _enforce_budget(cc, max_tokens)
    return cc
