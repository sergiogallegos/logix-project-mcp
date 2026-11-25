# Agent handoff log

## 2026-11-23 · LPM-000 · Done

The local Python starter implements `get_project`, `list_tags`, and `read_routine` over MCP stdio. The synthetic `.L5X` test exercised all three tools. The Windows SDK smoke test read a Logix Designer 35.00 `.ACD` sample and its generated `.L5K` with the Rockwell Python wheel 2.0.2 and confirmed both source hashes were unchanged. Wheel build, dependency checks, and both agent skill validators passed.

The native tests passed with the inherited Windows environment. A reduced MCP child environment timed out on this host. The repository has a GitHub remote, and the managed process cannot access the GitHub CLI configuration or Windows credential store. Hosted CI is pending the first push.

## 2026-11-23 · LPM-004 · Blocked

The public remote is reachable and has no `HEAD` yet. GitHub CLI sign-in and Git's credential helper require credential storage that the managed process cannot access. Authenticate in a regular Windows PowerShell window, verify the active GitHub identity and remote write access, then proceed with the authorized initial push. The next ready product task is LPM-001.

## 2026-11-23 · LPM-004 · Done

The maintainer pushed `main` from their Windows PowerShell session using a command-scoped Git trust setting for the repository. `git ls-remote` confirmed that GitHub's default branch and local `main` both point to `2dfe3fa`. The first [hosted CI run](https://github.com/sergiogallegos/logix-project-mcp/actions/runs/45275063747) completed successfully for that commit. The next ready product task is LPM-001.

## 2026-11-23 · LPM-001 · Done · Codex on `lpm-001-windows-sdk-diagnostics`

Added `logix-project-mcp-doctor` and documented the MCP launch environment. The original reduced configuration with only `DOTNET_ROOT` forwarded reproduced a Rockwell SDK timeout. With `ProgramFiles` forwarded from the working Windows environment, the Python MCP client's reduced configuration and the inherited configuration both read the same Logix Designer 35.00 `.ACD` sample. The source SHA-256 was unchanged. The host was Windows 11 build 26200 with Python 3.12.10 x64, Python SDK 2.0.2, and .NET 10.0.11.

A fresh wheel installation without Rockwell's SDK passed the SDK-free stdio and diagnostic tests, opened a Rockwell `.L5X` sample at revision 17.00, and returned exit code 1 with installation guidance for a native project. `pip check` passed. The full compatibility matrix remains in LPM-003. The next ready task is LPM-002.

## 2026-11-24 · LPM-002 · Done · Codex on `main`

Each tool reads a verified temporary snapshot of the selected project and returns its `source_sha256`. The SDK-free wheel passed the MCP schema and stdio checks, including concurrent reads and recovery after a missing source. Regression tests rejected a same-size rewrite with a restored modification time and verified that cancellation and timeout reap a stand-in SDK process and allow the next read.

On Windows 11 build 26200 with Python 3.12.10 x64 and Rockwell's Python SDK 2.0.2, all eight tests passed against an SDK-created Logix Designer 38.02 `.ACD` and again against its `.L5K` export. Each run read the selected source twice over MCP. Both reads matched the source SHA-256, and the source hash was unchanged after each run. Wheel build and `pip check` passed. An upgraded legacy Rockwell sample returned `SetRSLinxEdition` during both a direct SDK call and an MCP read. LPM-003 is ready to document format and revision compatibility.

## 2026-11-24 · LPM-003 · Done · Codex on `main`

Published the [compatibility matrix](../compatibility.md) with the tested versions, operations, and fixture recipe. MCP stdio reported revision 38.02 for the paired synthetic `.ACD` and `.L5K` with Rockwell Python wheel 2.0.2. A separate SDK-free Python environment read full `.L5X` exports at 38.02 and 17.00. The 17.00 Rockwell sample exercised controller and program tags and routine XML. Every successful tool response matched its source SHA-256.

The 26.00 Rockwell `.ACD` returned `SetRSLinxEdition` on this host. The missing-wheel case returned installation guidance through MCP, and the diagnostic command exited with code 1. The checks preserved every source hash. The fixture recipe generated all three formats, and the SDK-free suite and `pip check` passed. LPM-015 is now ready. The next task in board order is LPM-010.

## 2026-11-24 · LPM-010 · Done · Codex on `main`

Published the [MCP tool contract](../mcp-contract.md) and added `get_capabilities` with contract version 1. The original tools retain their result fields and text content shapes. `get_project` adds a normalized format, and the read tools retain their source SHA-256. Expected failures return `isError` and a documented code in `_meta`. Calls with undeclared arguments return `invalid_arguments`.

