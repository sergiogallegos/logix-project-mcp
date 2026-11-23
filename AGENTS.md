# Repository Agent Guide

`logix-project-mcp` is a Python MCP server for saved Studio 5000 Logix Designer projects. See [README.md](README.md) for setup, client configuration, and implemented capabilities.

## Start here

- [BUILD.md](BUILD.md) covers packaging and validation.
- [CONTRIBUTING.md](CONTRIBUTING.md) describes how to prepare and report changes.
- [Architecture](docs/architecture.md) describes the project data flow and current boundaries.
- [Product task board](docs/agents/board.md) gives the delivery order, dependencies, and current status. Follow the [agent handoff workflow](docs/agents/README.md) when implementing the backlog.

## Source map

- `src/logix_project_mcp/server.py` defines the stdio server, user-selected project path, and MCP tools.
- `src/logix_project_mcp/project.py` handles L5X parsing and SDK-backed snapshots of ACD and L5K files.
- `src/logix_project_mcp/_sdk_worker.py` hosts the Rockwell SDK in a child process.
- `src/logix_project_mcp/doctor.py` checks local prerequisites and verifies a read through an MCP subprocess.
- `tests/test_stdio.py` checks installation and request handling through a real MCP connection.

## Skills

- Use the [Logix project inspection skill](.agents/skills/inspect-logix-project/SKILL.md) for project inspection or changes to the SDK-backed read path.
- Use the [change verification skill](.agents/skills/verify-logix-mcp-change/SKILL.md) when changing server code, packaging, tool schemas, or project parsing.

## Working agreements

This release reads saved projects offline. Preserve the selected source file and keep the Rockwell SDK optional for `.L5X` exports. Reserve stdout for MCP messages and keep diagnostics on stderr. Use synthetic exports or Rockwell sample projects in validation. Keep customer projects and vendor packages out of commits.
