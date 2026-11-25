# Working with a saved project

For a first connection, follow the [quick start](../README.md#quick-start). Use a fixed `--project` path to inspect one file. For a workstation with several projects, configure the client and Studio sharing helper with the same absolute `--selection-file` path. The server picks up a successful share on its next request. [Studio menu installation](studio-5000-integration.md#install-send-current-project-to-agent) · [Codex registration](studio-5000-integration.md#connect-codex)

## Check which save you are reading

In the intended Studio window, save your changes and choose **Tools > Send Current Project to Agent**. Call `get_project` and check the returned selection path, controller and software revision. If two windows contain copies with the same controller name, the path distinguishes them. Compare `source_sha256` with `Get-FileHash` on the saved file. Switching focus between windows leaves the last successful selection active. An asterisk in the editor title can explain why a change you see in Studio is missing from a read. [Desktop checks before and after Save](studio-5000-integration.md#observed-desktop-behavior)

## Change a description offline

1. Configure the client with an existing `--export-dir` and choose a new filename for each output. For ACD or L5K, use `export_project` to export the full project to L5X, then select that export. For a full UTF-8 L5X, select the file directly.
2. Call `get_project` on the selected L5X. Ask the client to preview a `set_description` operation using that response's source hash and, in shared mode, selection ID. Specify the program for a program tag or routine. Check the scoped target and before/after text. Retain the proposal and its `approval_id`. [Proposal fields and example](mcp-contract.md#offline-change-proposals)
3. Validate the reviewed proposal, create the documentation copy, and verify the copy using the artifact hash returned at creation. Save the exact proposal and creation response objects as JSON. These checks establish which bytes implement the proposal. [Creation and verification arguments](mcp-contract.md#documentation-copy)
4. Run the installed review command from a terminal in the same environment. Supply the original selection file (or the fixed source path used during preview), the two JSON files, and the candidate path. Review the values at the prompt. On approval, retain the returned `review_id` separately and keep the adjacent `.approval.json` with the candidate. [Review command examples](mcp-contract.md#local-review-and-approval)
5. Before opening the copy, run the review command with `--check`, the retained review ID and the same selection or source. In Studio, import the returned `artifact.path` into a separate, unused ACD destination. For a repeatable sample run with readback, use the [acceptance walkthrough](engineer-acceptance.md).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Client lists no tools, or cannot launch Python | Use the absolute executable path from the environment containing the wheel. Run its doctor against the same sample, then restart the client connection after correcting its configuration. [Client setup](../README.md#connect-an-agent) |
| `selection_required`, wrong project, or Studio error 786-0 | Open the saved project, share it from the intended window, and confirm the client and helper use the same selection path. A failed share preserves the previous selection. [Share and refresh](studio-5000-integration.md#share-and-refresh) |
| `invalid_project` or `project_unavailable` | For XML, check that you selected a full project export and consult any reported line and column. For an unavailable file, check its current path and read access, wait for Save to finish, then retry. |
| Native reads fail while a full L5X works | Run the environment's doctor with `--project <sample.ACD> --compare-launch-env`. Check the Rockwell wheel in that environment, matching Studio revision, activation, SDK service and .NET runtime. If only the reduced launch fails, forward the working environment values as described in the [installation checks](../README.md#check-the-installation). |
| `project_changed` or `selection_changed` after preview | Read the current selection again. A refresh changes its ID even when the bytes match. Generate and review a fresh proposal using the new identity. |
| `destination_exists` or `artifact_changed` | For an occupied destination, use an unused filename. For a changed candidate, return to the saved source, create and verify a new copy, then repeat local review. Keep the previous review record with its original artifact. |
| Studio rejects the import destination with 716-80042029 | In the revision 38.02 sample run Studio rejected `Studio inspection.ACD` and accepted `McpReviewed.ACD`. Try an unused simple project name in a writable scratch directory. If access is denied when opening the reviewed L5X, check the account that staged it and the account running Studio. [Desktop handoff](studio-5000-integration.md#open-a-reviewed-full-l5x-documentation-copy) |

For a support report, include the package and Python versions, host OS, selected format and software revision, tool or command, exact error code, and the doctor checks that passed or failed. For native failures, include the Studio and SDK versions and whether the inherited and reduced launches differed. Use a synthetic or Rockwell sample to reproduce the issue and redact private paths and project details. [Tool error reference](mcp-contract.md#tool-errors)