The SDK-free wheel passed discovery, valid calls, invalid arguments, lookup failures, malformed exports, and recovery through MCP stdio. The missing-wheel probe verified the capability flag and `sdk_error` diagnostic with the source hash unchanged. The native stdio tests passed on Windows 11 build 26200 with Python 3.12.10 x64 and Rockwell Python wheel 2.0.2 using Logix Designer 38.02 `.ACD` and `.L5K` samples. Both formats preserved their source hashes. The wheel build and `pip check` passed. LPM-011 and LPM-012 are ready, with LPM-011 next in board order.

## 2026-11-24 · LPM-011 · Done · Codex on `main`

Added [`get_inventory`](../mcp-contract.md#project-inventory) for controller metadata, scheduled tasks, programs, scoped tags, modules, user-defined types, and Add-On Instruction metadata. It preserves schedule order and qualifies program tags and routines by program. Synthetic stdio tests checked repeated names, absent sections, invalid arguments, and encoded and encrypted records. The inventory surfaced their metadata without returning protected payloads or routine bodies.

The SDK-free wheel passed the test suite and `pip check`. Rockwell's 17.00 `Add_On_Instructions_Samples.L5X` matched the exported schedule, program tags, 3 user-defined types, and 26 Add-On Instructions. `Coord_Motion_Drill_Cycle_Infeed_Blend.L5X` verified event-trigger fields. MCP returned inventory for the 38.02 synthetic `.ACD`, `.L5K`, and `.L5X` with unchanged source hashes. Native probes used Windows 11 build 26200, Python 3.12.10 x64, and Rockwell Python wheel 2.0.2. Protected-content coverage used synthetic exports. LPM-012 is next.

## 2026-11-24 · LPM-012 · Done · Codex on `main`

Extended [`read_routine`](../mcp-contract.md#routine-inspection) with numbered ladder and Structured Text source, structured Function Block and Sequential Function Chart elements, and readable, protected, and unsupported statuses. Available XML stays in `result`. Protected routines return metadata and a protection message. Synthetic stdio tests covered duplicate routine names, exact whitespace and comments, separate online-edit sections, protection, and absent or unsupported content.

The SDK-free wheel passed the test suite and `pip check`. Routine projections matched Rockwell's full `DayOfWeek.L5X`, `ST_Motion_Example.L5X`, `FBDLevelControlSimulation.L5X`, and `SFC_GearChange.L5X` samples. An SDK-generated Structured Text fixture passed through MCP from `.ACD` and `.L5K` at Logix Designer revision 38.02, using Windows 11 build 26200, Python 3.12.10 x64, and Rockwell wheel 2.0.2. All source hashes stayed unchanged. Protected records were verified with synthetic exports. LPM-013 and LPM-014 are ready, with LPM-013 next.

## 2026-11-24 · LPM-013 · Done · Codex on `main`

Added [`search_project` and `find_references`](../mcp-contract.md#scoped-search-and-cross-references) with scope, saved source identity, and bounded pages. The index resolves declared base symbols and exposes alias chains, source positions, and the reference relationships documented in the contract. Synthetic stdio tests covered name collisions, qualified operands, false substring matches, quoted text and comments, alias cycles, protected logic, and a 230-reference sequence with stale-page rejection.

The SDK-free wheel passed the test suite and `pip check`. Rockwell's revision 17.00 `DayOfWeek.L5X` returned eight scoped references to `TestDateTime`. On Windows 11 build 26200 with Python 3.12.10 x64 and Rockwell's Python wheel 2.0.2, SDK-generated `.ACD` and `.L5K` fixtures at revision 38.02 each returned two references to the selected program tag. All source hashes stayed unchanged. LPM-014 is next.

## 2026-11-24 · LPM-014 · Done · Codex on `main`

Added [`compare_projects`](../mcp-contract.md#project-comparison) for a baseline and candidate selected at launch. It reports component identities and unified diffs by scope, with readable Ladder and Structured Text context. The role and source SHA-256 identify each file even when their names match. Synthetic stdio tests covered unchanged export metadata, changed settings and values, additions and removals, routine edits, protected metadata, and invalid selections.

The SDK-free wheel passed the test suite and `pip check`. A one-line edit in a copy of an SDK-generated `.L5X` produced one routine change. The revision 38.02 `.ACD`/`.L5K` and `.L5K`/`.L5X` comparisons of the same fixture reported zero changes. Native checks used Windows 11 build 26200, Python 3.12.10 x64, and Rockwell Python wheel 2.0.2. All compared source hashes stayed unchanged. LPM-030 is now ready. LPM-015 is next in board order.

## 2026-11-24 · LPM-015 · Done · Codex on `main`

Added [`export_project`](../mcp-contract.md#offline-export) for full `.L5X` and `.L5K` and component `.L5X`. The local user enables export with `--export-dir` and supplies a new filename for each artifact. The server stages the output from a verified source snapshot and uses an atomic operation that refuses existing destinations.

On Windows 11 build 26200 with Python 3.12.10 x64, Logix Designer 38.02, and Rockwell Python wheel 2.0.2, MCP exported both full formats from `.ACD` and `.L5K`. The SDK reopened all four exports and imported the exported routine into a scratch project. Logix Designer desktop also imported a full `.L5X` to a distinct `.ACD`. MCP component tests covered programs, an equipment phase, a routine, a user-defined data type, an Add-On Instruction, and a ladder rung range. The existing-destination and missing-routine checks preserved the source and neighboring file hashes. The SDK-free wheel passed the test suite and `pip check`, covering byte-for-byte `.L5X` copy and a destination created during export. [Compatibility and reproduction steps](../compatibility.md#verified-exports)

LPM-020 is next in board order.

## 2026-11-24 · LPM-020 · Done · Codex on `main`

Verified the documented [Studio 5000 Custom Tools path handoff](../studio-5000-integration.md) on Windows 11 build 26200, Logix Designer 38.02, Python 3.12.10 x64, and Rockwell Python SDK wheel 2.0.2. Two simultaneous editor windows passed their own absolute `.ACD` paths with spaces as a single argument using `"%project_path%"`. An unsaved description edit retained its path and previous saved snapshot in MCP until Save; the subsequent call reported the new description and source hash. Completing a new project wizard created a readable `.ACD` before the first explicit Save. The Tools command with no open project raised macro error 786-0 before starting the helper.

Reviewed the published file-open SDK API and documented the latest-saved-project workflow and reproduction steps. MCP read the already-open and newly created projects with matching source fingerprints. The temporary Custom Tools configuration was restored to its original SHA-256, and the seed project hash matched its original. LPM-021 is ready and next in board order.

## 2026-11-24 · LPM-021 · Done · Codex on `main`

Added `logix-project-mcp-share` with a local CLI, Windows file picker and confirmation, and an explicit refresh action. The existing server supports an opt-in `--selection-file` path. The helper validates a saved project before publishing its selection atomically, and each MCP operation captures the selected path and ID. Inspection responses identify the saved revision and source SHA-256. A stale search page can be rejected even when two same-named projects have identical saved bytes. The fixed-path mode remains available. [Sharing and refresh walkthrough](../studio-5000-integration.md#share-and-refresh)

The SDK-free wheel passed the 17-test suite (the optional native test was skipped) and `pip check`. Stdio checks covered two same-named files, spaces, missing and moved files, invalid and stale selections, refresh, comparison, and export. On Windows 11 build 26200, Python 3.12.10 x64, Logix Designer 38.02 and Rockwell wheel 2.0.2, the helper and one connected MCP session switched between two open `.ACD` copies and observed an editor description change after Save and refresh. The source hash matched each inspected saved version. The Windows confirmation dialog and manual file picker published the expected paths. Shared selection also passed a native `.L5K` read and SDK-free full `.L5X` validation. LPM-022 is now ready.

## 2026-11-24 · LPM-022 · Done · Codex on `main`

Added `logix-project-mcp-menu` with repeatable `install` and `remove` commands for **Send Current Project to Agent**. The entry invokes the installed Python environment's Windows sharing helper with the configured selection JSON and quoted `%project_path%`. The installer preserves existing tools and backs up changed XML. It rejects conflicting names and invalid configurations. The manual path picker remains available. [Installation and removal](../studio-5000-integration.md#install-send-current-project-to-agent)

The SDK-free wheel passed the 20-test suite (the optional native test was skipped) and `pip check`. Its console installer passed repeated install and removal on a disposable XML file. On Windows 11 build 26200 with Python 3.12.10 x64, Logix Designer 38.02, and Rockwell wheel 2.0.2, the actual installed Tools entry shared `Shared project with spaces.ACD` and an already-connected MCP client read revision 38.02 with the matching source hash. Repeated installation and removal preserved the existing entries and ACL. The test deployment was removed and the original XML SHA-256 matched the pretest file. LPM-030 is next in board order.

## 2026-11-24 · LPM-016 · Done · Codex on `main`

Brought native snapshot caching forward following the maintainer's reported 30–40-second inspection latency. Added a session-local cache of validated immutable XML bytes, bounded to four entries and 128 MiB, keyed by selected path and verified SHA-256. Reads retain source consistency checks and parse fresh XML trees. Tests cover invalidation with equal timestamps and sizes, separate paths, missing sources, invalid or failed exports, and eviction. The board also records direct Codex registration (LPM-024) and read-only diagnostics feasibility (LPM-050).

On Windows 11 build 26200 with Python 3.12.10 x64 and SDK wheel 2.0.2, a synthetic revision 38.02 `.ACD` took 30.431 s on the first MCP read and 0.160 s on a repeat. A changed sample required 30.756 s for a fresh export and subsequently 0.142 s. `.L5K` took 34.907 s cold and 0.137 s warm. All fingerprints matched the saved source. The SDK-free wheel passed the 23-test suite with the optional native test skipped, and `pip check` passed. The [compatibility notes](../compatibility.md#native-snapshot-cache-measurements) record the measured scope. LPM-024 is next.

## 2026-11-24 · LPM-024 · Done · Codex on `main`

Registered the local stdio server with Codex CLI 0.172.0 using the permanent per-user selection JSON, explicit Python environment and `ProgramFiles` environment entry. Set a 120-second tool timeout and installed the Studio 5000 menu using the same selection path. The previous selection was preserved and the installer backed up the prior menu configuration. Existing editor windows must be reopened to load the updated menu. The [direct registration walkthrough](../studio-5000-integration.md#connect-codex) documents setup and manual sharing without user-specific paths.

On Windows 11 build 26200 with Python 3.12.10 x64 and Rockwell SDK wheel 2.0.2, a new Codex conversation used the registered MCP server with only its selection path overridden to a scratch JSON. Actual MCP calls to `get_capabilities` and two `get_project` calls succeeded for a synthetic revision 38.02 `.ACD`. Both returned the same SHA-256, independently matched against the saved source file. The sharing helper then selected a full synthetic `.L5X`; resuming the same Codex conversation returned the new selection ID, format and independently verified source hash. No customer project was used for these inspection tests. LPM-030 is next in board order, and LPM-050 is now ready.

## 2026-11-25 · LPM-030 · Done · Codex on `main`

Added [`preview_change_proposal` and `validate_change_proposal`](../mcp-contract.md#offline-change-proposals) with typed, scope-qualified documentation targets, saved-source identity, ordered before/after values, and a deterministic SHA-256 approval identity. Validation rebuilds the proposal against the current snapshot and checks the independently retained identity. Version 1 supports descriptions only; neither tool changes logic, configuration, tag values, or project files. The digest is not a signature or evidence of human approval.

The built wheel passed the 25-test suite in a separate SDK-free Python 3.12.10 environment (24 passed, optional native test skipped), and `pip check` passed. Stdio tests rejected ambiguous and duplicate targets, unsupported operations, invalid XML text, protected tags, malformed descriptions, altered previews, changed saved bytes, and shared selection refresh or switching. On Windows with Rockwell Python SDK wheel 2.0.2, both paired synthetic Logix Designer revision 38.02 `.ACD` and `.L5K` samples passed the separate native stdio smoke test, including preview and validation; the original source hashes were unchanged. No customer project or live controller was used. LPM-031 and LPM-032 are ready, with LPM-031 next in board order.

## 2026-11-25 · LPM-031 · In progress (documentation-only slice verified) · Codex on `main`

Added [`create_documentation_copy`](../mcp-contract.md#documentation-copy) for a reviewed description proposal and a new filename in the configured export directory. It validates the proposal against a fresh saved snapshot, changes only the relevant description byte ranges, reparses and checks the staged result, and rechecks the source and selection before publishing without overwriting an existing destination. The returned artifact hash identifies the staged bytes. The operation supports creation, replacement and removal of descriptions of existing controllers, programs, and scoped tags.

The 28-test suite passed both the editable installation and the built wheel in an SDK-free Python 3.12.10 Windows environment (27 passed, one optional native test skipped in each run), and `pip check` passed. Synthetic full L5X tests covered case-insensitive scoped names, empty and removed descriptions, escaped and Unicode text, byte-for-byte preservation of unrelated XML, stale saves, selection changes, modified previews, unsupported encoding, and competing destinations. The source and existing destination files remained intact. No SDK write, Studio 5000 import, or live controller was exercised. The agreed documentation-only scope is complete; tag definition/value changes, renames and removals in the broader original LPM-031 brief are not implemented, so the task remains In progress.

## Handoff entry template

Add an entry with the date, task ID, status, owner, and branch or worktree. Record the result, verification evidence, outstanding limitations or blockers, and next ready task. Link files or runs that support the status.
