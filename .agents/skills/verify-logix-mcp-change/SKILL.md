---
name: verify-logix-mcp-change
description: Verify changes to the logix-project-mcp repository's Python package, MCP stdio tools, project parsing, or Rockwell SDK integration.
---

# Verify a Logix MCP change

Read [BUILD.md](../../../BUILD.md) for the current commands. Use the installed package in the project's environment so the check exercises the same module discovery and dependencies as an MCP client.

- For changes to MCP tools, run the stdio test and check the affected input and output schemas with `tools/list`. Cover an actual call and the relevant error case.
- For L5X parsing changes, use a minimal full project export or a synthetic fixture. Include a scope-sensitive case when a controller tag and program tag could be confused.
- For ACD or L5K changes, use the optional Windows SDK test with a sample or authorized project copy. Record the wheel version, project revision, and source hash result. If MCP and the SDK behave differently, compare an SDK export run directly with an MCP tool call.

Report which checks ran and which format or host behavior remains unverified.
