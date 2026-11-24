# MCP tool contract

Call `tools/list` to discover the JSON Schema for each tool's arguments and successful `structuredContent`. Call `get_capabilities` to learn the contract version, the selected file, and the format requirements. [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)

## Arguments and success results

| Tool | Arguments | `structuredContent` |
| --- | --- | --- |
| `get_capabilities` | Empty object or omitted | Contract version, file selection, format requirements, and host information |
| `get_project` | Empty object or omitted | `file`, `format`, `controller`, `processor_type`, `software_revision`, `programs`, `source_sha256` |
| `list_tags` | Optional `program` string. Omit it or use `null` for controller scope. | `result` array of tag objects with `name`, `data_type`, and `description`, plus `source_sha256` |
| `read_routine` | Required `program` and `routine` strings | `result` string containing routine L5X XML, plus `source_sha256` |

Names match without regard to case. The server rejects arguments outside the tool's schema. The server selects the project through `--project` at launch. Restart it to select another file.

`file` is the selected file's basename. `format` is one of `acd`, `l5k`, or `l5x`. `software_revision` comes from the L5X `SoftwareRevision` attribute and may be `null`. `source_sha256` is the lowercase SHA-256 digest of the saved file snapshot. Compare hashes to determine whether reads used the same saved bytes.

The original three tool names and their result fields remain available. `get_project` adds `format`. Text content still contains the project summary as JSON, one JSON object per listed tag, or the routine as raw XML.

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
