"""Convert a temporary project copy in a process dedicated to the Rockwell SDK."""

import asyncio
import sys
from pathlib import Path


async def export(source: Path, destination: Path) -> None:
    from logix_designer_sdk import LogFileEventLogger, LogixProject

    with LogFileEventLogger(str(destination.with_suffix(".log"))) as logger:
        with (await LogixProject.open_logix_project(str(source), logger)) as project:
            await project.save_as(str(destination), detailed_l5x=True)


def main() -> None:
    try:
        asyncio.run(export(Path(sys.argv[1]), Path(sys.argv[2])))
    except ImportError as exc:
        sys.exit(f"Install Rockwell's Logix Designer Python wheel in this environment. {exc}")
    except RuntimeError as exc:
        sys.exit(f"Check the .NET runtime and DOTNET_ROOT in the MCP client configuration. {exc}")
    except Exception as exc:
        sys.exit(str(exc) or type(exc).__name__)


if __name__ == "__main__":
    main()
