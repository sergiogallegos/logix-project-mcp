# Contributing

Start with [BUILD.md](BUILD.md) for the development environment and [the architecture guide](docs/architecture.md) for the file and SDK boundaries.

- Describe the user workflow affected and the project formats involved.
- Exercise the MCP entry point when changing a tool name, argument, or response. Treat those as client-facing contracts.
- For parser changes, reproduce with a minimal synthetic export. For SDK compatibility changes, record the Rockwell SDK, Logix Designer revision, Windows version, and expected result.
- Include the checks you ran and any cases that still need a Windows SDK host. Share synthetic data or Rockwell samples where possible and redact proprietary project details.
