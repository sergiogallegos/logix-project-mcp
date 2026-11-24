# MCP tool contract

Call `tools/list` to discover the JSON Schema for each tool's arguments and successful `structuredContent`. Call `get_capabilities` to learn the contract version, the selected file, and the format requirements. [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## Arguments and success results

| Tool | Arguments | `structuredContent` |
| --- | --- | --- |
| `get_capabilities` | Empty object or omitted | Contract version, file selection, format requirements, and host information |
| `get_project` | Empty object or omitted | `file`, `format`, `controller`, `processor_type`, `software_revision`, `programs`, `source_sha256` |
| `get_inventory` | Empty object or omitted | File identity, source revision, and the [project inventory](#project-inventory) |
| `list_tags` | Optional `program` string. Omit it or use `null` for controller scope. | `result` array of tag objects with `name`, `data_type`, and `description`, plus `source_sha256` |
| `read_routine` | Required `program` and `routine` strings | `result` string containing routine L5X XML, plus `source_sha256` |

Names match without regard to case. The server rejects arguments outside the tool's schema. The server selects the project through `--project` at launch. Restart it to select another file.

`file` is the selected file's basename. `format` is one of `acd`, `l5k`, or `l5x`. `software_revision` comes from the L5X `SoftwareRevision` attribute and may be `null`. `source_sha256` is the lowercase SHA-256 digest of the saved file snapshot. Compare hashes to determine whether reads used the same saved bytes.

The original three tool names and their result fields remain available. `get_project` adds `format`. Text content still contains the project summary as JSON, one JSON object per listed tag, or the routine as raw XML.

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

## Capability reporting

`get_capabilities` returns `schema_version` as `1` and `read_only` as `true`. Its `project` object contains `file` and `format`. Each `formats` entry contains `format`, `requires_windows`, and `requires_rockwell_sdk`. `platform` is the Python platform identifier such as `win32` or `linux`.

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
| `unsupported_platform` | A native project read requires Windows. |
| `sdk_timeout` | The SDK worker exceeded its export time limit. |
| `sdk_error` | The SDK worker reported a failure. The message contains its diagnostic. |

Use `code` for programmatic handling and display `message` to the user. MCP handles malformed protocol messages and cancellation replies separately.
