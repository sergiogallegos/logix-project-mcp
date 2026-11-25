"""Convert a temporary project copy in a process dedicated to the Rockwell SDK."""

import asyncio
import sys
from enum import IntEnum
from pathlib import Path


class WorkerFailure(IntEnum):
    SDK_IMPORT = 20
    RUNTIME_LOAD = 21
    EXPORT = 22


async def export(source: Path, destination: Path, component_xpath: str | None = None) -> None:
    try:
        from logix_designer_sdk import LogixProject
    except ImportError:
        sys.exit(WorkerFailure.SDK_IMPORT)
    except RuntimeError:
        sys.exit(WorkerFailure.RUNTIME_LOAD)

    with (await LogixProject.open_logix_project(str(source))) as project:
        if component_xpath is None:
            await project.save_as(str(destination), detailed_l5x=True)
        else:
            await project.partial_export_to_xml_file(component_xpath, str(destination))


def main() -> None:
    try:
        source, destination, *selector = sys.argv[1:]
        asyncio.run(export(Path(source), Path(destination), *selector))
    except Exception:
        sys.exit(WorkerFailure.EXPORT)


if __name__ == "__main__":
    main()
