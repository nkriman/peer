# Hypothesis

## Headline

- unmatched gold defects: 50 across 7 sample(s)
- topic-drift samples (peer commented, matched none): 6
- top cost: $0.0872 on https://github.com/django/django/pull/17147
- total session cost: $0.3977
- precision-miss peer comments: 21

## Failure modes by severity

- critical: 0
- important: 20
- minor: 10
- nit: 20

### Per-sample failures

- https://github.com/django/django/pull/16603 — 22 unmatched (critical=0, important=11, minor=4, nit=7)
- https://github.com/django/django/pull/17147 — 11 unmatched (critical=0, important=2, minor=2, nit=7)
- https://github.com/pydantic/pydantic/pull/8059 — 5 unmatched (critical=0, important=2, minor=1, nit=2)
- https://github.com/pydantic/pydantic/pull/7900 — 2 unmatched (critical=0, important=2, minor=0, nit=0)
- https://github.com/django/django/pull/17256 — 5 unmatched (critical=0, important=1, minor=2, nit=2)
- https://github.com/django/django/pull/16746 — 4 unmatched (critical=0, important=1, minor=1, nit=2)
- https://github.com/pydantic/pydantic/pull/7677 — 1 unmatched (critical=0, important=1, minor=0, nit=0)

## Topic drift

### https://github.com/django/django/pull/17147 — peer wrote 5 comment(s); 0 matched gold

