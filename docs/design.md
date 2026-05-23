# Design rationale

> Companion document to the README. Explains the *why* behind `peer`'s
> design choices, intended to evolve into a full essay once v0.1 ships.

## The problem

Commercial AI PR reviewers are good enough for many teams. They are not
good enough for every team, because:

- Some codebases cannot be shared with a third party (security, compliance,
  regulatory).
- Some teams have strong opinions about review style — what to flag, what
  to ignore, how to phrase suggestions, how to weight severity.
- Some teams want the agent to use *their* specific terminology, internal
  norms, and review history.
- Some teams want to instrument their own agent's quality over time, not
  trust a vendor's marketing.

These teams build their own. Each team rebuilds the same plumbing.

There is currently no opinionated open-source framework for the PR-review
shape specifically. Codium's PR-Agent (the older OSS version) is the
closest, but Codium is now Qodo and the project's direction is commercial.
GitHub's `gh-aw` is a generic agentic-workflow runner, not specifically
shaped for PR review. Aider and OpenHands are general autonomous coding
agents.

`peer` is the framework that sits in this gap.

## Why eval-first

The harness around an agent matters more than the prompt inside it.
Specifically for PR review:

- A review agent that flags 100 things, 80 of which are noise, makes
  developers ignore the agent.
- A review agent that flags 5 things, all of which are real, makes
  developers trust it.
- The difference is measurement, not the model.

`peer` is designed so that every architectural choice can be measured.
The eval harness is a first-class part of the framework, not an add-on,
because shipping a PR review agent without measurement is shipping noise.

## Mining historical reviews as the gold standard

Most code review evaluation either invents synthetic test cases (slow,
expensive, biased toward the inventor's intuitions) or relies on a small
hand-labeled set (doesn't generalize, doesn't reflect your team's actual
review culture).

`peer` takes a third path: **your repository's own historical PR reviews
are the gold standard.**

This works because:

1. Active open-source projects (and most healthy private codebases)
   contain thousands of PRs with real human review comments, by real
   maintainers, against real changes. That's a large, free, repo-specific
   training/eval set.
2. The reviewers' judgments encode the team's standards better than any
   external rubric could.
3. Pre-AI-tool era PRs (roughly pre-2024) are particularly clean — they
   pre-date the commercial PR-review-bot adoption that now contaminates
   recent PRs with non-human comments.

The eval harness samples PRs from the configured date range, runs the
agent under test on each PR with the human reviews hidden, then scores
the agent's output against what the humans actually said.

## Non-goals

`peer` is **not**:

- A commercial PR review tool. Use CodeRabbit, Greptile, or similar if
  that's what you want.
- A general-purpose code review LLM. It is specifically for the PR
  review shape.
- A standalone benchmark. The eval is a feature of the framework. A
  separate public benchmark (`peer` reference agent vs commercial tools)
  may be published alongside, but the framework is the project.

## Open design questions

- Severity taxonomy: critical/important/minor/nit, or a more granular set?
- Comment substance judging: LLM-as-judge with what rubric?
- How to handle the case where the agent flags something the human reviewer
  *missed* but which is actually a real issue? (False-positive measurement
  is genuinely hard — needs to be addressed honestly in v0.1.)
- How to handle multi-turn discussion (agent comment → author response →
  reviewer follow-up) when the historical data is a flat list of comments?

All of these will be worked through in v0.1 and documented as the project
evolves.
