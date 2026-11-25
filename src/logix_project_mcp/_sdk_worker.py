"""Convert a temporary project copy in a process dedicated to the Rockwell SDK."""

import asyncio
import json
import sys
from enum import IntEnum
from pathlib import Path


class WorkerFailure(IntEnum):
    SDK_IMPORT = 20
    RUNTIME_LOAD = 21
    EXPORT = 22


async def build_project(source: Path, result: Path) -> None:
    try:
        from logix_designer_sdk import LogFileEventLogger, LogixProject
        from logix_designer_sdk.exceptions import LogixSdkError
    except ImportError:
        sys.exit(WorkerFailure.SDK_IMPORT)
    except RuntimeError:
        sys.exit(WorkerFailure.RUNTIME_LOAD)

    stage = "open"
    error = None
    with LogFileEventLogger(str(result.with_suffix(".log"))) as logger:
        try:
            with await LogixProject.open_logix_project(str(source), logger) as project:
                stage = "build"
                await project.build()
        except LogixSdkError as exc:
            error = f"{stage}: {exc}"[:2000]
    result.write_text(json.dumps({"error": error}), encoding="utf-8")


async def process_project(source: Path, destination: Path, component_xpath: str | None = None,
                          *, import_routine: bool = False) -> None:
    try:
        from logix_designer_sdk import LogixProject
        if import_routine:
            from logix_designer_sdk import ImportCollisionOptions
    except ImportError:
        sys.exit(WorkerFailure.SDK_IMPORT)
    except RuntimeError:
        sys.exit(WorkerFailure.RUNTIME_LOAD)

    with (await LogixProject.open_logix_project(str(source))) as project:
        if import_routine:
            await project.partial_import_from_xml_file(
                component_xpath, str(destination), ImportCollisionOptions.OVERWRITE_ON_COLL, continue_on_errors=False,
            )
            await project.save()
        elif component_xpath is None:
            await project.save_as(str(destination), detailed_l5x=True)
        else:
            await project.partial_export_to_xml_file(component_xpath, str(destination))


def main() -> None:
    try:
        args = sys.argv[1:]
        if args[0] == "--build":
            asyncio.run(build_project(Path(args[1]), Path(args[2])))
            return
        import_routine = args[0] == "--import-routine"
        source, destination, *selector = args[1:] if import_routine else args
        asyncio.run(process_project(Path(source), Path(destination), *selector, import_routine=import_routine))
    except Exception:
        sys.exit(WorkerFailure.EXPORT)


if __name__ == "__main__":
    main()
