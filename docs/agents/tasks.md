# Task briefs

Use the [board](board.md) to choose a task. Each brief gives a deliverable, an observable acceptance condition, and the evidence to record in the [handoff log](handoff.md).

## Foundation

### LPM-000

Ship a local Python MCP starter that reads a selected saved project. Acceptance is successful MCP initialization, tool discovery, and inspection of controller data, tags, and routines, with Windows native reads preserving the source file. See the [baseline evidence](handoff.md).

### LPM-001

Add a local diagnostic command and a supported Windows launch configuration. Report the Python architecture, SDK wheel, .NET runtime, and relevant Studio 5000 and SDK host checks without printing credentials or unrelated environment variables. Reproduce the reduced-environment timeout and provide a tested setup path with a clear diagnostic for installation failures. Verify `.ACD` through an actual MCP client launch and include an SDK-free `.L5X` smoke check.

### LPM-002

Make project snapshots and SDK worker cleanup predictable under cancellation, timeout, concurrent requests, and changes to the source during copying. Return a revision or fingerprint for each completed read and recover on a subsequent valid request. Add tests for source changes, an unavailable file, cancellation, and a stalled worker. Confirm repeated reads stay within the selected project and leave its hash intact.

### LPM-003

Publish the supported-format matrix with tested Windows, Python, Logix Designer, and SDK versions. Cover a native `.ACD`, its `.L5K` counterpart, a full `.L5X`, an unsupported revision, and missing vendor software. Record the actual project revision and tested operations separately from vendor-stated compatibility. Use synthetic exports or approved samples and record how to reproduce the checks.

### LPM-004

Authenticate the maintainer’s GitHub account, confirm write access to `sergiogallegos/logix-project-mcp`, and publish the initial tree with maintainer authorization. A regular Windows PowerShell session can use `gh auth login --hostname github.com --git-protocol https --web`, followed by `gh auth status --hostname github.com` and `gh auth setup-git`. In the repo, `git push --dry-run origin main` verifies write access before the authorized push. After pushing, confirm remote `main` points at the intended commit and record the first hosted CI run. The managed session currently cannot read the user GitHub configuration or use Windows Credential Manager.

## Project inspection and comparison

### LPM-010

Define stable request and response schemas for project identity, revision, capabilities, and errors. Preserve the existing `get_project`, `list_tags`, and `read_routine` entry points or document an explicit migration. Test MCP tool discovery, valid and invalid calls, and success and error response shapes through stdio.

### LPM-011

Expose a structured inventory of the controller, tasks and scheduling, programs, controller and program tags, modules, user-defined types, and Add-On Instruction metadata. Use qualified identities for duplicate names across scopes. Check results against a known exported project and test repeated names in different scopes, absent elements, and protected sections.

### LPM-012

Expose readable routine content for ladder logic and Structured Text, with structured inspection of Function Block and Sequential Function Chart content where the export provides it. Include positions and comments where available. Return an explicit status for protected or unsupported logic. Verify each supported routine type against a representative export and preserve exact source text for review.

### LPM-013

Search tags, symbols, routines, and comments, and return reference locations with scope and source revision. Add bounded results or pagination. Test same-name symbols across scopes, aliases, false substring matches, large result sets, and protected logic. Document which reference types the index can resolve.

### LPM-014

Compare two user-selected saved project snapshots by scope, reporting meaningful controller, tag, and routine changes with readable source context. Filter volatile export metadata while retaining substantive settings. Test an unchanged round trip, an added or removed component, a routine edit, and a project pair with the same display name.

### LPM-015

Support explicit offline export to a user-selected output path. Cover full `.L5X` and `.L5K` output on supported native revisions and component `.L5X` export where the SDK supports it. Verify an exported project or component can be opened or imported in Logix Designer, and confirm source and unrelated files retain their hashes when an export fails or a destination already exists.

### LPM-016

Reduce repeated native inspection latency, reported at around 30–40 seconds per request by the maintainer. Reuse a bounded, in-memory SDK export cache in each MCP session, keyed by the selected path and verified source SHA-256. Every request retains the source consistency checks. Exercise repeated calls, changed bytes with unchanged timestamps, different selections, missing files, failed exports, and cache eviction. Measure cold and warm MCP calls on a synthetic native sample and retain the broader performance work in LPM-041.

## Studio 5000 integration

### LPM-020

Test how Logix Designer passes the current project path through Custom Tools and document the behavior with multiple windows, an unsaved project, and an already-open saved `.ACD`. Check published support for access to an existing editor session. Acceptance is a reproducible desktop walkthrough and a documented user experience for the latest saved project when the editor API exposes only a path.

### LPM-021

Build a Windows helper that lets the engineer share the selected saved project and refresh it after saving. Validate the supplied path and identify the selected project and revision in MCP responses. Exercise paths with spaces, multiple open projects, a deleted or moved file, and a stale selection. Limit project selection changes to the local user action or an explicitly configured path.

