"""Share an explicitly selected saved project with a running MCP server."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .project import ProjectReadError, read_project
from .selection import publish_selection, read_selection, validate_project_path


async def share_project(file: Path, path: Path) -> dict:
    source = validate_project_path(path)
    snapshot = await read_project(source)
    selection = publish_selection(file, source)
    return {**selection.identity(snapshot)["selection"], "source_sha256": snapshot.source_sha256}


def main() -> None:
    parser = argparse.ArgumentParser(description="Share a saved Logix project with the local MCP server.")
    parser.add_argument("--selection-file", required=True, type=Path)
    parser.add_argument("--dialog", action="store_true", help="Use Windows dialogs for selection and feedback")
    parser.add_argument("--refresh", action="store_true", help="Share the previously selected path again")
    parser.add_argument("project", nargs="?", type=Path, help="Saved project path, including the Custom Tools argument")
    args = parser.parse_args()
    if args.refresh and args.project is not None:
        parser.error("--refresh uses the previously selected project path")
    if args.project is None and not (args.refresh or args.dialog):
        parser.error("Supply a project path, --refresh, or --dialog")

    root = None
    if args.dialog:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.withdraw()
    try:
        file = args.selection_file.resolve()
        path = args.project
        if args.refresh:
            path = read_selection(file).path
        elif path is None:
            chosen = filedialog.askopenfilename(parent=root, title="Choose saved Studio 5000 project", filetypes=[
                ("Logix projects", "*.ACD *.L5K *.L5X"),
            ])
            if not chosen:
                return
            path = Path(chosen)
        result = asyncio.run(share_project(file, path))
        if root is not None:
            messagebox.showinfo("Project shared", f"{result['path']}\n\nController: {result['controller']}\nLogix Designer: {result['software_revision']}\n\nThe MCP can now inspect the latest saved project.", parent=root)
        else:
            print(json.dumps(result, ensure_ascii=False))
    except (ProjectReadError, OSError, RuntimeError, ValueError) as exc:
        if root is not None:
            messagebox.showerror("Could not share project", str(exc), parent=root)
        else:
            print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        if root is not None:
            root.destroy()


if __name__ == "__main__":
    main()
