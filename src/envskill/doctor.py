"""Value-free diagnostics for envskill and Agent Skills installations."""

from __future__ import annotations

import platform
import shlex
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from . import __version__
from .setup import inspect_skill
from .store import inspect_store

SCHEMA_VERSION = 1
SUPPORTED_SYSTEMS = {"Darwin", "Linux"}


def _problem(code: str, message: str, remediation: Sequence[str]) -> Dict[str, object]:
    return {
        "code": code,
        "message": message,
        "remediation": list(remediation),
    }


def _store_command(path: str, command: str = "init") -> str:
    return f"envskill --file {shlex.quote(path)} {command}"


def _store_remediation(code: str, path: str, location: Optional[str] = None) -> List[str]:
    init = _store_command(path)
    if code in {"missing", "insecure_mode", "parent_missing"}:
        return [init]
    if code == "foreign_owner":
        return [f'chown "$(id -un)" {shlex.quote(path)}', init]
    if code == "parent_foreign_owner":
        parent = location or path
        return [f'chown "$(id -un)" {shlex.quote(parent)}', init]
    if code == "parent_insecure_mode":
        parent = location or path
        return [f"chmod go-w {shlex.quote(parent)}", init]
    if code == "parent_invalid_type":
        parent = location or path
        return [f"Replace {shlex.quote(parent)} with a regular directory, then run: {init}"]
    if code == "malformed":
        return [f"$EDITOR {shlex.quote(path)}", init]
    if code == "invalid_type":
        return [f"Replace {shlex.quote(path)} with a regular file, then run: {init}"]
    return [init]


def _skill_remediation(agent: str, status: str) -> List[str]:
    install = f"envskill install-skill --target {agent}"
    if status == "conflict":
        return [f"{install} --force"]
    if status == "invalid":
        return [f"Fix the {agent} skill target, then run: {install} --force"]
    if status == "unreadable":
        return [f"Fix permissions for the {agent} skill, then run: {install} --force"]
    return [install]


def _store_problems(store: Mapping[str, object]) -> List[Dict[str, object]]:
    path = str(store["path"])
    problems: List[Dict[str, object]] = []
    for item in store.get("problems", []):
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code", "invalid_store"))
        message = str(item.get("message", "Store check failed"))
        location = str(item.get("path", path))
        problems.append(_problem(code, message, _store_remediation(code, path, location)))
    return problems


def build_report(
    path: Path,
    *,
    requested_agent: str,
    detected_agents: Sequence[str],
    selected_agents: Sequence[str],
    target_dirs: Mapping[str, Path],
    cli_path: Optional[str] = None,
) -> Dict[str, object]:
    """Build the stable, JSON-serializable doctor report."""
    if cli_path is None:
        cli_path = shutil.which("envskill")
    system = platform.system() or sys.platform
    platform_report = {
        "name": sys.platform,
        "system": system,
        "supported": system in SUPPORTED_SYSTEMS,
    }
    cli_report = {
        "version": __version__,
        "path": cli_path,
        "available": cli_path is not None,
    }
    store = inspect_store(path)
    problems = _store_problems(store)

    if not platform_report["supported"]:
        problems.append(
            _problem(
                "unsupported_platform",
                f"Unsupported platform: {system}; supported platforms are macOS and Linux",
                ["Run envskill on macOS or Linux"],
            )
        )
    if not cli_report["available"]:
        problems.append(
            _problem(
                "cli_not_on_path",
                "envskill is not on PATH",
                ["python -m envskill.cli doctor --agent all --json"],
            )
        )

    agents: List[Dict[str, object]] = []
    for agent in selected_agents:
        parent = target_dirs.get(agent)
        if parent is None:
            agent_report: Dict[str, object] = {
                "name": agent,
                "target": None,
                "skill_path": None,
                "status": "unconfigured",
                "bundled_copy_match": None,
                "exists": False,
                "ok": False,
                "error": f"No skill target configured for agent: {agent}",
            }
        else:
            skill = inspect_skill(parent)
            agent_report = {
                "name": agent,
                "target": str(parent.expanduser()),
                "skill_path": skill["path"],
                "status": skill["status"],
                "bundled_copy_match": skill["bundled_copy_match"],
                "exists": skill["exists"],
                "ok": skill["ok"],
                "error": skill["error"],
            }
        agents.append(agent_report)
        if not agent_report["ok"]:
            status = str(agent_report["status"])
            message = f"{agent} skill is {status}: {agent_report['skill_path']}"
            if agent_report["error"]:
                message += f" ({agent_report['error']})"
            problems.append(
                _problem(agent_report["status"], message, _skill_remediation(agent, status))
            )

    notes: List[str] = []
    if requested_agent == "auto" and not selected_agents:
        notes.append("No supported agent detected; use --agent all to check every supported target")

    report: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "ok": not problems,
        "cli": cli_report,
        "platform": platform_report,
        "store": store,
        "agent_selection": {
            "requested": requested_agent,
            "detected": list(detected_agents),
            "selected": list(selected_agents),
        },
        "agents": agents,
        "problems": problems,
        "notes": notes,
    }
    return report


def format_report(report: Mapping[str, object]) -> str:
    """Format a concise human-readable doctor report."""
    store = report["store"]
    cli = report["cli"]
    platform_report = report["platform"]
    selection = report["agent_selection"]
    lines: List[str] = []

    if report["ok"] and store["private"] is True and cli["available"]:
        lines.append(f"OK: store={store['path']}; permissions=private; cli=available")
    else:
        for item in report["problems"]:
            lines.append(f"FAIL: {item['message']}")

    platform_status = "supported" if platform_report["supported"] else "unsupported"
    lines.append(f"Platform: {platform_report['system']} ({platform_status})")
    selected = selection["selected"]
    lines.append(
        f"Agents ({selection['requested']}): {', '.join(selected) if selected else 'none detected'}"
    )
    for agent in report["agents"]:
        status = "OK" if agent["ok"] else "FAIL"
        lines.append(
            f"{status}: {agent['name']} skill={agent['status']}; path={agent['skill_path']}"
        )

    for item in report["problems"]:
        for command in item["remediation"]:
            lines.append(f"  Fix: {command}")
    for note in report["notes"]:
        lines.append(f"NOTE: {note}")
    return "\n".join(lines)
