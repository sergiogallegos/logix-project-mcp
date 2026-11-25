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

## 2026-11-25 · LPM-032 · In progress (routine documentation slice verified) · Codex on `main`

Extended the version 1 documentation proposal target union with a program-qualified `routine` target for existing Ladder and Structured Text routines that have saved readable content. The same preview, identity validation, and documentation-copy workflow supports creation, replacement, or removal of their descriptions. Source-protected, encoded, ambiguous, missing, and unsupported routine targets are rejected. Routine creation and executable logic edits are not implemented.

The 29-test suite passed both the editable package and the built wheel in a separate SDK-free Windows Python 3.12.10 environment (28 passed, one optional native test skipped); `pip check` passed. The synthetic revision 38.02 L5X stdio test used same-named RLL/ST routines in different programs, verified exact output bytes, and verified that existing rung and inline comments, routine sections including pending edits, and the source file were unchanged. A tampered target and an undeclared logic attribute were rejected. No native SDK editing or Studio 5000 import was exercised. The broader LPM-032 brief remains In progress.

## 2026-11-25 · LPM-050 · Done · Codex on `main`

Published the [read-only diagnostics feasibility assessment](../diagnostics-feasibility.md) after reviewing Rockwell's Getting Results Guide, the installed Python SDK 2.0.2 public method documentation, and the maintainer's rust-ethernet-ip upstream documentation and PyPI release 1.2.1. The SDK documents observation capabilities beyond this project's offline reader. No demonstrated requirement presently justifies adding another communication provider to the MCP server. The assessment explicitly distinguishes documented capability from tested behavior and records prerequisites and limitations for any future evaluation.

The deterministic offline simulation uses the real inventory parser on a synthetic revision 38.02 L5X and fabricated observation records. Tests cover same-named scoped tags, simulated fresh data, stale data, absent observations, errors, and association with a different source fingerprint. The simulation and focused test passed; the SDK-free Windows Python 3.12.10 regression suite passed 29 tests with one optional native test skipped (30 total). `pip check` passed. No controller or real diagnostic endpoint was contacted and no new runtime MCP tools or dependencies were added. This was the remaining independent Ready task; LPM-033 depends on the broader unfinished LPM-031 and LPM-032 work.

## 2026-11-25 · LPM-033 · In progress (documentation artifact verification slice verified) · Codex on `main`

