# Studio 5000 integration

The planned Windows integration uses a Studio 5000 Custom Tools command to hand the selected project path to a local helper. The MCP server reads the latest saved file at that path, using the existing snapshot and SDK worker. The helper and permanent Tools menu installation are tracked by [LPM-021 and LPM-022](agents/board.md).

## Supported entry point

Logix Designer offers a **Project Path** argument in its Custom Tools dialog. The macro in the XML configuration is written as `"%project_path%"`, including quotes to preserve paths containing spaces. Rockwell's own version-control tools use this argument for file-based commands. [Custom Tools help (38.02)](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/about-tool-windows/add-applications-to-the-tools-menu.html) · [Rockwell's Custom Tools XML example](https://github.com/RockwellAutomation/ra-logix-designer-vcs-custom-tools/blob/main/src/l5xgit/Assets/CustomToolsMenu.xml)

The published Logix Designer SDK API opens an existing project by filename and returns a project object for that SDK session. The installed Python SDK reference (wheel 2.0.2) and published getting-results guide describe this file-based interface. Attachment to an existing desktop editor's working copy is unspecified in the reviewed SDK references. For editor integration, the project will use the documented path handoff and latest saved snapshot. [Rockwell SDK Getting Results Guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)

Logix Designer keeps pending edits in a working copy. Applying properties commits them to the working copy, and saving commits them to the project file. An engineer should save the project to make editor changes visible to MCP. [Rockwell commit semantics](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-03/contents-ditamap/studio-5000-logix-designer/about_rsl5k_project_components/commit-semantics.html)

## Observed desktop behavior

Validated on Windows 11 x64 build 26200 with Logix Designer 38.02, Python 3.12.10 x64, and SDK wheel 2.0.2. A temporary menu entry recorded the actual Windows argument array and working directory. The two copied samples shared the controller name `McpSnapshotSample`.

| Editor state | Observed result |
| --- | --- |
| Two open editor windows | The first window passed one argument ending in `Menu Alpha.ACD` and the second passed one ending in `Menu Beta.ACD`. Both were absolute paths with spaces. |
| Saved `.ACD` already open | MCP opened a snapshot of the selected file and reported software revision 38.02. The source SHA-256 before and after the request matched. |
| Unsaved edit in the first window | After applying a controller description, the editor title included `*`. The menu still passed `Menu Alpha.ACD`. MCP reported the previous saved description and hash. |
| After Save | MCP reported the new description and a different source SHA-256 from the same path. |
| No open project | The tool entry remained available. Selecting it produced Logix Designer error 786-0 about a macro problem, before the path-capture process launched. |
| New project before explicit Save | Completing the wizard created `McpNewBeforeSave.ACD` at the chosen location. The menu passed its absolute path immediately after creation, and MCP read the new project at revision 38.02. |

The pre-save SHA-256 for the edited sample began `795ee045`, and the post-save SHA-256 began `9fb2726c`. The source hash checks matched the saved bytes during each MCP request. The temporary Custom Tools entry used the documented XML file. The original configuration was restored and its SHA-256 matched the backup.

## Desktop walkthrough

Use copies of a matching synthetic project and put spaces in both filenames, for example, `Probe Alpha.ACD` and `Probe Beta.ACD`. Use the Windows setup in the [compatibility matrix](compatibility.md). Create an empty scratch directory for the diagnostic tool.

1. Save this script as `capture.py` in the scratch directory.

   ```python
   import json
   import sys
   from pathlib import Path

   with Path(__file__).with_name("project-path.jsonl").open("a", encoding="utf-8") as log:
       print(json.dumps(sys.argv[1:]), file=log)
   ```

2. Open **Tools > Custom Tools** in Logix Designer. Configuring the shared menu may require administrator access. The standard installation on this host stores its configuration at `C:\Program Files (x86)\Rockwell Software\RSLogix 5000\Common\CustomToolsMenu.xml`. Back up that file before adding the probe.
3. Add a new entry named **MCP Path Probe**. Set **Command** to the MCP Python environment's `Scripts\pythonw.exe`. Under **Arguments**, enter the quoted absolute path of `capture.py`, followed by a space and `"%project_path%"`. Choose the scratch directory as **Working Directory**. Confirm the dialog and reopen the editor windows to load the entry. The documented XML file is also suitable for configuring the same entry.
4. Open each of the two sample files in a separate Logix Designer window. Invoke **Tools > MCP Path Probe** from each window and compare the recorded argument arrays with their actual full `.ACD` paths.
5. In one sample window, open Controller Properties and edit the description while offline. Apply the edit and leave the project unsaved. Invoke the path probe, then read `get_inventory` through MCP with the recorded path selected using `--project`. Compare `controller.description` and `source_sha256` with another call after saving the sample.
6. Close the project and invoke the probe to reproduce error 786-0. Complete **File > New** using a scratch project name and directory, then repeat the probe before using Save. Inspect the created `.ACD` through MCP.
7. Restore the original configuration from its backup if the probe was the only change. Compare the restored SHA-256 with the backup. If other entries changed during the test, remove the temporary entry through Custom Tools and preserve those changes. Close the sample windows.

## Selection and refresh behavior

- Share the path from the editor window in which the engineer chooses the command. The helper validates the existing `.ACD` file and gives the engineer confirmation of which project was selected.
- Display the path, controller, software revision, and snapshot fingerprint. The current MCP process accepts one launch-time selection through `--project`; reopen the connection to select a different file until the selection helper is implemented.
- An engineer saves editor edits before requesting a refresh. Subsequent reads of the same selection take a fresh verified snapshot. If a file is unavailable or changes during copying, display the MCP error and retry after the save completes.
- If the selected path is missing, empty, or cannot be opened, show a local prompt to save or choose a saved project. When the editor shows error 786-0, open or create a project and invoke the command again. Provide an independent manual `.ACD`, `.L5K`, and full `.L5X` selection route for installations where the menu entry is unavailable.

Keep the editor session and the SDK worker's temporary project copies within their existing file-based responsibilities. [Architecture](architecture.md)
