"""Command-line interface for envskill."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from . import __version__
from .setup import SUPPORTED_AGENTS, TARGET_DIRS, install_skill, run_setup
from .store import (
    StoreError,
    default_path,
    import_values,
    initialize,
    insecure_mode,
    load,
    set_value,
    unset_value,
    validate_name,
    validate_store,
)

SAFE_PARENT_NAMES = {
    "COLORTERM",
    "COMSPEC",
    "FORCE_COLOR",
    "HOME",
    "LANG",
    "LC_ADDRESS",
    "LC_ALL",
    "LC_COLLATE",
    "LC_CTYPE",
    "LC_IDENTIFICATION",
    "LC_MEASUREMENT",
    "LC_MESSAGES",
    "LC_MONETARY",
    "LC_NAME",
    "LC_NUMERIC",
    "LC_PAPER",
    "LC_TELEPHONE",
    "LC_TIME",
    "LOGNAME",
    "NO_COLOR",
    "PATH",
    "PATHEXT",
    "SHELL",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "TZ",
    "USER",
    "WINDIR",
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="envskill",
        description=(
            "Pass selected environment variables to AI-agent commands without printing them."
        ),
    )
    root.add_argument("--file", type=Path, help="Override the secret store for this command")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the owner-only secret store")
    sub.add_parser("path", help="Print the active secret-store path")

    list_parser = sub.add_parser("list", help="List variable names, never values")
    list_parser.add_argument("--json", action="store_true")

    has_parser = sub.add_parser("has", help="Check whether a variable exists")
    has_parser.add_argument("name")

    set_parser = sub.add_parser("set", help="Securely add or rotate a variable")
    set_parser.add_argument("name")
    set_parser.add_argument(
        "--stdin", action="store_true", help="Read the value from stdin instead of a hidden prompt"
    )

    unset_parser = sub.add_parser("unset", help="Remove a variable")
    unset_parser.add_argument("name")

    import_parser = sub.add_parser(
        "import-env", help="Import values from a single-line dotenv file"
    )
    import_parser.add_argument("--from", dest="source", type=Path, required=True)
    import_parser.add_argument(
        "--overwrite", action="store_true", help="Replace names already present in the store"
    )

    run_parser = sub.add_parser("run", help="Run a command with selected variables injected")
    scope = run_parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--only", help="Comma-separated variable names to inject")
    scope.add_argument("--all", action="store_true", help="Inject all variables (broad scope)")
    run_parser.add_argument(
        "--inherit", help="Comma-separated non-secret parent variable names to preserve"
    )
    run_parser.add_argument("argv", nargs=argparse.REMAINDER)

    install_parser = sub.add_parser("install-skill", help="Install the bundled Agent Skill")
    destination = install_parser.add_mutually_exclusive_group()
    destination.add_argument(
        "--target", choices=sorted(TARGET_DIRS), default="universal", help="Agent preset"
    )
    destination.add_argument("--dir", type=Path, help="Custom parent skills directory")
    install_parser.add_argument(
        "--force", action="store_true", help="Replace an existing SKILL.md"
    )

    setup_parser = sub.add_parser(
        "setup", help="Initialize the store and configure Agent Skills hosts"
    )
    setup_parser.add_argument(
        "--agent",
        choices=["auto", "all", *SUPPORTED_AGENTS],
        default="auto",
        help="Host to configure (default: detect installed hosts)",
    )
    setup_parser.add_argument(
        "--import",
        dest="import_source",
        type=Path,
        metavar="PATH",
        help="Import names and values from an explicitly selected dotenv file",
    )
    setup_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace names already present in the store during --import",
    )
    setup_parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing, different Agent Skill copy",
    )

    sub.add_parser("doctor", help="Check store permissions and skill availability")
    return root


def active_path(argument: Optional[Path]) -> Path:
    return argument.expanduser() if argument else default_path()


def selected_values(
    values: Dict[str, str], only: Optional[str], all_values: bool
) -> Dict[str, str]:
    if all_values:
        return values
    names = [item.strip() for item in (only or "").split(",") if item.strip()]
    if not names:
        raise StoreError("--only requires at least one variable name")
    for name in names:
        validate_name(name)
    missing = [name for name in names if name not in values]
    if missing:
        raise StoreError("Missing variables: " + ", ".join(missing))
    return {name: values[name] for name in names}


def child_environment(parent: Dict[str, str], inherit: Optional[str]) -> Dict[str, str]:
    """Build a minimal functional environment plus explicitly inherited names."""
    names = set(SAFE_PARENT_NAMES)
    for raw_name in (inherit or "").split(","):
        if raw_name.strip():
            names.add(validate_name(raw_name.strip()))
    return {name: parent[name] for name in names if name in parent}


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    path = active_path(args.file)
    try:
        if args.command == "path":
            print(path)
            return 0

        if args.command == "init":
            created = initialize(path)
            print(f"Store {'created' if created else 'already exists'}: {path}")
            return 0

        if args.command == "install-skill":
            parent = args.dir if args.dir else TARGET_DIRS[args.target]
            installed = install_skill(parent, args.force)
            print(f"Skill installed: {installed}")
            return 0

        if args.command == "setup":
            for message in run_setup(
                path,
                agent=args.agent,
                import_source=args.import_source,
                overwrite=args.overwrite,
                force=args.force,
                target_dirs=TARGET_DIRS,
            ):
                print(message)
            return 0

        if args.command == "doctor":
            problems: List[str] = []
            if not path.exists():
                problems.append(f"store missing: {path} (run: envskill init)")
            try:
                bad_mode = insecure_mode(path)
                if bad_mode is not None:
                    problems.append(f"store permissions are {bad_mode:04o}, expected 0600")
                validate_store(path)
            except StoreError as exc:
                problems.append(str(exc))
            if shutil.which("envskill") is None:
                problems.append("envskill is not on PATH")
            if problems:
                for problem in problems:
                    print(f"FAIL: {problem}")
                return 1
            print(f"OK: store={path}; permissions=private; cli=available")
            return 0

        validate_store(path)
        values = load(path)

        if args.command == "list":
            names = sorted(values)
            print(json.dumps(names) if args.json else "\n".join(names))
            return 0

        if args.command == "has":
            name = validate_name(args.name)
            present = name in values
            print(f"{name}: {'present' if present else 'missing'}")
            return 0 if present else 1

        if args.command == "set":
            name = validate_name(args.name)
            if args.stdin:
                value = sys.stdin.read()
                if value.endswith("\n"):
                    value = value[:-1]
            elif sys.stdin.isatty():
                value = getpass.getpass(f"Value for {name}: ")
            else:
                raise StoreError("No TTY available; pipe the value and pass --stdin")
            set_value(path, name, value)
            print(f"{name}: saved (value hidden)")
            return 0

        if args.command == "unset":
            name = validate_name(args.name)
            removed = unset_value(path, name)
            print(f"{name}: {'removed' if removed else 'not present'}")
            return 0

        if args.command == "import-env":
            source = args.source.expanduser()
            if not source.is_file():
                raise StoreError(f"Import source does not exist or is not a file: {source}")
            if source.resolve() == path.resolve():
                raise StoreError("Source and destination are the same file")
            imported = load(
                source,
                require_private=False,
                require_owner=True,
                trusted_parent=False,
            )
            imported_count, skipped = import_values(path, imported, args.overwrite)
            print(f"Imported {imported_count} variable(s); skipped {skipped}; values hidden")
            return 0

        if args.command == "run":
            command = list(args.argv)
            if command and command[0] == "--":
                command = command[1:]
            if not command:
                raise StoreError("No command supplied after --")
            injected = selected_values(values, args.only, args.all)
            environment = child_environment(os.environ, args.inherit)
            environment.update(injected)
            try:
                os.execvpe(command[0], command, environment)
            except OSError as exc:
                raise StoreError(f"Cannot run {command[0]!r}: {exc.strerror}") from exc

        return 2
    except StoreError as exc:
        print(f"envskill: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