Peer wrote about:
- django/core/handlers/asgi.py:208 — When `process_request` (tasks[1]) raises an unexpected exception other than `RequestAborted` or `AssertionError`, it is silently swallowed. The `task.result()` call will re-raise the exception, but on
- django/core/handlers/asgi.py:219 — When a pending task is cancelled and `await task` raises something other than `asyncio.CancelledError` (e.g. the view catches `CancelledError` and raises a different exception, or `send_response` rais
- django/core/handlers/asgi.py:206 — The ordering of tasks in the list matters for correctness: the comment says `listen_for_disconnect` goes first so that its errors don't prevent cancellation of `process_request`. However, if `listen_f
- tests/asgi/tests.py:503 — The `test_streaming` test fetches a third output message (line 503) and then asserts a `TimeoutError` on a fourth (lines 504-505). For a two-chunk streaming response (`first\n` and `last\n`), the ASGI
- docs/ref/request-response.txt:1301 — The documentation example catches `asyncio.CancelledError` in the streaming generator but does not import `asyncio`. Readers copying this snippet will get a `NameError`. The docs should either add `im

Gold expected:
- [minor] django/core/handlers/asgi.py:219 — If this is a single-pass design, prefer defining a local async function over adding another method on self.
- [important] tests/asgi/tests.py:520 — ResourceWarning: unclosed SpooledTemporaryFile in asgi tests on Python 3.12. The test infrastructure is leaking the temporary body file.
- [minor] tests/asgi/tests.py:240 — Added tests pass without the patch under review; extra test coverage should land as a separate commit/PR.
- [nit] tests/asgi/tests.py:242 — Typo in test comment — 'forces' should be 'force' to match the plural subject.
- [nit] tests/asgi/tests.py:241 — Django style: omit prefixes like 'This test', 'Ensure', 'Test' in test docstrings.
- [nit] docs/ref/request-response.txt:1285 — Remove the orphan documentation code block.
- [nit] docs/ref/request-response.txt:1312 — Wrap documentation text at 79 characters per project convention.
- [nit] docs/topics/async.txt:200 — Django docs convention: omit semicolons.
- [nit] django/core/handlers/asgi.py:197 — Django comment style: omit 'We' in comments.
- [nit] tests/asgi/tests.py:520 — Django doesn't use typing annotations, so the type-ignore suppression comment can be removed.
- [important] tests/asgi/tests.py:282 — ResourceWarning: unclosed SpooledTemporaryFile in `test_assert_in_listen_for_disconnect` on Python 3.12. Same root cause as the other ResourceWarning above.

### https://github.com/pydantic/pydantic/pull/8059 — peer wrote 1 comment(s); 0 matched gold

Peer wrote about:
- docs/concepts/type_adapter.md:75 — A new `TypeAdapter` instance is created inline here (`TypeAdapter(List[Item]).validate_python(item_data)`), which contradicts the performance guidance added just below (lines 83–86) that recommends cr

Gold expected:
- [nit] docs/concepts/type_adapter.md:8 — Grammar fix: remove the 'needing to create a' fragment for cleaner sentence flow.
- [minor] docs/concepts/type_adapter.md:26 — Rename example variable from `UserListValidator` to `UserListAdapter` so the docs convey TypeAdapter's broader capability beyond validation.
- [important] docs/concepts/type_adapter.md:46 — Add a !!! note clarifying that TypeAdapter should not be used as a type annotation for BaseModel fields, to avoid misuse.
- [nit] mkdocs.yml:70 — Capitalization: 'Type Adapter' (with space) for nav consistency.
- [important] docs/concepts/type_adapter.md:81 — Add a !!! info block on performance considerations: TypeAdapter construction is expensive, callers should reuse instances.

### https://github.com/pydantic/pydantic/pull/7900 — peer wrote 2 comment(s); 0 matched gold

Peer wrote about:
- pydantic/type_adapter.py:236 — `__init__` doesn't return anything (it returns `None`). The `Returns` section saying "A type adapter configured for the specified `type`" is misleading — that description belongs on `__new__` or the c
- docs/concepts/json_schema.md:547 — The `source_type` parameter is typed as `Type[BaseModel]`, but `__get_pydantic_core_schema__` receives the annotated type being processed (here `int`, not a `BaseModel` subclass). The correct type hin

Gold expected:
- [important] pydantic/type_adapter.py:222 — Docstring describes the `type` parameter as a Python type but TypeAdapter also accepts pydantic models, TypedDicts, etc. Docstring should reflect that.
- [important] pydantic/type_adapter.py:223 — Docstring should mention that `config` cannot be used when the type already has its own config (e.g. a BaseModel).

### https://github.com/django/django/pull/17256 — peer wrote 1 comment(s); 0 matched gold

Peer wrote about:
- django/db/migrations/serializer.py:353 — `functools._lru_cache_wrapper` is a private/internal CPython implementation detail. It is not part of the public API and could be renamed, removed, or changed in future Python versions without notice.

Gold expected:
- [minor] docs/topics/migrations.txt:788 — Docs should make it explicit that functools.cache decorator support is intentionally supported, not implicit, to help readers understand the design intent.
- [nit] docs/releases/5.0.txt:404 — Release-notes wording: drop the redundant 'Migrations now' prefix since the section title already specifies Migrations context.
- [important] docs/topics/migrations.txt:788 — Nested items in the migrations docs are rendering incorrectly (visible in the linked screenshot). Fix the RST nesting.
- [minor] docs/releases/5.0.txt:404 — Release-notes line has malformed markdown — unclosed backtick in 'Migrations now support serialization of functions...'.
- [nit] docs/releases/5.0.txt:404 — Django release-notes convention: use present tense, not past tense.

### https://github.com/django/django/pull/16746 — peer wrote 2 comment(s); 0 matched gold

Peer wrote about:
- django/core/paginator.py:50 — When `error_messages=None`, `self.error_messages` is assigned the class-level `default_error_messages` dict directly (not a copy). This means any mutation of `self.error_messages` on an instance would
- docs/ref/paginator.txt:59 — The attribute is documented as `Paginator.error_messages`, but the parameter is named `error_messages` in `__init__`. The prose says "The `error_messages` argument lets you override…" — it would be cl

Gold expected:
- [minor] docs/ref/paginator.txt:59 — New docs are nearly identical to the existing forms-fields error-messages docs; reduce duplication or unify.
- [nit] django/core/paginator.py:35 — Use shorter dict keys (e.g. 'invalid_page') for cleaner, more maintainable code.
- [important] docs/ref/paginator.txt:59 — Missing `versionadded:: 5.0` annotation. Also document the available error_messages keys and add release notes for the new customization feature.
- [nit] tests/pagination/tests.py:140 — Test refactor: extract the expected error message into a variable for readability.

### https://github.com/pydantic/pydantic/pull/7677 — peer wrote 5 comment(s); 0 matched gold

Peer wrote about:
- pydantic/mypy.py:809 — `args[0]` is accessed without checking that `args` is non-empty. If a `RootModel` subclass has no fields at all (e.g. `class Pets1(RootModel[List[str]]): pass`), `get_field_arguments` will return an e
- pydantic/mypy.py:434 — The `is_root_model` check uses `ROOT_MODEL_FULLNAME in base.fullname` (substring match) rather than `base.fullname == ROOT_MODEL_FULLNAME` (exact match). This could produce a false positive if a third
- pydantic/mypy.py:1099 — `error_extra_fields_on_root_model` declares its `api` parameter as `CheckerPluginInterface`, but it is called from `collect_fields` where `self._api` is a `SemanticAnalyzerPluginInterface`. These are 
- tests/mypy/modules/root_models.py:22 — The test module only covers the case of a single extra (non-`root`) field on a `RootModel` subclass. It would be useful to also test: (1) a subclass that defines both `root` and an extra field, and (2
- tests/mypy/outputs/1.0.1/mypy-plugin_ini/root_models.py:1 — Output files are only provided for mypy `1.0.1` with `mypy-plugin.ini`. There are no output files for other mypy versions (e.g. `0.971`, `1.1.1`) or other config variants (e.g. `mypy-plugin-strict.ini

Gold expected:
- [important] pydantic/mypy.py:811 — Reviewer suggests adding a check for whether the root field has a default value; the current logic may not handle the no-default case correctly.

## Cost outliers

- $0.0872 — https://github.com/django/django/pull/17147 (5 comments)
- $0.0774 — https://github.com/django/django/pull/16603 (6 comments)
- $0.0696 — https://github.com/pydantic/pydantic/pull/7677 (5 comments)

## Precision concerns

- 21 peer comment(s) matched no gold defect:
  - [important] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:190 — If the pending task (e.g. `run_get_response`) raises an exception other than `CancelledError` after being cancelled, tha
  - [important] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:195 — `body_file` is not closed when `done.result()` raises an exception that is neither `RequestAborted` nor `AssertionError`
  - [minor] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:187 — The unpacking `done, pending = done.pop(), pending.pop()` assumes exactly one task in each set. While `asyncio.FIRST_COM
  - [minor] https://github.com/django/django/pull/16603 @ tests/asgi/urls.py:14 — `hello_with_delay` uses `time.sleep(1)` (a blocking synchronous sleep) inside what is used as a delayed ASGI view. Under
  - [minor] https://github.com/django/django/pull/16603 @ docs/topics/async.txt:147 — The documentation states that `asyncio.CancelledError` will be raised "in the view", but this only applies to async view
  - [important] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:208 — When `process_request` (tasks[1]) raises an unexpected exception other than `RequestAborted` or `AssertionError`, it is 
  - [important] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:219 — When a pending task is cancelled and `await task` raises something other than `asyncio.CancelledError` (e.g. the view ca
  - [important] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:206 — The ordering of tasks in the list matters for correctness: the comment says `listen_for_disconnect` goes first so that i
  - [minor] https://github.com/django/django/pull/17147 @ tests/asgi/tests.py:503 — The `test_streaming` test fetches a third output message (line 503) and then asserts a `TimeoutError` on a fourth (lines
  - [minor] https://github.com/django/django/pull/17147 @ docs/ref/request-response.txt:1301 — The documentation example catches `asyncio.CancelledError` in the streaming generator but does not import `asyncio`. Rea
  - [minor] https://github.com/pydantic/pydantic/pull/8059 @ docs/concepts/type_adapter.md:75 — A new `TypeAdapter` instance is created inline here (`TypeAdapter(List[Item]).validate_python(item_data)`), which contra
  - [minor] https://github.com/pydantic/pydantic/pull/7900 @ pydantic/type_adapter.py:236 — `__init__` doesn't return anything (it returns `None`). The `Returns` section saying "A type adapter configured for the 
  - [minor] https://github.com/pydantic/pydantic/pull/7900 @ docs/concepts/json_schema.md:547 — The `source_type` parameter is typed as `Type[BaseModel]`, but `__get_pydantic_core_schema__` receives the annotated typ
  - [important] https://github.com/django/django/pull/17256 @ django/db/migrations/serializer.py:353 — `functools._lru_cache_wrapper` is a private/internal CPython implementation detail. It is not part of the public API and
  - [important] https://github.com/django/django/pull/16746 @ django/core/paginator.py:50 — When `error_messages=None`, `self.error_messages` is assigned the class-level `default_error_messages` dict directly (no
  - [nit] https://github.com/django/django/pull/16746 @ docs/ref/paginator.txt:59 — The attribute is documented as `Paginator.error_messages`, but the parameter is named `error_messages` in `__init__`. Th
  - [critical] https://github.com/pydantic/pydantic/pull/7677 @ pydantic/mypy.py:809 — `args[0]` is accessed without checking that `args` is non-empty. If a `RootModel` subclass has no fields at all (e.g. `c
  - [minor] https://github.com/pydantic/pydantic/pull/7677 @ pydantic/mypy.py:434 — The `is_root_model` check uses `ROOT_MODEL_FULLNAME in base.fullname` (substring match) rather than `base.fullname == RO
  - [important] https://github.com/pydantic/pydantic/pull/7677 @ pydantic/mypy.py:1099 — `error_extra_fields_on_root_model` declares its `api` parameter as `CheckerPluginInterface`, but it is called from `coll
  - [minor] https://github.com/pydantic/pydantic/pull/7677 @ tests/mypy/modules/root_models.py:22 — The test module only covers the case of a single extra (non-`root`) field on a `RootModel` subclass. It would be useful 
  - ...+1 more

## Suggested mutation axes

When proposing your next mutation, pick ONE axis (or a small combo). Cite a specific failure mode above as your motivation.

- system_prompt (edit prompts/default_system_prompt.md content / structure)
- temperature (raise for diversity, lower for consistency)
- model (swap sonnet ↔ opus ↔ haiku for cost/quality)
- retries (raise output retries to recover from grounding misses)
- post_processing.max_comments_per_pr (cap to fight volume blowups)
- post_processing.severity_floor (drop nits / minors to lift precision)
- reviewer_dotted_path = draft_critique (add a self-critique pass)
- reviewer_dotted_path = two_model_pipeline (cheap screen + expensive detail)
- reviewer_dotted_path = self_filter (drop low-confidence comments)
- codebase_context_max_tokens (raise for more context, lower for cost)
