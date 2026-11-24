"""Convert a temporary project copy in a process dedicated to the Rockwell SDK."""

import asyncio
import sys
from pathlib import Path


async def export(source: Path, destination: Path, component_xpath: str | None = None) -> None:
    from logix_designer_sdk import LogFileEventLogger, LogixProject

    with LogFileEventLogger(str(destination.with_suffix(".log"))) as logger:
        with (await LogixProject.open_logix_project(str(source), logger)) as project:
            if component_xpath is None:
                await project.save_as(str(destination), detailed_l5x=True)
            else:
                await project.partial_export_to_xml_file(component_xpath, str(destination))


def main() -> None:
    try:
        source, destination, *selector = sys.argv[1:]
        asyncio.run(export(Path(source), Path(destination), *selector))
    except ImportError as exc:
        sys.exit(f"Install Rockwell's Logix Designer Python wheel in this environment. {exc}")
    except RuntimeError as exc:
        sys.exit(f"Check the .NET runtime and DOTNET_ROOT in the MCP client configuration. {exc}")
    except Exception as exc:
        sys.exit(str(exc) or type(exc).__name__)


if __name__ == "__main__":
    main()
