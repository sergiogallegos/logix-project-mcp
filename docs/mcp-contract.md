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
| `compare_projects` | Optional `scope` when a candidate was [selected at launch](#project-comparison) | `before`, `after`, scoped `changes`, and `protected_components` |
| `export_project` | Required `filename` and optional `component` when an [export directory](#offline-export) was selected at launch | `path`, `format`, `component`, and `source_sha256` |

Inspection matches names without regard to case. The server rejects arguments outside the tool's schema. The server selects the project through `--project` at launch. Restart it to select another file.

`file` is the selected file's basename. `format` is one of `acd`, `l5k`, or `l5x`. `software_revision` comes from the L5X `SoftwareRevision` attribute and may be `null`. `source_sha256` is the lowercase SHA-256 digest of the saved file snapshot. Compare hashes to determine whether reads used the same saved bytes.

The original three tool names and their result fields remain available. `get_project` adds `format`. Text content contains the project summary as JSON, one JSON object per listed tag, or the routine XML when available.

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

Both tools return `file`, `format`, `software_revision`, and `source_sha256` for the saved snapshot. `limit` defaults to 50 and accepts 1–200. `offset` defaults to 0 and accepts up to 2,147,483,647. Keep the query and scope fixed between pages. Send `next_offset` as `offset` and the first page's `source_sha256` as `expected_source_sha256`. A newer save then returns `project_changed`, and a `null` `next_offset` marks the last page.

## Project comparison

Set `--project` to the baseline and add `--compare-project` with the candidate path in the server's launch arguments. Each can be an `.ACD`, `.L5K`, or full `.L5X`. With two paths configured, `tools/list` includes `compare_projects` and `get_capabilities` reports the `comparison_project` selection. Inspection tools continue to use the baseline.

Call `compare_projects` with `{}` for all supported scopes. Use `{"scope":{"kind":"controller"}}` for controller scope or `{"scope":{"kind":"program","program":"Main"}}` for one program. A program present on either side can be reviewed by name. The response labels the snapshots as `before` and `after`, each with file name, format, controller, software revision, and source SHA-256. The roles and hashes distinguish same-named projects.

Components match by kind and case-insensitive qualified name. The controller is matched by its role. Changes cover controller settings, tasks, modules, user-defined types, Add-On Instructions, programs, scoped tags, and routines. Each change includes its identity, an `added`, `removed`, or `modified` status, and a unified `xml_diff`. Ladder and Structured Text changes can also include a `source_diff` with rung or line positions and surrounding text.

Comparison normalizes XML indentation and attribute order and ignores export headers, common author and timestamp attributes, and `Use` context markers. Decorated tag values take precedence when an export also includes a redundant raw or L5K value. Saved settings such as the controller serial number, tag values, and schedule or rung order are compared. Protected components are listed in `protected_components` and compared using available metadata. [Rockwell Logix 5000 Import/Export reference](https://literature.rockwellautomation.com/idc/groups/literature/documents/rm/1756-rm014_-en-p.pdf)

## Offline export

Add `--export-dir` and an existing directory to the launch arguments to enable `export_project`. The export always uses the saved file selected by `--project`. Supply a filename without directory segments. The server publishes the finished artifact only when there is no existing entry at the destination. It returns the absolute artifact `path`, lowercase `format`, requested `component` or `null`, and the source snapshot's SHA-256.

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
| `project_changed` | The source changed during copying. Retry after the save completes. |
| `invalid_project` | The XML is invalid, rejected by the parser, or missing the required full project structure. |
| `unsupported_platform` | The operation requires the Rockwell SDK on Windows. |
| `sdk_timeout` | The SDK worker exceeded its export time limit. |
| `sdk_error` | The SDK worker reported a failure. The message contains its diagnostic. |
| `destination_exists` | The export destination is already occupied. |
| `export_failed` | An output file could not be created, validated, or published. |

Use `code` for programmatic handling and display `message` to the user. MCP handles malformed protocol messages and cancellation replies separately.
