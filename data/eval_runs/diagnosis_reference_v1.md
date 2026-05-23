# Diagnosis: why is DefectRecall 7.5% on the v1 reference dataset?

Source: `data/eval_runs/reference_v1_sonnet46.json` (Sonnet 4.6 on
`dataset/reference/django_pydantic_v1.jsonl`, 30 PRs, 14 with gold defects,
56 total gold defects, 2 matches, judge calls 64).

Classifying every missed gold defect and every novel peer comment across all
14 PRs that had at least one gold defect. Buckets:

**For each missed gold defect:**
- **(B) GOLD OVER-CLASS** — the raw human comment was not actually a defect
  report (Q&A, info, "looks good", suggestion-not-defect). The default
  classifier should have routed it to `discussion`. This is a *dataset
  pipeline* problem, not an agent problem.
- **(A) PEER MISS** — real defect; peer didn't comment on the area.
- **(C) JUDGE TOO STRICT** — peer DID comment in the same code area but the
  judge said DIFFERENT. The concern is the same / related; the judge is
  binary and over-rejecting.
- **(D) PEER COULDN'T SEE** — the defect references something outside the
  diff + surrounding-code context (prior discussion, follow-up changes).

**For each novel peer comment:**
- **(R) REAL CATCH** — legitimate concern humans didn't flag.
- **(S) STYLE NIT** — peer flagged a stylistic preference at higher severity
  than warranted.
- **(H) HALLUCINATED / OVERSTATED** — peer invented or overstated detail.

---

## PR-by-PR diagnosis

### pydantic#7677 — 1 gold, 4 peer, 0 matched (0%)

**Gold-miss #1** `pydantic/mypy.py:808` important / defect-correctness
> Raw: "Try `self._cls.info`"
> → **(B) GOLD OVER-CLASS** — dmontagu answering sydney-runkle's implementation
> question. Not a defect; pure collaborative Q&A. Should have been `discussion`.

**Peer-novel #1** `pydantic/mypy.py:432` important
> "is_root_model uses `in` substring matching when it should use ==…"
> → **(R) REAL CATCH** — verified in earlier session that line 444 of the source
> does use `==`; peer correctly flagged the substring inconsistency.

**Peer-novel #2** `pydantic/mypy.py:808` critical
> "args[0] will raise IndexError if args is empty"
> → **(R) REAL CATCH** — defensive coding concern peer caught; on the same line
> as the (over-classified) gold but a completely distinct concern.

**Peer-novel #3** `pydantic/mypy.py:1099` minor
> "error_extra_fields_on_root_model takes CheckerPluginInterface but caller passes SemanticAnalyzerPluginInterface"
> → **(R) REAL CATCH** — type-signature mismatch.

**Peer-novel #4** `tests/mypy/modules/root_models.py:22` minor
> "test infrastructure runs against multiple mypy versions but only one output exists"
> → **(R) REAL CATCH** — concrete test-coverage gap.

**Verdict:** the gold defect is invalid (over-class); all 4 peer comments are
real. True recall on this PR is N/A (no real gold defects).

---

### pydantic#7435 — 1 gold, 3 peer, 0 matched (0%)

**Gold-miss #1** `pydantic/_internal/_core_utils.py:68` important / defect-correctness
> "Type refs not reflecting generic parameters could produce two different schemas with the same ref"
> → **(A) PEER MISS** — real, subtle defect about generic schema ref collisions.
> Peer didn't see it; would have required understanding of the schema-ref
> system to catch.

**Peer-novel #1** `_core_utils.py:11` important: importing `typing._GenericAlias` (private). **(R)**
**Peer-novel #2** `_core_utils.py:77` important: silently drops `args_override` when type is `_GenericAlias`. **(R)**
**Peer-novel #3** `tests/test_dataclasses.py:2075` minor: tests coupled to internal schema structure. **(R)**

**Verdict:** real gold defect peer missed. 3 novels are all real, complementary.

---

