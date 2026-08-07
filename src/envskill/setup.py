"""Guided, value-free first-run setup for envskill."""

from __future__ import annotations

import importlib.resources
import os
import shutil
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Callable, List, Mapping, Optional, Tuple

from .store import (
    StoreError,
    import_values,
    initialize,
    insecure_mode,
    load,
    validate_store,
)

SUPPORTED_AGENTS = ("codex", "claude", "hermes")
_AGENT_EXECUTABLES = {
    "codex": "codex",
    "claude": "claude",
    "hermes": "hermes",
}


def hermes_home(home: Optional[Path] = None) -> Path:
    """Resolve Hermes' home consistently for detection and installation targets."""
    base = home.expanduser() if home else Path.home()
    configured = os.environ.get("HERMES_HOME")
    return Path(configured).expanduser() if configured else base / ".hermes"


# Keep the target paths in one place so install-skill and setup cannot drift.
TARGET_DIRS = {
    # The open Agent Skills user directory used by Codex and other compatible hosts.
    "universal": Path.home() / ".agents" / "skills",
    "codex": Path.home() / ".agents" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "hermes": hermes_home() / "skills",
}


def bundled_skill() -> importlib.resources.abc.Traversable:
    return importlib.resources.files("envskill").joinpath("bundled_skill", "SKILL.md")


