---
name: markdown_documentation_standards
description: Triggers when writing, updating, or formatting markdown documentation, build plans, technical guides, or architecture docs in the workspace.
---

# Markdown Documentation Standards

This skill defines the mandatory structure, design patterns, and aesthetic standards for writing technical documentation, build plans, roadmap guides, and architecture specs in this repository.

---

## 1. Header & Metadata Block

Every plan, guide, or architecture document must start with a standardized header block containing metadata, followed by a horizontal separator:

```markdown
# [Title of Document]

> **Author:** Antigravity AI · **Date:** YYYY-MM-DD  
> **Purpose / Strategy:** High-level one-line summary  
> **Baseline / Metrics:** Key baseline metrics or current system state  
> **Defaults / Scope:** Staking, threshold, or scope defaults

---
```

---

## 2. Executive Summary & Overview

Directly below the header, include an **Executive Summary** that gives a quick overview of the goal, scope, and structural boundaries.

- **Non-destructive principle**: Highlight that new features should be additive (e.g., zero modifications to core models unless explicitly intended).
- **Phase Overview Table**: Summarize phases or modules in a structured table:

```markdown
### Phase Overview

| # | Phase | Tier | Effort | Files Created |
|---|-------|------|:------:|---------------|
| 1 | Component Name | Infrastructure | 🟡 Medium | `path/to/file.py` |
| 2 | Feature Engine | Core Logic | 🟢 Low | `path/to/file2.py` |
| 3 | Heavy Module | Integration | 🔴 High | `path/to/file3.py` |
```

Effort / Priority Emojis:
- 🟢 Low Effort / Low Risk
- 🟡 Medium Effort / Medium Risk
- 🔴 High Effort / Critical Priority

---

## 3. File Structure & Dependencies

Provide clear context on where files live and what libraries are required before detailing step-by-step logic.

- **Directory Tree**: Use code blocks displaying exact file locations and phase mappings.
- **Dependencies Table**: List required Python packages, purpose, and installation commands (`pip install ...`).

---

## 4. Phase Execution Flow & ASCII Diagrams

Include a visual flowchart illustrating execution order, data pipeline steps, or module interactions using clean ASCII diagrams:

```markdown
```
Phase 1: First Component
    │
    ▼
Phase 2: Second Component
    │
    ▼
Phase 3: Integration & Output
```
```

---

## 5. Phase / Section Deep Dives

For each phase, feature, or step in the build plan, use the standardized triple-subsection pattern:

```markdown
## Phase N: [Phase Title]

**File:** `src/module/filename.py` (NEW / MODIFY)  
**Priority:** 🔴 Critical / 🟡 Medium / 🟢 Low  
**Dependencies:** Required upstream modules or packages

### Problem
Concise description of what problem this phase solves and why it is needed.

### Implementation
Step-by-step technical execution details, including:
- Classes, signatures, formulas, or code stubs
- Key logic & data flow
- Sub-steps numbered 1, 2, 3

### Verification
Concrete, executable shell/python command to test and verify the phase independently:
```bash
py -c "from src.module import Component; ..."
```
Expected output description.
```

---

## 6. Callout Blocks (GitHub Alerts)

Use GitHub blockquote alerts strategically to draw attention to important rules, warnings, or notes:

- `> [!IMPORTANT]` — Key architectural decisions or workflow requirements
- `> [!WARNING]` — Caveats, potential biases, or performance pitfalls
- `> [!CAUTION]` — High-risk actions, breaking changes, or non-regression mandates
- `> [!NOTE]` — Helpful background context or supplementary info

---

## 7. Tracking, Validation & Risk Assessment

Conclude build plans and technical guides with progress tracking, regression rules, and risk mitigation.

### Implementation Tracking Table
```markdown
## Implementation Tracking

| Phase | Component | Status | Notes |
|-------|-----------|:------:|-------|
| 1 | Description | `[x] Completed` | Note on completion |
| 2 | Description | `[ ]` | Pending |
```

### Live Progress Updates (mandatory while implementing)

A build plan is not a write-once artifact. **The moment a phase is actually implemented — not just planned — its row in the Implementation Tracking Table must be updated immediately**, before moving to the next phase. This applies whether the implementer is a human or an AI agent executing the plan.

Each completed row's **Notes** column must summarize the real outcome, not just flip the checkbox:
- What was built (file path, if it deviated from the plan's original design).
- The concrete verification result — actual numbers from the phase's `Verification` command (metrics, pass/fail, error rates), not a restatement of the expected output block.
- Any deviation from the plan as originally written (e.g. an added parameter, a different library choice) and why.

```markdown
| 1 | Delivery-Outcome Model | `[x] Completed` | Two-stage multinomial, GroupKFold(5)+final. Marginals match empirical within ±0.2pp; log loss 1.4166 vs 1.4788 naive baseline; top-1 acc 44.7% vs 35.4% baseline |
| 2 | Innings Simulator | `[ ]` | Pending |
```

> [!IMPORTANT]
> Update the tracking table as work happens, phase by phase — never batch updates to the end of an implementation session. A plan whose tracking table lags behind actual progress is worse than no tracking table: it actively misleads anyone (including a future session) who reads it to gauge status.

### Risk Assessment Matrix
```markdown
## Risk Assessment

| Risk | Severity | Mitigation |
|------|:--------:|------------|
| Potential Issue | 🟡 Medium | Concrete mitigation strategy |
```

### Regression Guard
Always include a explicit caution section emphasizing system stability and read-only / additive constraints where applicable.
