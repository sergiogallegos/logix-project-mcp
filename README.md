# logix-project-mcp

A local MCP server for saved Rockwell Studio 5000 Logix Designer projects. The first version gives an agent read-only access to the controller metadata, tags, and routines in a project you select.

| Format | How the server reads it |
| --- | --- |
| `.ACD` | Opens a temporary copy with the Rockwell SDK and inspects its `.L5X` export |
| `.L5K` | Imports a temporary copy with the same SDK and inspects its `.L5X` export |
| `.L5X` | Parses a full project export directly |

The server reads the latest saved file on each tool call. Save in Studio 5000 before asking the agent to inspect changes. A Studio 5000 Tools menu entry for sharing the current project path and a reviewed offline editing workflow are planned.

## Requirements

For a full `.L5X` export, install **Python 3.12 or later** with `pip` and `venv`, and use an MCP client that can launch a local stdio server. The Python MCP SDK and XML parser install with the server.

For native `.ACD` and `.L5K` files using the Rockwell SDK 2.02.00 setup shown here, also install:

- **Windows** and **Studio 5000 Logix Designer** 31 or later, with the version needed to open the selected project.
- **Logix Designer SDK 2.02.00** and its **Python 2.0.2 wheel**. Rockwell requires a **Professional Edition license or toolkit** to activate this SDK. This wheel supports Python **3.12 and 3.13**.
- **FactoryTalk Linx**, **FactoryTalk Services Platform**, and **FactoryTalk Activation 4.04 or later**.
- The SDK installer supplies the **x86 .NET 10, .NET Desktop 10, and ASP.NET Core 10 runtimes** for its Windows components. The Python client also needs a .NET runtime that matches Python's process architecture. The example MCP configuration below uses 64-bit Python and an x64 .NET 10 installation.

See the [Rockwell SDK 2.02.00 requirements](https://compatibility.rockwellautomation.com/GeneratedReleaseNote.aspx?v1=66601) for operating system versions and vendor prerequisites.

## Install

Create a Python 3.12 environment and install the server. From PowerShell in the repository root, run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

For `.ACD` or `.L5K`, install the Rockwell wheel into the same environment. Adjust the wheel filename for your installation.

```powershell
$sdk = Join-Path $env:PUBLIC 'Documents\Studio 5000\Logix Designer SDK\python\logix_designer_sdk-2.0.2-py3-none-any.whl'
.\.venv\Scripts\python.exe -m pip install $sdk
```

## Connect an agent

Add a local stdio server in your MCP client. The example uses the `mcpServers` configuration format. Replace both paths with the absolute paths on your machine.

```json
{
  "mcpServers": {
    "logix-project-mcp": {
      "command": "C:/path/to/logix-project-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "logix_project_mcp.server", "--project", "C:/path/to/MyProject.ACD"],
      "env": { "DOTNET_ROOT": "C:/Program Files/dotnet" }
    }
  }
}
```

`DOTNET_ROOT` gives the Rockwell SDK the .NET installation path. Adjust it for your installation. For native files, configure the MCP client to inherit the Windows user environment. A client that replaces that environment with a minimal allowlist can start the server yet time out when the SDK opens a project. Use the [Windows SDK smoke test](BUILD.md#verify-rockwell-sdk-integration-on-windows) to confirm the local installation. A full `.L5X` export only needs the Python dependencies.

| Tool | Response |
| --- | --- |
| `get_project` | Controller metadata and the program and routine tree |
| `list_tags` | Names, data types, and descriptions for controller tags or a specified program's tags |
| `read_routine` | Routine logic and comments in L5X XML |

## Contribute

See [BUILD.md](BUILD.md) for local and CI checks, [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance, and [AGENTS.md](AGENTS.md) for the source map and agent skills. The [product task board](docs/agents/board.md) tracks the path to 1.0. The server is [MIT-licensed](LICENSE). The Rockwell SDK is installed separately.
