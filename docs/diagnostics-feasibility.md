# Read-only diagnostics feasibility (LPM-050)

**Recommendation:** keep the 1.0 MCP implementation focused on saved projects. The Rockwell SDK has documented observation capabilities beyond our current offline reader, so there is not yet a demonstrated functional gap that requires adding another driver. The maintainer's `rust-ethernet-ip` is a plausible alternative source for separately acquired tag observations if reducing SDK dependency becomes a product requirement, but it has not been integrated or verified in this application.

## Evidence and boundaries

The current server's inventory, routine inspection, search, and comparison describe the saved file, not a running controller. The source SHA-256 binds results to saved bytes, including when an export is reused from the session cache. A saved setting or tag declaration says nothing about the present value, controller mode, connection health, or whether the deployed program matches the file.

Rockwell's [Logix Designer SDK Getting Results Guide, LDSDK-GR001C-EN-P (January 2025)](https://literature.rockwellautomation.com/idc/groups/literature/documents/gr/ldsdk-gr001_-en-p.pdf) describes project access and controller-related testing capabilities. The installed Python wheel 2.0.2 was inspected statically; its documented public surface includes controller mode, connected state, and typed tag value reads with explicit online/offline semantics. These methods were **not called** during this evaluation. The guide describes a Windows Logix Designer/FactoryTalk Linx environment; see our [tested offline format matrix](compatibility.md) for the established local prerequisites instead of treating the installed SDK as proof of online compatibility.

The maintainer's [rust-ethernet-ip repository](https://github.com/sergiogallegos/rust-ethernet-ip) documents direct Logix tag access and Python bindings. Its [PyPI distribution](https://pypi.org/project/rust-ethernet-ip/1.2.1/) provides a separately distributed Python package (release 1.2.1 was reviewed). That independent distribution may matter to users without the Rockwell SDK. The library is a general-purpose communication library, not a read-only diagnostic product; its upstream compatibility claims do not establish compatibility with our MCP server.

| Information | Saved-project MCP today | Rockwell SDK documented capability | rust-ethernet-ip documented capability |
| --- | --- | --- | --- |
| Project declarations, descriptions, routines | Implemented; source hash identifies snapshot | File-based engineering APIs | Not a saved-project reader |
| Tag values | Inventory describes declarations; it does not report observations | Typed value retrieval, with offline and online modes distinguished | Tag observations are within the upstream library's stated scope |
| Connected state and controller mode | Not observed | Documented state/mode read APIs | No equivalent capability established by this review |
| Fault history, task timing, module health | Saved configuration only; no current measurements | Not established by this review | Not established by this review |
| Unverified or stale information | Saved snapshots have consistency checks | Runtime behavior not tested here | Runtime behavior not tested here |

Neither provider is a dependency for `.L5X` inspection. We found no evidence that introducing a second provider would improve the existing saved-project workflow. A separate requirement for vendor-independent observations would warrant a new design evaluation. No changes to the MCP tool list or dependencies are proposed by LPM-050.

## Offline UX evaluation

Run the deterministic [simulation](../examples/diagnostics_simulation.py) from the checkout using its installed Python environment:

```sh
python -m examples.diagnostics_simulation
python -m unittest discover -s tests -p test_diagnostics_simulation.py -v
```

It uses the existing full L5X parser and inventory on an embedded synthetic project, then displays invented observation records side by side. No network acquisition, device access, or vendor runtime is used. The display clock and 30-second freshness threshold are deliberately fixed for demonstration, not production requirements.

| Saved identity | Fabricated observation | Display |
| --- | --- | --- |
| Controller / DemoCounter | 42, five seconds old | Simulated fresh |
| Example / DemoCounter | 17, five minutes old | Stale; explicitly labelled |
| Controller / Unavailable | Synthetic error | Unavailable; no fallback value |
| Controller / NoObservation | No record | Not observed |
| Controller / DifferentSnapshot | Record associated with a different saved fingerprint | Snapshot mismatch; hide value |

The result separates the saved metadata from the observation record and labels every observation as synthetic. The two same-named tags are not merged; program scope is part of the identity. A fresh sample timestamp does not prove controller deployment matches the project. An association with a saved SHA-256 is only record provenance, not independent verification of the running program. Missing observations cannot be replaced with a default or a saved value and presented as current facts.

## Further work

If a future product requirement calls for observations, first establish exactly what information an engineer needs that the saved project cannot provide. Define provenance, timestamps, uncertainty, and explicit handling of stale or unavailable readings. Confirm permission and the applicable environment with the maintainer. A separate approved evaluation should establish compatibility, access boundaries, and transport behavior before considering any connection-capable integration. Until then, the prototype stays entirely offline, and no claim is made about live performance, diagnostic coverage, or compatibility with particular controller models.
