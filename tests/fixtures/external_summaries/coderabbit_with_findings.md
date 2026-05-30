<!-- This is an auto-generated comment: summarize by coderabbit.ai -->
<!-- walkthrough_start -->

<details>
<summary>📝 Walkthrough</summary>

## Walkthrough

This PR introduces a durable outreach workflow system that wraps the core outreach logic into a Temporal-compatible step, creates a bounded-loop orchestrator that handles action branching and durable sleep, validates the orchestration with comprehensive tests, and exposes a server action with authentication and tracing.

## Changes

**Durable Outreach Workflow**

| Layer / File(s) | Summary |
|---|---|
| **Durable step wrapper** <br> `apps/web/lib/agents/servicer-outreach/outreach.steps.ts` | `runOutreachStep` wraps the core `runOutreach` function with Temporal step semantics: rebuilds dependencies, executes the core logic, logs PII-safe outcomes, and throws on send rejection (when `touchSent` is `null`) to trigger WDK retries. |
| **Workflow orchestrator** <br> `apps/web/lib/agents/servicer-outreach/outreach.workflow.ts` | `outreachWorkflow` implements a bounded-loop durable orchestration that repeatedly invokes `runOutreachStep` and branches on `action.kind`: returns immediately on `stop` or `unsupported_channel`, durably waits until `action.until` and continues on `wait`, or loops on `send` for the next evaluation. Throws if max iteration count is exceeded. |
| **Workflow behavior tests** <br> `apps/web/lib/agents/servicer-outreach/outreach.workflow.test.ts` | Vitest suite with mocked `sleep` and `runOutreachStep` validates three scenarios: normal send→sleep→step→stop orchestration, immediate return on `unsupported_channel` without sleep, and rejection with iteration error when evaluator does not terminate. Includes local helpers for mock result construction and a pinned iteration bound constant. |
| **Server-side durable action** <br> `apps/web/lib/agents/servicer-outreach/run-outreach-durable-action.ts` | `runOutreachFromDealDurable` server action authenticates the current Clerk org and user, loads corresponding database records, initiates `outreachWorkflow` via the Temporal API, and wraps execution with OpenTelemetry span instrumentation to record result attributes and error details. |

## Estimated code review effort

🎯 3 (Moderate) | ⏱️ ~25 minutes

## Possibly related PRs

- [connorbhickey/Project_CEMA#85](https://github.com/connorbhickey/Project_CEMA/pull/85): Introduces the core `buildOutreachDeps`, `runOutreach`, and `OutreachResult` contracts that are directly wrapped and orchestrated by this PR's durable step and workflow system.

## Poem

> 🐰 A rabbit leaps through Temporal dreams,  
> Step by step and sleep in streams,  
> Workflow loops with bounded grace,  
> Tracing paths through auth's embrace,  
> Outreach hops to every door! 🐇

</details>

<!-- walkthrough_end -->
<!-- pre_merge_checks_walkthrough_start -->

<details>
<summary>🚥 Pre-merge checks | ✅ 4 | ❌ 1</summary>

### ❌ Failed checks (1 warning)

|     Check name     | Status     | Explanation                                                                           | Resolution                                                                         |
| :----------------: | :--------- | :------------------------------------------------------------------------------------ | :--------------------------------------------------------------------------------- |
| Docstring Coverage | ⚠️ Warning | Docstring coverage is 50.00% which is insufficient. The required threshold is 80.00%. | Write docstrings for the functions missing them to satisfy the coverage threshold. |

<details>
<summary>✅ Passed checks (4 passed)</summary>

|         Check name         | Status   | Explanation                                                                                                                                                                                                     |
| :------------------------: | :------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|         Title check        | ✅ Passed | The title accurately reflects the main addition: introducing outreachWorkflow as a durable WDK wrapper around runOutreach, which is the core feature of this changeset.                                         |
|      Description check     | ✅ Passed | The description covers all required sections: Summary, Changes (through bullet points and detail), Test plan (with checkmarks and specific commands), and Compliance checklist (marked N/A with justification). |
|     Linked Issues check    | ✅ Passed | Check skipped because no linked issues were found for this pull request.                                                                                                                                        |
| Out of Scope Changes check | ✅ Passed | Check skipped because no linked issues were found for this pull request.                                                                                                                                        |

</details>

<sub>✏️ Tip: You can configure your own custom pre-merge checks in the settings.</sub>

</details>

<!-- pre_merge_checks_walkthrough_end -->
<!-- finishing_touch_checkbox_start -->

<details>
<summary>✨ Finishing Touches</summary>

<details>
<summary>📝 Generate docstrings</summary>

- [ ] <!-- {"checkboxId": "7962f53c-55bc-4827-bfbf-6a18da830691"} --> Create stacked PR
- [ ] <!-- {"checkboxId": "3e1879ae-f29b-4d0d-8e06-d12b7ba33d98"} --> Commit on current branch

</details>
<details>
<summary>🧪 Generate unit tests (beta)</summary>

- [ ] <!-- {"checkboxId": "f47ac10b-58cc-4372-a567-0e02b2c3d479", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Create PR with unit tests
- [ ] <!-- {"checkboxId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Commit unit tests in branch `feat/m12-outreach-wdk`

</details>

</details>

<!-- finishing_touch_checkbox_end -->
<!-- This is an auto-generated comment: all tool run failures by coderabbit.ai -->

> [!WARNING]
> There were issues while running some tools. Please review the errors and either fix the tool's configuration or disable the tool if it's a critical failure.
> 
> <details>
> <summary>🔧 ESLint</summary>
> 
> > If the error stems from missing dependencies, add them to the package.json file. For unrecoverable errors (e.g., due to private dependencies), disable the tool in the CodeRabbit configuration.
> 
> <details>
> <summary>apps/web/lib/agents/servicer-outreach/outreach.steps.ts</summary>
> 
> ESLint skipped: missing config or dependency (missing-dependency). The ESLint configuration references a package that is not available in the sandbox.
> 
> </details>
> 
> <details>
> <summary>apps/web/lib/agents/servicer-outreach/outreach.workflow.test.ts</summary>
> 
> ESLint skipped: the ESLint configuration for this file references a package that is not available in the sandbox.
> 
> </details>
> 
> <details>
> <summary>apps/web/lib/agents/servicer-outreach/outreach.workflow.ts</summary>
> 
> ESLint skipped: the ESLint configuration for this file references a package that is not available in the sandbox.
> 
> </details>
> 
> + 1 others
> 
> </details>

<!-- end of auto-generated comment: all tool run failures by coderabbit.ai -->
<!-- tips_start -->

---




<sub>Comment `@coderabbitai help` to get the list of available commands and usage tips.</sub>

<!-- tips_end -->
<!-- internal state start -->


<!-- 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 -->

<!-- internal state end -->
