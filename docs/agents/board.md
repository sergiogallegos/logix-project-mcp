# Product task board

**1.0 outcome.** An engineer can select the project they have open in Studio 5000, share its latest saved `.ACD` with an MCP client, inspect and compare the project, review a proposed offline edit, and reopen a validated `.ACD` copy or import the reviewed `.L5X` component into Studio 5000. The server also supports the documented `.L5K` and `.L5X` workflows.

**Current progress.** [LPM-031](tasks.md#lpm-031) and [LPM-032](tasks.md#lpm-032): documentation-only slices are implemented and verified. Reviewed controller, program, scoped tag, and existing Ladder/ST routine descriptions can be created, replaced, or removed in a new full UTF-8 L5X copy. Broader tag and routine operations in the original briefs remain unimplemented. [LPM-050](tasks.md#lpm-050), the independent read-only diagnostics feasibility review, is complete. LPM-033 still depends on LPM-031 and LPM-032.

Follow the [agent workflow](README.md) and record acceptance evidence in the [handoff log](handoff.md). Each task links to its deliverable and verification criteria.

| Task | Deliverable | Depends on | Status | Owner |
| --- | --- | --- | --- | --- |
| [LPM-000](tasks.md#lpm-000) | Python MCP and read-only baseline | — | Done | — |
| [LPM-001](tasks.md#lpm-001) | Windows SDK and client launch diagnostics | — | Done | Codex on `lpm-001-windows-sdk-diagnostics` |
| [LPM-002](tasks.md#lpm-002) | Snapshot consistency and SDK worker lifecycle | — | Done | Codex on `main` |
| [LPM-003](tasks.md#lpm-003) | Format and revision compatibility matrix | LPM-001, LPM-002 | Done | Codex on `main` |
| [LPM-004](tasks.md#lpm-004) | GitHub bootstrap and first hosted CI run | — | Done | — |
| [LPM-010](tasks.md#lpm-010) | Stable MCP schemas and capability reporting | — | Done | Codex on `main` |
| [LPM-011](tasks.md#lpm-011) | Controller and project inventory | LPM-010 | Done | Codex on `main` |
| [LPM-012](tasks.md#lpm-012) | Routine inspection by language | LPM-010 | Done | Codex on `main` |
| [LPM-013](tasks.md#lpm-013) | Scoped search and cross-references | LPM-011, LPM-012 | Done | Codex on `main` |
| [LPM-014](tasks.md#lpm-014) | Reviewable project comparison | LPM-002, LPM-011, LPM-012 | Done | Codex on `main` |
| [LPM-015](tasks.md#lpm-015) | Full and component export | LPM-002, LPM-003 | Done | Codex on `main` |
| [LPM-020](tasks.md#lpm-020) | Studio 5000 integration feasibility | — | Done | Codex on `main` |
| [LPM-021](tasks.md#lpm-021) | Share and refresh a selected project | LPM-002, LPM-020 | Done | Codex on `main` |
| [LPM-022](tasks.md#lpm-022) | Installable Studio 5000 Tools menu entry | LPM-021 | Done | Codex on `main` |
| [LPM-016](tasks.md#lpm-016) | SHA-256 native snapshot cache | LPM-002, LPM-021 | Done | Codex on `main` |
| [LPM-024](tasks.md#lpm-024) | Direct Codex MCP connection and persistent selection | LPM-021, LPM-022 | Done | Codex on `main` |
| [LPM-030](tasks.md#lpm-030) | Typed offline change proposals | LPM-010, LPM-014 | Done | Codex on `main` |
| [LPM-031](tasks.md#lpm-031) | Offline tag and metadata edits | LPM-011, LPM-030 | In progress | Codex on `main` |
| [LPM-032](tasks.md#lpm-032) | Offline ladder and structured text edits | LPM-012, LPM-030 | In progress | Codex on `main` |
| [LPM-033](tasks.md#lpm-033) | Staged `.ACD` and `.L5X` outputs | LPM-015, LPM-031, LPM-032 | Planned | — |
| [LPM-034](tasks.md#lpm-034) | Logix verification and preservation checks | LPM-003, LPM-033 | Planned | — |
| [LPM-035](tasks.md#lpm-035) | Local review, approval, and artifact finalization | LPM-030, LPM-034 | Planned | — |
| [LPM-023](tasks.md#lpm-023) | Open or import reviewed artifacts in Studio 5000 | LPM-022, LPM-035 | Planned | — |
| [LPM-040](tasks.md#lpm-040) | Failure recovery, file boundaries, and diagnostics | LPM-002, LPM-021, LPM-033 | Planned | — |
| [LPM-041](tasks.md#lpm-041) | Large-project performance and reliability | LPM-013, LPM-014, LPM-016, LPM-040 | Planned | — |
| [LPM-042](tasks.md#lpm-042) | Packaging, clean installs, and release CI | LPM-001, LPM-022, LPM-035, LPM-040 | Planned | — |
| [LPM-043](tasks.md#lpm-043) | End-to-end engineer acceptance | LPM-003, LPM-023, LPM-041, LPM-042 | Planned | — |
| [LPM-044](tasks.md#lpm-044) | User documentation and support guide | LPM-042, LPM-043 | Planned | — |
| [LPM-045](tasks.md#lpm-045) | Review and publish 1.0 | LPM-004, LPM-044 | Planned | — |
| [LPM-050](tasks.md#lpm-050) | Read-only diagnostics feasibility | LPM-016, LPM-024 | Done | Codex on `main` |

## 1.0 release gate

- Clean installation works in the documented MCP clients, with the SDK-free `.L5X` path and the supported Windows native path verified.
- Saved `.ACD` selection, review, staged edit, verification, and reopen work end to end. The source stays intact. A stale proposal prompts a refresh before approval.
- The compatibility matrix identifies which revisions and formats were tested, which editing operations are supported, and how the Studio 5000 menu handles unsaved work.
- CI passes, built artifacts reproduce the tested behavior, and the maintainer approves publication.