### pydantic#7589 — 2 gold, 2 peer, 0 matched (0%)

**Gold-miss #1** `pydantic/plugin/_loader.py:36` nit / style-nit
> Raw: "Just an empty tuple should be enough as `Iterable`"
> → Borderline **(B)**. It's a one-line implementation suggestion. Peer didn't
> see it because it's not a defect — it's a micro-optimization tip.

**Gold-miss #2** `tests/plugin/example_plugin.py:10` minor / defect-test-gap
> Raw: "`assert` ?"
> → **(B) GOLD OVER-CLASS** — a single-word question. Pure discussion.

**Peer-novel #1** `_loader.py:58` important: unhandled exceptions propagating from `get_plugins()`. **(R)**
**Peer-novel #2** `_loader.py:22` minor: comment trails off mid-sentence. **(R)** (small but verifiable).

**Verdict:** both gold items are over-classed; peer's 2 are real.

---

### django#17314 — 1 gold, 1 peer, 0 matched (0%)

**Gold-miss #1** `tests/model_fields/test_generatedfield.py:202` important / defect-test-gap
> Raw: "I moved test for adding this field to the `schema/tests.py`."
> → **(B) GOLD OVER-CLASS** — felixxm explaining what they did. Pure info.
> Classifier hallucinated a coverage concern from neutral text.

**Peer-novel #1** `tests/schema/tests.py:848` minor: test creates model but doesn't assert anything meaningful. **(R)**

**Verdict:** gold is info, not defect. Peer found a real test-quality issue.

---

### django#17171 — 1 gold, 4 peer, 0 matched (0%)

**Gold-miss #1** `django/db/models/lookups.py:221` important / defect-correctness
> "We should still call `field_cast_sql()` when it's implemented in 3rd-party DB backends and add a deprecation warning"
> → **(C) JUDGE TOO STRICT.** Peer-novel #4 below is on `lookups.py:231` and is
> explicitly about the third-party-override / deprecation interaction with
> `field_cast_sql()`. Same code, same concern, different lines (221 vs 231).
> The judge saw them as DIFFERENT because of line number drift.

**Peer-novel #1** `operations.py:229` important: deprecation warning fires unconditionally. **(R)**
**Peer-novel #2** `test_operations.py:248` nit: typo (missing comma) in expected message. **(R)**
**Peer-novel #3** `lookups.py:223` minor: `hasattr(connection.ops.__class__, "field_cast_sql")` always True. **(R)**
**Peer-novel #4** `lookups.py:231` important: third-party backend override triggers warning. **(R)** — also = the gold above.

**Verdict:** judge-too-strict miss; peer effectively caught the gold defect.

---

### django#17147 — 10 gold, 6 peer, 0 matched (0%)

The streaming/ASGI-disconnect PR. Lots of human feedback, very mixed quality.

**Gold-miss #1** `asgi.py:201` important — qxcv "Assuming you mean the change from..."
> → **(B) GOLD OVER-CLASS** — clarification/discussion thread.

**Gold-miss #2** `tests/asgi/tests.py:520` important — "ResourceWarning unclosed SpooledTemporaryFile"
> → **(C) JUDGE TOO STRICT.** Peer-novel #2 (asgi.py:222) is about `body_file.close()` not in a finally block — *the cause of* this ResourceWarning. Same root issue.

**Gold-miss #3** `tests/asgi/tests.py:242` nit — "Typo" in test comment
> → real nit. **(A) PEER MISS** — peer didn't comment on test comments at all.

**Gold-miss #4** `tests/asgi/tests.py:241` nit — "Omit prefixes like 'This test', 'Ensure'"
> → Django-specific style preference. **(B)** — it's stylistic guidance, not a defect; classifier kept it as a nit defect.

**Gold-miss #5** `docs/.../request-response.txt:1285` minor — "remove this doc block"
> → **(B)** — a code-suggestion comment from a reviewer. Implementation guidance, not defect.

