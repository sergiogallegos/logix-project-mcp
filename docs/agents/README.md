# Agent task workflow

Use the [board](board.md) for task status, the [task briefs](tasks.md) for acceptance criteria, and the [handoff log](handoff.md) for decisions and verification evidence. Task IDs are stable across sessions and branches.

1. Read `AGENTS.md`, the board, and the brief for the task. Resume an owned `In progress` item first. Otherwise claim the first `Ready` item in board order and record the owner.
2. Implement and verify the task through its normal entry point. Use the repo-local verification skill and the task-specific checks. Record which host, SDK revision, project revision, and format were exercised when relevant.
3. Mark the task `Done` after its acceptance criteria pass. Add one handoff entry with the result, checks, and remaining limitations. Promote newly unblocked items from `Planned` to `Ready`, then start the next `Ready` item in the same session when implementation is in scope.
4. If a task needs an external decision, access, or hardware, record the specific blocker and what would clear it. Move the task to `Blocked` and pick the next `Ready` item whose dependencies are satisfied. Recheck the blocked item when the prerequisite changes.

## Status meanings

| Status | Meaning |
| --- | --- |
| Ready | Dependencies are satisfied and the work can start. |
| In progress | An agent owns the task on a named branch or worktree. |
| Planned | One or more listed dependencies are still open. |
| Blocked | A specific external prerequisite prevents progress. |
| Done | Acceptance criteria passed and verification is recorded. |

Use one primary agent per worktree. Parallel work needs separate worktrees and clear ownership. Mention task IDs in PRs and verification notes. Report the next ready task at handoff, even if it remains ready for another session.

Use samples or authorized saved copies for integration tests. The 1.0 workflow covers offline project engineering, with user review before applying edits. Follow the maintainer’s directions for GitHub publication and any Studio 5000 desktop or lab validation.
