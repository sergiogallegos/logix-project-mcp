# Format and revision compatibility

This matrix covers offline inspection and export through MCP stdio. Save changes in Studio 5000 before inspecting or exporting a project. The [product task board](agents/board.md) tracks the Studio 5000 Tools menu and offline editing workflows.

## Verified reads

The local test host ran Windows 11 x64 build 26200 and Python 3.12.10 x64. Native checks used Studio 5000 Logix Designer 38.02, SDK 2.02.00 with Rockwell's Python wheel 2.0.2, and .NET 10.0.11. The full-export checks used a separate Python environment without the Rockwell wheel.

| Selected file | Logix Designer revision | MCP operations exercised |
| --- | --- | --- |
| `.ACD` created with the SDK | 38.02 | `get_project` |
| `.L5K` exported from the same synthetic project | 38.02 | `get_project` |
| Full `.L5X` exported from the same synthetic project | 38.02 | `get_project`, controller-scope `list_tags` |
| Rockwell's full `DayOfWeek.L5X` sample | 17.00 | `get_project`, `list_tags` in both scopes, `read_routine` |

Each successful read returned `source_sha256` matching the selected file's hash. The selected files kept their original hashes after the checks. `get_project` returned the software revisions shown here in `software_revision`.

Earlier Windows smoke tests also passed `get_project` on a 35.00 `.ACD` and its `.L5K` counterpart with Python wheel 2.0.2. GitHub CI checks SDK-free synthetic `.L5X` reads on Windows and Ubuntu with Python 3.12 and 3.13. [Earlier Windows smoke tests](agents/handoff.md) · [CI test matrix](../.github/workflows/ci.yml)

## Verified exports

On the same Windows and SDK versions, revision 38.02 `.ACD` and `.L5K` inputs each produced full `.L5X` and `.L5K` files through `export_project`. The Logix Designer SDK reopened all four artifacts and recovered the saved controller and Structured Text routine. Component exports exercised a program, an equipment phase, a routine, a user-defined data type, an Add-On Instruction, and a two-rung ladder selection. The SDK imported the exported routine into a separate project copy and reported zero errors or warnings. An occupied destination and a missing routine returned tool errors. The source, existing destination, and unrelated file retained their SHA-256 hashes. The SDK-free wheel also passed a byte-for-byte copy of a full `.L5X`.

Logix Designer desktop imported the full `.L5X` exported from `.ACD` and created a separate `.ACD` from it.

## Native snapshot cache measurements

On the Windows 11 build 26200 and SDK wheel 2.0.2 setup above, one MCP session read synthetic revision 38.02 projects through shared selection. The elapsed times include the verified source copy, XML inspection, and MCP response.

| Request | First read | Repeated read |
| --- | ---: | ---: |
| `.ACD` `get_project` | 30.431 s | 0.160 s |
| `.ACD` after replacing the saved bytes with an edited sample | 30.756 s | 0.142 s |
| `.L5K` `get_project` | 34.907 s | 0.137 s |

`get_inventory` on the first cached `.ACD` took 0.367 s. The edited sample produced the new description and fingerprint, and every response matched the saved source hash. These are measurements of the small synthetic sample, with larger projects covered by the planned performance task. The cached exports are bounded to four entries and 128 MiB combined per server process. Larger individual exports are inspected without caching.

## Failure cases

| Case | Observed outcome |
| --- | --- |
| Rockwell `DayOfWeek.ACD` at revision 26.00, below Rockwell's native support range | `get_project` returned an SDK `SetRSLinxEdition` error on this host. |
| Revision 38.02 `.ACD` with the Rockwell Python wheel absent from the MCP environment | `get_project` returned wheel installation guidance. `logix-project-mcp-doctor --project` identified the missing wheel and exited with code 1. |

Both rejected files kept their original hashes. The missing-wheel check ran on a Windows host with Studio 5000 and the SDK service installed.

## Rockwell's SDK requirements

