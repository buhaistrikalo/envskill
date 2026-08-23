"""Dotenv-backed secret storage with locked, atomic, owner-only writes."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import stat
import tempfile
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Optional

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LINE_RE = re.compile(
    r"^(?P<prefix>\s*(?:export\s+)?)"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<sep>\s*=\s*)(?P<value>.*)$"
)
LOCK_TIMEOUT_SECONDS = 5.0


class StoreError(RuntimeError):
    """Raised when a secrets file cannot be parsed or updated safely."""


def default_path() -> Path:
    """Resolve the store without depending on any agent-specific directory."""
    override = os.environ.get("ENVSKILL_FILE")
    if override:
        return Path(override).expanduser()
    configured_home = os.environ.get("XDG_CONFIG_HOME")
    config_home = Path(configured_home).expanduser() if configured_home else Path.home() / ".config"
    return config_home / "envskill" / "secrets.env"


def validate_name(name: str) -> str:
    if not NAME_RE.fullmatch(name):
        raise StoreError(f"Invalid variable name: {name!r}")
    return name


def validate_value(value: str) -> str:
    if "\x00" in value:
        raise StoreError("Environment variable values cannot contain NUL bytes")
    return value


def decode_value(raw: str, path: Path, line_number: int) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            decoded, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as exc:
            raise StoreError(f"Cannot parse {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(decoded, str):
            raise StoreError(f"Cannot parse {path}:{line_number}: value must be a string")
        remainder = value[end:].strip()
        if remainder and not remainder.startswith("#"):
            raise StoreError(f"Cannot parse {path}:{line_number}: unexpected text after value")
        return validate_value(decoded)
    if value.startswith("'"):
        match = re.fullmatch(r"'((?:\\.|[^'])*)'\s*(?:#.*)?", value)
        if match is None:
            raise StoreError(f"Cannot parse {path}:{line_number}: unterminated quote")
        decoded = match.group(1).replace("\\'", "'").replace("\\\\", "\\")
        return validate_value(decoded)
    # In unquoted values, a comment starts only after whitespace.
    return validate_value(re.split(r"\s+#", value, maxsplit=1)[0].rstrip())


def encode_value(value: str) -> str:
    """Use ASCII JSON strings so every stored variable stays on one physical line."""
    return json.dumps(validate_value(value), ensure_ascii=True)


def _effective_uid() -> int:
    return os.geteuid() if hasattr(os, "geteuid") else os.getuid()


def _validate_descriptor(
    descriptor: int,
    path: Path,
    *,
    require_private: bool,
    require_owner: bool,
) -> os.stat_result:
    try:
        info = os.fstat(descriptor)
    except OSError as exc:
        raise StoreError(f"Cannot inspect {path}: {exc}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise StoreError(f"File must be regular: {path}")
    if os.name == "posix" and require_owner and info.st_uid != _effective_uid():
        raise StoreError(f"File is not owned by the current user: {path}")
    mode = stat.S_IMODE(info.st_mode)
    if os.name == "posix" and require_private and mode != 0o600:
        raise StoreError(
            f"Secret store permissions are {mode:04o}, expected 0600; run: envskill init"
        )
    return info


def _ensure_store_parent(path: Path) -> None:
    """Create and verify a user-owned parent that other OS users cannot modify."""
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.parent.lstat()
    except OSError as exc:
        raise StoreError(f"Cannot prepare store directory {path.parent}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise StoreError(f"Store parent must be a real directory, not a symlink: {path.parent}")
    if os.name == "posix":
        if info.st_uid != _effective_uid():
            raise StoreError(f"Store parent is not owned by the current user: {path.parent}")
        if stat.S_IMODE(info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            raise StoreError(f"Store parent is writable by another user: {path.parent}")


def _open_verified(
    path: Path,
    *,
    require_private: bool,
    require_owner: bool,
    trusted_parent: bool,
) -> Optional[int]:
    if trusted_parent:
        _ensure_store_parent(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif os.name == "posix":
        raise StoreError("This platform cannot safely reject symlinked secret stores")
    try:
        descriptor = os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise StoreError(f"File must not be a symlink: {path}") from exc
        raise StoreError(f"Cannot open {path}: {exc}") from exc
    try:
        _validate_descriptor(
            descriptor,
            path,
            require_private=require_private,
            require_owner=require_owner,
        )
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def read_lines(
    path: Path,
    *,
    require_private: bool = True,
    require_owner: bool = True,
    trusted_parent: bool = True,
) -> List[str]:
    descriptor = _open_verified(
        path,
        require_private=require_private,
        require_owner=require_owner,
        trusted_parent=trusted_parent,
    )
    if descriptor is None:
        return []
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", newline="") as handle:
            descriptor = -1
            text = handle.read()
    except (OSError, UnicodeError) as exc:
        raise StoreError(f"Cannot read {path}: {exc}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def load(
    path: Path,
    *,
    require_private: bool = True,
    require_owner: bool = True,
    trusted_parent: bool = True,
) -> Dict[str, str]:
    """Parse a single-line dotenv file. Physical CR/LF multiline values are rejected."""
    values: Dict[str, str] = {}
    lines = read_lines(
        path,
        require_private=require_private,
        require_owner=require_owner,
        trusted_parent=trusted_parent,
    )
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            raise StoreError(f"Cannot parse {path}:{number}")
        values[match.group("name")] = decode_value(match.group("value"), path, number)
    return values


def validate_store(path: Path, require_private: bool = True) -> None:
    descriptor = _open_verified(
        path,
        require_private=require_private,
        require_owner=True,
        trusted_parent=True,
    )
    if descriptor is not None:
        os.close(descriptor)


def insecure_mode(path: Path) -> Optional[int]:
    descriptor = _open_verified(
        path,
        require_private=False,
        require_owner=True,
        trusted_parent=True,
    )
    if descriptor is None:
        return None
    try:
        mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
        return mode if os.name == "posix" and mode != 0o600 else None
    finally:
        os.close(descriptor)


def _path_type(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "other"


def _owner_status(info: os.stat_result) -> str:
    if os.name != "posix":
        return "unknown"
    return "current" if info.st_uid == _effective_uid() else "other"


def _inspect_store_parent(path: Path) -> List[Dict[str, str]]:
    """Inspect a store parent without creating or following it."""
    try:
        info = path.parent.lstat()
    except FileNotFoundError:
        return [
            {
                "code": "parent_missing",
                "path": str(path.parent),
                "message": f"Store parent is missing: {path.parent}",
            }
        ]
    except OSError as exc:
        return [
            {
                "code": "parent_unreadable",
                "path": str(path.parent),
                "message": f"Cannot inspect store parent {path.parent}: {exc}",
            }
        ]

    problems: List[Dict[str, str]] = []
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        problems.append(
            {
                "code": "parent_invalid_type",
                "path": str(path.parent),
                "message": f"Store parent must be a real directory: {path.parent}",
            }
        )
        return problems
    if os.name == "posix":
        if info.st_uid != _effective_uid():
            problems.append(
                {
                    "code": "parent_foreign_owner",
                    "path": str(path.parent),
                    "message": f"Store parent is not owned by the current user: {path.parent}",
                }
            )
        if stat.S_IMODE(info.st_mode) & (stat.S_IWGRP | stat.S_IWOTH):
            problems.append(
                {
                    "code": "parent_insecure_mode",
                    "path": str(path.parent),
                    "message": f"Store parent is writable by another user: {path.parent}",
                }
            )
    return problems


def inspect_store(path: Path) -> Dict[str, object]:
    """Return value-free store metadata without creating, locking, or changing files."""
    path = path.expanduser()
    base: Dict[str, object] = {
        "path": str(path),
        "exists": False,
        "type": "missing",
        "owner": "unknown",
        "mode": None,
        "private": None,
        "parseable": None,
        "valid": False,
        "problems": [],
    }
    try:
        info = path.lstat()
    except FileNotFoundError:
        base["problems"] = [
            {"code": "missing", "path": str(path), "message": f"Store missing: {path}"},
        ]
        base["problems"].extend(
            problem
            for problem in _inspect_store_parent(path)
            if problem["code"] != "parent_missing"
        )
        return base
    except OSError as exc:
        base["type"] = "unreadable"
        base["problems"] = [
            {
                "code": "unreadable",
                "path": str(path),
                "message": f"Cannot inspect store {path}: {exc}",
            },
        ]
        return base

    mode = stat.S_IMODE(info.st_mode)
    mode_text = f"{mode:04o}"
    owner = _owner_status(info)
    base.update(
        {
            "exists": True,
            "type": _path_type(info.st_mode),
            "owner": owner,
            "mode": mode_text,
            "private": mode_text == "0600" if os.name == "posix" else None,
        }
    )
    problems: List[Dict[str, str]] = []
    if base["type"] != "file":
        problems.append(
            {
                "code": "invalid_type",
                "path": str(path),
                "message": f"Store must be a regular, non-symlink file: {path}",
            }
        )
    if os.name == "posix" and owner != "current":
        problems.append(
            {
                "code": "foreign_owner",
                "path": str(path),
                "message": f"Store is not owned by the current user: {path}",
            }
        )
    if os.name == "posix" and mode != 0o600:
        problems.append(
            {
                "code": "insecure_mode",
                "path": str(path),
                "message": f"Store permissions are {mode_text}, expected 0600",
            }
        )
    problems.extend(_inspect_store_parent(path))

    if base["type"] == "file" and not (os.name == "posix" and owner != "current"):
        try:
            load(
                path,
                require_private=False,
                require_owner=True,
                trusted_parent=False,
            )
        except StoreError as exc:
            problems.append({"code": "malformed", "path": str(path), "message": str(exc)})
            base["parseable"] = False
        else:
            base["parseable"] = True

    base["problems"] = problems
    base["valid"] = not problems
    return base


@contextmanager
def _store_lock(path: Path) -> Iterator[None]:
    """Use a persistent kernel-backed lock; crashes release it without stale-file races."""
    _ensure_store_parent(path)
    lock_path = path.with_name(f".{path.name}.lock")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(lock_path), flags, 0o600)
    except OSError as exc:
        raise StoreError(f"Cannot open store lock {lock_path}: {exc}") from exc
    try:
        _validate_descriptor(
            descriptor,
            lock_path,
            require_private=False,
            require_owner=True,
        )
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise StoreError(f"Timed out waiting for store lock: {lock_path}") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        raise StoreError(f"Cannot lock {path}: {exc}") from exc
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, lines: Iterable[str]) -> None:
    _ensure_store_parent(path)
    materialized = list(lines)
    text = "\n".join(materialized)
    if materialized:
        text += "\n"

    descriptor: Optional[int] = None
    temp_name: Optional[str] = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".secrets.", dir=str(path.parent), text=True
        )
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
        if os.name == "posix":
            with suppress(OSError):
                directory = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
    except OSError as exc:
        raise StoreError(f"Cannot write {path}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temp_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temp_name)


def initialize(path: Path) -> bool:
    with _store_lock(path):
        descriptor = _open_verified(
            path,
            require_private=False,
            require_owner=True,
            trusted_parent=True,
        )
        if descriptor is not None:
            try:
                if os.name == "posix":
                    os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
            return False
        _atomic_write(path, ["# Managed by envskill. Values are never printed by the CLI."])
        return True


def _updated_lines(lines: Iterable[str], updates: Mapping[str, str]) -> List[str]:
    output: List[str] = []
    replaced = set()
    for line in lines:
        match = LINE_RE.match(line)
        if match and match.group("name") in updates:
            name = match.group("name")
            if name not in replaced:
                output.append(f"{name}={encode_value(updates[name])}")
                replaced.add(name)
            continue
        output.append(line)
    for name, value in updates.items():
        if name not in replaced:
            output.append(f"{name}={encode_value(value)}")
    return output


def set_values(path: Path, updates: Mapping[str, str]) -> None:
    for name, value in updates.items():
        validate_name(name)
        validate_value(value)
    if not updates:
        return
    with _store_lock(path):
        _atomic_write(path, _updated_lines(read_lines(path), updates))


def import_values(
    path: Path, candidates: Mapping[str, str], overwrite: bool
) -> tuple[int, int]:
    """Merge imported values under one lock, preserving concurrent additions."""
    for name, value in candidates.items():
        validate_name(name)
        validate_value(value)
    with _store_lock(path):
        existing = load(path)
        selected = {
            name: value
            for name, value in candidates.items()
            if overwrite or name not in existing
        }
        if selected:
            _atomic_write(path, _updated_lines(read_lines(path), selected))
        return len(selected), len(candidates) - len(selected)


def set_value(path: Path, name: str, value: str) -> None:
    set_values(path, {name: value})


def unset_value(path: Path, name: str) -> bool:
    validate_name(name)
    with _store_lock(path):
        lines = read_lines(path)
        output: List[str] = []
        changed = False
        for line in lines:
            match = LINE_RE.match(line)
            if match and match.group("name") == name:
                changed = True
                continue
            output.append(line)
        if changed:
            _atomic_write(path, output)
        return changed
