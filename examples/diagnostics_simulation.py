"""Offline diagnostics UX demonstration using only fixed, synthetic data."""

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from logix_project_mcp.inventory import project_inventory
from logix_project_mcp.project import controller_from_l5x, parse_l5x_bytes


SAVED_PROJECT = b"""<RSLogix5000Content TargetType="Controller" SoftwareRevision="38.02">
  <Controller Name="SyntheticDemo">
    <Tags>
      <Tag Name="DemoCounter" DataType="DINT" ExternalAccess="Read Only"/>
      <Tag Name="Unavailable" DataType="DINT"/>
      <Tag Name="NoObservation" DataType="DINT"/>
      <Tag Name="DifferentSnapshot" DataType="DINT"/>
    </Tags>
    <Programs><Program Name="Example">
      <Tags><Tag Name="DemoCounter" DataType="DINT" ExternalAccess="Read Only"/></Tags>
    </Program></Programs>
  </Controller>
</RSLogix5000Content>"""


def simulate() -> dict:
    """Return a fixed illustration; never acquire data or connect to a controller."""
    root = parse_l5x_bytes(SAVED_PROJECT)
    controller = controller_from_l5x(root)
    inventory = project_inventory(controller)
    fingerprint = sha256(SAVED_PROJECT).hexdigest()
    display_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    freshness = timedelta(seconds=30)
    observations = {
        (None, "DemoCounter"): {
            "value": 42, "observed_at": display_time - timedelta(seconds=5),
            "related_saved_sha256": fingerprint,
        },
        ("Example", "DemoCounter"): {
            "value": 17, "observed_at": display_time - timedelta(minutes=5),
            "related_saved_sha256": fingerprint,
        },
        (None, "Unavailable"): {
            "error": "Synthetic read unavailable", "observed_at": display_time,
            "related_saved_sha256": fingerprint,
        },
        (None, "DifferentSnapshot"): {
            "value": 99, "observed_at": display_time,
            "related_saved_sha256": "0" * 64,
        },
    }
    tags = [(None, tag) for tag in inventory["controller_tags"]]
    tags.extend(
        (program["name"], tag)
        for program in inventory["programs"]
        for tag in program["tags"]
    )
    rows = []
    for program, tag in tags:
        observation = observations.get((program, tag["name"]))
        saved = {
            "provenance": "saved_project",
            "program": program,
            "name": tag["name"],
            "data_type": tag["data_type"],
            "external_access": tag["external_access"],
        }
        shown = {
            "provenance": "synthetic_fixture",
            "status": "not_observed",
            "value": None,
            "observed_at": None,
        }
        if observation is not None:
            shown["observed_at"] = observation["observed_at"].isoformat()
            shown["related_saved_sha256"] = observation["related_saved_sha256"]
            if observation["related_saved_sha256"] != fingerprint:
                shown["status"] = "snapshot_mismatch"
            elif "error" in observation:
                shown["status"] = "unavailable"
                shown["message"] = observation["error"]
            elif display_time - observation["observed_at"] > freshness:
                shown["status"] = "stale"
                shown["value"] = observation["value"]
            else:
                shown["status"] = "simulated_fresh"
                shown["value"] = observation["value"]
        rows.append({"saved": saved, "observation": shown})
    return {
        "mode": "offline_simulation",
        "notice": "All observations are fabricated; no controller was contacted.",
        "display_time": display_time.isoformat(),
        "illustrative_freshness_seconds": int(freshness.total_seconds()),
        "saved_source": {
            "controller": controller.get("Name"),
            "software_revision": root.get("SoftwareRevision"),
            "source_sha256": fingerprint,
        },
        "rows": rows,
    }


if __name__ == "__main__":
    print(json.dumps(simulate(), indent=2))
