<!-- Sync Impact Report
Version change: none -> 1.0.0
Modified principles: placeholders replaced with project-specific principles
Added sections: Operational Constraints, Development Workflow
Removed sections: none
Templates requiring updates: ✅ .specify/templates/plan-template.md (no change needed), ✅ .specify/templates/spec-template.md (no change needed), ✅ .specify/templates/tasks-template.md (no change needed)
Follow-up TODOs: none
-->

# rag-simple-claude Constitution

## Core Principles

### I. Simple, Learnable RAG
Project design MUST favor a minimal, understandable retrieval pipeline: PDF upload → text extraction → chunking → embedding → index search → answer. Implementation MUST avoid premature complexity and keep the codebase easy to read for learning and maintenance.

### II. Source-Grounded Answers
Every user-facing answer MUST be anchored to retrieved document sources. The system MUST answer only from the top-ranked Pinecone chunks and otherwise report that the information is unavailable.

### III. Observable Behavior
The application MUST expose clear, measurable signals for ingestion, search, and response generation. Metrics, index stats, and request timings MUST be available so regressions are detectable and debugging remains local.

### IV. Secure, Configurable Operation
Secrets and deploy-time values MUST live in environment configuration (`.env.local`) and never be hard-coded. External service access is allowed only through explicit configuration, and local development MUST remain reproducible without embedded credentials.

### V. Documented Learning
Design, usage, and troubleshooting MUST be documented in `README.md`, code comments, and user-facing UI text. Educational intent is part of the project’s value: architecture and RAG tradeoffs MUST be visible to anyone reading the repository.

## Operational Constraints
The app MUST remain a single Flask service with no hidden runtime subsystems. Runtime behavior is constrained to: PDF import, text chunking, OpenAI embeddings, Pinecone vector search, chat completion, and simple browser UI. No extra microservices, scheduled jobs, or hidden data pipelines are acceptable for this project.

## Development Workflow
Work MUST follow a local, incremental workflow: create or update a feature, verify against the existing README and app behavior, then commit with a clear explanation of how it preserves or extends the constitution. Changes to chunking, search, or prompts require explicit justification in the PR description.

## Governance
This constitution is the authoritative guide for architecture, feature decisions, and documentation priorities in `rag-simple-claude`.
- Amendments require a PR with the proposed text changes, rationale linked to the current principles, and a version bump.
- All code and documentation must be reviewed for consistency with the principles before merge.
- Use MAJOR for principle or governance changes, MINOR for added sections or new project-wide constraints, PATCH for clarifications and wording refinements.
- The current version is the source of truth for compliance reviews; any implementation that violates a principle must include an explicit exception rationale.

**Version**: 1.0.0 | **Ratified**: 2026-07-28 | **Last Amended**: 2026-07-28