Rockwell lists Logix Designer 31 and later for SDK project reads and lists version 38 among the tested releases. SDK 2.02.00 uses Python 3.12 or 3.13 for its Python client. Rockwell lists Windows 10 Pro and Enterprise, Windows 11 Enterprise, and Windows Server 2022 as tested operating systems. [Rockwell SDK 2.02.00 release notes](https://compatibility.rockwellautomation.com/GeneratedReleaseNote.aspx?v1=66601)

The native setup also requires Professional Edition activation or toolkit entitlement, FactoryTalk Linx, FactoryTalk Services Platform, and FactoryTalk Activation 4.04 or later. The SDK Windows service uses matching x86 .NET 10 runtime patches, and the Python client needs a runtime that matches its architecture. See the release notes for the complete requirements and known issues. [Rockwell SDK 2.02.00 release notes](https://compatibility.rockwellautomation.com/GeneratedReleaseNote.aspx?v1=66601)

The full 17.00 `.L5X` sample passed through the server's XML reader in the SDK-free environment. A separate smoke test of an upgraded legacy sample also encountered `SetRSLinxEdition` in both the SDK and MCP. Use the project revision and the published version range to assess support. Rockwell specifies FactoryTalk Linx for SDK communication. [Earlier Windows smoke tests](agents/handoff.md) · [Rockwell SDK 2.02.00 release notes](https://compatibility.rockwellautomation.com/GeneratedReleaseNote.aspx?v1=66601)

## Reproduce the checks

### Prepare a matching sample set

Use the Windows [native setup](../README.md#install) and an empty fixture directory. Run the following from the repository root to generate a synthetic project and both exports. The installed major revision 38 determines the exact Logix Designer patch used for the files.

```powershell
$sdkPython = (Resolve-Path '.venv/Scripts/python.exe').Path
$fixtures = New-Item -ItemType Directory -Path '.local/compatibility' -Force
@'
import asyncio
import sys
from pathlib import Path

from logix_designer_sdk import LogFileEventLogger, LogixProject

async def main():
    acd = Path(sys.argv[1]) / "Synthetic38.ACD"
    with LogFileEventLogger(str(acd.with_suffix(".log"))) as logger:
        with (await LogixProject.create_new_project(str(acd), 38, "1756-L85E", "McpSnapshotSample", logger)) as project:
            await project.save_as(str(acd.with_suffix(".L5K")))
            await project.save_as(str(acd.with_suffix(".L5X")), detailed_l5x=True)

asyncio.run(main())
'@ | & $sdkPython - $fixtures.FullName
```

On a standard Studio 5000 installation with the matching sample packs, the Rockwell samples used here are under `$env:PUBLIC\Documents\Studio 5000\Samples`. Use `DayOfWeek.L5X` in that directory and `ENU\v26\Rockwell Automation\DayOfWeek.ACD` below it.

### Verify native reads

Run the [native MCP smoke test](../BUILD.md#verify-rockwell-sdk-integration-on-windows) once with `Synthetic38.ACD` and once with `Synthetic38.L5K`. It checks two `get_project` calls and the source hash. Use the diagnostic command with `--project` to display the revision for each selected file. [Launch diagnostics](../README.md#check-the-installation)

### Verify SDK-free reads and expected failures

Create a second Python environment with just the MCP package.

```powershell
py -3.12 -m venv .local/compatibility-sdk-free
$sdkFreePython = (Resolve-Path '.local/compatibility-sdk-free/Scripts/python.exe').Path
& $sdkFreePython -m pip install .
& $sdkFreePython -m logix_project_mcp.doctor --project (Join-Path $fixtures.FullName 'Synthetic38.ACD')
```

- Start an [MCP client](../README.md#connect-an-agent) with `$sdkFreePython` for each full `.L5X`. Call `get_project` and controller-scope `list_tags` on both. Use `DayOfWeek.L5X` to call `list_tags` with a program name and `read_routine` with a program and routine from `get_project`. Compare each `source_sha256` with `Get-FileHash -Algorithm SHA256` for that file.
- Use the same SDK-free client with `Synthetic38.ACD` and call `get_project` to check the missing-wheel error. The diagnostic command above should also fail with wheel installation guidance.
- Use the SDK-enabled Python executable with the v26 `DayOfWeek.ACD` and call `get_project` to observe the tool error on an unsupported native revision. Compare `Get-FileHash -Algorithm SHA256` before and after each failure case.

### Verify offline export

Launch the SDK-enabled MCP with a synthetic revision-matched `.ACD` or `.L5K` and add `--export-dir` with an existing scratch directory. Use `get_project` to choose a routine from the sample. Call `export_project` for a full `.L5X`, a full `.L5K`, and a routine `.L5X`, using a new filename each time. Compare each returned `source_sha256` with `Get-FileHash -Algorithm SHA256` for the selected file. Retry with an existing destination and a missing routine, then recheck the selected file, the existing output, and a neighboring file. [Export arguments](mcp-contract.md#offline-export)

In Logix Designer, choose **File > Open** to import a full `.L5X` or `.L5K` and enter a new `.ACD` path when prompted. For a routine export, open a scratch project, select the destination program, and choose the routine option under **File > Import Component**. [Rockwell full-project import](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/import-and-export/import-export-a-full-project.html) · [Rockwell component import](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/studio-5000-logix-designer/import-and-export.html)
