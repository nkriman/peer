<!-- This is an auto-generated comment: summarize by coderabbit.ai -->
<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->

> [!WARNING]
> ## Review limit reached
> 
> `@DisabledAbel`, we couldn't start this review because you've reached your PR review rate limit.
> 
> More reviews will be available in 54 minutes and 30 seconds. [Learn how PR review limits work](https://docs.coderabbit.ai/management/plans#fair-usage-limits-policy).
> 
> Your organization has run out of usage credits. Purchase more in the [billing tab](https://app.coderabbit.ai/settings/subscription?tab=usage&tenantId=3d5033f6-e7f2-4c96-8544-7379dff98cbf).
> 
> <details>
> <summary>⌛ How to resolve this issue?</summary>
> 
> After more reviews become available, a review can be triggered using the `@coderabbitai review` command as a PR comment. Alternatively, push new commits to this PR.
> 
> We recommend that you space out your commits to avoid hitting the rate limit.
> 
> </details>
> 
> 
> <details>
> <summary>🚦 How do rate limits work?</summary>
> 
> CodeRabbit enforces hourly rate limits for each developer per organization.
> 
> Our paid plans include higher PR review limits than trial, open-source, and free plans. In all cases, reviews become available again over time. During sustained high-volume PR review activity, CodeRabbit may temporarily slow when the next review becomes available.
> 
> Please see our [Fair Usage Limits Policy](https://docs.coderabbit.ai/management/plans#fair-usage-limits-policy) for further information.
> 
> </details>
> 
> <details>
> <summary>ℹ️ Review info</summary>
> 
> <details>
> <summary>⚙️ Run configuration</summary>
> 
> **Configuration used**: defaults
> 
> **Review profile**: CHILL
> 
> **Plan**: Pro
> 
> **Run ID**: `840f7e15-dc5c-4d5e-9a66-33bce95fbbb3`
> 
> </details>
> 
> <details>
> <summary>📥 Commits</summary>
> 
> Reviewing files that changed from the base of the PR and between 0ba66f70cff45ec17ba4dbd1dca114c7d9afefae and 0add8c754775383b918f45a9e397ecb82beeecbe.
> 
> </details>
> 
> <details>
> <summary>📒 Files selected for processing (1)</summary>
> 
> * `README.md`
> 
> </details>
> 
> </details>

<!-- end of auto-generated comment: rate limited by coderabbit.ai -->

<!-- walkthrough_start -->

<details>
<summary>📝 Walkthrough</summary>

## Walkthrough

This pull request updates the README.md to improve clarity around local setup and Vercel deployment. The Vercel badge link is configured with a repository URL parameter, local run instructions are restructured into explicit clone, install, and run steps, and the deployment section references the badge and clarifies repository structure.

## Changes

**Setup and Deployment Documentation**

| Layer / File(s) | Summary |
|---|---|
| **Setup and deployment documentation** <br> `README.md` | Vercel deployment badge links to a specific repository URL; "Run locally" section restructures instructions into explicit clone/install/run steps; Vercel deployment section clarifies repository components and provides command-line deployment as an alternative method. |

## Estimated code review effort

🎯 1 (Trivial) | ⏱️ ~3 minutes

## Poem

> 📖 A readme refined with care,
> Setup steps laid crystal clear,
> Deploy buttons bright and true,
> Local clones quick to pursue,
> Clarity blooms, confusion fades away! 🐰

</details>

<!-- walkthrough_end -->
<!-- pre_merge_checks_walkthrough_start -->

<details>
<summary>🚥 Pre-merge checks | ✅ 5</summary>

<details>
<summary>✅ Passed checks (5 passed)</summary>

|         Check name         | Status   | Explanation                                                                                                                           |
| :------------------------: | :------- | :------------------------------------------------------------------------------------------------------------------------------------ |
|      Description Check     | ✅ Passed | Check skipped - CodeRabbit’s high-level summary is enabled.                                                                           |
|         Title check        | ✅ Passed | The title accurately summarizes the main changes: adding local setup commands and a Vercel deploy button to the README documentation. |
|     Docstring Coverage     | ✅ Passed | No functions found in the changed files to evaluate docstring coverage. Skipping docstring coverage check.                            |
|     Linked Issues check    | ✅ Passed | Check skipped because no linked issues were found for this pull request.                                                              |
| Out of Scope Changes check | ✅ Passed | Check skipped because no linked issues were found for this pull request.                                                              |

</details>

<sub>✏️ Tip: You can configure your own custom pre-merge checks in the settings.</sub>

</details>

<!-- pre_merge_checks_walkthrough_end -->
<!-- finishing_touch_checkbox_start -->

<details>
<summary>✨ Finishing Touches</summary>

<details>
<summary>🧪 Generate unit tests (beta)</summary>

- [ ] <!-- {"checkboxId": "f47ac10b-58cc-4372-a567-0e02b2c3d479", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Create PR with unit tests
- [ ] <!-- {"checkboxId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8", "radioGroupId": "utg-output-choice-group-unknown_comment_id"} -->   Commit unit tests in branch `codex/update-readme-with-local-setup-instructions`

</details>

</details>

<!-- finishing_touch_checkbox_end -->
<!-- tips_start -->

---

Thanks for using [CodeRabbit](https://coderabbit.ai?utm_source=oss&utm_medium=github&utm_campaign=DisabledAbel/MakeICS&utm_content=5)! It's free for OSS, and your support helps us grow. If you like it, consider giving us a shout-out.

<details>
<summary>❤️ Share</summary>

- [X](https://twitter.com/intent/tweet?text=I%20just%20used%20%40coderabbitai%20for%20my%20code%20review%2C%20and%20it%27s%20fantastic%21%20It%27s%20free%20for%20OSS%20and%20offers%20a%20free%20trial%20for%20the%20proprietary%20code.%20Check%20it%20out%3A&url=https%3A//coderabbit.ai)
- [Mastodon](https://mastodon.social/share?text=I%20just%20used%20%40coderabbitai%20for%20my%20code%20review%2C%20and%20it%27s%20fantastic%21%20It%27s%20free%20for%20OSS%20and%20offers%20a%20free%20trial%20for%20the%20proprietary%20code.%20Check%20it%20out%3A%20https%3A%2F%2Fcoderabbit.ai)
- [Reddit](https://www.reddit.com/submit?title=Great%20tool%20for%20code%20review%20-%20CodeRabbit&text=I%20just%20used%20CodeRabbit%20for%20my%20code%20review%2C%20and%20it%27s%20fantastic%21%20It%27s%20free%20for%20OSS%20and%20offers%20a%20free%20trial%20for%20proprietary%20code.%20Check%20it%20out%3A%20https%3A//coderabbit.ai)
- [LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https%3A%2F%2Fcoderabbit.ai&mini=true&title=Great%20tool%20for%20code%20review%20-%20CodeRabbit&summary=I%20just%20used%20CodeRabbit%20for%20my%20code%20review%2C%20and%20it%27s%20fantastic%21%20It%27s%20free%20for%20OSS%20and%20offers%20a%20free%20trial%20for%20proprietary%20code)

</details>


<sub>Comment `@coderabbitai help` to get the list of available commands and usage tips.</sub>

<!-- tips_end -->
<!-- internal state start -->


<!-- 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= -->

<!-- internal state end -->