Added [`verify_documentation_copy`](../mcp-contract.md#documentation-copy), a read-only check for an existing full UTF-8 L5X documentation output in the configured export directory. It verifies the source, selection, proposal, retained receipt digest, and complete artifact bytes against a fresh reconstruction of the reviewed output, then rechecks the source and artifact fingerprints and selection. New error codes distinguish altered and unavailable artifacts. Verification does not change either file and is not vendor import or build verification.

The 31-test suite passed both the editable installation and the built wheel in the SDK-free Windows Python 3.12.10 test environment (30 passed, one optional native test skipped); `pip check` passed. Synthetic MCP tests covered exact source/output preservation, concurrent verification, wrong or replaced hashes, altered descriptions and unrelated XML, missing artifacts, tampered proposals, stale saves, and path validation. Race tests covered source, artifact, and selection changes during verification. No native SDK edit or import was attempted. The documentation artifact slice is verified, but LPM-033's original native ACD and component output requirements and its broader editing prerequisites remain open.

## 2026-11-25 · LPM-034 · In progress (documentation preservation and SDK reopen slice verified) · Codex on `main`

Added synthetic AOI and opaque protected-record preservation tests and a conservative rejection of recognized safety-class, lock and signature indicators for documentation proposals, leaving saved-project reads available. The verifier now explicitly returns `vendor_verification: "not_performed"`; exact XML verification does not authenticate a signature or certify a vendor build. See [verification limits and reproduction](../compatibility.md#documentation-verification).

The SDK-free wheel passed 32 tests, with two optional native checks skipped (34 total); `pip check` passed. The editable package passed the applicable regression tests before addition of the optional SDK test. On Windows 11, Python 3.12.10, Rockwell SDK wheel 2.0.2 and the synthetic Logix Designer revision 38.02 full L5X, the optional SDK test passed. It opened and re-exported a scratch copy of the MCP-created documentation artifact, verified the exact reviewed controller CDATA text and other inventory fields, and confirmed the original source and reviewed artifact hashes. The initial direct text assertion differed because of vendor formatting newlines outside CDATA; this was diagnosed and resolved by checking the CDATA payload. No build, native project edit, safety-signature validation, or live controller operation was attempted. Broader LPM-034 requirements remain open alongside LPM-031 through LPM-033.

## 2026-11-25 · LPM-035 · In progress (local documentation review slice verified) · Codex on `main`

Added the packaged [`logix-project-mcp-review`](../mcp-contract.md#local-review-and-approval) local interactive command. It accepts the exact proposal and creation receipt JSON, explicit saved source or shared selection, and candidate artifact path. It verifies the candidate before displaying the complete review and after local confirmation. Finalization atomically publishes a separate, non-overwriting approval sidecar bound to the proposed changes, source and artifact hashes, and exact paths. The record is a local audit record, not an authenticated signature, vendor build approval, or a substitute for reverification. Decline and invalid/stale inputs cannot create an approval record, and the existing source and artifact are never changed.

The editable package and SDK-free wheel both passed 36 tests, with two optional native checks skipped (38 total); `pip check` passed. The wheel and refreshed editable installation expose the new console command. Synthetic tests covered mocked interactive confirmation and decline, piped input rejection in a subprocess, invalid receipt identity, replay, a competing sidecar, and source, artifact, or selection changes during the review. No real project was approved. Generated approval sidecars are ignored by Git. Broader native-artifact approval and Studio 5000 integration remain unimplemented; this task stays In progress against the original brief.

## 2026-11-25 · LPM-023 · In progress · Codex on `main`

Implemented a read-only handoff for an approved full L5X documentation copy. The local review command takes the independently retained review ID, the current project selection and the explicit artifact path. It reconstructs the expected XML, checks the approval record and returns the verified paths and hashes. The [desktop walkthrough](../studio-5000-integration.md#open-a-reviewed-full-l5x-documentation-copy) covers pending editor edits and choosing a separate ACD destination.

On Windows with Python 3.12.10 the editable install and SDK-free wheel each passed 37 tests with two optional native checks skipped. Both passed `pip check`. The optional synthetic SDK 2.0.2 reopen test also passed separately. In a desktop test, Logix Designer imported the checked revision 38.02 full L5X into a fresh scratch ACD. An MCP subprocess read the resulting ACD and confirmed its saved hash and the exact synthetic controller description after stripping vendor formatting whitespace. The UI probe timed out waiting for the editor title after import. The saved ACD read supplied the result evidence.

The full task still depends on reviewed native ACD and component L5X output. A component-name conflict and import into an already dirty project remain untested. No subsequent task is marked Ready.

## 2026-11-25 · LPM-040 · In progress · Codex on `main`

Hardened failure reporting across the saved-project reader, sharing helper, Custom Tools XML parser and SDK worker. Malformed XML reports a position when available. Prohibited declarations and unsupported encodings have fixed messages. The server discards worker output, maps exit status to a setup or retry hint and opens the SDK project without a file event logger. The [README](../../README.md#check-the-installation) covers retrying the selected file.

Windows stdio tests exercised corrected XML, a released byte-range lock, a selected file replaced by a symbolic link, and an occupied linked export destination. The same connection handled the subsequent valid request. Helper tests checked preservation of an existing selection and menu configuration. Worker tests checked timeout, cancellation, unexpected exit, cleanup and retry. A separate SDK-free MCP call on the synthetic ACD returned wheel installation guidance.

On Windows 11 with Python 3.12.10 and Rockwell SDK 2.0.2, the 40-test native-enabled run passed, including the revision 38.02 ACD read and documentation L5X reopen. The additional link test, updated Custom Tools tests and a separate revision 38.02 L5K read passed. The ACD and L5K retained their source hashes. The SDK-free wheel passed 39 of 41 tests with the two native-only checks skipped. Both environments passed `pip check`.

LPM-040 stays open for failure handling on the native staged outputs tracked by LPM-033. No downstream task meets all its board dependencies yet.

## 2026-11-25 · LPM-041 · Done · Codex on `main`

Added a [repeatable inspection benchmark and host-specific regression targets](../performance.md). The saved-project paths needed for this benchmark have passed LPM-040 recovery checks. LPM-040's remaining native staged-output work is independent of these reads.

On Windows 11, Python 3.12.10 and MCP 1.30.0, the SDK-free wheel searched the larger synthetic L5X (8,192 tags and 16,384 comment lines) in 0.19–0.23 seconds and compared it in 0.75–0.99 seconds. Two independent clients found the same scoped match in 0.27 seconds wall time. The first server peaked at 90.1 MiB.

With Rockwell SDK 2.0.2, the revision 38.02 L5K with 8,192 tags opened in 52.76 seconds and repeated in under 0.28 seconds. The synthetic 38.02 and Rockwell 35.00 ACDs opened in about 30 seconds. For each format, replacing a scratch copy at the same path produced a new hash and summary consistent with an independent cold read. Source hashes matched after the runs.

LPM-042 is next in delivery order. Its full packaging and release checks still depend on LPM-035 and LPM-040, so no downstream task is newly Ready.

## 2026-11-25 · LPM-042 · Done · Codex on `main`

CI builds one universal wheel, retains it as the `python-wheel` artifact and installs that file into four fresh environments. The hosted Windows and Ubuntu jobs passed on Python 3.12 and 3.13. The stdio smoke test launches the installed server command. The README and build guide cover wheel setup, client configuration, upgrades and removal. [Hosted CI run and wheel](https://github.com/sergiogallegos/logix-project-mcp/actions/runs/45668135199) · [Reproduce the packaging checks](../../BUILD.md#test-the-distribution-wheel)

On Windows 11, Python 3.12.10, a clean SDK-free environment upgraded from the earlier LPM-022 wheel. Both development builds report version 0.1.0, so this exercised same-version replacement. The shared selection survived the upgrade and uninstall, all five launchers were removed, and the unrelated Custom Tools entry survived removal of the sharing command. The helper setup ran against disposable XML. The suite passed 39 tests with two optional native checks skipped.

In a second clean environment, the locally built wheel and Rockwell SDK 2.0.2 passed all 41 tests, including the revision 38.02 synthetic ACD read and SDK documentation L5X reopen with source hash checks. Hosted CI remains SDK-free. Packaging covers the currently implemented tools. The remaining native output and approval features stay on their own tasks.

The wheel downloaded from the linked run had SHA-256 `6466ce0274529b2785378c3f8baafba10d616ca0a6523b0670b378dd0568d15d`. That artifact also passed a clean Windows SDK install, repeated reads of a synthetic revision 38.02 L5K with matching source hashes, and removal. This run passed 40 tests and skipped the separate documentation reopen check.

LPM-043 is next in delivery order. Its full engineer acceptance run still depends on LPM-023's reviewed native and component handoff.

## 2026-11-25 · LPM-043 · In progress · Codex on `main`

Exercised the full-project L5X documentation workflow on Windows 11 build 26200 with two fresh Python 3.12.10 environments and the LPM-042 hosted wheel (SHA-256 `6466ce0274529b2785378c3f8baafba10d616ca0a6523b0670b378dd0568d15d`). The desktop already had Logix Designer and the licensed SDK. Only the native environment received the Rockwell 2.0.2 wheel. Both installations passed `pip check`. [Repeat the acceptance run](../engineer-acceptance.md)

| Saved sample (software revision 38.02) | Checks and outcome |
| --- | --- |
| Synthetic ACD open in Studio | Shared the saved file via the installed helper, found `MainProgram.InspectText`, and exported a full baseline L5X. Studio imported the reviewed L5X as `McpReviewed.ACD`. An independent stdio read of that ACD returned controller `McpSnapshotSample`, the same revision, ST language and routine sections, and the description `LPM-043 synthetic acceptance note`. |
| Synthetic L5K | The SDK imported the saved sample. The runner found the same ST routine, verified the single documentation change and reopened the reviewed full L5X over MCP. |
| Full synthetic L5X | Without the SDK, the runner found `Main.MainRoutine`, created and checked a reviewed copy, and read its description and original logic over MCP. |

Each run rejected an outdated proposal with `selection_changed` before a copy existed, succeeded after a fresh preview, and preserved the original source SHA-256. Codex acted as test operator at the local approval prompts. The ACD source hash was `d4f900f333f132a171a591267e4c7c3c4a11c80ca256f2bbca3b9167700e245e`, the reviewed L5X hash was `ceb063a584b79e9a30d1ffae974994a45cf2fad84394b070dcb8c31d244ab2c2`, and the imported ACD hash was `4f6ce81a60fb25ffe4bcb3608e144e1e514afc5bfb44a1e8036698a46d08066e`. The desktop probe initially timed out. A subsequent attempt captured Studio error `716-80042029` (“Name is invalid”) for `Studio inspection.ACD`. Changing the destination to `McpReviewed.ACD` allowed the import and readback to finish.

All 42 tests passed with the SDK and both optional samples configured. The SDK-free environment passed 40 and skipped the two native tests. The automated regression simulates only the local review decision for a generated fixture. The installed helper was invoked directly while the ACD was open. LPM-022 records the separate menu check.

LPM-043 remains in progress pending LPM-023's reviewed native output and component handoff. Engineer sign-off is outstanding. LPM-044 is next in delivery order once acceptance is complete.

## 2026-11-25 · LPM-044 · In progress · Codex on `main`

Added a first-read quick start, a format-by-operation matrix, instructions for changing a description, troubleshooting and development release notes. The notes identify the tested commit, CI artifact and wheel hash. The desktop import instructions now use the simple ACD filename that passed the LPM-043 run. [Quick start](../../README.md#quick-start) · [Operator guide](../support.md) · [Development notes](../release-notes.md)

Walked through the setup on Windows 11 build 26200 with Python 3.12.10. Installed the hosted wheel from commit `532d8df` in two fresh virtual environments using cached dependency wheels. Both passed `pip check`. With the SDK-free environment, the doctor opened Rockwell's `DayOfWeek.L5X` at revision 17.00. A stdio client using the README's configuration read the saved hash and the Ladder routine `MainProgram.DayOfWeek`. A shared-selection client first returned `selection_required`, then read the same hash and routine after the installed helper shared the sample.

The SDK-free doctor identified the missing Rockwell wheel when given a native sample. With SDK wheel 2.0.2 installed, the doctor opened a synthetic 38.02 ACD in both inherited and reduced launch environments and a 38.02 L5K in the inherited environment. A separate synthetic L5X run recovered from a stale proposal, staged a routine description, passed local review with Codex as test operator, and checked the artifact and source hashes on readback. The desktop menu and Studio import evidence comes from LPM-022 and LPM-043. This walkthrough used the installed workstation and left its Studio menu and persistent client registration alone.

Documentation for the current development wheel is ready. LPM-044 remains open for the final format matrix and release notes after LPM-043 engineer acceptance and the reviewed native/component handoff. LPM-045 publication remains planned.

## 2026-11-25 · LPM-031 · Done for supported tags · Codex on `main`

Added a read-only MCP preview and a local interactive publisher for one private decimal DINT tag in a full UTF-8 L5X. Controller and program scopes support create, saved value update, rename and remove. The preview ties the exact change to the selected save. The publisher reconstructs it, checks the staged declaration, displays the destination and artifact hash, and rechecks the source and selection after approval. Existing files are preserved. [Supported declarations, collisions and command](../mcp-contract.md#private-dint-tag-edits)

Synthetic stdio and local review tests exercised all four operations, DINT bounds, case-insensitive collisions, possible references, mismatched data representations, changed selection and source, decline and a competing output. A program-tag sequence returned the entire export to its original bytes after removal. A separate test checked preservation of CDATA descriptions, whitespace and both saved value representations.

On Windows with Python 3.12.10 and SDK wheel 2.0.2, the SDK reopened a synthetic revision 38.02 copy containing a new controller tag with value −17. In a second run, Codex acted as test operator at the installed review command. The SDK reopened the resulting program tag `MainProgram.McpScratchCount` with value 42, and an MCP client listed it under the expected program on the SDK re-export. The reviewed copy and source hashes matched the receipt after readback.

LPM-031 covers this supported DINT subset and the earlier description operations. Other tag types, access modes, reference rewriting and direct native output are outside its verified scope. LPM-032 is the next unfinished implementation task.

## Handoff entry template

Add an entry with the date, task ID, status, owner, and branch or worktree. Record the result, verification evidence, outstanding limitations or blockers, and next ready task. Link files or runs that support the status.
