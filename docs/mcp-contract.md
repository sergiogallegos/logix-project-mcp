# MCP tool contract

Call `tools/list` to discover the JSON Schema for each tool's arguments and successful `structuredContent`. Call `get_capabilities` to learn the contract version, the selected file, and the format requirements. [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## Arguments and success results

| Tool | Arguments | `structuredContent` |
| --- | --- | --- |
| `get_capabilities` | Empty object or omitted | Contract version, file selection, format requirements, and host information |
| `get_project` | Empty object or omitted | `file`, `format`, `controller`, `processor_type`, `software_revision`, `programs`, `source_sha256` |
| `get_inventory` | Empty object or omitted | File identity, source revision, and the [project inventory](#project-inventory) |
| `list_tags` | Optional `program` string. Omit it or use `null` for controller scope. | `result` array of tag objects with `name`, `data_type`, and `description`, plus `source_sha256` |
| `read_routine` | Required `program` and `routine` strings | `result` string, `source_sha256`, and [routine inspection](#routine-inspection) |
| `search_project` | Required `query`. Optional `kind`, `program`, and [paging arguments](#scoped-search-and-cross-references). | Saved source identity, `matches`, and `next_offset` |
| `find_references` | Required `name`. Optional `kind`, `program`, and [paging arguments](#scoped-search-and-cross-references). | Saved source identity, `matches`, and `next_offset` |
| `preview_change_proposal` | Required `expected_source_sha256`, `operations`, and in shared mode `expected_selection_id` | [Typed documentation preview](#offline-change-proposals), source identity, and `approval_id` |
| `validate_change_proposal` | Required `proposal`, `expected_approval_id` | `valid: true`, source identity, and checked `approval_id` |
| `create_documentation_copy` | Required `proposal`, `expected_approval_id`, and new `.L5X` `filename` when an export directory is configured | [Documentation-only artifact](#documentation-copy), source identity, approval identity, and artifact SHA-256 |
| `verify_documentation_copy` | Required `proposal`, `expected_approval_id`, existing `.L5X` `filename`, and `expected_artifact_sha256` when an export directory is configured | Artifact identity and `valid: true`, `verification: "exact_documentation_copy"` |
| `compare_projects` | Optional `scope` when a candidate was [selected at launch](#project-comparison) | `before`, `after`, scoped `changes`, and `protected_components` |
| `export_project` | Required `filename` and optional `component` when an [export directory](#offline-export) was selected at launch | `path`, `format`, `component`, and `source_sha256` |

Inspection matches names without regard to case. The server rejects arguments outside the tool's schema. Select a fixed project through `--project` at launch or enable the [shared selection](#shared-selection) using `--selection-file`.

`file` is the selected file's basename. `format` is one of `acd`, `l5k`, or `l5x`. `software_revision` comes from the L5X `SoftwareRevision` attribute and may be `null`. `source_sha256` is the lowercase SHA-256 digest of the saved file snapshot. Compare hashes to determine whether reads used the same saved bytes.

Repeated native inspections can reuse a validated SDK export in the current server process. Each call verifies a fresh source copy and its SHA-256 before any cache lookup. Changed bytes, a different path, unavailable files, and failed reads retain their normal snapshot and error behavior.

The original three tool names and their result fields remain available. `get_project` adds `format`. Text content contains the project summary as JSON, one JSON object per listed tag, or the routine XML when available.

## Shared selection

Configure an absolute `--selection-file` JSON path and use the local [sharing helper](studio-5000-integration.md#share-and-refresh) with the same path. Only local selection-file updates change the project selection. A server can initialize before the first share, when capabilities report `project: null` and project reads return `selection_required`.

In shared mode `get_capabilities` includes `selection_mode: "shared"`. Successful project responses include `selection.path` (the absolute saved path) and `selection.selection_id` (a 32-character lowercase hexadecimal identifier). Inspection, search, and comparison also include `selection.controller` and `selection.software_revision` from their actual snapshot. Capabilities and export results provide the path and selection ID. Each successful local share or explicit refresh creates a fresh selection ID. A request uses the selection it captured when starting its read.

Saving an edit updates `source_sha256` on the next inspection while the selection ID stays the same. A moved or deleted saved file returns `project_unavailable` until the engineer shares an existing path. A missing selection file returns `selection_required`, and an invalid one returns `invalid_selection`.

## Project inventory

`get_inventory` returns `file`, `format`, `software_revision`, and `source_sha256` for a single saved snapshot. The sections below are available in the same response. The full success schema is available through `tools/list`.

| Section | Contents |
| --- | --- |
| `controller` | Name, description, processor type, and controller major and minor revisions |
| `tasks` | Task type and class, rate, priority, watchdog, event configuration, and scheduled program names in execution order |
| `programs` | Main and fault routine names, child program references, program tags, and routine identities |
| `controller_tags` | Controller-scope tag names, types, dimensions, alias targets, descriptions, and external access |
| `modules` | Catalog numbers, parent and port relationships, revisions, inhibition flags, and port addresses |
| `user_defined_types` | Type metadata and declared members, including hidden backing fields and bit targets |
| `add_on_instructions` | Names, revisions, vendor and protection metadata, and parameter declarations present in the export |

Controller tags use their bare names as `qualified_name`. Program tags and routines use `Program:<program>.<name>` within their respective inventories. Each tag carries its `scope`. Arrays retain export order, including the task schedule and child program references. Absent collections are empty arrays and missing optional fields are `null`. Values such as task `rate`, `priority`, `watchdog`, and revisions retain their exported text. User-defined types include entries marked `Class="User"` and entries whose class is absent in the export.

Encoded routines and Add-On Instructions appear with their visible metadata and `protected: true`. The flag also reflects recognized encryption markers on XML records. The inventory contains component metadata and omits tag values, routine bodies, and encoded payloads. [Rockwell Logix 5000 Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

## Routine inspection

`read_routine` resolves the requested program and routine without regard to case. `inspection` includes the exported names, `qualified_name`, the routine `language` code from `Type`, an optional description, `status`, and any readable `sections`. Each section preserves its XML attributes. Multiple sections keep export order, so `OnlineEditType` distinguishes original, pending, and test edits.

| Language | Section contents |
| --- | --- |
| `RLL` | `rungs` with saved `number`, rung `type`, instruction `text`, and optional `comment` |
| `ST` | `lines` with saved `number` and `text`, including inline comments and blank lines |
| `FBD` | `elements` such as sheets, blocks, wires, and text boxes, with nested entries and their exported attributes |
| `SFC` | `elements` such as steps, actions, transitions, branches, and directed links, with nested entries and their exported attributes |

Diagram entries contain `kind`, `attributes`, `text`, and `children`. The attributes retain sheet numbers, IDs, coordinates, connection endpoints, and pin names when present. Rung, line, and diagram text retains its characters and spacing after standard XML decoding and line-ending normalization. The source hash covers the exact saved file bytes. [Rockwell Logix 5000 Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

| `inspection.status` | Contents |
| --- | --- |
| `readable` | Language-specific sections and the legacy L5X XML string in `result` and text content |
| `protected` | Visible metadata and a protection message. `sections` is empty, `result` is an empty string, and text content carries the message. |
| `unsupported` | An explanation for an unknown language or missing content section, plus the available L5X XML string in `result` and text content |

A supported content section may be present and empty. Routine and program lookup failures use `not_found`.

## Scoped search and cross-references

`search_project` matches names case-insensitively and exactly, including qualified names such as `Program:Main.Counter`. Comment queries match a literal word or phrase at word boundaries. `kind` defaults to `all` and also accepts `tag`, `symbol`, `routine`, `comment`, or `reference`. `symbol` searches user-defined types and Add-On Instruction declarations. Use `program` to restrict the **locations** returned to one program. In reference searches, a name can match the direct symbol or one of its alias targets.

`find_references` selects a declaration by its bare `name`, `kind`, and `program`. `kind` defaults to `tag` and also accepts `routine`, `data_type`, or `add_on_instruction`. Supply `program` for a program tag or routine. Controller tags and controller-level types use the default `null` program. This tool searches across all programs for references to the selected declaration.

Each match reports its `kind`, `location`, a short `excerpt`, and its `symbol` when available. The location identifies controller or program scope and includes the originating declaration or routine. Routine locations include saved rung, line, sheet, diagram element ID, and a one-based text offset when applicable, plus the zero-based section and its exported online-edit type. For references, `reference_kind` identifies the relationship, `symbol` identifies the direct declaration, and `alias_targets` lists subsequent declarations reached through aliases.

| `reference_kind` | Supported source locations |
| --- | --- |
| `operand` | Declared base tags found in Ladder and Structured Text, diagram `Operand` attributes, and embedded Structured Text in Function Block or Sequential Function Chart content |
| `alias_target` | `AliasFor` on controller or program tags |
| `data_type` | Tag `DataType` attributes naming a declared user-defined type or Add-On Instruction |
| `routine_call` | A named first operand of `JSR` resolved in the calling program |
| `instruction_call` | Textual calls to declared Add-On Instructions |

Unqualified tag operands resolve to the current program before controller scope. Explicit `Program:<program>.<tag>` operands resolve in that program. Structure and array access resolve to the declared base tag. Array index expressions can also contain tag references. Alias resolution stops at unresolved targets or cycles. Comments and quoted strings are excluded from operand matching. Visible descriptions, rung comments, inline logic comments, and diagram text are searchable as comments. Protected routine headers remain searchable as declarations, while their bodies contribute zero matches. Tag operand matching is lexical and uses exported declarations. Use Studio 5000 for instruction-specific operand validation, indirect target resolution, and read/write analysis. [Rockwell Logix 5000 Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

Both tools return `file`, `format`, `software_revision`, and `source_sha256` for the saved snapshot. `limit` defaults to 50 and accepts 1–200. `offset` defaults to 0 and accepts up to 2,147,483,647. Keep the query and scope fixed between pages. Send `next_offset` as `offset` and the first page's `source_sha256` as `expected_source_sha256`. In shared mode also pass `selection.selection_id` as `expected_selection_id`. A newer save returns `project_changed`, a changed selection returns `selection_changed`, and a `null` `next_offset` marks the last page.

## Project comparison

Select the baseline using `--project` or the shared selection and add `--compare-project` with the candidate path in the server's launch arguments. Each can be an `.ACD`, `.L5K`, or full `.L5X`. With a candidate configured, `tools/list` includes `compare_projects` and `get_capabilities` reports the `comparison_project` selection. Inspection tools use the baseline.

Call `compare_projects` with `{}` for all supported scopes. Use `{"scope":{"kind":"controller"}}` for controller scope or `{"scope":{"kind":"program","program":"Main"}}` for one program. A program present on either side can be reviewed by name. The response labels the snapshots as `before` and `after`, each with file name, format, controller, software revision, and source SHA-256. The roles and hashes distinguish same-named projects.

Components match by kind and case-insensitive qualified name. The controller is matched by its role. Changes cover controller settings, tasks, modules, user-defined types, Add-On Instructions, programs, scoped tags, and routines. Each change includes its identity, an `added`, `removed`, or `modified` status, and a unified `xml_diff`. Ladder and Structured Text changes can also include a `source_diff` with rung or line positions and surrounding text.

Comparison normalizes XML indentation and attribute order and ignores export headers, common author and timestamp attributes, and `Use` context markers. Decorated tag values take precedence when an export also includes a redundant raw or L5K value. Saved settings such as the controller serial number, tag values, and schedule or rung order are compared. Protected components are listed in `protected_components` and compared using available metadata. [Rockwell Logix 5000 Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

## Offline change proposals

Both proposal tools are read-only and available without an export directory. First inspect the saved project, then pass its `source_sha256` as `expected_source_sha256`. In shared mode also pass the inspected `selection.selection_id` as `expected_selection_id`. The operation list must contain 1–50 entries.

Version 1 supports only `set_description`: documentation for an existing controller, program, controller tag, program tag, or saved readable Ladder or Structured Text routine. No tag values, control logic, project settings, or files are changed. Target records are typed and names resolve without regard to case; the returned target uses the spelling from the export. A program tag or routine must specify its program, even when another program or controller scope contains the same name.

| Target `kind` | Required additional fields |
| --- | --- |
| `controller` | None |
| `program` | `program` |
| `controller_tag` | `name` |
| `program_tag` | `program`, `name` |
| `routine` | `program`, `name` |

For example, the operations argument can contain:

```json
[{"operation":"set_description","target":{"kind":"program_tag","program":"Main","name":"Counter"},"description":"Sample documentation"}]
```

Descriptions are limited to 4,096 characters and must be valid XML text. A description of `null` proposes removing it; an empty string proposes an empty description. The preview preserves that distinction on both sides. Unsupported operations, multiple matching names, repeated targets, protected tags and routines, routines without saved Ladder/ST content, and unsupported description structures are rejected.

The response includes `schema_version: 1`, `source` (absolute path, nullable selection ID, SHA-256, controller name and software revision), normalized `operations`, and ordered `preview` entries with explicit `before` and `after` values. The `approval_id` is the SHA-256 of the ASCII JSON encoding of those fields, with sorted keys, no insignificant whitespace, and non-ASCII characters escaped.

Present the complete proposal to the reviewer and retain its approval identity independently. To check a previously reviewed proposal, send the unchanged proposal and that retained value as `expected_approval_id` to `validate_change_proposal`. Validation re-reads the selected saved project and rebuilds the entire preview; changes to the source bytes, selection, target, operation, before/after text, or identity are rejected. A successful check confirms content consistency at inspection time, not authorization or a guarantee against subsequent saves. The identity is a digest, not a signature or proof of human approval. No edit or artifact is materialized by either preview or validation.

## Documentation copy

With `--export-dir` configured, `create_documentation_copy` accepts a reviewed proposal, its independently retained `expected_approval_id`, and a new basename ending in `.L5X`. It reads a verified copy of the selected full UTF-8 L5X, validates the proposal against that exact snapshot, and changes only the targeted description byte ranges. Creating a description in a self-closing element also expands that element's closing delimiter. Other XML bytes, including logic, attributes, data, comments, and CDATA, remain unchanged.

The tool reparses the staged result and checks each description against the reviewed preview, checks the staged bytes, and rechecks the selected source fingerprint and selection immediately before publishing. A competing destination is never replaced. The result contains the absolute `path`, `format: "l5x"`, `source`, `approval_id`, and `artifact_sha256`. A save or selection change after the final check is still possible; the result identifies the exact source snapshot used.

This is an SDK-free documentation-only workflow. It supports creating, replacing, and removing descriptions of existing controllers, programs, scoped tags, and readable Ladder or Structured Text routines. Rung comments, inline ST comments, online-edit sections, routine dependencies and executable content remain unchanged. Native ACD/L5K input, non-UTF-8 L5X, changing tag declarations or values, creating routines, and modifying routine logic are not supported. The staged XML and preservation checks do not constitute Studio 5000 import or project verification.

Retain the proposal, reviewed approval identity, and the creation result's `artifact_sha256` independently. To check an existing output later, call the read-only `verify_documentation_copy` with those values and the artifact's basename in the configured export directory. The tool makes verified temporary copies of the saved source and artifact, checks the retained digest, reconstructs the expected documentation output from the reviewed proposal, and compares the entire artifact byte for byte. It checks both files and the selection again before returning. A new digest for an altered artifact cannot make it match the original reviewed output. Missing files, stale sources, changed selections, modified proposals, and altered artifacts fail without changing the source or artifact. Success provides `valid: true` and `verification: "exact_documentation_copy"` alongside the existing artifact identity fields.

This confirms exact correspondence to the supported documentation proposal as of the verification snapshots. It is not proof of human approval, a vendor build or import check, or a guarantee that an external process cannot modify the files after verification.

## Offline export

Add `--export-dir` and an existing directory to the launch arguments to enable `export_project`. The export uses the selected saved file. Supply a filename without directory segments. The server publishes the finished artifact only when there is no existing entry at the destination. It returns the absolute artifact `path`, lowercase `format`, requested `component` or `null`, and the source snapshot's SHA-256.

For a full export, omit `component` or pass `null`. Choose either `.L5X` or `.L5K`. Full `.L5X` input exported to `.L5X` is copied byte for byte. Other combinations require Windows and an SDK-compatible project revision. For component export, choose `.L5X` and use the names recorded in the saved project. [Rockwell SDK Getting Results Guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)

| `component.kind` | Other `component` fields |
| --- | --- |
| `program` | `name` of the program or equipment phase |
| `routine` | `program` and routine `name` |
| `data_type` | `name` of the user-defined data type |
| `add_on_instruction` | `name` of the Add-On Instruction |
| `rungs` | `program`, `routine`, and inclusive, zero-based `first` and `last` rung numbers |

Example component request.

```json
{"filename":"MainRoutine.L5X","component":{"kind":"routine","program":"MainProgram","name":"MainRoutine"}}
```

Rockwell's component exporter includes referenced project elements as context. Rockwell documents that exported safety components may omit safety signatures. [Rockwell SDK Getting Results Guide](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf)

## Capability reporting

`get_capabilities` returns `schema_version` as `1`. `read_only` is `true` by default and `false` when `--export-dir` enables file creation. Its `project` object contains `file` and `format`. Each `formats` entry describes inspection and contains `format`, `requires_windows`, and `requires_rockwell_sdk`. `platform` is the Python platform identifier such as `win32` or `linux`.

`rockwell_sdk_module_found` reports whether the server's Python environment can locate the vendor module. Use the [launch diagnostics](../README.md#check-the-installation) to test the SDK service, installed Logix Designer revision, runtime, and project read. `get_capabilities` can report the selection and requirements while the save file is unavailable.

## Tool errors

Expected failures return `isError: true` and a human-readable `content` block. Clients can read the stable error object from `_meta["logix-project-mcp/error"]`. Its JSON Schema is available in each tool definition's `_meta["logix-project-mcp/error-schema"]`.

```json
{
  "isError": true,
  "content": [{"type": "text", "text": "Program 'Missing' was not found."}],
  "_meta": {
    "logix-project-mcp/error": {
      "code": "not_found",
      "message": "Program 'Missing' was not found."
    }
  }
}
```

| `code` | Meaning |
| --- | --- |
| `invalid_arguments` | A tool argument was missing, had the wrong type, or was outside the schema. |
| `unknown_tool` | The requested tool name is absent from this server. |
| `not_found` | The named program or routine is absent from the saved project. |
| `project_unavailable` | The source or a working file could not be read or copied. |
| `project_changed` | The source changed during copying or differs from an expected saved fingerprint. Inspect the latest saved version. |
| `invalid_project` | The XML is invalid, rejected by the parser, or missing the required full project structure. |
| `unsupported_platform` | The operation requires the Rockwell SDK on Windows. |
| `sdk_timeout` | The SDK worker exceeded its export time limit. |
| `sdk_error` | The SDK worker reported a failure. The message contains its diagnostic. |
| `destination_exists` | The export destination is already occupied. |
| `export_failed` | An output file could not be created, validated, or published. |
| `selection_required` | Share a saved project using the local helper. |
| `invalid_selection` | The configured selection file could not be read as a valid selection. |
| `selection_changed` | The project selection differs from the expected search or proposal selection. |
| `ambiguous_target` | A proposal target matches multiple components or addresses the same description more than once. |
| `invalid_proposal` | The proposal cannot be previewed or the reviewed content and identity do not match. |
| `artifact_changed` | A documentation artifact has changed during verification, differs from its retained digest, or is not the exact reviewed output. |
| `artifact_unavailable` | The documentation artifact or temporary verification copy could not be read. |

Use `code` for programmatic handling and display `message` to the user. MCP handles malformed protocol messages and cancellation replies separately.