**Gold-miss #6** `docs/.../request-response.txt:1312` nit — "Wrap at 79 chars"
> → real nit, project-style. **(A)**

**Gold-miss #7** `docs/topics/async.txt:200` nit — "Omit `;` in docs"
> → real nit, project-style. **(A)**

**Gold-miss #8** `asgi.py:197` nit — "Please omit 'We' in comments"
> → real nit, project-style. **(A)**

**Gold-miss #9** `tests/asgi/tests.py:520` nit — "There is no typing in Django, so this suppression comment can be removed"
> → real nit, project-knowledge. **(A)**

**Gold-miss #10** `tests/asgi/tests.py:282` important — ResourceWarning #2 (same issue as #2 above)
> → **(C) JUDGE TOO STRICT.** Same root cause as peer-novel #2.

**Peer novels:**
- `asgi.py:207` important — exceptions other than RequestAborted/AssertionError swallowed. **(R)**
- `asgi.py:222` important — body_file.close not in finally. **(R)** + addresses gold #2 and #10.
- `asgi.py:200` minor — iteration order comment imprecise. **(R)**
- `tests/asgi/tests.py:504` minor — receive_output behaviour quirk. **(R)**
- `tests/asgi/urls.py:55` minor — `streaming_view` doesn't guard `request.GET["sleep"]`. **(R)**
- `docs/.../request-response.txt:1307` minor — example references asyncio without importing it. **(R)**

**Verdict:** 2 of 10 golds are judge-too-strict; 2 are over-class; 6 are real
Django-style/nit items peer doesn't know about (no project style guide in
context). All 6 peer novels are real, complementary catches.

---

### django#17637 — 2 gold, 1 peer, 0 matched (0%)

**Gold-miss #1** `tests/gis_tests/.../test_geom.py:62` important / defect-test-gap
> Raw: "`self.assertEqual(repr(OGRGeomType('point')), '<OGRGeomType: Point>')`"
> → felixxm suggesting test assertion. **(B)** — reviewer-supplied code suggestion. Not a defect; pure how-to.

**Gold-miss #2** `geomtype.py:59` nit / style-nit
> "use `__qualname__` instead of `__name__`"
> → real style nit. **(A)** — peer didn't suggest this micro-change.

**Peer-novel #1** `tests/gis_tests/.../test_geom.py:62` minor: only tests `Point`, suggest more cases. **(R)** + same-line as gold #1 but addressing test coverage breadth not assertion form.

**Verdict:** 1 over-class, 1 small real nit peer missed, 1 different-angle novel.

---

### django#17256 — 6 gold, 1 peer, 0 matched (0%)

Heavy docs PR. All 6 gold defects are docs comments.

**Gold-miss #1** `migrations.txt:788` minor — "make support explicit". Suggestion. **(B)**
**Gold-miss #2** `releases/5.0.txt:404` nit — "remove redundant 'Migrations now'". Real nit. **(A)**
**Gold-miss #3** `migrations.txt:788` important — "nested items rendering incorrectly". Real doc-render bug. **(A)**
**Gold-miss #4** `migrations.txt:788` nit — author acknowledging missing blank lines. **(B)** — pure author self-comment.
**Gold-miss #5** `releases/5.0.txt:404` minor — "malformed markdown, unclosed backtick". Real defect. **(A)**
**Gold-miss #6** `releases/5.0.txt:404` nit — "present tense in release notes". Real nit, project-style. **(A)**

**Peer-novel #1** `serializer.py:353` important: `functools._lru_cache_wrapper` is private. **(R)** — on a completely different file (code, not docs).

**Verdict:** 4 of 6 gold are real (peer missed them — all docs/style); 2 are over-class. Peer focused on code defect on different file.

---

### django#16746 — 4 gold, 3 peer, 0 matched (0%)

