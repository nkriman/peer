# Hypothesis

## Headline

- unmatched gold defects: 47 across 7 sample(s)
- topic-drift samples (peer commented, matched none): 4
- top cost: $0.0913 on https://github.com/django/django/pull/16603
- total session cost: $0.4350
- precision-miss peer comments: 28

## Failure modes by severity

- critical: 0
- important: 19
- minor: 8
- nit: 20

### Per-sample failures

- https://github.com/django/django/pull/16603 — 21 unmatched (critical=0, important=11, minor=3, nit=7)
- https://github.com/django/django/pull/17147 — 11 unmatched (critical=0, important=2, minor=2, nit=7)
- https://github.com/pydantic/pydantic/pull/8059 — 5 unmatched (critical=0, important=2, minor=1, nit=2)
- https://github.com/pydantic/pydantic/pull/7900 — 1 unmatched (critical=0, important=1, minor=0, nit=0)
- https://github.com/django/django/pull/17256 — 4 unmatched (critical=0, important=1, minor=1, nit=2)
- https://github.com/django/django/pull/16746 — 4 unmatched (critical=0, important=1, minor=1, nit=2)
- https://github.com/pydantic/pydantic/pull/7677 — 1 unmatched (critical=0, important=1, minor=0, nit=0)

## Topic drift

### https://github.com/django/django/pull/17147 — peer wrote 6 comment(s); 0 matched gold

