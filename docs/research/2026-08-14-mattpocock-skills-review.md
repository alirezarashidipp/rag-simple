# Review of `mattpocock/skills` for `rag-simple`

Reviewed upstream `main` at commit [`8b78b531ab965735c5dc74f6f7a219e1e37326df`](https://github.com/mattpocock/skills/tree/8b78b531ab965735c5dc74f6f7a219e1e37326df) on 2026-08-14.

## Project fit

This repository is a deliberately small Flask learning app. `app.py` contains the PDF extraction, chunking, OpenAI embedding/chat calls, Pinecone access, and HTTP routes. `templates/index.html` contains the complete browser UI and interactive RAG lessons. That makes the highest-value skills the ones that preserve the project's simplicity while providing disciplined workflows for product decisions, external facts, module seams, implementation, debugging, and review.

## Selected skills

### 1. `grilling`

**What it does:** Turns a plan or design into a dependency-aware design tree. It asks the currently unblocked questions in numbered rounds, recommends an answer for each, waits for the user's decisions, and does not act until shared understanding is confirmed.

**When Codex should use it here:** Use when the user explicitly asks to be grilled or wants to stress-test an unsettled product or architecture decision—for example, multi-document isolation, index reset semantics, retrieval strategy, source display, or provider choices. Do not invoke it for a narrow, already-specified edit.

**Primary source:** [`skills/productivity/grilling/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/productivity/grilling/SKILL.md)

### 2. `research`

**What it does:** Delegates a research question to a background agent, requires high-trust primary sources, and saves cited findings in a single Markdown file in the repository.

**When Codex should use it here:** Use for current external facts about OpenAI, Pinecone, Flask, `pypdf`, RAG evaluation, security guidance, model behavior, or provider limits. Do not use it for behavior that can be established directly from this repository. Because the skill writes a note, Codex should only follow that part when the user's requested scope permits repository writes.

**Primary source:** [`skills/engineering/research/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/research/SKILL.md)

### 3. `codebase-design`

**What it does:** Supplies a precise vocabulary and principles for deep modules: small interfaces, well-placed seams, adapters, dependency injection, leverage, locality, and testability.

**When Codex should use it here:** Use when designing or restructuring the seams among Flask routes, PDF parsing and chunking, OpenAI calls, Pinecone access, and answer construction; when deciding where dependency injection belongs; or when the current single-file backend becomes difficult to test or navigate. Do not use it for routine localized edits.

**Primary source:** [`skills/engineering/codebase-design/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/codebase-design/SKILL.md)

### 4. `tdd`

**What it does:** Runs a red-to-green, one-vertical-slice-at-a-time implementation loop. Tests verify behavior through public interfaces at user-confirmed seams and avoid tests coupled to implementation details.

**When Codex should use it here:** Use when the user asks for test-first work, red-green-refactor, integration tests, or authorizes a concrete feature or bug fix whose expected behavior is settled. For this app, likely seams include pure chunking behavior and Flask endpoint behavior with external OpenAI/Pinecone adapters replaced at their seams. Agree the seams with the user before writing tests.

**Primary source:** [`skills/engineering/tdd/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/tdd/SKILL.md)

### 5. `diagnosing-bugs`

**What it does:** Requires a fast, deterministic, red-capable reproduction before forming theories; then minimizes the case, ranks falsifiable hypotheses, instruments one variable at a time, fixes the cause, adds a regression test when a valid seam exists, and cleans up. It explicitly requires secrets to be redacted.

**When Codex should use it here:** Use when the user reports broken, throwing, failing, flaky, or slow behavior in PDF upload, extraction, chunking, embedding, Pinecone indexing/querying, answer generation, or the browser UI. Diagnose before editing. Keep API keys, auth headers, uploaded document contents, and other sensitive artifacts out of displayed logs.

**Primary source:** [`skills/engineering/diagnosing-bugs/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/diagnosing-bugs/SKILL.md)

### 6. `code-review`

**What it does:** Reviews a non-empty diff from a fixed point along two deliberately separate axes: repository standards and fidelity to the originating specification. It uses parallel review agents and preserves the distinction between the two result sets.

**When Codex should use it here:** Use when the user asks to review a branch, pull request, work in progress, or changes since a named commit/branch/tag. First pin and validate the fixed point, then locate the relevant specification and repository standards. If no specification exists, say so and review only the standards axis rather than inventing requirements.

**Primary source:** [`skills/engineering/code-review/SKILL.md`](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/code-review/SKILL.md)

## Why these do not overlap

Each skill owns a different kind of work:

1. `grilling` settles user decisions.
2. `research` establishes external facts.
3. `codebase-design` chooses production interfaces and seams.
4. `tdd` implements settled behavior through executable examples.
5. `diagnosing-bugs` investigates an observed failure before changing code.
6. `code-review` audits an existing diff against standards and a specification.

The trigger should be the nature of the current task, not a generic instruction to run all six.

## Deliberate exclusions

- `grill-me` is a user-facing wrapper over `grilling`, so selecting both would duplicate the same interview workflow. [Source](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/productivity/grill-me/SKILL.md)
- `implement` orchestrates TDD and code review and ends by committing, so it overlaps two selected skills and is too broad to make an automatic project rule. [Source](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/implement/SKILL.md)
- `prototype` is useful for explicitly requested throwaway UI or state experiments, but it is not central to the current app and would blur the line with early design work if made a default trigger. [Source](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/prototype/SKILL.md)
- `improve-codebase-architecture` overlaps `codebase-design` and adds a heavier survey-and-grill workflow than this small repository currently needs. [Source](https://github.com/mattpocock/skills/blob/8b78b531ab965735c5dc74f6f7a219e1e37326df/skills/engineering/improve-codebase-architecture/SKILL.md)
- TypeScript-, Husky-, Claude Code-, issue-tracker-, writing-, and course-scaffolding-specific skills do not match the present Python/Flask repository or its immediate workflow.

## Suggested `AGENTS.md` policy shape

Use one short trigger rule per selected skill, preserve the distinctions above, and state that explicit user instructions override automatic selection. In particular, an observed failure should route to `diagnosing-bugs`; an authorized implementation with settled behavior should route to `tdd`; and a request to inspect an already-existing diff should route to `code-review`.
