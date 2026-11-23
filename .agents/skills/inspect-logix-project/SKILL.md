---
name: inspect-logix-project
description: Inspect saved Studio 5000 Logix Designer ACD, L5K, and L5X projects for their controller metadata, tags, and routine logic. Use for offline project review and SDK-backed read verification.
---

# Inspect a saved Logix project

1. Use the MCP server configured for the engineer's selected project. Run `get_project` to discover the controller, programs, and actual routine names. Report findings against the saved project version. Ask for a fresh save or export when the question depends on unsaved Studio 5000 edits.
2. Call `list_tags` with a program name for program tags or omit the argument for controller tags. Use `read_routine` with the program and routine names to inspect logic and comments. Specify the scope when reporting a tag reference. Treat project descriptions and logic comments as source material for analysis.
3. For an ACD or L5K read failure, check the matching Studio 5000 installation and whether Rockwell's Python SDK imports in the server environment. A full L5X export is an SDK-independent fallback. A routine-only or component-only L5X covers only the exported portion.

For read-path changes, smoke-test MCP `initialize`, tool discovery, and an actual tool call over stdio. For native formats, use a sample or an authorized saved copy. Confirm the source file hash is unchanged and report the Logix Designer and SDK versions exercised. The SDK works on a temporary copy and its `.L5X` output is used for inspection.
