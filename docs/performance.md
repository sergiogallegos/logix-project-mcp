# Saved-project inspection performance

On this Windows host, comparing two full synthetic L5X exports with 8,192 tags and one changed description took 0.75–0.99 seconds. Opening a saved ACD with an empty MCP cache took about 30 seconds. Repeating that read in the same session took 0.13–0.16 seconds.

## Host and measurement

Windows 11 x64 build 26200, Intel Core i7-10750H at 2.60 GHz, 12 logical processors, 63.8 GiB usable RAM, Python 3.12.10 and MCP Python SDK 1.30.0. The L5X benchmark used the installed wheel in an SDK-free environment. Native reads used Rockwell SDK 2.0.2.

Each client launched an installed stdio server. Startup covers process launch through MCP initialization. Request timings cover the client call through receipt of the structured response, including snapshot hashing. A cold native read means the session has no cached export for those bytes. The operating system and vendor service may already have been warm.

Memory is the Windows high-water mark for one Python MCP server measured after the calls. Each server has its own cache. Client processes, the transient SDK worker and the shared Rockwell service are outside these figures.

## L5X search and comparison

The small export had one program, 16 tags, four routines and 32 Structured Text comment lines (3,920 bytes). The larger export had 32 programs, 8,192 tags, 128 routines and 16,384 comment lines (1,852,091 bytes). A full comment search had one match on the last program's last tag. Each comparison had one changed tag description. The benchmark checked the scoped results and both saved fingerprints.

| Operation | Small export | Larger export |
| --- | ---: | ---: |
| Fresh server startup | 1.31 s | 1.27 s |
| Project summary, three calls | 0.033–0.049 s | 0.121–0.139 s |
| Comment search, three calls | 0.052–0.058 s | 0.192–0.226 s |
| Comparison, three calls | 0.038–0.040 s | 0.750–0.987 s |
| Two simultaneous searches, wall time | 0.086 s | 0.267 s |
| Peak server working set, first / second client | 58.1 / 57.9 MiB | 90.1 / 72.8 MiB |

The second client started a separate server and performed only the concurrent search. Both clients checked the same saved hash and match location. The large comparison was the slowest L5X request measured. It reads two complete snapshots and normalizes the components on both sides to find the changed description.

## Native opens and saved changes

The benchmark copied the first sample to a temporary path, opened it three times, then atomically replaced that path with the second sample while the client stayed connected. Every response had to match the saved fingerprint. The summary had to change as well. A separate server then opened the second sample cold and had to return the same summary. The original samples retained their fingerprints.

| Saved version | Bytes | First open of these bytes | Next two opens | Peak server working set to this point |
| --- | ---: | ---: | ---: | ---: |
| ACD, synthetic revision 38.02, empty project | 3,855,391 | 30.05 s | 0.130 / 0.139 s | 70.4 MiB |
| ACD, Rockwell View Designer sample revision 35.00, two programs | 4,416,276 | 30.84 s | 0.129 / 0.153 s | 73.0 MiB |
| L5K, synthetic revision 38.02, 16 tags | 3,237 | 34.05 s | 0.104 / 0.141 s | 69.7 MiB |
| L5K, synthetic revision 38.02, 8,192 tags | 370,091 | 52.76 s | 0.274 / 0.253 s | 90.3 MiB |

The ACD session started in 1.24 seconds and the L5K session in 1.32 seconds. The largest cost was the native open and export on a cache miss. Even on a cache hit the server still reads and hashes the selected source and parses the cached XML. The small packed ACD and the much smaller text L5K took comparable time to open cold, so input byte count alone is a poor basis for a timeout.

## Regression targets

Use these investigation thresholds when repeating the same workloads on a comparable Windows host. They leave headroom above the observed times and apply to local files. The timings describe the observed range across three sequential requests per tool.

| Measurement | Target |
| --- | ---: |
| Fresh MCP server startup | ≤ 2 s |
| Large L5X summary or full comment search | ≤ 0.4 s per call |
| Large L5X comparison with one changed description | ≤ 1.5 s |
| Two simultaneous large L5X searches | ≤ 0.5 s wall time |
| First native open after launch or a new save | ≤ 75 s |
| Cached native project summary | ≤ 0.5 s |
| Peak resident memory per MCP server across these workloads | ≤ 128 MiB |

The 128 MiB working-set target is specific to the measured samples. The separate 128 MiB native cache limit counts retained XML bytes only. Larger outputs, extensive diffs and multiple clients can require more host memory. The concurrent-client measurement covers SDK-free searches. Simultaneous cold exports against one Rockwell service and the service's memory use were outside this run.

## Repeat the measurements

From the checkout, run the following with a Python environment that has this package installed. The default benchmark generates its own L5X exports and prints the individual samples as JSON.

```powershell
.\.venv\Scripts\python.exe benchmarks/inspection.py
```

For native runs, use the SDK-enabled environment and the revision 38 sample set from the [compatibility walkthrough](compatibility.md#prepare-a-matching-sample-set). The ACD example uses the Rockwell View Designer revision 35 sample. Two other saved samples of the same format with visibly different project summaries can also be supplied.

```powershell
$viewSample = Join-Path $env:PUBLIC 'Documents\Studio 5000\Samples\View Designer\Sample_Application_v35_v10.ACD'
.\.venv\Scripts\python.exe benchmarks/inspection.py --native-pair .local/compatibility/Synthetic38.ACD $viewSample
.\.venv\Scripts\python.exe benchmarks/inspection.py --synthetic-l5k .local/compatibility/Synthetic38.L5K
```