### LPM-022

Add **Send Current Project to Agent** to the Studio 5000 Tools menu through documented Custom Tools configuration. Provide installation and removal steps that preserve existing entries and can be repeated. Verify the command on a supported Studio 5000 installation using a sample and a path containing spaces. Include a manual path-selection route for setups where menu integration is unavailable.

### LPM-023

Give the engineer a documented way to open the verified `.ACD` copy and to import a reviewed `.L5X` component into the intended offline project. Show paths, source and result identities, and the import target. Verify the workflow in Studio 5000, including a conflicting component name and a project that already has unsaved changes.

### LPM-024

Document and verify direct Codex registration of the local MCP server using a stable selection file shared with the Studio 5000 menu helper. Exercise tool discovery in a new agent session, selection changes, and the native Windows launch environment. Keep the manual sharing route and record the setup without committing user paths or project data.

## Offline project editing

### LPM-030

Define typed change proposals tied to a source revision and stable component identifiers. Produce a readable before-and-after preview and an approval identity tied to its content. Tests should reject ambiguous targets, stale sources, modified previews, and unsupported operations before materializing edits.

### LPM-031

Implement approved offline tag and metadata operations for supported scopes and data types. Cover create, update, and supported rename or remove operations with explicit reference and collision behavior. Verify expected metadata on a staged export and preserve unrelated tags, settings, and documentation.

### LPM-032

Implement supported offline ladder and Structured Text routine edits with scoped targets, documented import semantics, and readable previews. Record the treatment of comments and component dependencies. Test creation and update of a routine on a sample, a syntax error, a name collision, and protected logic. Keep the preview and any resulting artifact aligned.

### LPM-033

Apply an approved change proposal to a staged native project and emit a new `.ACD` copy plus component `.L5X` for supported changes. Preserve the required project revision unless conversion is explicitly selected. Test successful output, canceled or failed import, concurrency, destination collisions, and a source save between preview and application. Source and prior outputs retain their hashes on failure.

### LPM-034

Run the project checks available on each supported SDK and Logix Designer version. For release-supported edits, verify the resulting project opens, the intended change is present, and unrelated content is preserved. Report syntax or build errors and distinguish an automated Logix verification result from a manual verification step. Include representative AOI, protected content, and safety-signature preservation or rejection cases and document the supported editing boundary.

### LPM-035

Give the engineer a local review and approval step bound to the exact proposal, source fingerprint, and output path. Finalize the staged copy only after approval and the applicable validation checks. Test approval, decline, replay, a stale source, and failed validation. Document recovery using the original saved file and the generated diff.

## Hardening and release

### LPM-040

Harden input boundaries and failure recovery across MCP, the desktop helper, and the SDK worker. Test malformed or untrusted XML, path or link escapes, conflicting writes, locked files, interrupted workers, and retries. Keep structured diagnostics useful without writing project content, credentials, or unrelated user paths to logs. Verify a normal request succeeds after a recoverable failure.

### LPM-041

Measure cold start, native open, search, and diff on representative small and large projects. Set and document practical response and memory targets from the measurements. Exercise repeated requests and concurrent clients, then verify caches invalidate after a new save. Record hardware, project size, versions, and remaining bottlenecks.

### LPM-042

Build and test installable artifacts, including a Python wheel and Windows setup for the Studio 5000 helper. Validate clean installs of SDK-free and native modes and document representative supported MCP client configurations. Keep hosted CI SDK-free and record Windows SDK integration runs separately. Test upgrade, removal, and preservation of existing local settings.

### LPM-043

Run the complete workflow on a clean documented Windows setup with a sample project. Open `.ACD` in Studio 5000, share it, find and compare logic, preview an offline edit, approve it, verify the new copy, and reopen it or import the component. Also run the SDK-free `.L5X` path and `.L5K` verification. Record evidence for failures and recovery as well as the successful path.

### LPM-044

Finish the quick start, SDK and license prerequisites, supported-format matrix, desktop and MCP client setup, offline editing guide, troubleshooting, and release notes. Walk through the instructions from a clean environment. Make version and verification claims traceable to release evidence, including saved versus unsaved project behavior.

### LPM-045

Review the 1.0 release gate, select the release commit, confirm CI and manual Windows evidence, and verify artifacts from that commit. Record the maintainer’s publication approval before tagging and releasing. Confirm the published artifacts install and match the documented revision and features.

## Future diagnostics

### LPM-050

Review documented read-only diagnostics capabilities of the Rockwell SDK and assess whether the maintainer's `rust-ethernet-ip` library would fill a demonstrated gap. Evaluate the proposed user experience with offline or simulated data, including the distinction between saved project information and current observations. Record capability limitations, provenance, and prerequisites for any further work.
