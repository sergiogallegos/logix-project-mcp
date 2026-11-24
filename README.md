# logix-project-mcp

A local MCP server for saved Rockwell Studio 5000 Logix Designer projects. An agent can inspect controller metadata, tags, and routines, compare saved projects, and create offline exports when you enable export.

| Format | How the server reads it |
| --- | --- |
| `.ACD` | Opens a temporary copy with the Rockwell SDK and inspects its `.L5X` export |
| `.L5K` | Imports a temporary copy with the same SDK and inspects its `.L5X` export |
| `.L5X` | Parses a temporary copy of a full project export without the Rockwell SDK |

Each inspection tool takes a fresh snapshot of the selected saved file. Its successful structured response includes `source_sha256`, the SHA-256 of the saved bytes used for that read. Use it to match results from the same saved version. If the file changes during copying, retry after the save completes. A Studio 5000 Tools menu entry for sharing the current project path and a reviewed offline editing workflow are planned.

See the [compatibility matrix](docs/compatibility.md) for tested formats and revisions, SDK requirements, and instructions to reproduce the checks.

## Requirements

For a full `.L5X` export, install **Python 3.12 or later** with `pip` and `venv`, and use an MCP client that can launch a local stdio server. The Python MCP SDK and XML parser install with the server.

For native project reads, format conversions, and component exports with the Rockwell SDK 2.02.00, also install:

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

Add a local stdio server in your MCP client. Replace both paths in the `mcpServers` example with the absolute paths on your machine. For `.ACD` or `.L5K` on a standard 64-bit Windows setup, forward the value of `$env:ProgramFiles` from the Windows session where the SDK works. A client with full environment inheritance can use that existing value.

```json
{
  "mcpServers": {
    "logix-project-mcp": {
      "command": "C:/path/to/logix-project-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "logix_project_mcp.server", "--project", "C:/path/to/MyProject.ACD"],
      "env": { "ProgramFiles": "C:\\Program Files" }
    }
  }
}
```

| Tool | Response |
| --- | --- |
| `get_capabilities` | Contract version, selected file, and format requirements |
| `get_project` | Controller metadata and the program and routine tree |
| `get_inventory` | Controller, task schedules, programs, scoped tags, modules, user-defined types, and Add-On Instruction metadata |
| `list_tags` | Names, data types, and descriptions for controller tags or a specified program's tags |
| `read_routine` | Saved routine source, language-specific sections, and protection status |
| `search_project` | Scoped declarations, comments, and resolved references matching a query |
| `find_references` | Locations that refer to a specific declaration, including through alias chains |
| `compare_projects` | Scoped changes between the baseline and candidate selected at launch |
| `export_project` | A new full `.L5X` or `.L5K` file, or a component `.L5X`, in your chosen directory |

To enable comparison, keep `--project` set to the baseline and add `--compare-project` followed by the candidate path in the MCP configuration's `args` array.

To enable export, add `--export-dir` followed by an existing directory you choose. Ask the agent for a new filename in that directory, such as `Review.L5X`. The tool reads a snapshot of `--project` and preserves existing files. Copying a full `.L5X` to a new `.L5X` keeps its exact bytes and works without the SDK. Converting formats and exporting components use the Rockwell SDK on Windows.

See the [MCP tool contract](docs/mcp-contract.md) for arguments, structured results, and error codes.

## Check the installation

Run `logix-project-mcp-doctor` from the same Windows PowerShell session you use to launch your MCP client. Without a project, it reports Python architecture, package versions, standard Logix Designer installations, .NET runtimes, and the local SDK service. Pass a saved sample to test an actual `get_project` call over MCP stdio. You can also invoke it directly from the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m logix_project_mcp.doctor
.\.venv\Scripts\python.exe -m logix_project_mcp.doctor --project 'C:\path\to\Sample.ACD' --compare-launch-env
```

The comparison tries the inherited Windows environment first. It then tries the Python MCP client's reduced environment with `ProgramFiles` and any existing `DOTNET_ROOT` forwarded. If the inherited launch passes and the reduced launch warns about a timeout, configure your client to inherit the working environment. For a nonstandard .NET installation, set `DOTNET_ROOT` to the runtime matching Python's architecture and repeat the check before updating your client environment.

Pass a full `.L5X` export with `--project` to test the SDK-free path. The diagnostic prints setup and launch results without printing project contents or environment values. Its exit code is `0` when the requested primary checks pass and `1` when a required check or primary MCP probe fails. A failed reduced comparison prints a warning when the inherited launch passes.

## Contribute

See [BUILD.md](BUILD.md) for local and CI checks, [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance, and [AGENTS.md](AGENTS.md) for the source map and agent skills. The [product task board](docs/agents/board.md) tracks the path to 1.0. The server is [MIT-licensed](LICENSE). The Rockwell SDK is installed separately.