def detect_agents(
    home: Optional[Path] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> List[str]:
    """Detect supported hosts from executable names and config directories only."""
    home = home.expanduser() if home else Path.home()
    hermes_home_path = hermes_home(home)
    markers = {
        "codex": (home / ".codex",),
        "claude": (home / ".claude",),
        "hermes": (hermes_home_path,),
    }
    detected: List[str] = []
    for agent in SUPPORTED_AGENTS:
        executable = _AGENT_EXECUTABLES[agent]
        if which(executable) or any(marker.is_dir() for marker in markers[agent]):
            detected.append(agent)
    return detected


def resolve_agents(selection: str, detected: List[str]) -> List[str]:
    """Resolve an explicit agent selection or the hosts found by auto-detection."""
    if selection == "auto":
        return list(detected)
    if selection == "all":
        return list(SUPPORTED_AGENTS)
    if selection in SUPPORTED_AGENTS:
        return [selection]
    raise StoreError(f"Unknown agent selection: {selection}")


def _validate_directory(path: Path, label: str, info: os.stat_result) -> None:
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise StoreError(f"{label.capitalize()} must be a real directory: {path}")
    if os.name == "posix":
        if info.st_uid != os.geteuid():
            raise StoreError(f"{label.capitalize()} is not owned by the current user: {path}")
        if stat.S_IMODE(info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            raise StoreError(f"{label.capitalize()} is writable by another user: {path}")
        if not os.access(path, os.W_OK | os.X_OK):
            raise StoreError(f"{label.capitalize()} is not writable by the current user: {path}")


def _verify_directory(path: Path, label: str, *, create: bool = True) -> None:
    if create:
        try:
            path.mkdir(mode=0o755, parents=True, exist_ok=True)
            info = path.lstat()
        except OSError as exc:
            raise StoreError(f"Cannot prepare {label} {path}: {exc}") from exc
        _validate_directory(path, label, info)
        return

    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise StoreError(f"Cannot inspect {label} {path}: {exc}") from exc
    _validate_directory(path, label, info)


def _prepare_skill_location(
    parent: Path, *, create: bool = True, allow_insecure_target: bool = False
) -> Tuple[Path, Path, bool, bool]:
    """Validate a skill location before reading or replacing anything in it."""
    parent = parent.expanduser()
    _verify_directory(parent, "skills parent", create=create)
    destination = parent / "envskill"
    destination_exists = True
    try:
        destination_info = destination.lstat()
    except FileNotFoundError:
        destination_exists = False
        if create:
            try:
                destination.mkdir(mode=0o755)
                destination_info = destination.lstat()
            except OSError as exc:
                raise StoreError(f"Cannot create skill destination {destination}: {exc}") from exc
    except OSError as exc:
        raise StoreError(f"Cannot inspect skill destination {destination}: {exc}") from exc

    if destination_exists:
        if stat.S_ISLNK(destination_info.st_mode) or not stat.S_ISDIR(destination_info.st_mode):
            raise StoreError(f"Skill destination must be a real directory: {destination}")
        if os.name == "posix":
            if destination_info.st_uid != os.geteuid():
                raise StoreError(
                    f"Skill destination is not owned by the current user: {destination}"
                )
            if stat.S_IMODE(destination_info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
                raise StoreError(
                    f"Skill destination is writable by another user: {destination}"
                )

    target = destination / "SKILL.md"
    target_exists = True
    try:
        target_info = target.lstat()
    except FileNotFoundError:
        target_exists = False
    except OSError as exc:
        raise StoreError(f"Cannot inspect skill file {target}: {exc}") from exc
    if target_exists:
        if stat.S_ISLNK(target_info.st_mode) or not stat.S_ISREG(target_info.st_mode):
            raise StoreError(f"Existing SKILL.md must be a regular, non-symlink file: {target}")
        if os.name == "posix" and not allow_insecure_target:
            if target_info.st_uid != os.geteuid():
                raise StoreError(f"Existing SKILL.md is not owned by the current user: {target}")
            if stat.S_IMODE(target_info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
                raise StoreError(f"Existing SKILL.md is writable by another user: {target}")
    return destination, target, destination_exists, target_exists


def _write_skill(target: Path) -> Path:
    descriptor: Optional[int] = None
    temp_name: Optional[str] = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".SKILL.", dir=str(target.parent), text=True
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = None
            handle.write(bundled_skill().read_text(encoding="utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
        temp_name = None
        return target
    except OSError as exc:
        raise StoreError(f"Cannot install skill at {target}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temp_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temp_name)


def install_skill(parent: Path, force: bool) -> Path:
    """Install the bundled skill, preserving the existing command's strict semantics."""
    _, target, destination_exists, target_exists = _prepare_skill_location(
        parent, allow_insecure_target=force
    )
    if destination_exists and not force:
        raise StoreError(f"Skill already exists: {target.parent}; use --force to replace it")
    if target_exists and not force:
        raise StoreError(f"Skill already exists: {target.parent}; use --force to replace it")
    return _write_skill(target)


def _skill_status(target: Path, target_exists: bool, force: bool) -> str:
    if not target_exists:
        return "installed"
    try:
        current = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        if force:
            return "updated"
        raise StoreError(f"Cannot read existing skill {target}: {exc}") from exc
    bundled = bundled_skill().read_text(encoding="utf-8")
    if current == bundled:
        return "updated" if force else "already"
    if not force:
        return "conflict"
    return "updated"


def ensure_skill(parent: Path, force: bool) -> Tuple[Path, str]:
    """Install a skill idempotently, never replacing a custom copy without --force."""
    _, target, _, target_exists = _prepare_skill_location(
        parent, allow_insecure_target=force
    )
    status = _skill_status(target, target_exists, force)
    if status in {"already", "conflict"}:
        return target, status
    return _write_skill(target), status


def preflight_skill(parent: Path, force: bool) -> None:
    """Validate an installation target without creating or replacing anything."""
    _, target, _, target_exists = _prepare_skill_location(
        parent, create=False, allow_insecure_target=force
    )
    _skill_status(target, target_exists, force)


def run_setup(
    path: Path,
    *,
    agent: str = "auto",
    import_source: Optional[Path] = None,
    overwrite: bool = False,
    force: bool = False,
    target_dirs: Optional[Mapping[str, Path]] = None,
) -> List[str]:
    """Initialize the store, optionally import values, install skills, and verify the result."""
    if overwrite and import_source is None:
        raise StoreError("--overwrite requires --import")

    path = path.expanduser()
    imported: Optional[Mapping[str, str]] = None
    if import_source is not None:
        source = import_source.expanduser()
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

    if target_dirs is None:
        target_dirs = TARGET_DIRS
    detected = detect_agents() if agent == "auto" else []
    selected = resolve_agents(agent, detected)
    skill_parents: List[Tuple[str, Path]] = []
    for name in selected:
        try:
            parent = target_dirs[name]
        except KeyError as exc:
            raise StoreError(f"No skill target configured for agent: {name}") from exc
        preflight_skill(parent, force)
        skill_parents.append((name, parent))

    created = initialize(path)
    validate_store(path)
    load(path)  # Parse the store during setup, while keeping all values inside the process.
    messages = [f"Store {'created' if created else 'ready'}: {path}"]

    if imported is not None:
        imported_count, skipped = import_values(path, imported, overwrite)
        action = "overwritten" if overwrite else "kept"
        messages.append(
            f"Imported {imported_count} variable(s); {action} {skipped}; values hidden"
        )

    if selected:
        messages.append("Agents: " + ", ".join(selected))
        for name, parent in skill_parents:
            target, status = ensure_skill(parent, force)
            if status == "already":
                messages.append(f"Skill already installed for {name}: {target}")
            elif status == "conflict":
                messages.append(
                    f"Skill exists and was not overwritten for {name}: {target}; "
                    "use --force to replace it"
                )
            elif status == "updated":
                messages.append(f"Skill updated for {name}: {target}")
            else:
                messages.append(f"Skill installed for {name}: {target}")
    else:
        messages.append("No supported agent detected; no skill installed")
        messages.append("Use --agent codex, --agent claude, --agent hermes, or --agent all")

    validate_store(path)
    load(path)
    if insecure_mode(path) is not None:
        raise StoreError(f"Secret store permissions are not private: {path}")
    messages.append("Doctor: OK (private store; values hidden)")
    messages.append("Setup complete")
    return messages