**Gold-miss #1** `paginator.txt:59` important — "almost the same as existing docs". Dedup suggestion. **(B)** — observation, not defect.
**Gold-miss #2** `paginator.py:35` nit — "use shorter dict keys". Style. **(B)** borderline / real nit.
**Gold-miss #3** `paginator.txt:59` important — "versionadded missing, document keys, release notes". Real doc gap. **(A)**.
**Gold-miss #4** `tests/pagination/tests.py:140` nit — "extract msg to variable". Style. **(B)**.

**Peer-novel #1** `paginator.txt:59` minor: doc says attribute but it's an init param. **(C)** OR (R) — same file/line as gold #1/#3 but different angle.
**Peer-novel #2** `paginator.py:50` important: subclass override merging concern. **(R)**.
**Peer-novel #3** `tests/pagination/tests.py:131` minor: no test for extra/unknown keys. **(R)**.

**Verdict:** 1 real gold peer missed (versionadded); 3 over-class; 3 peer novels real.

---

### django#16603 — 19 gold, 7 peer, 1 matched (5%) ← THE BIG ONE

Substantive ASGI streaming PR with rich review (carltongibson, ntachukwu, felixxm).

**Match #1** `asgi.py:211` peer.minor / gold.important — both about `assert` usage. ✓

**Gold-misses (18):**

Real defects peer missed:
- `asgi.py:259` important — perf concern about pause delay (carltongibson). **(A)**
- `asgi.py:197` important — view runs sync, should be concurrent task (carltongibson). **(A)**
- `asgi.py:197` important — unnecessary loop, ASGI spec only allows one disconnect (carltongibson). **(A)**
- `asgi.py:220` important — race condition with asyncio.wait ordering (ntachukwu). **(A)**
- `asgi.py:197` important — TimeoutError not raised when expected (ntachukwu). **(A)**
- `asgi.py:213` important — missing test for view cleanup (carltongibson). **(A)**
- `tests/asgi/tests.py:253` important — test structure inadequate (carltongibson). **(A)**

