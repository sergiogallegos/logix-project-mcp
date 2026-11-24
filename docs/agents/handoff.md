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

## Handoff entry template

Add an entry with the date, task ID, status, owner, and branch or worktree. Record the result, verification evidence, outstanding limitations or blockers, and next ready task. Link files or runs that support the status.