Peer wrote about:
- django/core/handlers/asgi.py:208 — When `process_request` is done and `listen_for_disconnect` is still pending, the code calls `task.result()` on `process_request` but silently swallows any non-`AssertionError` exception it raised (e.g
- django/core/handlers/asgi.py:219 — When a task is cancelled and re-raises `CancelledError`, the `except asyncio.CancelledError` branch silently swallows it. But if the task raises a *different* exception after being cancelled (e.g. the
- django/core/handlers/asgi.py:214 — `body_file.close()` is called inside the `AssertionError` handler for the `listen_for_disconnect` task, but if `process_request` raises an `AssertionError` (second iteration of the loop), `body_file.c
- docs/ref/request-response.txt:1294 — The documentation says Django will cancel the coroutine "if the client disconnects during a streaming response", but this only applies to ASGI. WSGI streaming responses are unaffected. The docs should
- tests/asgi/tests.py:247 — Comment says `ASGHandler.send_response()` — missing the 'I' in `ASGI`.
- tests/asgi/tests.py:503 — In `test_streaming`, after fetching the two body chunks, the test fetches one more output and then asserts a `TimeoutError` on the next. It's unclear what the third `receive_output` call at line 503 i

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

### https://github.com/pydantic/pydantic/pull/8059 — peer wrote 3 comment(s); 0 matched gold

Peer wrote about:
- docs/concepts/type_adapter.md:75 — The second code example creates a `TypeAdapter` inline (`TypeAdapter(List[Item]).validate_python(item_data)`) without storing it in a variable. This directly contradicts the performance note added jus
- docs/concepts/type_adapter.md:52 — The section says "This function behaves similarly to `BaseModel.model_validate`" — but `TypeAdapter` is a class, not a function. Consider changing "This function" to "This method" or "This" to avoid c
- pydantic/type_adapter.py:1 — The module-level docstring has been reduced from a rich, example-filled description to just `"Type adapter specification."`. While the content has been moved to the concepts docs page, tools that rend

Gold expected:
- [nit] docs/concepts/type_adapter.md:8 — Grammar fix: remove the 'needing to create a' fragment for cleaner sentence flow.
- [minor] docs/concepts/type_adapter.md:26 — Rename example variable from `UserListValidator` to `UserListAdapter` so the docs convey TypeAdapter's broader capability beyond validation.
- [important] docs/concepts/type_adapter.md:46 — Add a !!! note clarifying that TypeAdapter should not be used as a type annotation for BaseModel fields, to avoid misuse.
- [nit] mkdocs.yml:70 — Capitalization: 'Type Adapter' (with space) for nav consistency.
- [important] docs/concepts/type_adapter.md:81 — Add a !!! info block on performance considerations: TypeAdapter construction is expensive, callers should reuse instances.

### https://github.com/django/django/pull/16746 — peer wrote 3 comment(s); 0 matched gold

Peer wrote about:
- django/core/paginator.py:50 — When `error_messages is None`, `self.error_messages` is assigned the class-level `default_error_messages` dict directly (not a copy). This means any mutation of `self.error_messages` on an instance wo
- docs/ref/paginator.txt:59 — `error_messages` is documented as a `.. attribute::` but it is actually a constructor parameter (like `orphans` and `allow_empty_first_page`, which are documented as `.. attribute::` too — so this fol
- tests/pagination/tests.py:131 — The test does not cover the case where an unknown/extra key is passed in `error_messages` (e.g. a typo like `{'invlaid_page': '...'}`) — the dict merge would silently ignore it and the default message

Gold expected:
- [minor] docs/ref/paginator.txt:59 — New docs are nearly identical to the existing forms-fields error-messages docs; reduce duplication or unify.
- [nit] django/core/paginator.py:35 — Use shorter dict keys (e.g. 'invalid_page') for cleaner, more maintainable code.
- [important] docs/ref/paginator.txt:59 — Missing `versionadded:: 5.0` annotation. Also document the available error_messages keys and add release notes for the new customization feature.
- [nit] tests/pagination/tests.py:140 — Test refactor: extract the expected error message into a variable for readability.

### https://github.com/pydantic/pydantic/pull/7677 — peer wrote 5 comment(s); 0 matched gold

Peer wrote about:
- pydantic/mypy.py:434 — The `is_root_model` check uses `in` on `base.fullname`, which is a substring match. For example, a class whose full name happens to contain the string `'pydantic.root_model.RootModel'` as a substring 
- pydantic/mypy.py:809 — `args[0]` is accessed without checking whether `args` is non-empty. If a `RootModel` subclass has no fields (e.g. `class Pets1(RootModel[List[str]]): pass`), `args` will be empty and this will raise a
- pydantic/mypy.py:1099 — `error_extra_fields_on_root_model` declares its `api` parameter as `CheckerPluginInterface`, but it is called from `collect_fields` where `self._api` is a `SemanticAnalyzerPluginInterface`. These are 
- tests/mypy/modules/root_models.py:17 — The test module only covers positional instantiation (`Pets1(['dog', 'cat'])`). It would be valuable to also test keyword instantiation (`Pets1(root=['dog', 'cat'])`) and invalid instantiation (e.g. `
- tests/mypy/test_mypy.py:101 — The new `root_models.py` test case is only added under `mypy-plugin.ini`. It would be worth also adding it under `mypy-plugin-strict.ini` (and possibly `pyproject-plugin.toml`) to ensure the behavior 

Gold expected:
- [important] pydantic/mypy.py:811 — Reviewer suggests adding a check for whether the root field has a default value; the current logic may not handle the no-default case correctly.

## Cost outliers

- $0.0913 — https://github.com/django/django/pull/16603 (8 comments)
- $0.0873 — https://github.com/django/django/pull/17147 (6 comments)
- $0.0672 — https://github.com/pydantic/pydantic/pull/7677 (5 comments)

## Precision concerns

- 28 peer comment(s) matched no gold defect:
  - [important] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:190 — If the pending task (e.g. `run_get_response`) raises an exception other than `CancelledError` after being cancelled, tha
  - [important] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:196 — `done.result()` is called assuming `done` is the task that completed first. But if `listen_for_disconnect` completes fir
  - [important] https://github.com/django/django/pull/16603 @ django/core/handlers/asgi.py:198 — `body_file.close()` is called in the `except RequestAborted` and `except AssertionError` branches, but not in the normal
  - [minor] https://github.com/django/django/pull/16603 @ tests/asgi/tests.py:397 — The test uses `await asyncio.sleep(0.1)` to "let the view actually start" before sending the disconnect. This is a timin
  - [minor] https://github.com/django/django/pull/16603 @ tests/asgi/urls.py:16 — `hello_with_delay` uses `time.sleep(1)` (a blocking synchronous sleep) inside what will be run as an ASGI view. This blo
  - [minor] https://github.com/django/django/pull/16603 @ docs/topics/async.txt:151 — The documentation example shows catching `asyncio.CancelledError` and re-raising it, but doesn't show how to import `asy
  - [important] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:208 — When `process_request` is done and `listen_for_disconnect` is still pending, the code calls `task.result()` on `process_
  - [important] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:219 — When a task is cancelled and re-raises `CancelledError`, the `except asyncio.CancelledError` branch silently swallows it
  - [minor] https://github.com/django/django/pull/17147 @ django/core/handlers/asgi.py:214 — `body_file.close()` is called inside the `AssertionError` handler for the `listen_for_disconnect` task, but if `process_
  - [minor] https://github.com/django/django/pull/17147 @ docs/ref/request-response.txt:1294 — The documentation says Django will cancel the coroutine "if the client disconnects during a streaming response", but thi
  - [nit] https://github.com/django/django/pull/17147 @ tests/asgi/tests.py:247 — Comment says `ASGHandler.send_response()` — missing the 'I' in `ASGI`.
  - [minor] https://github.com/django/django/pull/17147 @ tests/asgi/tests.py:503 — In `test_streaming`, after fetching the two body chunks, the test fetches one more output and then asserts a `TimeoutErr
  - [minor] https://github.com/pydantic/pydantic/pull/8059 @ docs/concepts/type_adapter.md:75 — The second code example creates a `TypeAdapter` inline (`TypeAdapter(List[Item]).validate_python(item_data)`) without st
  - [nit] https://github.com/pydantic/pydantic/pull/8059 @ docs/concepts/type_adapter.md:52 — The section says "This function behaves similarly to `BaseModel.model_validate`" — but `TypeAdapter` is a class, not a f
  - [minor] https://github.com/pydantic/pydantic/pull/8059 @ pydantic/type_adapter.py:1 — The module-level docstring has been reduced from a rich, example-filled description to just `"Type adapter specification
  - [minor] https://github.com/pydantic/pydantic/pull/7900 @ pydantic/type_adapter.py:237 — The `Returns` section says "A type adapter configured for the specified `type`", but `__init__` returns `None` by conven
  - [minor] https://github.com/pydantic/pydantic/pull/7900 @ docs/concepts/json_schema.md:547 — The `source_type` parameter is annotated as `Type[BaseModel]`, but `__get_pydantic_core_schema__` receives the actual an
  - [minor] https://github.com/pydantic/pydantic/pull/7900 @ docs/concepts/json_schema.md:527 — The sentence "annotating a field with a `BaseModel` type can be used to modify or override the generated json schema" is
  - [important] https://github.com/django/django/pull/17256 @ django/db/migrations/serializer.py:353 — `functools._lru_cache_wrapper` is a private/internal CPython implementation detail. Relying on it may break across Pytho
  - [minor] https://github.com/django/django/pull/17256 @ tests/migrations/test_writer.py:592 — The test `test_serialize_decorated_functions` only calls `assertSerializedEqual`, which checks that the serialized outpu
  - ...+8 more

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
