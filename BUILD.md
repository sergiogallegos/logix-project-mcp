# Build and verify

Create the environment described in [README.md](README.md#install) and activate it or invoke its Python executable. Install the package in editable mode while developing. CI installs the package from the checkout and runs the same offline checks on Windows and Ubuntu with Python 3.12 and 3.13.

```sh
python -m pip install -e .
python -m pip check
python -m unittest discover -s tests -v
```

The default test suite starts a real local MCP process and verifies tool schemas, capabilities, reads, exports, and errors with a synthetic project. It checks that an occupied export destination survives a request, including when the file appears while an export is in progress. It also exercises concurrent reads, source changes, cancellation, and timeout recovery with a stand-in SDK subprocess. To build a distributable wheel, run `python -m pip wheel --no-deps --wheel-dir dist .`.

Proposal tests verify the documentation-only preview and content identity through MCP stdio, with duplicate scoped names, modified previews, stale saved bytes, unsupported operations, and selection refresh or switching. The optional native smoke test also checks proposal preview and validation without modifying the sample.

Documentation-copy tests cover creation, replacement, and removal of existing component descriptions, exact preservation of unrelated XML bytes, staged artifact fingerprints, invalid encoding, changed source and selection during staging, and destination collisions. These are SDK-free L5X checks, not Studio 5000 import verification.

Artifact verification tests also check concurrent read-only calls, retained fingerprints, modified descriptions and unrelated content, missing artifacts, stale sources, and source, artifact, or selection changes during verification.

Preservation tests use synthetic AOI definitions and opaque protected records, require exact preservation of unrelated XML, and reject representative safety-signature and safety-class indicators without blocking normal saved-project inspection. The verifier explicitly reports that vendor verification was not performed.

For the optional SDK documentation reopen test, see [documentation verification](docs/compatibility.md#documentation-verification).

Routine-documentation tests exercise same-named Ladder and Structured Text routines in separate programs through the MCP tools, rejection of ambiguous, protected, unsupported and missing routines, and byte-for-byte preservation of saved source, comments, and pending sections.

Shared-selection tests launch the packaged sharing module and switch between same-named projects in an existing MCP session. They exercise refresh, missing and moved files, stale search pages, and failed selection validation.

Custom Tools tests exercise installation, updates, and removal on disposable XML configurations, including repeated operations, backup contents, menu name conflicts, and an intervening file change. Use the [Windows menu walkthrough](docs/studio-5000-integration.md#install-send-current-project-to-agent) for desktop validation.

## Verify Rockwell SDK integration on Windows

Install the native prerequisites from [README.md](README.md#requirements). Point the optional SDK smoke test at a Rockwell sample project or another saved copy you are authorized to inspect. Run once per native format you want to verify. The test sends `get_project` twice through MCP stdio, checks both returned fingerprints, and compares the source file hash before and after.

```powershell
$env:LOGIX_PROJECT_MCP_TEST_PROJECT = 'C:\path\to\Sample.ACD'
python -m unittest discover -s tests -v
Remove-Item Env:LOGIX_PROJECT_MCP_TEST_PROJECT
```

The test inherits the launching PowerShell environment. Use [the diagnostic command](README.md#check-the-installation) to compare that setup with the reduced MCP client environment. Report the project revision, SDK wheel version, and the formats exercised. An SDK export run directly in Python checks a different entry point from the MCP smoke test. Record both outcomes when diagnosing a native failure.

Follow the [offline export checks](docs/compatibility.md#verify-offline-export) to verify native format conversion and component import.
