# Build and verify

Create the environment described in [README.md](README.md#install) and activate it or invoke its Python executable. Install the package in editable mode while developing. CI builds one universal wheel and tests that artifact on Windows and Ubuntu with Python 3.12 and 3.13.

```sh
python -m pip install -e .
python -m pip check
python -m unittest discover -s tests -v
```

The default test suite starts a real local MCP process and verifies tool schemas, capabilities, reads, exports, and errors with a synthetic project. It checks that an occupied export destination survives a request, including when the file appears while an export is in progress. It also exercises concurrent reads, source changes, cancellation, and timeout recovery with a stand-in SDK subprocess. To build a distributable wheel, run `python -m pip wheel --no-deps --wheel-dir dist .`.

Failure-recovery tests use the same MCP connection before and after an invalid XML declaration, unsupported encoding, locked Windows file, linked source or occupied export path. The sharing helper also checks that a rejected document preserves the previous selection. Worker tests check each failure status and verify that diagnostic text written by the child stays out of the client response.

Proposal tests verify the documentation-only preview and content identity through MCP stdio, with duplicate scoped names, modified previews, stale saved bytes, unsupported operations, and selection refresh or switching. The optional native smoke test also checks proposal preview and validation without modifying the sample.

Documentation-copy tests cover creation, replacement, and removal of existing component descriptions, exact preservation of unrelated XML bytes, staged artifact fingerprints, invalid encoding, changed source and selection during staging, and destination collisions. These are SDK-free L5X checks, not Studio 5000 import verification.

Artifact verification tests also check concurrent read-only calls, retained fingerprints, modified descriptions and unrelated content, missing artifacts, stale sources, and source, artifact, or selection changes during verification.

Preservation tests use synthetic AOI definitions and opaque protected records, require exact preservation of unrelated XML, and reject representative safety-signature and safety-class indicators without blocking normal saved-project inspection. The verifier explicitly reports that vendor verification was not performed.

For the optional SDK documentation reopen test, see [documentation verification](docs/compatibility.md#documentation-verification).

Local review tests cover the packaged command, mocked interactive approval and decline, noninteractive rejection, invalid receipts, replay and a competing approval sidecar, and changes to source, artifact, or shared selection during review. They use synthetic documentation artifacts and never approve a real project.

The same tests exercise the read-only `--check` command with a retained review ID. They cover a moved or altered record, a different selection, edits to the source or reviewed copy, and a record replaced during verification. The optional SDK reopen test also uses the path returned by this check.

Routine-documentation tests exercise same-named Ladder and Structured Text routines in separate programs through the MCP tools, rejection of ambiguous, protected, unsupported and missing routines, and byte-for-byte preservation of saved source, comments, and pending sections.

Shared-selection tests launch the packaged sharing module and switch between same-named projects in an existing MCP session. They exercise refresh, missing and moved files, stale search pages, and failed selection validation.

Custom Tools tests exercise installation, updates, and removal on disposable XML configurations, including repeated operations, backup contents, menu name conflicts, and an intervening file change. Use the [Windows menu walkthrough](docs/studio-5000-integration.md#install-send-current-project-to-agent) for desktop validation.

The [inspection benchmark](docs/performance.md#repeat-the-measurements) runs separately from the test suite. Its SDK-free mode generates both project sizes in a temporary directory. Native mode uses saved sample copies and the installed Windows SDK.

## Verify Rockwell SDK integration on Windows

Install the native prerequisites from [README.md](README.md#requirements). Point the optional SDK smoke test at a Rockwell sample project or another saved copy you are authorized to inspect. Run once per native format you want to verify. The test sends `get_project` twice through MCP stdio, checks both returned fingerprints, and compares the source file hash before and after.

```powershell
$env:LOGIX_PROJECT_MCP_TEST_PROJECT = 'C:\path\to\Sample.ACD'
python -m unittest discover -s tests -v
Remove-Item Env:LOGIX_PROJECT_MCP_TEST_PROJECT
```

The test inherits the launching PowerShell environment. Use [the diagnostic command](README.md#check-the-installation) to compare that setup with the reduced MCP client environment. Report the project revision, SDK wheel version, and the formats exercised. An SDK export run directly in Python checks a different entry point from the MCP smoke test. Record both outcomes when diagnosing a native failure.

Follow the [offline export checks](docs/compatibility.md#verify-offline-export) to verify native format conversion and component import.

## Test the distribution wheel

Build from a checkout and pass the wheel to the same verifier that CI runs. The script creates a disposable virtual environment, exercises the installed commands outside the checkout, and runs the repository test suite with that environment's Python. The Windows jobs use a disposable Custom Tools XML file. The verifier also checks that the shared selection and unrelated menu entries survive package replacement and removal.

```powershell
python -m pip wheel --no-deps --wheel-dir dist .
$wheel = (Get-Item .\dist\logix_project_mcp-*.whl).FullName
python scripts/verify_wheel.py $wheel
```

Use a build directory containing one project wheel, or specify the exact filename. By default the upgrade check reinstalls the same build. Use `--previous-wheel` with a prior wheel containing the sharing and menu commands to exercise an upgrade between builds. For a local native check, set `LOGIX_PROJECT_MCP_TEST_PROJECT` to a synthetic ACD or L5K and add `--sdk-wheel` with the locally installed Rockwell wheel path. The hosted matrix exercises only the SDK-free installation.

## Upgrade or remove a wheel installation

Keep the same environment and selection-file path when updating the installed wheel. Run `python -m pip install --upgrade <wheel-path>` using the environment's Python. For a replacement development build with the same version number, add `--force-reinstall`. Restart the MCP client process to load the new code. The documented stdio JSON configuration and the Codex shared-selection configuration both work with the wheel environment. [Client configuration](README.md#connect-an-agent) · [Codex registration](docs/studio-5000-integration.md#connect-codex)

To uninstall, first remove the managed Studio menu entry using the installed menu helper. Then run `python -m pip uninstall logix-project-mcp` in the same environment and remove the server registration from the MCP client where you added it. The selection JSON belongs to the engineer and can be reused on reinstall. [Menu removal](docs/studio-5000-integration.md#remove-the-menu-entry)
