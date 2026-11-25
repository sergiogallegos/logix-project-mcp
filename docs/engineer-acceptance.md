# Verify an offline routine documentation change

This walkthrough follows one saved sample from Studio 5000 through local review and back into Studio. It exercises the installed wheel, uses a private selection file in the run directory, and checks that the original file keeps its SHA-256.

## Share, inspect and review

From a repository checkout, install the wheel into a fresh Python environment. Use the Windows native prerequisites and Rockwell wheel for an ACD or L5K input. For the SDK-free check, install only the project wheel in a second environment and use a full L5X sample. [Wheel installation and SDK prerequisites](../README.md#requirements)

1. Open a disposable ACD in the matching Studio version. Save it and leave it open. Choose a readable Ladder or Structured Text routine. For the L5X and L5K runs, start from the corresponding saved sample on disk.
2. From an interactive PowerShell terminal, run the command below with the saved file path, the program and routine names as displayed in Studio, and a description different from the existing one. Choose a new work directory for each run. The directory can contain project contents and should stay local.

   ```powershell
   $python = '.\.venv\Scripts\python.exe'
   $run = '.local\acceptance-acd'
   & $python scripts/acceptance.py run 'C:\Samples\McpSample.ACD' --work-dir $run --program MainProgram --routine InspectText --description 'Synthetic acceptance note'
   ```

3. The runner shares the saved file with the installed sharing helper, locates the scoped routine and reads its logic over stdio. It exports and selects a full baseline L5X. It then refreshes the selection after preview and checks that the stale proposal fails with `selection_changed` before a copy exists. A fresh preview against the current selection allows the runner to create and verify `Reviewed.L5X`.
4. At the local review prompt, check the target, old and new descriptions, source and artifact hashes, and destination. Type `APPROVE` only if the change matches your intent. Any other answer declines, returns exit code 2, and leaves the staged file without an approval record. To repeat the walkthrough, choose another empty destination by supplying a fresh directory name.
5. After approval the runner rechecks the sidecar against the review ID, reopens the verified L5X over MCP, and compares the saved routine sections with the original. A successful run writes `acceptance.json` with the hashes, qualified routine, revision, review ID and artifact path. Retain the review ID separately when handing the file to another operator. Keep the source, selection and run directory available for readback.

For repeat coverage, run the same command with an L5K sample in the SDK environment and a full L5X sample in the SDK-free environment. Supply the routine names for each sample.

## Read back the Studio import

Open the verified full L5X in Studio and import it into a **new scratch ACD**. Use a simple project filename such as `McpReviewed.ACD`. Finish the import and save the project. From the SDK environment, run the following command against the file Studio created. [Studio handoff and import procedure](studio-5000-integration.md#open-a-reviewed-full-l5x-documentation-copy)

```powershell
& $python scripts/acceptance.py check-import (Join-Path $run 'McpReviewed.ACD') --work-dir $run
```

The command rechecks the reviewed artifact and reads the new ACD through the installed MCP server. It compares controller name, project software revision, routine language, saved sections and description, and reports the imported file's SHA-256. Studio may surround the saved description with a pair of formatting newlines. Keep this result with the review evidence. The dated handoff records which formats, versions and desktop steps have been exercised. [LPM-043 verification record](agents/handoff.md#2026-11-25--lpm-043--in-progress--codex-on-main)