Style nits peer missed (mostly Django-specific):
- `asgi.py:261` nit — grammar fix. **(A)** (or **(B)** — it's a tiny wording change in a comment).
- `asgi.py:207` nit — docstring formatting. **(A)** style-only.
- `asgi.py:212` nit — f-string Django style guideline. **(A)** project-style.
- `asgi.py:217` nit — wording preference. **(A)** project-style.
- `async.txt:139` nit — heading change suggestion. **(A)** project-style.
- `async.txt:144` nit — wording change. **(A)** project-style.
- `tests/asgi/tests.py:376` nit — comment style. **(A)** project-style.
- `tests/asgi/urls.py:17` nit — f-string preferred. **(A)** project-style.

Doc-gaps peer missed:
- `async.txt:143` important — `versionadded:: 5.0` missing. **(A)**
- `async.txt:142` important — reference release notes. **(A)**
- `async.txt:142` important — add anchor for cross-reference. **(A)**

**Peer novels (6):**
- `asgi.py:199` important — body_file leak on AssertionError. **(R)** — related to felixxm's general concerns.
- `asgi.py:188` important — body_file leak on unhandled exception. **(R)**.
- `asgi.py:184` important — view catching CancelledError without re-raising. **(R)**.
- `asgi.py:211` minor — %-style formatting violates Django style. **(R)** + related to gold f-string nits.
- `tests/asgi/urls.py:14` important — `time.sleep(1)` blocking in async test. **(R)** — same area as multiple gold items.
- `async.txt:155` minor — example missing `asyncio` import. **(R)**.

**Verdict:** the only PR where peer + humans agree on something substantive
(the `assert` issue). Peer misses 7 real architectural defects (carltongibson
and ntachukwu's review work) and 11 Django-specific nits. Peer's novels are
mostly real, in the same area, but different specific issues.

This PR alone accounts for ~34% (19/56) of all gold defects in the dataset
and dominates the recall denominator.

---

### django#17218 — 1 gold, 1 peer, 0 matched (0%)

**Gold-miss #1** `color.py:21` important / defect-doc-gap
> Raw: "I confirmed that `OSError` still seems relevant. [link to ticket]"
> → **(B) GOLD OVER-CLASS** — timgraham confirming the existing code is correct. Pure info / agreement.

**Peer-novel #1** `color.py:17` nit: off-by-one in comment about colorama version boundary. **(R)** — small but verifiable.

**Verdict:** gold is info, not defect. Peer's nit is real.

---

### pydantic#7900 — 2 gold, 4 peer, 2 matched (100%) ★

Only PR with full recall.

**Matches:**
- `type_adapter.py:222` peer.minor / gold.important — docstring describes `type` as Python type but accepts more (TypedDict, BaseModel). ✓
- `type_adapter.py:223` peer.minor / gold.important — `config` param doesn't mention model-with-config limitation. ✓

Severity calibration: peer rated both as `minor`, gold as `important`. Two-step under-severity from peer.

**Peer-novels (2):**
- `json_schema.md:527` minor: Metadata class used as metadata, not field type — sentence is misleading. **(R)**
- `json_schema.md:549` nit: `source_type` typed as `Type[BaseModel]` but can be `int`. **(R)**

**Verdict:** the demonstration case that the framework works when gold and
peer are both looking at docstrings of the same parameters. Severity
disagreement: both peer comments rated lower than gold.

---

### pydantic#8059 — 5 gold, 2 peer, 0 matched (0%)

Heavy docs PR for TypeAdapter concepts page.

**Gold-misses:**
- `type_adapter.md:8` nit — grammar fix suggestion. **(A)** real nit / **(B)** borderline (it's a one-line replacement).
- `type_adapter.md:26` important — "rename Validator to Adapter in docs". **(A)** project-style suggestion.
- `type_adapter.md:46` important — clarify when not to use TypeAdapter. **(A)** real doc gap.
- `mkdocs.yml:70` nit — capitalization. **(A)** project-style.
- `type_adapter.md:81` important — add performance considerations. **(A)** real doc gap.

**Peer-novels:**
- `type_adapter.md:72` minor: TypeAdapter created and immediately discarded — inconsistent with the new performance section. **(R)** — clever cross-reference catch.
- `api/type_adapter.md:1` minor: API ref omits other public symbols. **(R)**.

**Verdict:** docs-heavy PR; peer made smart cross-reference catches but missed
all 5 specific gold improvements. Real **(A) PEER MISS** pattern: peer didn't
see the docs through the same lens humans did.

---

### pydantic#8442 — 1 gold, 1 peer, 0 matched (0%)

**Gold-miss #1** `types.py:1555` important / defect-correctness
> "SecretStr('') prints as '' instead of being masked — may indicate incorrect redaction"
> → **(A) PEER MISS** — real behavior defect.

**Peer-novel #1** `types.py:1564` minor: docstring has two conflicting sentences. **(R)** — but unrelated to the empty-secret bug.

**Verdict:** real defect peer missed; peer found different doc issue.

---

## Aggregate counts

Across all 14 PRs / 56 gold defects:

| Bucket | Count | % |
|---|---|---|
| **(B) GOLD OVER-CLASS** — should not be in gold | **~21** | **~38%** |
| **(A) PEER MISS** — real defect peer didn't catch | ~25 | ~45% |
| **(C) JUDGE TOO STRICT** — peer caught same area, judge said different | ~4 | ~7% |
| **(D) PEER COULDN'T SEE** — needs context peer doesn't have | ~6 | ~11% |
| Total | 56 | 100% |

Across all 30 peer novel comments:

| Bucket | Count | % |
|---|---|---|
| **(R) REAL CATCH** | ~28 | ~93% |
| **(S) STYLE NIT** — over-severed | ~2 | ~7% |
| **(H) HALLUCINATED** | 0 | 0% |

## Key findings

### 1. The dominant problem is gold over-classification, not peer's quality

~38% of gold defects (21/56) shouldn't be in gold at all. They are:
- Author-reviewer Q&A ("Try `self._cls.info`", "`assert`?")
- Informational comments ("I moved this test", "OSError still seems relevant")
- Reviewer-supplied code suggestions ("self.assertEqual(repr(...), '...')")
- Pure agreement / approval

If we exclude these from gold, the real-defect denominator drops from 56 to
~35. Peer hits 2 → corrected recall is **~6%** still. But the ceiling moves:
the remaining 35 are mostly real defects.

### 2. Many "peer misses" are project-specific style/nit knowledge

In PR 16603 alone, ~11 of 18 gold misses are Django-style preferences:
"omit 'We' in comments", "use f-strings except for plain access", "wrap docs
at 79 chars", "use `__qualname__`". Peer has no project style guide in
context. These are real misses but reflect a context gap, not a reasoning gap.

### 3. The judge's binary SAME/DIFFERENT misses semantic adjacency

~4 cases (PR 17171, 17147, 16746, 17637) where peer's comment addresses the
same defect from a different angle or on a different line. Binary judge
collapses these to DIFFERENT. A 3-way SAME / RELATED / DIFFERENT with
RELATED scored as partial credit would lift recall meaningfully.

### 4. Peer is finding real things humans missed at high rates

93% of peer's novel comments (28/30) are real, verifiable concerns. Only
~7% are style nits over-severed. Zero hallucinations in the sample. This
means peer's value is mostly **complementary** to human reviewers, not
replicative — different reviewers (human and AI) catch different things.

### 5. Peer's recall ceiling on PR 16603 is the data-engineering problem in microcosm

PR 16603 alone has 19 gold defects (34% of dataset). 7 of those are real
architectural issues from senior reviewers (carltongibson, ntachukwu). The
remaining 12 are 8 Django style-nits + 4 doc gaps. The 7 senior-review items
are the most valuable defect labels in the entire dataset — but peer misses
all of them because:
- They require understanding the broader ASGI / async architecture
- Some require seeing the parent PR / prior discussion not in peer's context
- Some require understanding the project's testing patterns

## Concrete recommendations

### High-impact, low-cost (do first):

1. **Sharpen the classifier with few-shot discussion examples.** Add
   examples to the LLM classifier prompt for the patterns we systematically
   misclassify: implementation-Q&A, informational, agreement, reviewer-as-
   author code suggestion. Estimated impact: -25% to -40% on gold over-class
   rate, lifting the meaningful recall denominator.

2. **Add a "must-be-defect-not-discussion" gate.** A second-pass binary
   classifier ("Is this a defect to fix, or is this conversation?") before
   category assignment. Catches the Q&A patterns the multi-class classifier
   misses.

3. **Cap style/nit severity by file path.** If `path` matches `docs/**` or
   the raw comment is < 50 chars, force `nit` severity at most. Reduces
   noisy "important" labels on what are really style preferences.

### Medium-cost:

4. **3-way judge: SAME / RELATED / DIFFERENT.** Score RELATED matches as
   0.5 credit. Lifts recall on the ~4 judge-strict cases without inventing
   matches.

5. **Add team-style-guide context to the agent.** Allow `Agent(team_style=...)`
   that injects a docstring / coding-conventions blob into the prompt. Would
   let peer catch Django-specific nits if a user provides their style guide.

### Lower-priority:

6. **Track over-class rate as a dataset health metric.** Surface "X% of gold
   defects derive from raw comments under 50 chars" as a curation-quality
   signal in `peer dataset list`.

7. **For PR 16603 specifically:** consider whether substantive multi-
   reviewer PRs deserve manual gold-curation rather than auto-classify, given
   how many real defects are at stake.

## What this validates about the framework

The 7.5% headline number is largely a **dataset pipeline calibration**
problem, not a reviewer quality problem. The framework is doing its job: it
*reproducibly measures* peer's hit rate against a defined ground truth, and
the comment-by-comment dump above lets us *see exactly* where the
disagreement is. That visibility is the whole point. The next iteration
(sharper classifier → better gold → re-eval) is the cycle the framework was
built for.
