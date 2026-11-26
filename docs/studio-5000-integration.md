# Studio 5000 integration

The Windows sharing helper accepts a Studio 5000 Custom Tools project-path argument or a manually chosen saved project. The MCP server reads the latest saved file at that path, using the existing snapshot and SDK worker. The menu installer adds the sharing command to an existing Logix Designer installation.

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

### Open a reviewed ACD or import its routine

Keep the review ID from local approval and the published directory containing `Reviewed.ACD`, `Routine.L5X` and the approval record. Immediately before using either output, check the bundle against the original source selection. Substitute your actual paths. If approval used `--selection-file`, supply that same selection file in place of `--project`. [Native approval and recheck](mcp-contract.md#reviewed-native-outputs)

```powershell
$reviewId = Read-Host 'Review ID retained at approval'
$json = logix-project-mcp-review-native --project 'C:\Projects\Source.ACD' --check $reviewId 'C:\Reviews\Trial'
if ($LASTEXITCODE -ne 0) { throw 'Recheck failed. Resolve the reported mismatch before opening or importing.' }
$review = $json | ConvertFrom-Json
$review.proposal.source | Format-List path, source_sha256, controller, software_revision
$review.proposal.preview | ConvertTo-Json -Depth 4
'Published paths'
$review.outputs | Format-List acd, l5x
'Approved SHA-256'
$review.sha256 | Format-List acd, l5x
$review.build.status
```

The preview names the destination program and routine and shows the approved description before and after the edit. Each key in `outputs` has a matching key in `sha256`. If the build status is `manual_required`, complete the [manual offline build check](compatibility.md#offline-controller-build) and record its result.

**Open the complete reviewed project.** In a separate offline Logix Designer window, choose **File > Open** and enter the absolute `outputs.acd` path. Check the controller, program, routine and description against the receipt. To continue editing, work on a separate copy. Keep the published files at their recorded paths for future checks.

**Import the reviewed routine into an offline working copy.**

1. Identify the intended destination by its full ACD path, controller and revision. If the open editor shows an asterisk, leave that window open. To include its pending edits, use **File > Save As** to save them under a new path, inspect the saved changes and review the proposal against that new baseline before importing. To keep the pending work separate, open a fresh copy of the reviewed source in another window. Confirm that the copy's SHA-256 matches `proposal.source.source_sha256` before editing it.
2. In the destination window, confirm **Offline**. In **Controller Organizer**, right-click the program named in the preview and choose **Import Routine**. Enter the absolute `outputs.l5x` path and confirm the file picker (**Open** in the tested 38.02 editor) to reach **Import Configuration**. [Rockwell routine import procedure](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/import-and-export/importing-exporting-a-routine.html)
3. The approved description edit targets an existing routine, so expect a same-name collision. Check the destination program, **Final Name**, routine type and collision details. **Use Existing** keeps the destination routine's current description. Choose **Overwrite** for that one routine only after confirming the logic matches and the description difference is the one approved. Inspect referenced components and keep their existing definitions. Cancel on an unexpected name, reference change or logic difference. [Rockwell routine import operations](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/37-01/contents-ditamap/studio-5000-logix-designer/import-and-export/import-routine-considerations.html)
4. Choose **OK**, verify the destination project in Studio and save the working copy. Reopen it, check the routine description and logic, and confirm any separately reviewed edits. Record the saved destination's absolute path and its own SHA-256 with `Get-FileHash -LiteralPath 'C:\Projects\Working copy.ACD'`. The receipt's ACD hash identifies the published complete project. The new hash identifies this Studio save.

### Open a reviewed full L5X documentation copy

1. Keep the `review_id` from the successful interactive approval in your review notes. Keep the adjacent `.approval.json` file with the staged copy. The ID identifies the reviewed paths, hashes and proposed descriptions. The approval record identifies a local decision and carries no signer credentials. [Local review and approval](mcp-contract.md#local-review-and-approval)
2. Immediately before opening the file, run the following command with the retained ID and both paths. For a shared project, use the original `--selection-file` in place of `--project`. A refresh changes the selection ID.

   ```powershell
   $reviewId = Read-Host 'Review ID retained at approval'
   logix-project-mcp-review --check $reviewId --project 'C:\Projects\Source.L5X' 'C:\Reviews\Reviewed.L5X'
   ```

3. On success, the JSON gives the absolute file to open in `artifact.path`, the verified SHA-256 in `artifact.artifact_sha256`, and the saved source path and hash in `artifact.source`. If the command reports a mismatch, check the selected paths and ID. A changed project requires a fresh proposal and approval. This check reads the files on disk and cannot see pending edits in an editor window.
4. Open a separate offline Logix Designer window if another project has unsaved edits. Choose **File > Open** and enter the verified `artifact.path`. In **Save Imported Project As**, choose an unused scratch destination such as `C:\Reviews\McpReviewed.ACD`, then select **Import**. Review the import messages and compare the scoped descriptions with the proposal before using the imported copy. The verified hash identifies the input L5X. Studio creates the destination ACD during import. [Rockwell full-project import](https://www.rockwellautomation.com/en-gb/docs/studio-5000-logix-designer/38-02/contents-ditamap/studio-5000-logix-designer/import-and-export/import-export-a-full-project.html)

Run staging, review and Studio under a Windows account that can read the resulting files. In the desktop test the sandbox account could read its staged copy, while the editor account received an access-denied error. Staging a fresh synthetic copy under the editor account resolved that error.

On Windows 11, Logix Designer imported the synthetic revision 38.02 reviewed L5X into a new ACD. Reading that ACD through MCP returned the reviewed controller description. The saved source and reviewed L5X hashes also matched the approval record after import.

### Verify the Custom Tools path

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

## Share and refresh

Choose a local selection JSON file and configure the MCP client's server arguments with `--selection-file` followed by that absolute path. Start the server with that configuration once. The helper creates the file on its first successful share. The path can be in your own Windows profile, for example the following PowerShell commands from the repository root.

```powershell
$selection = Join-Path $env:LOCALAPPDATA 'logix-project-mcp\selection.json'
.\.venv\Scripts\python.exe -m logix_project_mcp.share --selection-file $selection 'C:\Projects\Line One.ACD'
```

For a graphical file picker, omit the project path and supply `--dialog`. Use `--refresh` to validate and share the previous saved path again. Adding `--dialog` to either a supplied project or a refresh displays the confirmation or the error in a Windows dialog.

```powershell
.\.venv\Scripts\python.exe -m logix_project_mcp.share --selection-file $selection --dialog
.\.venv\Scripts\python.exe -m logix_project_mcp.share --selection-file $selection --refresh --dialog
```

The installed `logix-project-mcp-share` command accepts the same arguments. The menu installer uses the Python environment's `Scripts\pythonw.exe` with arguments `-m logix_project_mcp.share --dialog --selection-file "C:\path\to\selection.json" "%project_path%"`. Use the JSON path configured for your MCP client.

- Share the path from the editor window in which the engineer chooses the command. The helper reads a verified copy of the existing project and confirms the selected path, controller, and software revision. Each successful share creates a new selection ID.
- MCP responses identify the path, selection ID, and actual inspected revision. The shared server switches to the last successfully shared project on its next request. Moving between editor windows alone leaves the last shared selection in effect.
- Save editor edits before requesting a refresh. Subsequent reads of the same selection take a fresh verified snapshot. The explicit refresh also changes the selection ID. If a file is unavailable or changes during copying, retry after the save completes or share the new saved path.
- A failed validation leaves the prior selection in place. When the editor shows error 786-0, open or create a project and invoke the command again. The manual file picker supports `.ACD`, `.L5K`, and full `.L5X` selection. If the selection JSON itself is invalid, choose a fresh JSON path for the client and helper.

Keep the editor session and the SDK worker's temporary project copies within their existing file-based responsibilities. [Architecture](architecture.md)

### Helper verification

On the same Windows and SDK setup used for the desktop walkthrough, the helper switched between two open 38.02 `.ACD` copies while a single MCP session remained connected. An offline controller description edit saved in the second editor became visible after the helper's explicit refresh. The response's source hash changed from `795ee045` to `d4f900f3` and matched the current saved bytes. The first copy retained its original hash. The supplied-project Windows confirmation and the manual L5X picker both published valid selections.

The same helper and MCP selection mode read a 38.02 saved `.L5K` and returned its matching source hash. The SDK-free wheel's sharing command also validated and selected a full `.L5X`.

## Connect Codex

From a normal Windows PowerShell in the repository, after completing the Python and SDK setup, register the stdio server with the installed Codex CLI. Use a selection file in your own Windows profile rather than a project-specific or temporary directory. The `ProgramFiles` environment entry makes the installed .NET runtime discoverable to the native SDK worker.

```powershell
$selection = Join-Path $env:LOCALAPPDATA 'logix-project-mcp\selection.json'
$python = (Resolve-Path '.venv/Scripts/python.exe').Path
codex mcp add logix-project-mcp --env "ProgramFiles=$env:ProgramFiles" -- $python -m logix_project_mcp.server --selection-file $selection
codex mcp list
codex mcp get logix-project-mcp
```

The registration persists in your Codex configuration. Allow extra time for the first SDK export of a saved `.ACD` or `.L5K`: in the existing `[mcp_servers.logix-project-mcp]` section of `~/.codex/config.toml`, set `tool_timeout_sec = 120`. Unchanged native snapshots are cached within a connected server session. See the [Codex MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) for configuration details.

Use that same absolute selection file when [installing the Studio 5000 menu](#install-send-current-project-to-agent) or [sharing manually](#share-and-refresh). If you use a different administrator account for menu installation, pass the original user's selection path explicitly. Open a new Codex session after registration, share a saved project, and ask Codex to use `logix-project-mcp`'s `get_project` tool to identify it. Share another saved project to change the selection without editing the MCP configuration. If the menu was previously installed with a different selection file, save your work and reopen Logix Designer to load the updated command. The selection persists across Codex sessions and Windows restarts.

The registration configures saved-project inspection only. It does not establish an online controller connection. If no project has been shared, use the menu or manual picker before requesting an inspection.

## Install Send Current Project to Agent

Configure the MCP client for shared selection as described above. Note the absolute `--selection-file` path from that configuration. Close the Logix Designer editor windows before changing the shared Custom Tools configuration so that the next launch loads the new entry. Run the following from an administrator PowerShell in the repository, using the actual selection path from your MCP client.

```powershell
$selection = 'C:\Users\YourName\AppData\Local\logix-project-mcp\selection.json'
.\.venv\Scripts\python.exe -m logix_project_mcp.custom_tools install --selection-file $selection
```

The installed `logix-project-mcp-menu` command provides the same `install` and `remove` subcommands. The installer locates `CustomToolsMenu.xml` in the standard Rockwell installation directories. If it cannot identify a single existing configuration, specify the file using `--config` before the subcommand. The XML format follows Rockwell's published Custom Tools configuration. [Rockwell Custom Tools XML help](https://www.rockwellautomation.com/en-us/docs/studio-5000-logix-designer/38-01/contents-ditamap/studio-5000-logix-designer/about-tool-windows/add-a-custom-tool-to-the-tools-menu.html)

Reopen Logix Designer and a saved project. Save any pending edits, then select **Tools > Send Current Project to Agent**. The confirmation window identifies the shared project and revision. Call `get_project` from the connected MCP client to inspect the current selection. Repeat from a different editor window to share that project.

The command updates its own entry when the configured Python environment or selection file changes. Repeating an identical installation leaves the XML bytes intact. Each actual change reports the path to a backup of the previous configuration. Existing menu entries, separators, and comments are retained. An unrelated entry using the same name or an occupied 16-tool menu requires resolving the conflict first.

### Remove the menu entry

Close Logix Designer and run the following from administrator PowerShell.

```powershell
.\.venv\Scripts\python.exe -m logix_project_mcp.custom_tools remove
```

Use the same `--config` override if needed. Removal targets the installer-managed entry and reports a backup on a change. A repeated removal reports no change. The saved selection is available to the manual sharing helper, which provides a file picker for any setup where Custom Tools is unavailable.

### Menu verification

On Windows 11 build 26200 with Logix Designer 38.02 and SDK wheel 2.0.2, the installer added **Send Current Project to Agent** alongside the existing entries in the standard Rockwell configuration. Selecting the command in an editor opened on `Shared project with spaces.ACD` launched the sharing helper. An already-connected MCP client received the absolute path and read the controller at revision 38.02 with the matching saved-file SHA-256.

The second install and second removal both reported no change. Existing entries and the configuration ACL matched their originals. After the test, the original XML was restored byte for byte. The SDK-free wheel's console installer also passed repeated install and removal against a disposable configuration.
