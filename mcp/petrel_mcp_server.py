#!/usr/bin/env python3
"""No-Ocean local MCP server for Petrel export automation.

This server intentionally wraps the tested PowerShell automation boundary instead
of using Ocean SDK APIs. It speaks newline-delimited JSON-RPC over stdio, which is
the standard transport used by MCP stdio clients.
"""

from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVER_NAME = "petrel-no-ocean-control"
SERVER_VERSION = "0.8.3"
PROTOCOL_VERSION = "2024-11-05"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_NAME = "Petrel2010 demo project"
DEFAULT_PETREL_VERSION = "2018.2.0.5333"
DEFAULT_VERSION_SCOPE = "Petrel 2018.2 local help with Petrel 2010 demo-project automation copy"
DEFAULT_PROJECT_FILE = REPO_ROOT / "Petrel_DemoData_project" / "Petrel2010 demo project ExportPilot.pet"
DEFAULT_WORKFLOW_NAME = "ExportPiloX"
DEFAULT_MANIFEST_ROWS_PREVIEW = 10
DEFAULT_INVENTORY_PACKAGE = (
    REPO_ROOT
    / "build"
    / "inventory_pilots"
    / "Petrel2010_demo_project_inventory_20260701_055128"
)
DEFAULT_EXPORT_PACKAGE = (
    REPO_ROOT
    / "build"
    / "export_pilots"
    / "petrel2010_demo_project_export_20260701_060609"
)
DEFAULT_UNIVERSAL_EXPORT_OBJECT_TYPES = [
    "project_metadata",
    "well",
    "well_log",
    "well_top_petrel_ascii_export",
    "seismic_cube",
    "surface",
    "horizon",
    "fault",
    "model_grid",
    "grid_property",
    "workflow_report",
    "petrel_native_store",
]
DEFAULT_REQUIRED_FORMATS = {
    "project_metadata": ["JSON", "CSV"],
    "well": ["CSV"],
    "well_log": ["LAS"],
    "well_top_petrel_ascii_export": ["ASCII"],
    "seismic_cube": ["SEG-Y"],
    "surface": ["ZMAP", "ASCII", "CSV"],
    "horizon": ["CSV", "ASCII"],
    "fault": ["CSV", "ASCII"],
    "model_grid": ["RESQML", "RESCUE", "CSV"],
    "grid_property": ["RESQML", "CSV"],
    "workflow_report": ["TSV", "CSV", "JSON"],
    "petrel_native_store": ["BINARY", "XML", "PETREL_TEXT"],
}
TOOL_MATURITY_REGISTRY = {
    "stable": {
        "description": "Agent-safe entry points for local status, KB lookup, zero-GUI package work, validation, and read-only native inspection.",
        "tools": [
            "petrel_agent_readiness",
            "petrel_tool_creation_hierarchy",
            "petrel_tool_failure_policy",
            "petrel_status",
            "petrel_query_kb",
            "petrel_prepare_mvp",
            "petrel_register_and_validate",
            "petrel_export_native_zero_gui",
            "petrel_run_zero_gui_export_mvp",
            "petrel_export_native_semantic_zero_gui",
            "petrel_export_well_tables_zero_gui",
            "petrel_export_well_tops_native_probe",
            "petrel_import_gui_well_tops_table",
            "petrel_validate_workflow_coverage",
            "petrel_native_map_workflow",
            "petrel_native_snapshot",
            "petrel_native_compare_snapshots",
            "petrel_analyze_exportseismiccmd_records",
            "petrel_analyze_systemcmd_records",
            "petrel_analyze_workflow_command_clone_readiness",
            "petrel_analyze_workflow_clone_side_effects",
            "petrel_analyze_workflow_clone_storage_blocks",
            "petrel_extract_workflow_command_clone_recipe",
            "petrel_generate_workflow_from_okf",
            "petrel_export_surfaces_zero_gui",
            "petrel_survey_geometry",
            "petrel_grid_convert",
            "petrel_export_seismic_zgy_zero_gui",
            "petrel_write_well_tops_ascii",
            "petrel_las_convert",
            "petrel_project_audit_report",
        ],
    },
    "beta": {
        "description": "Useful but requires Petrel runtime state, a saved donor command, or deterministic GUI preconditions.",
        "tools": [
            "petrel_open_project",
            "petrel_run_mvp",
            "petrel_export_well_logs_ui",
            "petrel_export_well_tops_ui",
            "petrel_run_deterministic_gui_workflow",
            "petrel_export_segy_filename_patch",
            "petrel_export_segy_token_patch",
            "petrel_export_systemcmd_token_patch",
        ],
    },
    "experimental": {
        "description": "Low-level native edit primitives. Use only inside guarded proof workflows or dry-run analysis.",
        "tools": [
            "petrel_native_patch_string",
            "petrel_native_patch_offset",
        ],
    },
}
TOOL_CREATION_HIERARCHY_PATH = REPO_ROOT / "mcp" / "petrel_tool_creation_hierarchy.json"
FAILURE_POLICIES_PATH = REPO_ROOT / "mcp" / "petrel_mcp_failure_policies.json"
VERSION_AWARE_INPUTS = {
    "petrel_version": {
        "type": "string",
        "default": DEFAULT_PETREL_VERSION,
        "description": "Petrel version that this tool call targets or validates against.",
    },
    "version_scope": {
        "type": "string",
        "default": DEFAULT_VERSION_SCOPE,
        "description": "Human-readable compatibility scope; keep generated workflows and tool results tied to this scope.",
    },
    "target_versions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Petrel versions the result is intended to cover. Defaults to petrel_version.",
    },
}


class McpError(Exception):
    def __init__(self, message: str, code: int = -32000) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Any

    def mcp_shape(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


def as_path(value: str | None, default: Path) -> Path:
    if value is None or str(value).strip() == "":
        return default
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def resolve_existing_path(path: Path, label: str) -> Path:
    try:
        return path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise McpError(f"{label} not found: {path}") from exc


def ps_bool(enabled: bool, name: str) -> list[str]:
    return [f"-{name}"] if enabled else []


def _clean_executable_candidate(value: Any) -> str:
    return str(value or "").strip().strip('"')


def _resolve_executable_candidate(candidate: str) -> str | None:
    candidate = _clean_executable_candidate(candidate)
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_absolute() or "\\" in candidate or "/" in candidate:
        return str(path.resolve()) if path.exists() and path.is_file() else None
    found = shutil.which(candidate)
    return found or None


def _probe_executable(candidate: str, source: str, version_args: list[str]) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "source": source,
        "candidate": _clean_executable_candidate(candidate),
        "resolved_path": "",
        "ok": False,
    }
    resolved = _resolve_executable_candidate(candidate)
    if not resolved:
        detail["error"] = "not_found"
        return detail
    detail["resolved_path"] = resolved
    try:
        proc = subprocess.run(
            [resolved, *version_args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        detail["exit_code"] = proc.returncode
        detail["version"] = output.splitlines()[0] if output else ""
        detail["ok"] = proc.returncode == 0
    except Exception as exc:
        detail["error"] = str(exc)
    return detail


def resolve_mcp_executable(
    label: str,
    candidates: list[tuple[str, Any]],
    version_args: list[str] | None = None,
) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    seen: set[str] = set()
    args = version_args or ["--version"]
    for source, candidate in candidates:
        cleaned = _clean_executable_candidate(candidate)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        detail = _probe_executable(cleaned, source, args)
        checked.append(detail)
        if detail.get("ok"):
            return {
                "ok": True,
                "label": label,
                "path": detail.get("resolved_path") or cleaned,
                "version": detail.get("version") or "",
                "source": source,
                "checked": checked,
            }
    return {
        "ok": False,
        "label": label,
        "path": "",
        "version": "",
        "source": "",
        "checked": checked,
        "error": f"{label} was not found or could not be executed.",
    }


def resolve_mcp_python(arguments: dict[str, Any]) -> dict[str, Any]:
    explicit = _clean_executable_candidate(arguments.get("python_path"))
    candidates = (
        [("argument.python_path", explicit)]
        if explicit
        else [
            ("env.PETREL_MCP_PYTHON", os.environ.get("PETREL_MCP_PYTHON")),
            ("env.PYTHON", os.environ.get("PYTHON")),
            ("mcp_server.sys.executable", sys.executable),
            ("repo.venv", REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
            ("PATH.python.exe", "python.exe"),
            ("PATH.python", "python"),
            ("PATH.py.exe", "py.exe"),
            ("PATH.py", "py"),
        ]
    )
    return resolve_mcp_executable(
        "Python for Petrel MCP",
        candidates,
        ["--version"],
    )


def resolve_mcp_tesseract(arguments: dict[str, Any]) -> dict[str, Any]:
    explicit = _clean_executable_candidate(arguments.get("tesseract_path"))
    candidates = (
        [("argument.tesseract_path", explicit)]
        if explicit
        else [
            ("env.PETREL_TESSERACT_PATH", os.environ.get("PETREL_TESSERACT_PATH")),
            ("env.TESSERACT_PATH", os.environ.get("TESSERACT_PATH")),
            ("default.program_files", r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            ("default.program_files_x86", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ("PATH.tesseract.exe", "tesseract.exe"),
            ("PATH.tesseract", "tesseract"),
        ]
    )
    return resolve_mcp_executable(
        "Tesseract OCR for Petrel MCP",
        candidates,
        ["--version"],
    )


_POWERSHELL_RUNTIME: dict[str, Any] | None = None


def resolve_powershell_runtime() -> str:
    global _POWERSHELL_RUNTIME
    if _POWERSHELL_RUNTIME is None:
        _POWERSHELL_RUNTIME = resolve_mcp_executable(
            "Windows PowerShell for Petrel MCP",
            [("PATH.powershell.exe", "powershell.exe")],
            ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
        )
    if not _POWERSHELL_RUNTIME.get("ok"):
        raise McpError(str(_POWERSHELL_RUNTIME.get("error") or "powershell.exe was not found."))
    return str(_POWERSHELL_RUNTIME["path"])


def dependency_preflight_failed(
    operation: str,
    preflight: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    return tool_result(
        {
            "operation": operation,
            "status": "preflight_failed",
            "error": "; ".join(failures),
            "preflight": preflight,
            "petrel_not_touched": True,
        }
    )


def build_dependency_preflight(
    arguments: dict[str, Any],
    *,
    require_python: bool = False,
    require_tesseract: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    preflight: dict[str, Any] = {
        "status": "passed",
        "python_required": require_python,
        "tesseract_required": require_tesseract,
    }
    failures: list[str] = []
    if require_python:
        python = resolve_mcp_python(arguments)
        preflight["python"] = python
        if not python.get("ok"):
            failures.append(str(python.get("error") or "Python dependency failed."))
    if require_tesseract:
        tesseract = resolve_mcp_tesseract(arguments)
        preflight["tesseract"] = tesseract
        if not tesseract.get("ok"):
            failures.append(str(tesseract.get("error") or "Tesseract dependency failed."))
    if failures:
        preflight["status"] = "failed"
    return preflight, failures


def preflight_python_path(preflight: dict[str, Any]) -> str:
    python = preflight.get("python")
    if isinstance(python, dict) and python.get("ok"):
        return str(python.get("path") or "")
    return ""


def preflight_tesseract_path(preflight: dict[str, Any]) -> str:
    tesseract = preflight.get("tesseract")
    if isinstance(tesseract, dict) and tesseract.get("ok"):
        return str(tesseract.get("path") or "")
    return ""


def run_powershell_script(script: str, args: list[str], timeout_seconds: int = 900) -> dict[str, Any]:
    script_path = resolve_existing_path(REPO_ROOT / "scripts" / script, f"Script {script}")
    command = [
        resolve_powershell_runtime(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        *args,
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise McpError(f"Timed out after {timeout_seconds}s running {script}") from exc

    return {
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def latest_file(pattern: str) -> Path | None:
    matches = [Path(item) for item in glob.glob(pattern)]
    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def stdout_labeled_value(stdout: str, label: str) -> str | None:
    values = stdout_labeled_values(stdout, label)
    return values[0] if values else None


def stdout_labeled_values(stdout: str, label: str) -> list[str]:
    prefix = f"{label}:"
    values: list[str] = []
    for line in stdout.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            if value:
                values.append(value)
    return values


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def resolve_artifact_path(value: str | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def csv_row_count(path: Path | None) -> int:
    if path is None or not path.exists() or not path.is_file():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def first_csv_row(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists() or not path.is_file():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return next(reader, {}) or {}


def latest_artifact(pattern: Path) -> Path | None:
    matches = [Path(item) for item in glob.glob(str(pattern))]
    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def attach_labeled_path(
    payload: dict[str, Any],
    stdout: str,
    label: str,
    path_key: str,
    report_key: str | None = None,
) -> None:
    path_value = stdout_labeled_value(stdout, label)
    if not path_value:
        return
    payload[path_key] = path_value
    if report_key:
        path = Path(path_value)
        if path.exists() and path.is_file():
            payload[report_key] = load_json(path)


def enrich_well_tops_native_probe_payload(payload: dict[str, Any], export_package: Path) -> None:
    stdout = str(payload.get("stdout") or "")
    report_candidates = stdout_labeled_values(stdout, "Report")
    native_probe_report_path = ""
    registration_report_path = ""
    validation_report_path = ""
    for candidate in report_candidates:
        name = Path(candidate).name.lower()
        if name.startswith("well_tops_native_probe_"):
            native_probe_report_path = candidate
        elif name.startswith("petrel_file_export_registration_"):
            registration_report_path = candidate
        elif name.startswith("export_validation_"):
            validation_report_path = candidate

    if not native_probe_report_path and isinstance(payload.get("report"), dict):
        outputs = payload["report"].get("outputs")
        if isinstance(outputs, dict):
            native_probe_report_path = str(outputs.get("report") or "")
    if not native_probe_report_path:
        latest_native = latest_artifact(
            export_package / "07_workflows_reports" / "zero_gui_well_exports" / "well_tops_native_probe_*.json"
        )
        if latest_native:
            native_probe_report_path = str(latest_native)
    if not registration_report_path:
        latest_registration = latest_artifact(
            export_package / "07_workflows_reports" / "automation_runs" / "petrel_file_export_registration_*.json"
        )
        if latest_registration:
            registration_report_path = str(latest_registration)
    if not validation_report_path:
        latest_validation = latest_artifact(
            export_package / "07_workflows_reports" / "validation_reports" / "export_validation_*.md"
        )
        if latest_validation:
            validation_report_path = str(latest_validation)

    native_report = payload.get("report")
    if not isinstance(native_report, dict) and native_probe_report_path:
        native_report_file = resolve_artifact_path(native_probe_report_path)
        if native_report_file and native_report_file.exists():
            native_report = load_json(native_report_file)
            payload["report"] = native_report

    well_top_dir = export_package / "02_wells" / "well_tops"
    parsed_petrel_ascii_csv = well_top_dir / "well_tops_from_petrel_ascii_export.csv"
    parsed_row_count = csv_row_count(parsed_petrel_ascii_csv)
    first_row = first_csv_row(parsed_petrel_ascii_csv)
    raw_petrel_ascii_path = resolve_artifact_path(first_row.get("source_file"))
    raw_petrel_ascii = str(raw_petrel_ascii_path) if raw_petrel_ascii_path else ""
    raw_petrel_ascii_exists = bool(raw_petrel_ascii_path and raw_petrel_ascii_path.exists())
    petrel_authored_ascii_confirmed = (
        parsed_row_count > 0
        and str(first_row.get("petrel_export_confirmed") or "").lower() in {"yes", "true", "1"}
        and raw_petrel_ascii_exists
    )

    native_binary_pick_rows = 0
    source_ascii_pick_rows = 0
    boundary = ""
    if isinstance(native_report, dict):
        native_binary_pick_rows = int(native_report.get("actual_well_top_pick_rows_from_native_binary") or 0)
        source_ascii_pick_rows = int(native_report.get("source_ascii_pick_rows") or 0)
        boundary = str(native_report.get("boundary") or "")

    native_binary_pick_decode_confirmed = native_binary_pick_rows > 0
    agent_summary = {
        "status": "validated" if int(payload.get("exit_code") or 0) == 0 else "failed",
        "native_probe_report_path": native_probe_report_path,
        "registration_report_path": registration_report_path,
        "validation_report_path": validation_report_path,
        "raw_petrel_ascii_file": raw_petrel_ascii,
        "raw_petrel_ascii_exists": raw_petrel_ascii_exists,
        "parsed_petrel_ascii_csv": str(parsed_petrel_ascii_csv),
        "petrel_ascii_pick_row_count": parsed_row_count,
        "petrel_authored_ascii_confirmed": petrel_authored_ascii_confirmed,
        "native_binary_pick_decode_confirmed": native_binary_pick_decode_confirmed,
        "native_binary_pick_row_count": native_binary_pick_rows,
        "source_ascii_pick_rows": source_ascii_pick_rows,
        "boundary": boundary
        or "Petrel-authored ASCII export parsing is confirmed when present; native binary marker-pick decoding remains unconfirmed unless native_binary_pick_row_count is greater than zero.",
    }
    payload["agent_summary"] = agent_summary
    payload["native_probe_report_path"] = native_probe_report_path
    payload["registration_report_path"] = registration_report_path
    payload["validation_report_path"] = validation_report_path
    payload["raw_petrel_ascii_file"] = raw_petrel_ascii
    payload["parsed_csv"] = str(parsed_petrel_ascii_csv)
    payload["row_count"] = parsed_row_count
    payload["petrel_authored_ascii_confirmed"] = petrel_authored_ascii_confirmed
    payload["native_binary_pick_decode_confirmed"] = native_binary_pick_decode_confirmed


_FAILURE_POLICY_CONFIG: dict[str, Any] | None = None


def load_failure_policy_config() -> dict[str, Any]:
    global _FAILURE_POLICY_CONFIG
    if _FAILURE_POLICY_CONFIG is None:
        _FAILURE_POLICY_CONFIG = load_json(resolve_existing_path(FAILURE_POLICIES_PATH, "MCP failure policy"))
    return _FAILURE_POLICY_CONFIG


def clone_jsonlike(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def resolve_failure_policy(tool_name: str) -> dict[str, Any]:
    config = load_failure_policy_config()
    default_policy = clone_jsonlike(config.get("default_policy", {}))
    tool_policies = config.get("tool_policies", {})
    tool_policy = clone_jsonlike(tool_policies.get(tool_name, {}))
    template_name = str(tool_policy.get("template") or default_policy.get("template") or "planning_policy")
    template = clone_jsonlike(config.get("policy_templates", {}).get(template_name, default_policy))
    resolved = template
    for key, value in tool_policy.items():
        if key == "template":
            continue
        resolved[key] = value
    for key, value in default_policy.items():
        resolved.setdefault(key, clone_jsonlike(value))
    resolved["tool_name"] = tool_name
    resolved["template"] = template_name
    resolved["policy_version"] = config.get("policy_version")
    resolved["policy_path"] = str(FAILURE_POLICIES_PATH)
    if tool_name not in tool_policies:
        resolved["policy_warning"] = "No explicit policy was found for this tool; default policy is applied."
    return resolved


def failure_policy_summary(tool_name: str) -> dict[str, Any]:
    policy = resolve_failure_policy(tool_name)
    summary_keys = [
        "tool_name",
        "tier",
        "template",
        "confidence",
        "fail_closed",
        "runtime_gui_used",
        "petrel_process_expected",
        "success_evidence",
        "critical_failures",
        "fallback_chain",
        "retry_policy",
        "cleanup",
        "manual_intervention",
        "policy_version",
        "policy_path",
    ]
    return {key: policy[key] for key in summary_keys if key in policy}


def nested_get(data: Any, path: list[str]) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def text_contains_validation_passed(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.search(r"Validation status:\s*passed", value, flags=re.IGNORECASE))


def audit_passed(audit: dict[str, Any], evidence_id: str, detail: Any = None) -> None:
    evidence = {"id": evidence_id, "status": "passed"}
    if detail is not None:
        evidence["detail"] = detail
    audit["evidence"].append(evidence)


def audit_failed(audit: dict[str, Any], failure_class: str, evidence_id: str, detail: Any = None) -> None:
    evidence = {"id": evidence_id, "status": "failed", "failure_class": failure_class}
    if detail is not None:
        evidence["detail"] = detail
    audit["evidence"].append(evidence)
    audit["failures"].append(evidence)


def audit_skipped(audit: dict[str, Any], evidence_id: str, reason: str) -> None:
    audit["evidence"].append({"id": evidence_id, "status": "skipped", "reason": reason})


def build_base_audit(tool_name: str, policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tier": policy.get("tier"),
        "status": "passed",
        "failure_class": "",
        "fail_closed": bool(policy.get("fail_closed", True)),
        "evidence": [],
        "failures": [],
        "fallback_available": bool(policy.get("fallback_chain")),
        "fallback_chain": policy.get("fallback_chain", []),
        "retry_policy": policy.get("retry_policy", ""),
        "next_safe_action": "",
    }


def finalize_audit(audit: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if audit["failures"]:
        audit["status"] = "failed"
        audit["failure_class"] = str(audit["failures"][0].get("failure_class") or "failed")
        fallback_chain = policy.get("fallback_chain") or []
        if fallback_chain:
            audit["next_safe_action"] = str(fallback_chain[0])
        else:
            audit["next_safe_action"] = "Inspect evidence paths and rerun only after correcting the failed gate."
    else:
        audit["status"] = "passed"
        audit["failure_class"] = ""
        audit["next_safe_action"] = "Proceed to the next planned automation step."
    return audit


def audit_validation_result(payload: dict[str, Any], audit: dict[str, Any]) -> None:
    validation_result = payload.get("validation_result")
    if isinstance(validation_result, dict):
        stdout = str(validation_result.get("stdout") or "")
        exit_code = validation_result.get("exit_code")
        if exit_code is not None and int(exit_code) != 0:
            audit_failed(audit, "validation_failed", "validation_exit_zero", {"exit_code": exit_code})
        elif stdout:
            if text_contains_validation_passed(stdout):
                audit_passed(audit, "validation_status_passed")
            else:
                audit_failed(audit, "validation_failed", "validation_status_passed", stdout.splitlines()[:5])


def audit_generic_result(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    audit = build_base_audit(tool_name, policy)
    if "exit_code" in payload:
        exit_code = int(payload.get("exit_code") or 0)
        if exit_code == 0:
            audit_passed(audit, "process_exit_zero", {"exit_code": exit_code})
        else:
            audit_failed(audit, "process_failed", "process_exit_zero", {"exit_code": exit_code})

    status = str(payload.get("status") or "").lower()
    if status:
        if status in {"passed", "pass", "registered", "validated", "dry_run", "skipped", "ok"}:
            audit_passed(audit, "reported_status_acceptable", status)
        elif status in {"failed", "error", "preflight_failed"}:
            audit_failed(audit, "reported_failed", "reported_status_acceptable", status)
        elif status in {"needs_attention", "partial"}:
            audit_failed(audit, status, "reported_status_acceptable", status)

    audit_validation_result(payload, audit)
    return finalize_audit(audit, policy)


def audit_deterministic_gui_workflow(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    audit = audit_generic_result(tool_name, payload, policy)
    # Reopen the status after adding deterministic gates below.
    audit["status"] = "passed"
    audit["failure_class"] = ""
    audit["next_safe_action"] = ""

    execute = bool(payload.get("execute"))
    if not execute:
        audit_skipped(audit, "execution_requested", "execute=false; dry-run contract only")
        return finalize_audit(audit, policy)
    audit_passed(audit, "execution_requested", True)

    report = payload.get("report")
    if not isinstance(report, dict):
        audit_failed(audit, "report_missing", "runner_report_loaded", payload.get("report_path") or "")
        return finalize_audit(audit, policy)
    audit_passed(audit, "runner_report_loaded", payload.get("report_path") or "")

    report_status = str(report.get("status") or "").lower()
    if report_status == "passed":
        audit_passed(audit, "runner_report_status_passed", report_status)
    else:
        audit_failed(audit, "runner_failed", "runner_report_status_passed", report_status)

    ui_result = report.get("ui_driver_result")
    if isinstance(ui_result, dict) and int(ui_result.get("exit_code") or 0) == 0:
        audit_passed(audit, "ui_driver_exit_zero", ui_result.get("exit_code"))
    else:
        audit_failed(audit, "ui_driver_failed", "ui_driver_exit_zero", ui_result)

    output_candidates = [str(report.get("actual_output") or "")]
    postconditions_for_output = report.get("postcondition_results")
    if isinstance(postconditions_for_output, list):
        for item in postconditions_for_output:
            if isinstance(item, dict) and item.get("id") in {"ascii_file_written", "gui_table_file_written"}:
                output_candidates.append(str(item.get("path") or ""))
    output_candidates.append(str(report.get("expected_output") or ""))
    output_path = next((item for item in output_candidates if item), "")
    if output_path and Path(output_path).exists() and Path(output_path).is_file():
        output_info = Path(output_path)
        if output_info.stat().st_size > 0:
            audit_passed(audit, "raw_petrel_ascii_exists_nonempty", {"path": output_path, "bytes": output_info.stat().st_size})
        else:
            audit_failed(audit, "output_empty", "raw_petrel_ascii_exists_nonempty", output_path)
    else:
        audit_failed(audit, "output_missing", "raw_petrel_ascii_exists_nonempty", output_candidates)

    row_count_value = nested_get(report, ["ascii_import_report", "row_count"])
    skip_import = bool(report.get("skip_import"))
    if skip_import:
        audit_skipped(audit, "ascii_import_rows_gt_zero", "skip_import=true")
    else:
        try:
            row_count = int(row_count_value)
        except (TypeError, ValueError):
            row_count = 0
        if row_count > 0:
            audit_passed(audit, "ascii_import_rows_gt_zero", row_count)
        else:
            audit_failed(audit, "parse_failed", "ascii_import_rows_gt_zero", row_count_value)

    validation_stdout = str(nested_get(report, ["validation_result", "stdout"]) or "")
    if validation_stdout:
        if text_contains_validation_passed(validation_stdout):
            audit_passed(audit, "manifest_validation_passed")
        else:
            audit_failed(audit, "validation_failed", "manifest_validation_passed", validation_stdout.splitlines()[:5])
    else:
        audit_failed(audit, "validation_missing", "manifest_validation_passed", "")

    postconditions = report.get("postcondition_results")
    if isinstance(postconditions, list):
        failed_postconditions = [item for item in postconditions if isinstance(item, dict) and item.get("status") == "failed"]
        if failed_postconditions:
            audit_failed(audit, "postcondition_failed", "postconditions_passed", failed_postconditions)
        else:
            audit_passed(audit, "postconditions_passed", len(postconditions))

    return finalize_audit(audit, policy)


def path_status(path_value: Any, *, directory: bool = False, nonempty: bool = False) -> tuple[bool, dict[str, Any]]:
    path_text = str(path_value or "")
    if not path_text:
        return False, {"path": path_text}
    path = Path(path_text)
    detail: dict[str, Any] = {"path": path_text}
    if not path.exists():
        return False, detail
    if directory:
        detail["type"] = "directory"
        return path.is_dir(), detail
    detail["type"] = "file"
    if not path.is_file():
        return False, detail
    size = path.stat().st_size
    detail["bytes"] = size
    if nonempty and size <= 0:
        return False, detail
    return True, detail


def audit_existing_path(
    audit: dict[str, Any],
    evidence_id: str,
    path_value: Any,
    *,
    failure_class: str = "evidence_missing",
    directory: bool = False,
    nonempty: bool = False,
) -> None:
    exists, detail = path_status(path_value, directory=directory, nonempty=nonempty)
    if exists:
        audit_passed(audit, evidence_id, detail)
    else:
        audit_failed(audit, failure_class, evidence_id, detail)


def ascii_len(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return len(value.encode("ascii"))
    except UnicodeEncodeError:
        return None


def audit_same_length_report(audit: dict[str, Any], report: dict[str, Any]) -> None:
    expected_value = report.get("expected", report.get("search"))
    replacement_value = report.get("replace")
    expected_len = ascii_len(expected_value)
    replacement_len = ascii_len(replacement_value)
    byte_length = report.get("byte_length")
    try:
        byte_length_int = int(byte_length)
    except (TypeError, ValueError):
        byte_length_int = 0

    if expected_len and replacement_len and expected_len == replacement_len == byte_length_int:
        audit_passed(audit, "same_ascii_byte_length", byte_length_int)
    else:
        audit_failed(
            audit,
            "length_mismatch",
            "same_ascii_byte_length",
            {
                "expected_length": expected_len,
                "replacement_length": replacement_len,
                "byte_length": byte_length,
            },
        )


def audit_patch_report_integrity(
    audit: dict[str, Any],
    report: dict[str, Any],
    *,
    applied: bool | None = None,
) -> None:
    audit_same_length_report(audit, report)
    audit_existing_path(audit, "target_store_exists", report.get("target_path"), nonempty=True)
    audit_existing_path(audit, "backup_store_exists", report.get("target_backup"), nonempty=True)

    hit_count = report.get("hit_count")
    if hit_count is not None:
        try:
            hit_count_int = int(hit_count)
        except (TypeError, ValueError):
            hit_count_int = 0
        if hit_count_int > 0:
            audit_passed(audit, "target_occurrences_found", hit_count_int)
        else:
            audit_failed(audit, "target_not_found", "target_occurrences_found", hit_count)

    dry_run = bool(report.get("dry_run"))
    before_hash = str(report.get("before_sha256") or "")
    after_hash = str(report.get("after_sha256") or "")
    if before_hash and after_hash:
        audit_passed(audit, "hashes_recorded", {"before_sha256": before_hash, "after_sha256": after_hash})
        if dry_run:
            if before_hash == after_hash:
                audit_passed(audit, "dry_run_no_mutation")
            else:
                audit_failed(audit, "unexpected_mutation", "dry_run_no_mutation")
        else:
            if before_hash != after_hash:
                audit_passed(audit, "patch_changed_hash")
            else:
                audit_failed(audit, "patch_noop", "patch_changed_hash")
    else:
        audit_failed(audit, "hash_missing", "hashes_recorded")

    if applied is not None:
        if dry_run == (not applied):
            audit_passed(audit, "dry_run_matches_apply_flag", {"dry_run": dry_run, "applied": applied})
        else:
            audit_failed(
                audit,
                "apply_mode_mismatch",
                "dry_run_matches_apply_flag",
                {"dry_run": dry_run, "applied": applied},
            )


def compare_report_is_clean(report_path: Any) -> tuple[bool, dict[str, Any]]:
    path_text = str(report_path or "")
    detail: dict[str, Any] = {"path": path_text}
    if not path_text:
        return False, detail
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return False, detail
    try:
        report = load_json(path)
    except Exception as exc:
        detail["error"] = str(exc)
        return False, detail
    store_summaries = report.get("store_summaries")
    if not isinstance(store_summaries, list):
        detail["store_summaries"] = "missing"
        return False, detail
    changed = [item.get("store_file") for item in store_summaries if isinstance(item, dict) and item.get("changed")]
    detail["changed_stores"] = changed
    detail["store_count"] = len(store_summaries)
    return not changed, detail


def compare_report_has_change(report_path: Any) -> tuple[bool, dict[str, Any]]:
    path_text = str(report_path or "")
    detail: dict[str, Any] = {"path": path_text}
    if not path_text:
        return False, detail
    path = Path(path_text)
    if not path.exists() or not path.is_file():
        return False, detail
    try:
        report = load_json(path)
    except Exception as exc:
        detail["error"] = str(exc)
        return False, detail
    store_summaries = report.get("store_summaries")
    if not isinstance(store_summaries, list):
        detail["store_summaries"] = "missing"
        return False, detail
    changed = [item.get("store_file") for item in store_summaries if isinstance(item, dict) and item.get("changed")]
    detail["changed_stores"] = changed
    detail["store_count"] = len(store_summaries)
    return bool(changed), detail


def audit_validation_summary(audit: dict[str, Any], validation: Any, *, required: bool = True) -> None:
    if not isinstance(validation, dict):
        if required:
            audit_failed(audit, "validation_missing", "validation_summary_passed")
        else:
            audit_skipped(audit, "validation_summary_passed", "validation not requested")
        return

    status = str(validation.get("status") or "").lower()
    failed_count = validation.get("failed_count")
    try:
        failed_count_int = int(failed_count)
    except (TypeError, ValueError):
        failed_count_int = -1
    if status == "passed" and failed_count_int == 0:
        audit_passed(
            audit,
            "validation_summary_passed",
            {
                "status": status,
                "row_count": validation.get("row_count"),
                "failed_count": failed_count,
                "report_path": validation.get("report_path"),
            },
        )
    else:
        audit_failed(audit, "validation_failed", "validation_summary_passed", validation)


def audit_native_read_only(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    audit = audit_generic_result(tool_name, payload, policy)

    if tool_name == "petrel_native_map_workflow":
        audit_existing_path(audit, "map_summary_exists", payload.get("summary_path"), nonempty=True)
        audit_existing_path(audit, "term_map_exists", payload.get("term_map_path"), nonempty=True)
    elif tool_name == "petrel_native_snapshot":
        audit_existing_path(audit, "snapshot_directory_exists", payload.get("snapshot_path"), directory=True)
        audit_existing_path(audit, "snapshot_manifest_exists", payload.get("manifest_path"), nonempty=True)
        manifest_report = payload.get("manifest_report")
        if isinstance(manifest_report, dict):
            audit_passed(audit, "snapshot_manifest_loaded", {"files": len(manifest_report.get("files", []))})
        else:
            audit_failed(audit, "report_missing", "snapshot_manifest_loaded")
    elif tool_name == "petrel_native_compare_snapshots":
        audit_existing_path(audit, "compare_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        store_summaries = report.get("store_summaries") if isinstance(report, dict) else None
        if isinstance(store_summaries, list) and store_summaries:
            audit_passed(audit, "store_summaries_present", len(store_summaries))
        else:
            audit_failed(audit, "report_incomplete", "store_summaries_present")
    elif tool_name in {"petrel_analyze_exportseismiccmd_records", "petrel_analyze_systemcmd_records"}:
        audit_existing_path(audit, "analyzer_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        record_count = report.get("record_count") if isinstance(report, dict) else None
        try:
            record_count_int = int(record_count)
        except (TypeError, ValueError):
            record_count_int = 0
        if record_count_int > 0:
            audit_passed(audit, "native_records_found", record_count_int)
        else:
            audit_failed(audit, "record_not_found", "native_records_found", record_count)
        if isinstance(report, dict):
            for evidence_id, key in (
                ("records_csv_exists", "records_csv"),
                ("token_hits_csv_exists", "token_hits_csv"),
                ("model_hits_csv_exists", "model_hits_csv"),
            ):
                audit_existing_path(audit, evidence_id, report.get(key), nonempty=True)
    elif tool_name == "petrel_analyze_workflow_command_clone_readiness":
        audit_existing_path(audit, "clone_readiness_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        readiness = report.get("readiness") if isinstance(report, dict) else None
        if isinstance(readiness, dict) and isinstance(readiness.get("clone_safe"), bool):
            audit_passed(
                audit,
                "clone_readiness_evaluated",
                {
                    "clone_safe": readiness.get("clone_safe"),
                    "status": readiness.get("status"),
                    "blocker_count": readiness.get("blocker_count"),
                },
            )
        else:
            audit_failed(audit, "report_incomplete", "clone_readiness_evaluated")
        record_count = report.get("record_count") if isinstance(report, dict) else None
        try:
            record_count_int = int(record_count)
        except (TypeError, ValueError):
            record_count_int = 0
        if record_count_int > 0:
            audit_passed(audit, "native_records_found", record_count_int)
        else:
            audit_failed(audit, "record_not_found", "native_records_found", record_count)
        if isinstance(report, dict):
            audit_existing_path(audit, "clone_readiness_records_csv_exists", report.get("records_csv"), nonempty=True)
            audit_existing_path(audit, "clone_readiness_gates_csv_exists", report.get("gates_csv"), nonempty=True)
    elif tool_name == "petrel_analyze_workflow_clone_side_effects":
        audit_existing_path(audit, "clone_side_effect_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        analysis = report.get("analysis") if isinstance(report, dict) else None
        if isinstance(analysis, dict) and isinstance(analysis.get("side_effects_isolated"), bool):
            audit_passed(
                audit,
                "clone_side_effects_evaluated",
                {
                    "side_effects_isolated": analysis.get("side_effects_isolated"),
                    "status": analysis.get("status"),
                    "blocker_count": analysis.get("blocker_count"),
                },
            )
        else:
            audit_failed(audit, "report_incomplete", "clone_side_effects_evaluated")
        if isinstance(report, dict):
            for evidence_id, key in (
                ("clone_side_effect_ranges_csv_exists", "ranges_csv"),
                ("clone_side_effect_summary_csv_exists", "summary_csv"),
                ("clone_side_effect_required_actions_csv_exists", "required_actions_csv"),
                ("clone_side_effect_gates_csv_exists", "gates_csv"),
            ):
                audit_existing_path(audit, evidence_id, report.get(key), nonempty=True)
    elif tool_name == "petrel_analyze_workflow_clone_storage_blocks":
        audit_existing_path(audit, "clone_storage_block_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        analysis = report.get("analysis") if isinstance(report, dict) else None
        if isinstance(analysis, dict) and isinstance(analysis.get("storage_payload_separated"), bool):
            audit_passed(
                audit,
                "clone_storage_blocks_evaluated",
                {
                    "storage_payload_separated": analysis.get("storage_payload_separated"),
                    "status": analysis.get("status"),
                    "blocker_count": analysis.get("blocker_count"),
                },
            )
        else:
            audit_failed(audit, "report_incomplete", "clone_storage_blocks_evaluated")
        if isinstance(report, dict):
            for evidence_id, key in (
                ("clone_storage_block_segments_csv_exists", "segments_csv"),
                ("clone_storage_block_summary_csv_exists", "summary_csv"),
                ("clone_storage_block_required_actions_csv_exists", "required_actions_csv"),
                ("clone_storage_block_gates_csv_exists", "gates_csv"),
            ):
                audit_existing_path(audit, evidence_id, report.get(key), nonempty=True)
    elif tool_name == "petrel_extract_workflow_command_clone_recipe":
        audit_existing_path(audit, "clone_recipe_report_exists", payload.get("report_path"), nonempty=True)
        report = payload.get("report")
        recipe = report.get("recipe") if isinstance(report, dict) else None
        if isinstance(recipe, dict) and isinstance(recipe.get("recipe_safe_to_apply"), bool):
            audit_passed(
                audit,
                "clone_recipe_extracted",
                {
                    "recipe_safe_to_apply": recipe.get("recipe_safe_to_apply"),
                    "recipe_status": recipe.get("recipe_status"),
                    "blocker_count": recipe.get("blocker_count"),
                },
            )
        else:
            audit_failed(audit, "report_incomplete", "clone_recipe_extracted")
        payload_count = report.get("candidate_payloads") if isinstance(report, dict) else None
        payload_count_int = len(payload_count) if isinstance(payload_count, list) else 0
        if payload_count_int >= 2:
            audit_passed(audit, "candidate_payloads_extracted", payload_count_int)
        else:
            audit_failed(audit, "payload_missing", "candidate_payloads_extracted", payload_count_int)
        if isinstance(report, dict):
            audit_existing_path(audit, "clone_recipe_payloads_csv_exists", report.get("payloads_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_payload_mutations_csv_exists", report.get("payload_mutations_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_side_effect_summary_csv_exists", report.get("side_effect_summary_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_payload_signals_csv_exists", report.get("payload_signals_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_negative_controls_csv_exists", report.get("negative_controls_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_gates_csv_exists", report.get("gates_csv"), nonempty=True)
            audit_existing_path(audit, "clone_recipe_payload_directory_exists", report.get("payload_directory"), directory=True)

    return finalize_audit(audit, policy)


def audit_native_low_level_patch(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    audit = audit_generic_result(tool_name, payload, policy)
    audit_existing_path(audit, "patch_report_exists", payload.get("report_path"), nonempty=True)
    report = payload.get("report")
    if not isinstance(report, dict):
        audit_failed(audit, "report_missing", "patch_report_loaded")
        return finalize_audit(audit, policy)
    audit_passed(audit, "patch_report_loaded", payload.get("report_path"))

    applied = bool(payload.get("applied"))
    audit_patch_report_integrity(audit, report, applied=applied)
    if applied:
        audit_failed(
            audit,
            "runtime_validation_missing",
            "petrel_runtime_validation_present",
            "Low-level native patch was applied; run a patch-run-restore wrapper or Petrel validation before treating it as complete.",
        )
    else:
        audit_skipped(audit, "petrel_runtime_validation_present", "dry-run patch check only")

    return finalize_audit(audit, policy)


def audit_native_patch_run_restore(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    audit = audit_generic_result(tool_name, payload, policy)
    report = payload.get("report")
    if not isinstance(report, dict):
        audit_failed(audit, "report_missing", "runner_report_loaded", payload.get("report_path") or "")
        return finalize_audit(audit, policy)
    audit_passed(audit, "runner_report_loaded", payload.get("report_path") or "")

    report_status = str(report.get("status") or "").lower()
    if report_status == "passed":
        audit_passed(audit, "runner_report_status_passed", report_status)
    else:
        audit_failed(audit, "runner_failed", "runner_report_status_passed", report_status)

    if bool(report.get("patch_applied")):
        audit_passed(audit, "patch_applied")
    else:
        audit_failed(audit, "patch_not_applied", "patch_applied")

    audit_existing_path(audit, "before_snapshot_exists", report.get("before_snapshot"), directory=True)
    audit_existing_path(audit, "after_patch_snapshot_exists", report.get("after_patch_snapshot"), directory=True)
    audit_existing_path(audit, "patch_report_exists", report.get("patch_report"), nonempty=True)

    patch_compare_has_change, patch_compare_detail = compare_report_has_change(report.get("patch_compare_report"))
    if patch_compare_has_change:
        audit_passed(audit, "patch_compare_changed_store", patch_compare_detail)
    else:
        audit_failed(audit, "patch_compare_missing", "patch_compare_changed_store", patch_compare_detail)

    keep_patch = bool(report.get("keep_patch"))
    if keep_patch:
        audit_skipped(audit, "restore_clean", "keep_patch=true; native store intentionally left patched")
    else:
        if bool(report.get("restored")):
            audit_passed(audit, "restore_reported")
        else:
            audit_failed(audit, "restore_failed", "restore_reported")
        audit_existing_path(audit, "restore_report_exists", report.get("restore_report"), nonempty=True)
        audit_existing_path(audit, "after_restore_snapshot_exists", report.get("after_restore_snapshot"), directory=True)
        clean_value = report.get("restore_compare_clean")
        if clean_value is True:
            audit_passed(audit, "restore_clean", {"restore_compare_clean": True})
        else:
            clean, detail = compare_report_is_clean(report.get("restore_compare_report"))
            if clean:
                audit_passed(audit, "restore_clean", detail)
            else:
                audit_failed(audit, "restore_dirty", "restore_clean", detail)

    skip_run = bool(report.get("skip_run"))
    if skip_run:
        audit_skipped(audit, "petrel_workflow_confirmed", "skip_run=true")
        audit_validation_summary(audit, report.get("validation"), required=False)
        return finalize_audit(audit, policy)

    petrel_status = report.get("petrel_status")
    if isinstance(petrel_status, dict) and petrel_status.get("workflow_execution_status") == "confirmed":
        audit_passed(audit, "petrel_workflow_confirmed", report.get("petrel_status_path") or petrel_status.get("_status_path"))
    else:
        audit_failed(audit, "workflow_not_confirmed", "petrel_workflow_confirmed", petrel_status)

    if isinstance(petrel_status, dict) and str(petrel_status.get("validation_status") or "").lower() in {"passed", "skipped"}:
        audit_passed(audit, "petrel_status_validation_ok", petrel_status.get("validation_status"))
    else:
        audit_failed(audit, "validation_failed", "petrel_status_validation_ok", petrel_status)

    if tool_name in {"petrel_export_segy_filename_patch", "petrel_export_segy_token_patch"}:
        target_output = report.get("target_output")
        if isinstance(target_output, dict) and int(target_output.get("length_bytes") or 0) > 0:
            audit_passed(audit, "target_output_recorded_nonempty", target_output)
            audit_existing_path(audit, "target_output_exists_nonempty", target_output.get("path") or report.get("target_output_file"), nonempty=True)
        else:
            audit_failed(audit, "output_missing", "target_output_recorded_nonempty", target_output)
    elif tool_name == "petrel_export_systemcmd_token_patch":
        bridge_status = report.get("bridge_status")
        target_step = str(report.get("target_bridge_step_name") or "")
        actual_step = str(nested_get(report, ["bridge_status", "step_name"]) or "")
        if isinstance(bridge_status, dict) and target_step and actual_step == target_step:
            audit_passed(audit, "bridge_step_name_matched", {"target": target_step, "actual": actual_step})
        else:
            audit_failed(audit, "bridge_not_confirmed", "bridge_step_name_matched", {"target": target_step, "actual": actual_step})
        if isinstance(bridge_status, dict) and str(bridge_status.get("validation_status") or "").lower() in {"passed", "skipped"}:
            audit_passed(audit, "bridge_validation_ok", bridge_status.get("validation_status"))
        else:
            audit_failed(audit, "bridge_validation_failed", "bridge_validation_ok", bridge_status)
        audit_existing_path(audit, "bridge_probe_exists", report.get("bridge_probe_path"), nonempty=True)

    audit_validation_summary(audit, report.get("validation"), required=not bool(report.get("no_validate")))
    return finalize_audit(audit, policy)


def audit_tool_payload(tool_name: str, payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "petrel_run_deterministic_gui_workflow":
        return audit_deterministic_gui_workflow(tool_name, payload, policy)
    if tool_name in {
        "petrel_native_map_workflow",
        "petrel_native_snapshot",
        "petrel_native_compare_snapshots",
        "petrel_analyze_exportseismiccmd_records",
        "petrel_analyze_systemcmd_records",
        "petrel_analyze_workflow_command_clone_readiness",
        "petrel_analyze_workflow_clone_side_effects",
        "petrel_analyze_workflow_clone_storage_blocks",
        "petrel_extract_workflow_command_clone_recipe",
    }:
        return audit_native_read_only(tool_name, payload, policy)
    if tool_name in {"petrel_native_patch_string", "petrel_native_patch_offset"}:
        return audit_native_low_level_patch(tool_name, payload, policy)
    if tool_name in {
        "petrel_export_segy_filename_patch",
        "petrel_export_segy_token_patch",
        "petrel_export_systemcmd_token_patch",
    }:
        return audit_native_patch_run_restore(tool_name, payload, policy)
    return audit_generic_result(tool_name, payload, policy)


def annotate_tool_response(tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    try:
        content = result.get("content")
        if not isinstance(content, list) or not content:
            return result
        first = content[0]
        if not isinstance(first, dict) or first.get("type") != "text":
            return result
        payload = json.loads(str(first.get("text") or "{}"))
        if not isinstance(payload, dict):
            return result
        policy = failure_policy_summary(tool_name)
        payload.setdefault("mcp_failure_policy", policy)
        payload.setdefault("mcp_result_audit", audit_tool_payload(tool_name, payload, policy))
        first["text"] = json.dumps(payload, indent=2, ensure_ascii=False)
    except Exception:
        return result
    return result


def read_manifest(export_package: Path) -> list[dict[str, str]]:
    manifest = export_package / "00_manifest" / "export_manifest.csv"
    if not manifest.exists():
        return []
    with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def summarize_manifest(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in rows:
        source_type = row.get("source_object_type") or "(blank)"
        status = row.get("validation_status") or "(blank)"
        by_type[source_type] = by_type.get(source_type, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "row_count": len(rows),
        "by_source_object_type": by_type,
        "by_validation_status": by_status,
        "rows": rows,
    }


def summarize_manifest_counts(rows: list[dict[str, str]]) -> dict[str, Any]:
    summary = summarize_manifest(rows)
    summary.pop("rows", None)
    return summary


def count_domain_files(export_package: Path) -> dict[str, int]:
    folders = [
        "02_wells",
        "03_seismic",
        "04_surfaces_maps",
        "05_interpretation",
        "06_models_properties",
        "07_workflows_reports",
        "08_native_project",
    ]
    counts: dict[str, int] = {}
    for folder in folders:
        root = export_package / folder
        if not root.exists():
            counts[folder] = 0
            continue
        counts[folder] = sum(1 for item in root.rglob("*") if item.is_file())
    return counts


def latest_status(export_package: Path) -> dict[str, Any] | None:
    run_dir = export_package / "07_workflows_reports" / "automation_runs"
    latest = latest_file(str(run_dir / "petrel_automation_*.json"))
    if latest is None:
        return None
    status = load_json(latest)
    status["_status_path"] = str(latest)
    return status


def latest_confirmed_workflow_status(export_package: Path) -> dict[str, Any] | None:
    run_dir = export_package / "07_workflows_reports" / "automation_runs"
    matches = [Path(item) for item in glob.glob(str(run_dir / "petrel_automation_*.json"))]
    for path in sorted(matches, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            status = load_json(path)
        except Exception:
            continue
        if status.get("workflow_execution_status") == "confirmed":
            status["_status_path"] = str(path)
            return status
    return None


def tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, ensure_ascii=False),
            }
        ]
    }


def require_string(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or value.strip() == "":
        raise McpError(f"Missing required string argument: {name}", code=-32602)
    return value


def string_list(value: Any, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        items = [item.strip() for item in value.replace(";", ",").split(",")]
        return [item for item in items if item]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return list(default or [])


def version_context(arguments: dict[str, Any]) -> dict[str, Any]:
    petrel_version = str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION)
    target_versions = string_list(arguments.get("target_versions"), [petrel_version])
    version_scope = str(arguments.get("version_scope") or DEFAULT_VERSION_SCOPE)
    return {
        "petrel_version": petrel_version,
        "target_versions": target_versions,
        "version_scope": version_scope,
        "cross_version_policy": "Treat retrieved notes and export results as version-scoped evidence; revalidate before applying to any Petrel version outside target_versions.",
    }


def run_kb_query(query: str, top_k: int) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "query_agent_index.py"),
        "--query",
        query,
        "--top-k",
        str(top_k),
    ]
    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
    return {
        "query": query,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def tool_petrel_status(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = resolve_existing_path(as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE), "Export package")
    rows = read_manifest(export_package)
    include_manifest_rows = bool(arguments.get("include_manifest_rows"))
    raw_rows_limit = arguments.get("manifest_rows_limit")
    manifest_rows_limit = DEFAULT_MANIFEST_ROWS_PREVIEW if raw_rows_limit is None else max(0, int(raw_rows_limit))
    if include_manifest_rows:
        manifest_summary = summarize_manifest(rows)
    else:
        manifest_summary = summarize_manifest_counts(rows)
        preview = rows[:manifest_rows_limit]
        manifest_summary["rows_preview"] = preview
        manifest_summary["rows_omitted"] = len(rows) - len(preview)
        manifest_summary["rows_note"] = (
            "Row list truncated to keep this agent-facing summary compact; "
            "pass include_manifest_rows=true for the full row list."
        )
    status = latest_status(export_package)
    confirmed_workflow_status = latest_confirmed_workflow_status(export_package)
    source_types = {row.get("source_object_type") or "" for row in rows}
    semantic_source_types = {
        "fault_metadata",
        "horizon_metadata",
        "zone_metadata",
        "structural_framework_metadata",
        "native_gms_property_metadata",
        "seismic_metadata",
        "sqlite_metadata",
        "native_xml_metadata",
        "native_semantic_report",
    }
    payload = {
        "repo_root": str(REPO_ROOT),
        "version_context": version_context(arguments),
        "export_package": str(export_package),
        "latest_status": status,
        "latest_confirmed_workflow_status": confirmed_workflow_status,
        "manifest": manifest_summary,
        "domain_file_counts": count_domain_files(export_package),
        "readiness": {
            "no_ocean_path": True,
            "mvp_runner_available": (REPO_ROOT / "scripts" / "run_petrel_full_export_mvp.ps1").exists(),
            "workflow_bridge_validated": bool(confirmed_workflow_status),
            "zero_gui_native_export_ready": "petrel_native_store" in source_types,
            "zero_gui_semantic_export_ready": bool(source_types.intersection(semantic_source_types)),
            "first_real_export_ready": bool(source_types.intersection({"well", "well_log", "surface", "seismic_cube", "model_grid"})),
            "full_geological_export_ready": {"well", "well_log", "surface", "seismic_cube", "model_grid"}.issubset(source_types),
        },
    }
    return tool_result(payload)


def tool_prepare_mvp(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    workflow_name = str(arguments.get("workflow_name") or DEFAULT_WORKFLOW_NAME)
    result = run_powershell_script(
        "build_petrel_full_export_mvp.ps1",
        [
            "-ProjectName",
            str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
            "-ExportPackage",
            str(export_package),
            "-InventoryPackage",
            str(inventory_package),
            "-WorkflowName",
            workflow_name,
        ],
        timeout_seconds=int(arguments.get("timeout_seconds") or 300),
    )
    return tool_result({"operation": "prepare_mvp", **result})


def tool_run_mvp(arguments: dict[str, Any]) -> dict[str, Any]:
    args = [
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-WorkflowName",
        str(arguments.get("workflow_name") or DEFAULT_WORKFLOW_NAME),
        "-LicensePackage",
        str(arguments.get("license_package") or "BatchProfile"),
    ]
    export_package = arguments.get("export_package")
    inventory_package = arguments.get("inventory_package")
    if export_package:
        args += ["-ExportPackage", str(as_path(export_package, DEFAULT_EXPORT_PACKAGE))]
    if inventory_package:
        args += ["-InventoryPackage", str(as_path(inventory_package, DEFAULT_INVENTORY_PACKAGE))]
    # Safe-by-default as of 0.7.0: a missing dry_run means dry-run. A live Petrel run
    # requires an explicit dry_run=false from the caller.
    raw_dry_run = arguments.get("dry_run")
    dry_run = True if raw_dry_run is None else bool(raw_dry_run)
    args += ps_bool(bool(arguments.get("validate_only")), "ValidateOnly")
    args += ps_bool(dry_run, "DryRun")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "run_petrel_full_export_mvp.ps1",
        args,
        timeout_seconds=int(arguments.get("timeout_seconds") or 3600),
    )
    return tool_result({"operation": "run_mvp", "dry_run": dry_run, **result})


def tool_open_project(arguments: dict[str, Any]) -> dict[str, Any]:
    launch = bool(arguments.get("launch"))
    writable = bool(arguments.get("writable"))
    license_package = str(arguments.get("license_package") or "BatchProfile")
    args = [
        "-Mode",
        "OpenProject",
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-PetrelOptionStyle",
        str(arguments.get("petrel_option_style") or "Slash"),
        "-LicensePackage",
        license_package,
    ]
    if writable:
        args += ["-OpenProjectWritable"]
    if not launch:
        args += ["-DryRun"]
    if bool(arguments.get("wait")):
        args += ["-Wait"]
    result = run_powershell_script(
        "invoke_petrel_export_pilot.ps1",
        args,
        timeout_seconds=int(arguments.get("timeout_seconds") or 300),
    )
    return tool_result(
        {
            "operation": "open_project",
            "launch": launch,
            "writable": writable,
            "license_package": license_package,
            **result,
        }
    )


def tool_export_well_logs_ui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-ProjectPath",
        str(as_path(arguments.get("project_path"), DEFAULT_PROJECT_FILE.parent)),
        "-InventoryPackage",
        str(inventory_package),
        "-ExportPackage",
        str(export_package),
        "-LicenseProfile",
        str(arguments.get("license_profile") or "BatchProfile"),
        "-LicensePackage",
        str(arguments.get("license_package") or arguments.get("license_profile") or "BatchProfile"),
        "-PetrelOptionStyle",
        str(arguments.get("petrel_option_style") or "Slash"),
        "-TargetSubfolder",
        str(arguments.get("target_subfolder") or "02_wells\\well_logs_las"),
        "-Extension",
        str(arguments.get("extension") or "las"),
        "-DriveLetter",
        str(arguments.get("drive_letter") or "P"),
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    petrel_process_id = arguments.get("petrel_process_id")
    if petrel_process_id:
        args += ["-PetrelProcessId", str(int(petrel_process_id))]
    args += ps_bool(bool(arguments.get("open_project_writable")), "OpenProjectWritable")
    args += ps_bool(bool(arguments.get("allow_existing_target")), "AllowExistingTarget")
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")
    args += ps_bool(bool(arguments.get("keep_drive_mapping")), "KeepDriveMapping")

    result = run_powershell_script(
        "export_petrel_well_logs_ui.ps1",
        args,
        timeout_seconds=timeout_seconds + 180,
    )
    payload: dict[str, Any] = {"operation": "export_well_logs_ui", **result}
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_well_tops_ui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    coordinate_fallback = arguments.get("coordinate_fallback")
    if coordinate_fallback is None:
        coordinate_fallback = False
    preflight, failures = build_dependency_preflight(
        arguments,
        require_tesseract=not bool(coordinate_fallback),
    )
    if failures:
        return dependency_preflight_failed("export_well_tops_ui", preflight, failures)
    resolved_tesseract_path = preflight_tesseract_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-ProjectPath",
        str(as_path(arguments.get("project_path"), DEFAULT_PROJECT_FILE.parent)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-InventoryPackage",
        str(inventory_package),
        "-ExportPackage",
        str(export_package),
        "-LicenseProfile",
        str(arguments.get("license_profile") or "BatchProfile"),
        "-LicensePackage",
        str(arguments.get("license_package") or arguments.get("license_profile") or "BatchProfile"),
        "-PetrelOptionStyle",
        str(arguments.get("petrel_option_style") or "Slash"),
        "-TargetSubfolder",
        str(arguments.get("target_subfolder") or "02_wells\\well_tops"),
        "-Extension",
        str(arguments.get("extension") or "txt"),
        "-FormatPattern",
        str(arguments.get("format_pattern") or "Petrel.*well.*tops.*ASCII|Well Tops.*ASCII"),
        "-DriveLetter",
        str(arguments.get("drive_letter") or "P"),
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    if resolved_tesseract_path:
        args += ["-TesseractPath", resolved_tesseract_path]
    petrel_process_id = arguments.get("petrel_process_id")
    if petrel_process_id:
        args += ["-PetrelProcessId", str(int(petrel_process_id))]
    output_file_name = str(arguments.get("output_file_name") or "")
    if output_file_name:
        args += ["-OutputFileName", output_file_name]
    args += ps_bool(bool(arguments.get("open_project_writable")), "OpenProjectWritable")
    args += ps_bool(bool(arguments.get("allow_existing_target")), "AllowExistingTarget")
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")
    args += ps_bool(bool(arguments.get("keep_drive_mapping")), "KeepDriveMapping")
    args += ps_bool(bool(coordinate_fallback), "CoordinateFallback")

    result = run_powershell_script(
        "export_petrel_well_tops_ui.ps1",
        args,
        timeout_seconds=timeout_seconds + 180,
    )
    payload: dict[str, Any] = {"operation": "export_well_tops_ui", "preflight": preflight, **result}
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_run_deterministic_gui_workflow(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    execute = bool(arguments.get("execute"))
    coordinate_fallback = arguments.get("coordinate_fallback")
    if coordinate_fallback is None:
        coordinate_fallback = False
    preflight, failures = build_dependency_preflight(
        arguments,
        require_python=execute and not bool(arguments.get("skip_import")),
        require_tesseract=execute and not bool(coordinate_fallback),
    )
    if failures:
        return dependency_preflight_failed("run_deterministic_gui_workflow", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    resolved_tesseract_path = preflight_tesseract_path(preflight)
    args = [
        "-WorkflowId",
        str(arguments.get("workflow_id") or "export_well_tops_ascii"),
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-ProjectPath",
        str(as_path(arguments.get("project_path"), DEFAULT_PROJECT_FILE.parent)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-InventoryPackage",
        str(inventory_package),
        "-ExportPackage",
        str(export_package),
        "-LicenseProfile",
        str(arguments.get("license_profile") or "BatchProfile"),
        "-LicensePackage",
        str(arguments.get("license_package") or arguments.get("license_profile") or "BatchProfile"),
        "-PetrelOptionStyle",
        str(arguments.get("petrel_option_style") or "Slash"),
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    if resolved_python_path:
        args += ["-PythonPath", resolved_python_path]
    spec_path = arguments.get("spec_path")
    if spec_path:
        args += ["-SpecPath", str(as_path(str(spec_path), REPO_ROOT))]
    for source_name, switch_name in [
        ("license_dialog_timeout_seconds", "LicenseDialogTimeoutSeconds"),
        ("stable_file_ticks", "StableFileTicks"),
        ("file_poll_seconds", "FilePollSeconds"),
        ("well_tops_relative_x", "WellTopsRelativeX"),
        ("well_tops_relative_y", "WellTopsRelativeY"),
        ("export_object_relative_x", "ExportObjectRelativeX"),
        ("export_object_relative_y", "ExportObjectRelativeY"),
    ]:
        value = arguments.get(source_name)
        if value is not None:
            args += [f"-{switch_name}", str(int(value))]
    petrel_process_id = arguments.get("petrel_process_id")
    if petrel_process_id:
        args += ["-PetrelProcessId", str(int(petrel_process_id))]
    for source_name, switch_name in [
        ("execute", "Execute"),
        ("open_project_writable", "OpenProjectWritable"),
        ("allow_existing_target", "AllowExistingTarget"),
        ("no_register", "NoRegister"),
        ("no_validate", "NoValidate"),
        ("keep_drive_mapping", "KeepDriveMapping"),
        ("coordinate_fallback", "CoordinateFallback"),
        ("context_menu_keyboard", "ContextMenuKeyboard"),
        ("skip_import", "SkipImport"),
    ]:
        args += ps_bool(bool(arguments.get(source_name)), switch_name)
    for source_name, switch_name in [
        ("target_subfolder", "TargetSubfolder"),
        ("extension", "Extension"),
        ("output_file_name", "OutputFileName"),
        ("format_pattern", "FormatPattern"),
        ("drive_letter", "DriveLetter"),
    ]:
        value = arguments.get(source_name)
        if value:
            args += [f"-{switch_name}", str(value)]
    tesseract_arg = resolved_tesseract_path or str(arguments.get("tesseract_path") or "")
    if tesseract_arg:
        args += ["-TesseractPath", tesseract_arg]

    result = run_powershell_script(
        "invoke_petrel_deterministic_gui_workflow.ps1",
        args,
        timeout_seconds=timeout_seconds + (900 if bool(arguments.get("execute")) else 120),
    )
    report_path_value = stdout_labeled_value(result.get("stdout", ""), "Report")
    report = None
    if report_path_value:
        report_path = Path(report_path_value)
        if report_path.exists():
            report = load_json(report_path)
    payload: dict[str, Any] = {
        "operation": "run_deterministic_gui_workflow",
            "execute": execute,
            "preflight": preflight,
        **result,
        "report_path": report_path_value,
        "report": report,
    }
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_native_zero_gui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 1800)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-MaxTextProbeBytes",
        str(int(arguments.get("max_text_probe_bytes") or 10485760)),
        "-MaxCandidatesPerFile",
        str(int(arguments.get("max_candidates_per_file") or 200)),
    ]
    if arguments.get("project_path"):
        args += ["-ProjectPath", str(as_path(arguments.get("project_path"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("export_root"):
        args += ["-ExportRoot", str(as_path(arguments.get("export_root"), REPO_ROOT / "build" / "export_pilots"))]
    args += ps_bool(bool(arguments.get("create_new_package")), "CreateNewPackage")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "export_petrel_native_project_zero_gui.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_native_zero_gui", **result}
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_run_zero_gui_mvp(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 2400)
    preflight, failures = build_dependency_preflight(
        arguments,
        require_python=not bool(arguments.get("skip_semantic_extraction")),
    )
    if failures:
        return dependency_preflight_failed("run_zero_gui_export_mvp", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-InventoryPackage",
        str(inventory_package),
        "-ExportPackage",
        str(export_package),
        "-WorkflowName",
        str(arguments.get("workflow_name") or DEFAULT_WORKFLOW_NAME),
        "-MaxTextProbeBytes",
        str(int(arguments.get("max_text_probe_bytes") or 10485760)),
        "-MaxCandidatesPerFile",
        str(int(arguments.get("max_candidates_per_file") or 200)),
    ]
    if resolved_python_path:
        args += ["-PythonPath", resolved_python_path]
    args += ps_bool(bool(arguments.get("create_new_package")), "CreateNewPackage")
    args += ps_bool(bool(arguments.get("skip_semantic_extraction")), "SkipSemanticExtraction")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "run_petrel_zero_gui_export_mvp.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "run_zero_gui_mvp", "preflight": preflight, **result}
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_native_semantic_zero_gui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("export_native_semantic_zero_gui", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-MaxXmlNames",
        str(int(arguments.get("max_xml_names") or 20)),
    ]
    args += ["-PythonPath", resolved_python_path]
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "export_petrel_native_semantic_zero_gui.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_native_semantic_zero_gui", "preflight": preflight, **result}
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_well_tables_zero_gui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("export_well_tables_zero_gui", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-MaxNativeXmlRows",
        str(int(arguments.get("max_native_xml_rows") or 200)),
        "-PythonPath",
        resolved_python_path,
    ]
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "export_petrel_well_tables_zero_gui.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_well_tables_zero_gui", "preflight": preflight, **result}
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_surfaces_zero_gui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("export_surfaces_zero_gui", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-PythonPath",
        resolved_python_path,
    ]
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "export_petrel_surfaces_zero_gui.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_surfaces_zero_gui", "preflight": preflight, **result}
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_export_seismic_zgy_zero_gui(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("export_seismic_zgy_zero_gui", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-PythonPath",
        resolved_python_path,
    ]
    args += ps_bool(bool(arguments.get("export_volume")), "ExportVolume")
    args += ps_bool(bool(arguments.get("no_slices")), "NoSlices")
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "export_petrel_seismic_zgy_zero_gui.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_seismic_zgy_zero_gui", "preflight": preflight, **result}
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_survey_geometry(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    segy_arg = str(arguments.get("segy_path") or "03_seismic\\segy\\orig_amp_exportpilot_donor.sgy")
    segy = Path(segy_arg)
    if not segy.is_absolute():
        segy = export_package / segy_arg
    payload: dict[str, Any] = {"operation": "survey_geometry", "segy_path": str(segy)}
    if not segy.exists():
        payload["status"] = "failed"
        payload["error"] = "SEG-Y file not found; export a donor SEG-Y first or pass segy_path."
        return tool_result(payload)

    with open(segy, "rb") as handle:
        handle.seek(3220)
        samples_per_trace = struct.unpack(">H", handle.read(2))[0]
        trace_len = 240 + samples_per_trace * 4
        trace_count = (segy.stat().st_size - 3600) // trace_len

        def trace_header(index: int) -> tuple[int, int, int, int]:
            handle.seek(3600 + index * trace_len)
            raw = handle.read(240)
            g4 = lambda pos: struct.unpack_from(">i", raw, pos - 1)[0]
            return g4(189), g4(193), g4(181), g4(185)

        il0, xl0, x0, y0 = trace_header(0)
        xlines_per_inline = None
        for index in range(1, min(int(trace_count), 5000)):
            if trace_header(index)[0] != il0:
                xlines_per_inline = index
                break
        if xlines_per_inline is None:
            payload["status"] = "failed"
            payload["error"] = "Could not determine xlines-per-inline from trace headers."
            return tool_result(payload)
        il1, xl1, x1, y1 = trace_header(xlines_per_inline - 1)
        il2, xl2, x2, y2 = trace_header((int(trace_count) // xlines_per_inline - 1) * xlines_per_inline)
        il3, xl3, x3, y3 = trace_header(int(trace_count) - 1)

    xline_unit = ((x1 - x0) / (xl1 - xl0), (y1 - y0) / (xl1 - xl0))
    inline_unit = ((x2 - x0) / (il2 - il0), (y2 - y0) / (il2 - il0))
    payload.update(
        {
            "status": "passed",
            "samples_per_trace": samples_per_trace,
            "trace_count": int(trace_count),
            "xlines_per_inline": xlines_per_inline,
            "inline_range": [il0, il2],
            "xline_range": [xl0, xl1],
            "corners": {
                "origin": {"inline": il0, "xline": xl0, "x": x0, "y": y0},
                "xline_end": {"inline": il1, "xline": xl1, "x": x1, "y": y1},
                "inline_end": {"inline": il2, "xline": xl2, "x": x2, "y": y2},
                "far": {"inline": il3, "xline": xl3, "x": x3, "y": y3},
            },
            "xline_unit_vector": [round(xline_unit[0], 6), round(xline_unit[1], 6)],
            "inline_unit_vector": [round(inline_unit[0], 6), round(inline_unit[1], 6)],
            "rotation_deg": round(math.degrees(math.atan2(xline_unit[1], xline_unit[0])), 4),
            "bin_size_m": {
                "xline_step": round(math.hypot(*xline_unit) * 2, 4),
                "inline_step": round(math.hypot(*inline_unit) * 2, 4),
            },
            "surface_lattice_note": "Surface .zhz grids sit on this survey's cell centers: node(i, j) = origin + xline_unit*(2i+1) + inline_unit*(2j+1).",
        }
    )
    crs_sidecar = Path(str(segy) + ".crsmeta.xml")
    if crs_sidecar.exists():
        try:
            import xml.etree.ElementTree as ElementTree

            texts: dict[str, str] = {}
            for element in ElementTree.parse(crs_sidecar).getroot().iter():
                tag = element.tag.split("}")[-1]
                if element.text and element.text.strip() and tag not in texts:
                    texts[tag] = element.text.strip()[:160]
            payload["crs_sidecar"] = {"path": str(crs_sidecar), **dict(list(texts.items())[:12])}
        except Exception as exc:
            payload["crs_sidecar"] = {"path": str(crs_sidecar), "parse_error": str(exc)}
    return tool_result(payload)


def tool_grid_convert(arguments: dict[str, Any]) -> dict[str, Any]:
    input_path = require_string(arguments, "input_path")
    output_path = require_string(arguments, "output_path")
    script_args = ["--input", input_path, "--output", output_path]
    for key, flag in (("input_format", "--input-format"), ("output_format", "--output-format")):
        value = arguments.get(key)
        if value:
            script_args += [flag, str(value)]
    return run_python_chain_tool("grid_convert", "convert_petrel_grid.py", arguments, script_args)


def run_python_chain_tool(operation: str, script_name: str, arguments: dict[str, Any], script_args: list[str], timeout_default: int = 300) -> dict[str, Any]:
    """Shared runner for small python chain tools that print a SummaryJson line."""
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed(operation, preflight, failures)
    command = [preflight_python_path(preflight), str(REPO_ROOT / "scripts" / script_name), *script_args]
    proc = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=int(arguments.get("timeout_seconds") or timeout_default),
    )
    payload: dict[str, Any] = {
        "operation": operation,
        "preflight": preflight,
        "command": command,
        "exit_code": proc.returncode,
        "stderr": proc.stderr.strip()[-2000:],
    }
    for line in proc.stdout.splitlines():
        if line.startswith("SummaryJson:"):
            try:
                payload["report"] = json.loads(line[len("SummaryJson:"):])
                payload["status"] = payload["report"].get("status")
            except json.JSONDecodeError:
                payload["stdout"] = proc.stdout.strip()[-2000:]
            break
    else:
        payload["stdout"] = proc.stdout.strip()[-2000:]
    if proc.returncode != 0 and "status" not in payload:
        payload["status"] = "failed"
    return tool_result(payload)


def tool_write_well_tops_ascii(arguments: dict[str, Any]) -> dict[str, Any]:
    input_csv = require_string(arguments, "input_csv")
    output_path = require_string(arguments, "output_path")
    args = ["--input-csv", input_csv, "--output", output_path]
    if arguments.get("no_verify"):
        args.append("--no-verify")
    return run_python_chain_tool("write_well_tops_ascii", "write_petrel_well_tops_ascii.py", arguments, args)


def tool_las_convert(arguments: dict[str, Any]) -> dict[str, Any]:
    input_path = require_string(arguments, "input_path")
    output_path = require_string(arguments, "output_path")
    return run_python_chain_tool("las_convert", "convert_petrel_las.py", arguments, ["--input", input_path, "--output", output_path])


def tool_project_audit_report(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 600)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("project_audit_report", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-PythonPath",
        resolved_python_path,
    ]
    title = arguments.get("title")
    if title:
        args += ["-Title", str(title)]
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "report_petrel_project_audit.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "project_audit_report", "preflight": preflight, **result}
    for line in str(result.get("stdout", "")).splitlines():
        if line.startswith("SummaryJson:"):
            try:
                payload["report"] = json.loads(line[len("SummaryJson:"):])
                payload["status"] = payload["report"].get("status")
            except json.JSONDecodeError:
                pass
            break
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
    return tool_result(payload)


def tool_export_well_tops_native_probe(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("export_well_tops_native_probe", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-ProjectName",
        str(arguments.get("project_name") or DEFAULT_PROJECT_NAME),
        "-ProjectFile",
        str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE)),
        "-PetrelVersion",
        str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION),
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
        "-PythonPath",
        resolved_python_path,
    ]
    args += ps_bool(bool(arguments.get("no_register")), "NoRegister")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")
    source_well_tops_file = arguments.get("source_well_tops_file")
    if source_well_tops_file:
        args += ["-SourceWellTopsFile", str(source_well_tops_file)]

    result = run_powershell_script(
        "export_petrel_well_tops_native_probe.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {"operation": "export_well_tops_native_probe", "preflight": preflight, **result}
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    enrich_well_tops_native_probe_payload(payload, export_package)
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_import_gui_well_tops_table(arguments: dict[str, Any]) -> dict[str, Any]:
    gui_table_paste_value = arguments.get("gui_table_paste")
    if not gui_table_paste_value:
        raise McpError("gui_table_paste is required")
    gui_table_paste = resolve_existing_path(as_path(str(gui_table_paste_value), REPO_ROOT), "GUI table paste")
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    project_name = str(arguments.get("project_name") or DEFAULT_PROJECT_NAME)
    petrel_version = str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION)
    timeout_seconds = int(arguments.get("timeout_seconds") or 900)
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("import_gui_well_tops_table", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-GuiTablePaste",
        str(gui_table_paste),
        "-ProjectName",
        project_name,
        "-PetrelVersion",
        petrel_version,
        "-ExportPackage",
        str(export_package),
        "-PythonPath",
        resolved_python_path,
        "-NumericTolerance",
        str(float(arguments.get("numeric_tolerance") or 0.05)),
    ]
    source_ascii_csv = arguments.get("source_ascii_csv")
    if source_ascii_csv:
        args += ["-SourceAsciiCsv", str(source_ascii_csv)]

    import_result = run_powershell_script(
        "import_petrel_gui_well_tops_table.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {
        "operation": "import_gui_well_tops_table",
        "preflight": preflight,
        "import_result": import_result,
    }
    report_path = stdout_labeled_value(import_result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)

    if not bool(arguments.get("no_register")):
        payload["registration_result"] = run_powershell_script(
            "register_petrel_file_exports.ps1",
            [
                "-ExportPackage",
                str(export_package),
                "-ProjectName",
                project_name,
                "-PetrelVersion",
                petrel_version,
                "-InventoryPackage",
                str(inventory_package),
            ],
            timeout_seconds=300,
        )
    if not bool(arguments.get("no_validate")):
        payload["validation_result"] = run_powershell_script(
            "validate_export_package.ps1",
            [
                "-ExportPackage",
                str(export_package),
                "-UpdateManifest",
                "-WriteChecksums",
            ],
            timeout_seconds=900,
        )
    if export_package.exists():
        payload["manifest"] = summarize_manifest_counts(read_manifest(export_package))
        payload["domain_file_counts"] = count_domain_files(export_package)
    return tool_result(payload)


def tool_register_and_validate(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = resolve_existing_path(as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE), "Export package")
    workflow_name = str(arguments.get("workflow_name") or DEFAULT_WORKFLOW_NAME)
    project_name = str(arguments.get("project_name") or DEFAULT_PROJECT_NAME)
    petrel_version = str(arguments.get("petrel_version") or DEFAULT_PETREL_VERSION)
    inventory_package = str(as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE))

    artifact = run_powershell_script(
        "register_petrel_workflow_artifacts.ps1",
        [
            "-ExportPackage",
            str(export_package),
            "-WorkflowName",
            workflow_name,
            "-ProjectName",
            project_name,
            "-PetrelVersion",
            petrel_version,
            "-InventoryPackage",
            inventory_package,
        ],
        timeout_seconds=300,
    )
    files = run_powershell_script(
        "register_petrel_file_exports.ps1",
        [
            "-ExportPackage",
            str(export_package),
            "-ProjectName",
            project_name,
            "-PetrelVersion",
            petrel_version,
            "-InventoryPackage",
            inventory_package,
        ],
        timeout_seconds=300,
    )
    validation = run_powershell_script(
        "validate_export_package.ps1",
        ["-ExportPackage", str(export_package), "-UpdateManifest", "-WriteChecksums"],
        timeout_seconds=300,
    )
    return tool_result(
        {
            "operation": "register_and_validate",
            "artifact_registration": artifact,
            "file_registration": files,
            "validation": validation,
            "manifest": summarize_manifest_counts(read_manifest(export_package)),
        }
    )


def tool_native_map(arguments: dict[str, Any]) -> dict[str, Any]:
    args = []
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if arguments.get("store_file"):
        args += ["-RelativeStoreFile", str(arguments["store_file"])]
    terms = arguments.get("terms")
    if isinstance(terms, list) and terms:
        args += ["-TermsCsv", "|".join(str(term) for term in terms)]
    if arguments.get("compare_store_file"):
        args += ["-CompareStoreFile", str(as_path(arguments.get("compare_store_file"), REPO_ROOT))]
    result = run_powershell_script(
        "map_petrel_native_workflow_regions.ps1",
        args,
        timeout_seconds=int(arguments.get("timeout_seconds") or 600),
    )
    payload: dict[str, Any] = {"operation": "native_map", **result}
    attach_labeled_path(payload, result.get("stdout", ""), "Summary", "summary_path")
    attach_labeled_path(payload, result.get("stdout", ""), "Term map", "term_map_path")
    return tool_result(payload)


def tool_native_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    args = []
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if arguments.get("label"):
        args += ["-Label", str(arguments["label"])]
    store_files = arguments.get("store_files")
    if isinstance(store_files, list) and store_files:
        args += ["-StoreFilesCsv", "|".join(str(item) for item in store_files)]
    if arguments.get("output_root"):
        args += ["-OutputRoot", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    result = run_powershell_script(
        "new_petrel_native_workflow_snapshot.ps1",
        args,
        timeout_seconds=int(arguments.get("timeout_seconds") or 300),
    )
    payload: dict[str, Any] = {"operation": "native_snapshot", **result}
    attach_labeled_path(payload, result.get("stdout", ""), "Snapshot", "snapshot_path")
    attach_labeled_path(payload, result.get("stdout", ""), "Manifest", "manifest_path", "manifest_report")
    attach_labeled_path(payload, result.get("stdout", ""), "Summary", "summary_path")
    return tool_result(payload)


def tool_native_compare_snapshots(arguments: dict[str, Any]) -> dict[str, Any]:
    before_snapshot = require_string(arguments, "before_snapshot")
    after_snapshot = require_string(arguments, "after_snapshot")
    preflight, failures = build_dependency_preflight(arguments, require_python=True)
    if failures:
        return dependency_preflight_failed("native_compare_snapshots", preflight, failures)
    resolved_python_path = preflight_python_path(preflight)
    args = [
        "-BeforeSnapshot",
        str(as_path(before_snapshot, REPO_ROOT)),
        "-AfterSnapshot",
        str(as_path(after_snapshot, REPO_ROOT)),
        "-PythonPath",
        resolved_python_path,
    ]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    store_files = arguments.get("store_files")
    if isinstance(store_files, list) and store_files:
        args += ["-StoreFilesCsv", "|".join(str(item) for item in store_files)]
    terms = arguments.get("terms")
    if isinstance(terms, list) and terms:
        args += ["-TermsCsv", "|".join(str(term) for term in terms)]
    if arguments.get("output_root"):
        args += ["-OutputRoot", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    result = run_powershell_script(
        "compare_petrel_native_workflow_snapshots.ps1",
        args,
        timeout_seconds=int(arguments.get("timeout_seconds") or 900),
    )
    payload: dict[str, Any] = {"operation": "native_compare_snapshots", "preflight": preflight, **result}
    attach_labeled_path(payload, result.get("stdout", ""), "Report", "report_path", "report")
    attach_labeled_path(payload, result.get("stdout", ""), "Summary", "summary_path")
    return tool_result(payload)


def tool_patch_string(arguments: dict[str, Any]) -> dict[str, Any]:
    search = require_string(arguments, "search")
    replace = require_string(arguments, "replace")
    apply = bool(arguments.get("apply"))
    args = [
        "-RelativeStoreFile",
        str(arguments.get("store_file") or "Model.ptd"),
        "-Search",
        search,
        "-Replace",
        replace,
    ]
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if bool(arguments.get("allow_multiple")):
        args += ["-AllowMultiple"]
    if not apply:
        args += ["-DryRun"]
    result = run_powershell_script("patch_petrel_native_workflow_string.ps1", args, timeout_seconds=300)
    payload: dict[str, Any] = {"operation": "native_patch_string", "applied": apply, **result}
    attach_labeled_path(payload, result.get("stdout", ""), "Report", "report_path", "report")
    return tool_result(payload)


def tool_patch_offset(arguments: dict[str, Any]) -> dict[str, Any]:
    offset = arguments.get("offset")
    if not isinstance(offset, int):
        raise McpError("Missing required integer argument: offset", code=-32602)
    expected = require_string(arguments, "expected")
    replace = require_string(arguments, "replace")
    apply = bool(arguments.get("apply"))
    args = [
        "-RelativeStoreFile",
        str(arguments.get("store_file") or "Data.ptd"),
        "-Offset",
        str(offset),
        "-Expected",
        expected,
        "-Replace",
        replace,
    ]
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if not apply:
        args += ["-DryRun"]
    result = run_powershell_script("patch_petrel_native_workflow_offset.ps1", args, timeout_seconds=300)
    payload: dict[str, Any] = {"operation": "native_patch_offset", "applied": apply, **result}
    attach_labeled_path(payload, result.get("stdout", ""), "Report", "report_path", "report")
    return tool_result(payload)


def tool_export_segy_filename_patch(arguments: dict[str, Any]) -> dict[str, Any]:
    replacement_tail = require_string(arguments, "replacement_tail")
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 4200)
    args = [
        "-ReplacementTail",
        replacement_tail,
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
    ]
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if arguments.get("project_file"):
        args += ["-ProjectFile", str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE))]
    if arguments.get("project_name"):
        args += ["-ProjectName", str(arguments["project_name"])]
    if arguments.get("petrel_version"):
        args += ["-PetrelVersion", str(arguments["petrel_version"])]
    if arguments.get("workflow_name"):
        args += ["-WorkflowName", str(arguments["workflow_name"])]
    if arguments.get("license_package"):
        args += ["-LicensePackage", str(arguments["license_package"])]
    if arguments.get("store_file"):
        args += ["-StoreFile", str(arguments["store_file"])]
    if arguments.get("offset") is not None:
        offset = arguments.get("offset")
        if not isinstance(offset, int):
            raise McpError("Argument offset must be an integer", code=-32602)
        args += ["-Offset", str(offset)]
    if arguments.get("expected_tail"):
        args += ["-ExpectedTail", str(arguments["expected_tail"])]
    if arguments.get("output_prefix"):
        args += ["-OutputPrefix", str(arguments["output_prefix"])]
    if arguments.get("output_subfolder"):
        args += ["-OutputSubfolder", str(arguments["output_subfolder"])]
    if arguments.get("output_root"):
        args += ["-OutputRoot", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    args += ps_bool(bool(arguments.get("keep_patch")), "KeepPatch")
    args += ps_bool(bool(arguments.get("skip_run")), "SkipRun")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "invoke_petrel_segy_filename_patch_export.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {
        "operation": "export_segy_filename_patch",
        "replacement_tail": replacement_tail,
        **result,
    }
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        rows = read_manifest(export_package)
        if bool(arguments.get("include_manifest_rows")):
            payload["manifest"] = summarize_manifest(rows)
        else:
            payload["manifest"] = summarize_manifest_counts(rows)
        payload["domain_file_counts"] = count_domain_files(export_package)
        payload["latest_status"] = latest_status(export_package)
    return tool_result(payload)


def tool_export_segy_token_patch(arguments: dict[str, Any]) -> dict[str, Any]:
    offset = arguments.get("offset")
    if not isinstance(offset, int):
        raise McpError("Missing required integer argument: offset", code=-32602)
    expected_token = require_string(arguments, "expected_token")
    replacement_token = require_string(arguments, "replacement_token")
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 4200)
    args = [
        "-Offset",
        str(offset),
        "-ExpectedToken",
        expected_token,
        "-ReplacementToken",
        replacement_token,
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
    ]
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if arguments.get("project_file"):
        args += ["-ProjectFile", str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE))]
    if arguments.get("project_name"):
        args += ["-ProjectName", str(arguments["project_name"])]
    if arguments.get("petrel_version"):
        args += ["-PetrelVersion", str(arguments["petrel_version"])]
    if arguments.get("workflow_name"):
        args += ["-WorkflowName", str(arguments["workflow_name"])]
    if arguments.get("license_package"):
        args += ["-LicensePackage", str(arguments["license_package"])]
    if arguments.get("store_file"):
        args += ["-StoreFile", str(arguments["store_file"])]
    if arguments.get("expected_output_file_name"):
        args += ["-ExpectedOutputFileName", str(arguments["expected_output_file_name"])]
    if arguments.get("target_output_file_name"):
        args += ["-TargetOutputFileName", str(arguments["target_output_file_name"])]
    if arguments.get("output_prefix"):
        args += ["-OutputPrefix", str(arguments["output_prefix"])]
    if arguments.get("output_subfolder"):
        args += ["-OutputSubfolder", str(arguments["output_subfolder"])]
    if arguments.get("output_root"):
        args += ["-OutputRoot", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    args += ps_bool(bool(arguments.get("keep_patch")), "KeepPatch")
    args += ps_bool(bool(arguments.get("skip_run")), "SkipRun")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "invoke_petrel_segy_token_patch_export.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {
        "operation": "export_segy_token_patch",
        "offset": offset,
        "expected_token": expected_token,
        "replacement_token": replacement_token,
        **result,
    }
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        rows = read_manifest(export_package)
        if bool(arguments.get("include_manifest_rows")):
            payload["manifest"] = summarize_manifest(rows)
        else:
            payload["manifest"] = summarize_manifest_counts(rows)
        payload["domain_file_counts"] = count_domain_files(export_package)
        payload["latest_status"] = latest_status(export_package)
    return tool_result(payload)


def tool_analyze_exportseismiccmd_records(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_petrel_exportseismiccmd_records.py"),
    ]
    if arguments.get("project_directory"):
        command += ["--project-directory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "analyze_exportseismiccmd_records",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for key in ("records", "token_hits", "model_hits"):
                    for row in data.get(key, []):
                        row.pop("context", None)
            payload["report"] = data
    return tool_result(payload)


def tool_analyze_workflow_command_clone_readiness(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_petrel_workflow_command_clone_readiness.py"),
    ]
    if arguments.get("project_directory"):
        command += ["--project-directory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("first_donor_compare_report"):
        command += ["--first-donor-compare-report", str(as_path(arguments.get("first_donor_compare_report"), REPO_ROOT))]
    if arguments.get("second_donor_compare_report"):
        command += ["--second-donor-compare-report", str(as_path(arguments.get("second_donor_compare_report"), REPO_ROOT))]
    if arguments.get("filename_patch_proof"):
        command += ["--filename-patch-proof", str(as_path(arguments.get("filename_patch_proof"), REPO_ROOT))]
    if arguments.get("token_patch_proof"):
        command += ["--token-patch-proof", str(as_path(arguments.get("token_patch_proof"), REPO_ROOT))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    if bool(arguments.get("include_context")):
        command += ["--include-context"]

    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "analyze_workflow_command_clone_readiness",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for row in data.get("records", []):
                    row.pop("context", None)
                for row in data.get("token_hits", []):
                    row.pop("context", None)
            payload["report"] = data
            readiness = data.get("readiness", {})
            if isinstance(readiness, dict):
                payload["clone_safe"] = readiness.get("clone_safe")
                payload["clone_status"] = readiness.get("status")
                payload["clone_blocker_count"] = readiness.get("blocker_count")
                payload["clone_failed_gate_count"] = readiness.get("failed_gate_count")
    return tool_result(payload)


def tool_analyze_workflow_clone_side_effects(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_petrel_workflow_clone_side_effects.py"),
    ]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("first_donor_compare_report"):
        command += ["--first-donor-compare-report", str(as_path(arguments.get("first_donor_compare_report"), REPO_ROOT))]
    if arguments.get("second_donor_compare_report"):
        command += ["--second-donor-compare-report", str(as_path(arguments.get("second_donor_compare_report"), REPO_ROOT))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    if bool(arguments.get("include_context")):
        command += ["--include-context"]

    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "analyze_workflow_clone_side_effects",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for compare_key in ("first_donor_compare", "second_donor_compare"):
                    compare = data.get(compare_key)
                    if isinstance(compare, dict):
                        for row_key in ("before_records", "after_records", "before_token_hits", "after_token_hits"):
                            rows = compare.get(row_key)
                            if isinstance(rows, list):
                                for row in rows:
                                    if isinstance(row, dict):
                                        row.pop("context", None)
            payload["report"] = data
            analysis = data.get("analysis", {})
            if isinstance(analysis, dict):
                payload["side_effects_isolated"] = analysis.get("side_effects_isolated")
                payload["clone_patch_precondition_satisfied"] = analysis.get("clone_patch_precondition_satisfied")
                payload["side_effect_status"] = analysis.get("status")
                payload["side_effect_blocker_count"] = analysis.get("blocker_count")
                payload["side_effect_failed_gate_count"] = analysis.get("failed_gate_count")
                payload["model_edit_likely_required"] = analysis.get("model_edit_likely_required")
                blocking_groups = analysis.get("blocking_groups")
                if isinstance(blocking_groups, list):
                    payload["blocking_group_count"] = len(blocking_groups)
                    payload["blocking_groups"] = blocking_groups
            side_effect_summary = data.get("side_effect_summary")
            if isinstance(side_effect_summary, list):
                payload["side_effect_class_count"] = len(side_effect_summary)
            required_actions = data.get("required_actions")
            if isinstance(required_actions, list):
                payload["required_action_count"] = len(required_actions)
            for key in ("ranges_csv", "summary_csv", "required_actions_csv", "gates_csv", "payloads_csv"):
                if data.get(key):
                    payload[key] = data.get(key)
    return tool_result(payload)


def tool_analyze_workflow_clone_storage_blocks(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_petrel_workflow_clone_storage_blocks.py"),
    ]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("first_donor_compare_report"):
        command += ["--first-donor-compare-report", str(as_path(arguments.get("first_donor_compare_report"), REPO_ROOT))]
    if arguments.get("second_donor_compare_report"):
        command += ["--second-donor-compare-report", str(as_path(arguments.get("second_donor_compare_report"), REPO_ROOT))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    if bool(arguments.get("include_context")):
        command += ["--include-context"]

    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "analyze_workflow_clone_storage_blocks",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for compare_key in ("first_donor_compare", "second_donor_compare"):
                    compare = data.get(compare_key)
                    if isinstance(compare, dict):
                        for row_key in ("before_records", "after_records", "before_token_hits", "after_token_hits"):
                            rows = compare.get(row_key)
                            if isinstance(rows, list):
                                for row in rows:
                                    if isinstance(row, dict):
                                        row.pop("context", None)
            payload["report"] = data
            analysis = data.get("analysis", {})
            if isinstance(analysis, dict):
                payload["storage_payload_separated"] = analysis.get("storage_payload_separated")
                payload["clone_patch_precondition_satisfied"] = analysis.get("clone_patch_precondition_satisfied")
                payload["storage_block_status"] = analysis.get("status")
                payload["storage_blocker_count"] = analysis.get("blocker_count")
                payload["storage_failed_gate_count"] = analysis.get("failed_gate_count")
                blocking_classes = analysis.get("blocking_segment_classes")
                if isinstance(blocking_classes, list):
                    payload["blocking_segment_class_count"] = len(blocking_classes)
                    payload["blocking_segment_classes"] = blocking_classes
            storage_block_segments = data.get("storage_block_segments")
            if isinstance(storage_block_segments, list):
                payload["storage_block_segment_count"] = len(storage_block_segments)
            storage_block_summary = data.get("storage_block_summary")
            if isinstance(storage_block_summary, list):
                payload["segment_class_count"] = len(storage_block_summary)
            required_actions = data.get("required_actions")
            if isinstance(required_actions, list):
                payload["required_action_count"] = len(required_actions)
            for key in (
                "segments_csv",
                "summary_csv",
                "required_actions_csv",
                "gates_csv",
                "payloads_csv",
                "source_ranges_csv",
            ):
                if data.get(key):
                    payload[key] = data.get(key)
    return tool_result(payload)


def tool_extract_workflow_command_clone_recipe(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "extract_petrel_workflow_command_clone_recipe.py"),
    ]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("first_donor_compare_report"):
        command += ["--first-donor-compare-report", str(as_path(arguments.get("first_donor_compare_report"), REPO_ROOT))]
    if arguments.get("second_donor_compare_report"):
        command += ["--second-donor-compare-report", str(as_path(arguments.get("second_donor_compare_report"), REPO_ROOT))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    if bool(arguments.get("include_context")):
        command += ["--include-context"]

    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "extract_workflow_command_clone_recipe",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for compare_key in ("first_donor_compare", "second_donor_compare"):
                    compare = data.get(compare_key)
                    if isinstance(compare, dict):
                        for row_key in ("before_records", "after_records", "before_token_hits", "after_token_hits"):
                            rows = compare.get(row_key)
                            if isinstance(rows, list):
                                for row in rows:
                                    if isinstance(row, dict):
                                        row.pop("context", None)
            payload["report"] = data
            recipe = data.get("recipe", {})
            if isinstance(recipe, dict):
                payload["recipe_safe_to_apply"] = recipe.get("recipe_safe_to_apply")
                payload["recipe_status"] = recipe.get("recipe_status")
                payload["recipe_blocker_count"] = recipe.get("blocker_count")
                payload["recipe_failed_gate_count"] = recipe.get("failed_gate_count")
            candidate_payloads = data.get("candidate_payloads")
            if isinstance(candidate_payloads, list):
                payload["candidate_payload_count"] = len(candidate_payloads)
            payload_mutations = data.get("payload_mutations")
            if isinstance(payload_mutations, list):
                payload["payload_mutation_count"] = len(payload_mutations)
            side_effect_summary = data.get("side_effect_summary")
            if isinstance(side_effect_summary, list):
                payload["side_effect_class_count"] = len(side_effect_summary)
            payload_signals = data.get("payload_signals")
            if isinstance(payload_signals, list):
                payload["payload_signal_count"] = len(payload_signals)
            negative_controls = data.get("negative_controls")
            if isinstance(negative_controls, list):
                payload["negative_control_count"] = len(negative_controls)
            for key in (
                "payloads_csv",
                "payload_mutations_csv",
                "side_effect_summary_csv",
                "payload_signals_csv",
                "negative_controls_csv",
                "gates_csv",
            ):
                if data.get(key):
                    payload[key] = data.get(key)
    return tool_result(payload)


def tool_export_systemcmd_token_patch(arguments: dict[str, Any]) -> dict[str, Any]:
    offset = arguments.get("offset")
    if not isinstance(offset, int):
        raise McpError("Missing required integer argument: offset", code=-32602)
    expected_token = require_string(arguments, "expected_token")
    replacement_token = require_string(arguments, "replacement_token")
    export_package = as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE)
    inventory_package = as_path(arguments.get("inventory_package"), DEFAULT_INVENTORY_PACKAGE)
    timeout_seconds = int(arguments.get("timeout_seconds") or 4200)
    args = [
        "-Offset",
        str(offset),
        "-ExpectedToken",
        expected_token,
        "-ReplacementToken",
        replacement_token,
        "-ExportPackage",
        str(export_package),
        "-InventoryPackage",
        str(inventory_package),
    ]
    if arguments.get("project_directory"):
        args += ["-ProjectDirectory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        args += ["-ProjectStem", str(arguments["project_stem"])]
    if arguments.get("project_file"):
        args += ["-ProjectFile", str(as_path(arguments.get("project_file"), DEFAULT_PROJECT_FILE))]
    if arguments.get("project_name"):
        args += ["-ProjectName", str(arguments["project_name"])]
    if arguments.get("petrel_version"):
        args += ["-PetrelVersion", str(arguments["petrel_version"])]
    if arguments.get("workflow_name"):
        args += ["-WorkflowName", str(arguments["workflow_name"])]
    if arguments.get("license_package"):
        args += ["-LicensePackage", str(arguments["license_package"])]
    if arguments.get("store_file"):
        args += ["-StoreFile", str(arguments["store_file"])]
    if arguments.get("expected_bridge_step_name"):
        args += ["-ExpectedBridgeStepName", str(arguments["expected_bridge_step_name"])]
    if arguments.get("target_bridge_step_name"):
        args += ["-TargetBridgeStepName", str(arguments["target_bridge_step_name"])]
    if arguments.get("output_root"):
        args += ["-OutputRoot", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    args += ps_bool(bool(arguments.get("keep_patch")), "KeepPatch")
    args += ps_bool(bool(arguments.get("skip_run")), "SkipRun")
    args += ps_bool(bool(arguments.get("no_validate")), "NoValidate")

    result = run_powershell_script(
        "invoke_petrel_systemcmd_token_patch_export.ps1",
        args,
        timeout_seconds=timeout_seconds,
    )
    payload: dict[str, Any] = {
        "operation": "export_systemcmd_token_patch",
        "offset": offset,
        "expected_token": expected_token,
        "replacement_token": replacement_token,
        **result,
    }
    report_path = stdout_labeled_value(result.get("stdout", ""), "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            payload["report"] = load_json(report)
    if export_package.exists():
        rows = read_manifest(export_package)
        if bool(arguments.get("include_manifest_rows")):
            payload["manifest"] = summarize_manifest(rows)
        else:
            payload["manifest"] = summarize_manifest_counts(rows)
        payload["domain_file_counts"] = count_domain_files(export_package)
        payload["latest_status"] = latest_status(export_package)
    return tool_result(payload)


def tool_analyze_systemcmd_records(arguments: dict[str, Any]) -> dict[str, Any]:
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "analyze_petrel_systemcmd_records.py"),
    ]
    if arguments.get("project_directory"):
        command += ["--project-directory", str(as_path(arguments.get("project_directory"), DEFAULT_PROJECT_FILE.parent))]
    if arguments.get("project_stem"):
        command += ["--project-stem", str(arguments["project_stem"])]
    if arguments.get("output_root"):
        command += ["--output-root", str(as_path(arguments.get("output_root"), REPO_ROOT / "build" / "native_edit_experiments"))]
    if arguments.get("terms"):
        command += ["--terms", str(arguments["terms"])]
    proc = subprocess.run(command, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    payload: dict[str, Any] = {
        "operation": "analyze_systemcmd_records",
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
    report_path = stdout_labeled_value(proc.stdout, "Report")
    if report_path:
        payload["report_path"] = report_path
        report = Path(report_path)
        if report.exists():
            data = load_json(report)
            if not bool(arguments.get("include_context")):
                for key in ("records", "token_hits", "model_hits"):
                    for row in data.get(key, []):
                        row.pop("context", None)
            payload["report"] = data
    return tool_result(payload)


def tool_generate_workflow_from_okf(arguments: dict[str, Any]) -> dict[str, Any]:
    workflow_goal = require_string(arguments, "workflow_goal")
    top_k = int(arguments.get("top_k") or 6)
    vc = version_context(arguments)
    object_classes = string_list(arguments.get("object_classes"), DEFAULT_UNIVERSAL_EXPORT_OBJECT_TYPES)
    retrievals = [
        run_kb_query(
            f"{workflow_goal} Petrel {vc['petrel_version']} version_scope review_status confidence Workflow Editor MCP validation manifest",
            top_k,
        )
    ]
    for object_class in object_classes[:12]:
        retrievals.append(
            run_kb_query(
                f"{workflow_goal} {object_class} Petrel export universal format validation version_scope",
                max(3, min(top_k, 5)),
            )
        )

    workflow_scaffold = {
        "title": workflow_goal,
        "review_status": "design_draft",
        "confidence": "okf_generated_requires_petrel_side_validation",
        "version_context": vc,
        "evidence_policy": [
            "Prefer reviewed workflow/skill/tool notes.",
            "Use draft OKF notes when no reviewed note exists.",
            "Use OCR/raw source notes only as evidence with page/image provenance.",
            "Preserve review_status, confidence, and version_scope in the final workflow note.",
            "Do not promote a workflow beyond design_draft until it is run and validated for the target Petrel version.",
        ],
        "required_frontmatter": {
            "type": "petrel-workflow",
            "version_scope": {
                "petrel_versions": vc["target_versions"],
                "status": "needs_validation",
                "scope_note": vc["version_scope"],
            },
            "review_status": "design_draft",
            "confidence": "okf_generated_requires_petrel_side_validation",
        },
        "workflow_editor_variables": [
            "export_package",
            "inventory_package",
            "export_manifest",
            "petrel_version",
            "version_scope",
            "run_id",
            "export_scope",
            "overwrite_policy",
        ],
        "build_sequence": [
            "Query OKF/wiki for the workflow goal and each object class.",
            "Build a version-scoped evidence table with source note, review_status, confidence, and version_scope.",
            "Create or update the Workflow Editor workflow in an automation copy of the project.",
            "Pass Petrel version and package paths through Workflow Editor variables or the command-line bridge.",
            "Export each object class to the preferred universal format where Petrel supports it.",
            "Register every generated file into 00_manifest/export_manifest.csv with petrel_version.",
            "Run validation and checksum generation.",
            "Run coverage validation against expected object classes and formats.",
            "Update the OKF workflow note with validated versions, failed object classes, and next actions.",
        ],
        "object_class_plan": [
            {
                "source_object_type": object_class,
                "required_formats": DEFAULT_REQUIRED_FORMATS.get(object_class, []),
                "status": "needs_petrel_side_validation",
            }
            for object_class in object_classes
        ],
        "recommended_mcp_sequence": [
            "petrel_query_kb",
            "petrel_generate_workflow_from_okf",
            "petrel_prepare_mvp",
            "petrel_run_mvp",
            "petrel_register_and_validate",
            "petrel_validate_workflow_coverage",
        ],
    }

    payload: dict[str, Any] = {
        "operation": "generate_workflow_from_okf",
        "version_context": vc,
        "workflow_scaffold": workflow_scaffold,
        "retrievals": retrievals,
    }

    if bool(arguments.get("write_wiki_draft")):
        relative_path = str(arguments.get("draft_relative_path") or "")
        if not relative_path.strip():
            slug = re.sub(r"[^A-Za-z0-9]+", " ", workflow_goal).strip()
            relative_path = f"20 Workflows/{slug}.md"
        vault_root = REPO_ROOT / "vault" / "Petrel Knowledge Wiki"
        draft_path = (vault_root / relative_path).resolve()
        if vault_root.resolve() not in draft_path.parents:
            raise McpError("draft_relative_path must stay under vault/Petrel Knowledge Wiki", code=-32602)
        if draft_path.exists() and not bool(arguments.get("overwrite")):
            raise McpError(f"Draft already exists: {draft_path}", code=-32602)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = str(arguments.get("timestamp") or datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        body = [
            "---",
            "type: petrel-workflow",
            f'title: "{workflow_goal}"',
            'description: "Version-aware OKF-generated workflow draft."',
            "tags:",
            "  - petrel",
            "  - petrel-workflow",
            "  - version-aware",
            f"timestamp: {timestamp}",
            "version_scope:",
            "  petrel_versions:",
            *[f'    - "{version}"' for version in vc["target_versions"]],
            "  status: needs_validation",
            f'  scope_note: "{vc["version_scope"]}"',
            "review_status: design_draft",
            "confidence: okf_generated_requires_petrel_side_validation",
            "---",
            "",
            f"# Workflow: {workflow_goal}",
            "",
            "## Version Context",
            "",
            f"- Petrel version: `{vc['petrel_version']}`",
            f"- Version scope: `{vc['version_scope']}`",
            "- Cross-version policy: revalidate before applying outside the target versions.",
            "",
            "## Workflow Editor Variables",
            "",
            *[f"- `{name}`" for name in workflow_scaffold["workflow_editor_variables"]],
            "",
            "## Build Sequence",
            "",
            *[f"{index + 1}. {step}" for index, step in enumerate(workflow_scaffold["build_sequence"])],
            "",
            "## Review Status",
            "",
            "Keep this note as `design_draft` until the workflow has been run and coverage-validated for the target Petrel version.",
            "",
        ]
        draft_path.write_text("\n".join(body), encoding="utf-8")
        payload["draft_path"] = str(draft_path)

    return tool_result(payload)


def tool_validate_workflow_coverage(arguments: dict[str, Any]) -> dict[str, Any]:
    export_package = resolve_existing_path(as_path(arguments.get("export_package"), DEFAULT_EXPORT_PACKAGE), "Export package")
    vc = version_context(arguments)
    rows = read_manifest(export_package)
    expected_object_types = string_list(arguments.get("expected_object_types"), DEFAULT_UNIVERSAL_EXPORT_OBJECT_TYPES)

    required_formats_arg = arguments.get("required_formats")
    if isinstance(required_formats_arg, dict):
        required_formats = {
            str(key): string_list(value, DEFAULT_REQUIRED_FORMATS.get(str(key), []))
            for key, value in required_formats_arg.items()
        }
    else:
        required_formats = dict(DEFAULT_REQUIRED_FORMATS)

    by_type: dict[str, dict[str, Any]] = {}
    version_mismatches: list[dict[str, str]] = []
    validation_gaps: list[dict[str, str]] = []
    target_versions = set(vc["target_versions"])
    require_version_match = bool(arguments.get("require_version_match", True))

    for row in rows:
        source_type = row.get("source_object_type") or "(blank)"
        entry = by_type.setdefault(
            source_type,
            {"row_count": 0, "formats": {}, "validation_statuses": {}, "petrel_versions": {}},
        )
        entry["row_count"] += 1
        export_format = row.get("export_format") or "(blank)"
        validation_status = row.get("validation_status") or "(blank)"
        row_version = row.get("petrel_version") or "(blank)"
        entry["formats"][export_format] = entry["formats"].get(export_format, 0) + 1
        entry["validation_statuses"][validation_status] = entry["validation_statuses"].get(validation_status, 0) + 1
        entry["petrel_versions"][row_version] = entry["petrel_versions"].get(row_version, 0) + 1
        if require_version_match and row_version not in target_versions:
            version_mismatches.append(
                {
                    "export_id": row.get("export_id") or "",
                    "source_object_type": source_type,
                    "petrel_version": row_version,
                }
            )
        if validation_status != "validated":
            validation_gaps.append(
                {
                    "export_id": row.get("export_id") or "",
                    "source_object_type": source_type,
                    "validation_status": validation_status,
                }
            )

    missing_object_types = [source_type for source_type in expected_object_types if source_type not in by_type]
    format_gaps: list[dict[str, Any]] = []
    for source_type in expected_object_types:
        formats = by_type.get(source_type, {}).get("formats", {})
        required = required_formats.get(source_type, [])
        if not required or source_type not in by_type:
            continue
        if not any(required_format in formats for required_format in required):
            format_gaps.append(
                {
                    "source_object_type": source_type,
                    "required_any_of": required,
                    "observed_formats": sorted(formats),
                }
            )

    status = "pass"
    if missing_object_types or format_gaps or validation_gaps or version_mismatches:
        status = "needs_attention"

    payload: dict[str, Any] = {
        "operation": "validate_workflow_coverage",
        "version_context": vc,
        "export_package": str(export_package),
        "status": status,
        "coverage_basis": "00_manifest/export_manifest.csv",
        "manifest": summarize_manifest_counts(rows),
        "expected_object_types": expected_object_types,
        "coverage_by_source_object_type": by_type,
        "missing_object_types": missing_object_types,
        "format_gaps": format_gaps,
        "validation_gaps": validation_gaps[:100],
        "validation_gap_count": len(validation_gaps),
        "version_mismatches": version_mismatches[:100],
        "version_mismatch_count": len(version_mismatches),
        "notes": [
            "This is manifest-based coverage validation, not proof that every Petrel object can be exported losslessly.",
            "Version compatibility is proven only for rows whose petrel_version matches the target version set.",
            "Keep the workflow review_status as design_draft or needs_validation while missing object types remain.",
        ],
    }
    if bool(arguments.get("include_rows")):
        payload["rows"] = rows
    return tool_result(payload)


def tool_query_kb(arguments: dict[str, Any]) -> dict[str, Any]:
    query = require_string(arguments, "query")
    top_k = int(arguments.get("top_k") or 8)
    query_text = f"{query} Petrel {arguments.get('petrel_version') or DEFAULT_PETREL_VERSION} version_scope review_status confidence"
    result = run_kb_query(query_text, top_k)
    return tool_result(
        {
            "operation": "query_kb",
            "version_context": version_context(arguments),
            **result,
        }
    )


def tool_agent_readiness(arguments: dict[str, Any]) -> dict[str, Any]:
    classified = {tool for group in TOOL_MATURITY_REGISTRY.values() for tool in group["tools"]}
    unclassified = sorted(set(TOOLS) - classified)
    missing_from_server = sorted(tool for tool in classified if tool not in TOOLS)
    user_profile = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    appdata = Path(os.environ.get("APPDATA") or (user_profile / "AppData" / "Roaming"))
    localappdata = Path(os.environ.get("LOCALAPPDATA") or (user_profile / "AppData" / "Local"))
    claude_store_candidates = sorted(
        localappdata.glob(r"Packages\Claude_*\LocalCache\Roaming\Claude\claude_desktop_config.json")
    )
    client_configs = {
        "codex": str(user_profile / ".codex" / "config.toml"),
        "vscode": str(appdata / "Code" / "User" / "mcp.json"),
        "opencode": str(user_profile / ".config" / "opencode" / "opencode.jsonc"),
        "claude_roaming": str(appdata / "Claude" / "claude_desktop_config.json"),
        "claude_store_candidates": [str(path) for path in claude_store_candidates],
    }
    config_status = {}
    for name, value in client_configs.items():
        if isinstance(value, list):
            config_status[name] = [{"path": item, "exists": Path(item).exists()} for item in value]
        else:
            config_status[name] = {"path": value, "exists": Path(value).exists()}

    return tool_result(
        {
            "operation": "agent_readiness",
            "server": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
                "repo_root": str(REPO_ROOT),
                "python": sys.executable,
            },
            "status": "ready_local_agent_surface" if not missing_from_server else "registry_mismatch",
            "tool_maturity": TOOL_MATURITY_REGISTRY,
            "tool_counts": {
                "total_registered": len(TOOLS),
                "stable": len(TOOL_MATURITY_REGISTRY["stable"]["tools"]),
                "beta": len(TOOL_MATURITY_REGISTRY["beta"]["tools"]),
                "experimental": len(TOOL_MATURITY_REGISTRY["experimental"]["tools"]),
                "unclassified": len(unclassified),
                "missing_from_server": len(missing_from_server),
            },
            "unclassified_tools": unclassified,
            "missing_from_server": missing_from_server,
            "recommended_first_tools": [
                "petrel_agent_readiness",
                "petrel_status",
                "petrel_export_native_zero_gui",
                "petrel_export_well_tops_native_probe",
                "petrel_register_and_validate",
                "petrel_validate_workflow_coverage",
            ],
            "runtime_dependency_contract": {
                "python": "python_path argument -> PETREL_MCP_PYTHON -> PYTHON -> MCP server sys.executable -> repo .venv -> PATH python/py",
                "tesseract": "tesseract_path argument -> PETREL_TESSERACT_PATH -> TESSERACT_PATH -> default Program Files install -> PATH tesseract",
                "fail_closed_status": "preflight_failed",
                "petrel_not_touched_on_preflight_failure": True,
            },
            "client_config_status": config_status,
            "doctor_command": r'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\Computer\Code\Petrel_project\scripts\doctor_petrel_mcp.ps1"',
            "known_boundaries": [
                "Native .pet/.ptd store copy and semantic metadata extraction are zero-GUI.",
                "Petrel-authored Well Tops ASCII parsing is confirmed when the exported ASCII file exists; native binary marker-pick decoding is not yet confirmed.",
                "Deterministic GUI tools are beta fallbacks and must pass dependency/precondition gates before touching Petrel.",
                "Low-level native patch tools are experimental unless wrapped by a patch-run-restore proof tool.",
            ],
        }
    )


def tool_tool_creation_hierarchy(arguments: dict[str, Any]) -> dict[str, Any]:
    hierarchy = load_json(resolve_existing_path(TOOL_CREATION_HIERARCHY_PATH, "Tool creation hierarchy"))
    return tool_result(
        {
            "operation": "tool_creation_hierarchy",
            "version_context": version_context(arguments),
            "policy_path": str(TOOL_CREATION_HIERARCHY_PATH),
            "docs_path": str(REPO_ROOT / "docs" / "PETREL_TOOL_CREATION_HIERARCHY.md"),
            "hierarchy": hierarchy,
        }
    )


def tool_tool_failure_policy(arguments: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(arguments.get("tool_name") or "").strip()
    include_all = bool(arguments.get("include_all_tools"))
    config = load_failure_policy_config()
    if tool_name:
        if tool_name not in TOOLS:
            raise McpError(f"Unknown tool for failure policy: {tool_name}", code=-32602)
        payload: dict[str, Any] = {
            "operation": "tool_failure_policy",
            "version_context": version_context(arguments),
            "policy_version": config.get("policy_version"),
            "policy_path": str(FAILURE_POLICIES_PATH),
            "tool_name": tool_name,
            "policy": resolve_failure_policy(tool_name),
        }
    else:
        names = sorted(TOOLS) if include_all else sorted(config.get("tool_policies", {}))
        payload = {
            "operation": "tool_failure_policy",
            "version_context": version_context(arguments),
            "policy_version": config.get("policy_version"),
            "policy_path": str(FAILURE_POLICIES_PATH),
            "tool_count": len(names),
            "tools": {name: failure_policy_summary(name) for name in names},
            "available_policy_templates": sorted(config.get("policy_templates", {})),
        }
    return tool_result(payload)


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


def apply_version_aware_inputs(tools: dict[str, Tool]) -> None:
    for tool in tools.values():
        properties = tool.input_schema.setdefault("properties", {})
        for name, definition in VERSION_AWARE_INPUTS.items():
            properties.setdefault(name, definition)


TOOLS: dict[str, Tool] = {
    "petrel_agent_readiness": Tool(
        "petrel_agent_readiness",
        "Return the agent-facing readiness contract: stable/beta/experimental tool registry, dependency preflight rules, client config paths, and recommended first tool sequence.",
        schema({}),
        tool_agent_readiness,
    ),
    "petrel_tool_creation_hierarchy": Tool(
        "petrel_tool_creation_hierarchy",
        "Return the project hierarchy for choosing how to create a Petrel MCP/CLI tool: zero-GUI Python, zero-GUI Workflow Editor/native control, deterministic GUI fallback, or discovery-only donor capture.",
        schema({}),
        tool_tool_creation_hierarchy,
    ),
    "petrel_tool_failure_policy": Tool(
        "petrel_tool_failure_policy",
        "Return the fail-closed evidence, failure scenarios, retry policy, and fallback chain for one Petrel MCP tool or all registered tools.",
        schema(
            {
                "tool_name": {"type": "string", "description": "Optional MCP tool name. If omitted, summaries are returned."},
                "include_all_tools": {
                    "type": "boolean",
                    "default": False,
                    "description": "When tool_name is omitted, include every registered tool, including tools that only use the default policy.",
                },
            }
        ),
        tool_tool_failure_policy,
    ),
    "petrel_status": Tool(
        "petrel_status",
        "Summarize the current no-Ocean Petrel automation state, latest run JSON, manifest counts with a bounded row preview, and domain export file counts. Pass include_manifest_rows=true only when the full manifest row list is required; it can exceed agent context limits.",
        schema(
            {
                "export_package": {"type": "string", "description": "Optional export package path."},
                "include_manifest_rows": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return every manifest row instead of the compact preview. The full list can exceed agent context limits.",
                },
                "manifest_rows_limit": {
                    "type": "integer",
                    "default": DEFAULT_MANIFEST_ROWS_PREVIEW,
                    "description": "Maximum rows returned in manifest.rows_preview when include_manifest_rows is false. 0 disables the preview.",
                },
            }
        ),
        tool_petrel_status,
    ),
    "petrel_prepare_mvp": Tool(
        "petrel_prepare_mvp",
        "Generate the KB-derived full-project export plan, workflow JSON, MCP tool spec, and Petrel build sheet without launching Petrel.",
        schema(
            {
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "timeout_seconds": {"type": "integer", "default": 300},
            }
        ),
        tool_prepare_mvp,
    ),
    "petrel_run_mvp": Tool(
        "petrel_run_mvp",
        "Run the current Petrel Workflow Editor MVP wrapper. Safe by default since 0.7.0: dry_run defaults to true, so a bare call previews the run without launching Petrel. WARNING: passing dry_run=false explicitly launches Petrel and executes the saved workflow for real; only do so deliberately with the automation copy prepared.",
        schema(
            {
                "project_file": {"type": "string"},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "validate_only": {"type": "boolean", "default": False},
                "dry_run": {
                    "type": "boolean",
                    "default": True,
                    "description": "Preview the run without launching Petrel. Pass false explicitly for a live Petrel workflow run.",
                },
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 3600},
            }
        ),
        tool_run_mvp,
    ),
    "petrel_open_project": Tool(
        "petrel_open_project",
        "Prepare or launch Petrel with the automation project for UI workflow editing. Defaults to dry-run/read-only unless launch and writable are explicit.",
        schema(
            {
                "project_file": {"type": "string"},
                "launch": {"type": "boolean", "default": False},
                "writable": {"type": "boolean", "default": False},
                "wait": {"type": "boolean", "default": False},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "petrel_option_style": {"type": "string", "default": "Slash"},
                "timeout_seconds": {"type": "integer", "default": 300},
            }
        ),
        tool_open_project,
    ),
    "petrel_export_well_logs_ui": Tool(
        "petrel_export_well_logs_ui",
        "Drive the Petrel UI to export all logs under Input/Wells as LAS files, then register and validate the package. This is the first no-Ocean real data export path. WARNING: every argument has a default, so a bare call attempts a live Petrel desktop GUI run immediately (fail-closed preflight gates apply); only call this deliberately with a prepared Petrel session.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "project_path": {"type": "string"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "petrel_process_id": {"type": "integer"},
                "license_profile": {"type": "string", "default": "BatchProfile"},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "petrel_option_style": {"type": "string", "default": "Slash"},
                "target_subfolder": {"type": "string", "default": "02_wells\\well_logs_las"},
                "extension": {"type": "string", "default": "las"},
                "drive_letter": {"type": "string", "default": "P"},
                "timeout_seconds": {"type": "integer", "default": 900},
                "open_project_writable": {"type": "boolean", "default": False},
                "allow_existing_target": {"type": "boolean", "default": False},
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "keep_drive_mapping": {"type": "boolean", "default": False},
            }
        ),
        tool_export_well_logs_ui,
    ),
    "petrel_export_well_tops_ui": Tool(
        "petrel_export_well_tops_ui",
        "Drive the Petrel UI to export Explorer/Input/Wells/Well Tops with Petrel well tops ASCII, then register and validate the package. WARNING: every argument has a default, so a bare call attempts a live Petrel desktop GUI run immediately (fail-closed preflight gates apply); only call this deliberately with a prepared Petrel session.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "project_path": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "petrel_process_id": {"type": "integer"},
                "license_profile": {"type": "string", "default": "BatchProfile"},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "petrel_option_style": {"type": "string", "default": "Slash"},
                "target_subfolder": {"type": "string", "default": "02_wells\\well_tops"},
                "extension": {"type": "string", "default": "txt"},
                "output_file_name": {"type": "string"},
                "format_pattern": {"type": "string", "default": "Petrel.*well.*tops.*ASCII|Well Tops.*ASCII"},
                "tesseract_path": {"type": "string"},
                "drive_letter": {"type": "string", "default": "P"},
                "timeout_seconds": {"type": "integer", "default": 900},
                "open_project_writable": {"type": "boolean", "default": False},
                "allow_existing_target": {"type": "boolean", "default": False},
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "keep_drive_mapping": {"type": "boolean", "default": False},
                "coordinate_fallback": {
                    "type": "boolean",
                    "default": False,
                    "description": "Use the legacy coordinate-only fallback. The default semantic driver anchors the Explorer Input tab strip by requiring sibling tabs Models, Results, and Templates, rejects Processes > Input, then OCR-locates the visible Well Tops row above the tab strip.",
                },
            }
        ),
        tool_export_well_tops_ui,
    ),
    "petrel_run_deterministic_gui_workflow": Tool(
        "petrel_run_deterministic_gui_workflow",
        "Run a named deterministic Petrel GUI fallback workflow from a declarative spec. Defaults to dry-run and launches Petrel only when execute is true.",
        schema(
            {
                "workflow_id": {"type": "string", "default": "export_well_tops_ascii"},
                "spec_path": {"type": "string"},
                "execute": {"type": "boolean", "default": False},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "project_path": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "petrel_process_id": {"type": "integer"},
                "license_profile": {"type": "string", "default": "BatchProfile"},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "petrel_option_style": {"type": "string", "default": "Slash"},
                "target_subfolder": {"type": "string"},
                "extension": {"type": "string"},
                "output_file_name": {"type": "string"},
                "format_pattern": {"type": "string"},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "tesseract_path": {
                    "type": "string",
                    "description": "Optional explicit path to tesseract.exe for semantic OCR selection when Tesseract is not installed in the default location.",
                },
                "drive_letter": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 900},
                "license_dialog_timeout_seconds": {
                    "type": "integer",
                    "default": 3,
                    "description": "Seconds to wait for a Petrel license dialog before assuming it is absent in deterministic GUI runs.",
                },
                "stable_file_ticks": {
                    "type": "integer",
                    "default": 1,
                    "description": "Number of unchanged file polling cycles required before accepting the exported ASCII file.",
                },
                "file_poll_seconds": {
                    "type": "integer",
                    "default": 1,
                    "description": "Polling interval used while waiting for the exported ASCII file.",
                },
                "well_tops_relative_x": {
                    "type": "integer",
                    "default": 91,
                    "description": "Coordinate fallback X offset from the Petrel main window to the visible Well Tops row.",
                },
                "well_tops_relative_y": {
                    "type": "integer",
                    "default": 546,
                    "description": "Coordinate fallback Y offset from the Petrel main window to the visible Well Tops row.",
                },
                "export_object_relative_x": {
                    "type": "integer",
                    "default": 221,
                    "description": "Coordinate fallback X offset from the Petrel main window to the Export object context-menu item when keyboard selection is not used.",
                },
                "export_object_relative_y": {
                    "type": "integer",
                    "default": 415,
                    "description": "Coordinate fallback Y offset from the Petrel main window to the Export object context-menu item when keyboard selection is not used.",
                },
                "open_project_writable": {"type": "boolean", "default": False},
                "allow_existing_target": {"type": "boolean", "default": False},
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "keep_drive_mapping": {"type": "boolean", "default": False},
                "coordinate_fallback": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow the workflow's legacy coordinate fallback. Default false uses the semantic UIA/OCR adapter where available.",
                },
                "context_menu_keyboard": {
                    "type": "boolean",
                    "default": False,
                    "description": "After coordinate right-clicking the Well Tops row, use keyboard menu selection for Export object instead of a fixed menu coordinate.",
                },
                "skip_import": {
                    "type": "boolean",
                    "default": False,
                    "description": "Skip parsing the exported Petrel Well Tops ASCII file into normalized CSV evidence.",
                },
            }
        ),
        tool_run_deterministic_gui_workflow,
    ),
    "petrel_export_native_zero_gui": Tool(
        "petrel_export_native_zero_gui",
        "Export the full Petrel .pet/.ptd native project store without launching Petrel or using GUI, extract native metadata candidates, update the manifest, and validate checksums.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "project_path": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_root": {"type": "string"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "max_text_probe_bytes": {"type": "integer", "default": 10485760},
                "max_candidates_per_file": {"type": "integer", "default": 200},
                "create_new_package": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 1800},
            }
        ),
        tool_export_native_zero_gui,
    ),
    "petrel_run_zero_gui_export_mvp": Tool(
        "petrel_run_zero_gui_export_mvp",
        "Run the complete zero-GUI export MVP: build KB artifacts, copy/index the native project store, extract semantic native metadata, update the manifest, and validate checksums without launching Petrel.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "max_text_probe_bytes": {"type": "integer", "default": 10485760},
                "max_candidates_per_file": {"type": "integer", "default": 200},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path for the semantic zero-GUI extraction step. Defaults to the MCP server Python.",
                },
                "create_new_package": {"type": "boolean", "default": False},
                "skip_semantic_extraction": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 2400},
            }
        ),
        tool_run_zero_gui_mvp,
    ),
    "petrel_export_native_semantic_zero_gui": Tool(
        "petrel_export_native_semantic_zero_gui",
        "Extract safe semantic metadata from copied Petrel native stores without launching Petrel: SMD faults/horizons/zones/frameworks, GMS property metadata, SQLite schema/values, XML/BXML metadata, and ZGY inventory.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "max_xml_names": {"type": "integer", "default": 20},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_export_native_semantic_zero_gui,
    ),
    "petrel_export_well_tables_zero_gui": Tool(
        "petrel_export_well_tables_zero_gui",
        "Derive well headers, LAS curve inventory, and conservative well-top rows from the current export package without launching Petrel, then register and validate the package.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "max_native_xml_rows": {"type": "integer", "default": 200},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_export_well_tables_zero_gui,
    ),
    "petrel_export_surfaces_zero_gui": Tool(
        "petrel_export_surfaces_zero_gui",
        "Decode native .zhz surface arrays to XYZ CSV and ZMAP+ without launching Petrel: mask-gated layout validation, SEG-Y-derived survey georeferencing, well-top cross-checks, then register and validate the package.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_export_surfaces_zero_gui,
    ),
    "petrel_write_well_tops_ascii": Tool(
        "petrel_write_well_tops_ascii",
        "Write a Petrel Well Tops ASCII (VERSION 2) file from a CSV of marker picks, replicating the exact Petrel 2018.2 export dialect (CRLF, quoted strings, -999 undefined). Verifies by re-parsing the written file. Completes the export-edit-reimport chain.",
        schema(
            {
                "input_csv": {"type": "string", "description": "CSV with well/surface/x/y/z(depth) columns; extra columns used when present."},
                "output_path": {"type": "string"},
                "no_verify": {"type": "boolean", "default": False},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "timeout_seconds": {"type": "integer", "default": 300},
            },
            required=["input_csv", "output_path"],
        ),
        tool_write_well_tops_ascii,
    ),
    "petrel_las_convert": Tool(
        "petrel_las_convert",
        "Convert a Petrel-exported LAS well log file to CSV (depth plus curve columns) with a JSON summary of well name, curves, units, and ranges. Zero-GUI chain tool.",
        schema(
            {
                "input_path": {"type": "string", "description": "LAS file path."},
                "output_path": {"type": "string", "description": "CSV output path."},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "timeout_seconds": {"type": "integer", "default": 300},
            },
            required=["input_path", "output_path"],
        ),
        tool_las_convert,
    ),
    "petrel_project_audit_report": Tool(
        "petrel_project_audit_report",
        "Generate a self-contained HTML + JSON audit of a Petrel project from its export package without launching Petrel: wells/logs, well tops, decoded surfaces, ZGY seismic, native-store semantics, manifest breakdown, and QC flags. Sections degrade gracefully when evidence is missing; registers and validates the outputs.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "title": {"type": "string", "description": "Optional report title override."},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 600},
            }
        ),
        tool_project_audit_report,
    ),
    "petrel_export_seismic_zgy_zero_gui": Tool(
        "petrel_export_seismic_zgy_zero_gui",
        "Read native ZGY seismic cubes with pyzgy without launching Petrel: per-cube geometry/statistics reports, orthogonal mid-slice .npy exports, optional full-volume .npy (~100 MB per cube), then register and validate the package.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "export_volume": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also export each full decompressed volume as .npy with a JSON geometry sidecar (large).",
                },
                "no_slices": {"type": "boolean", "default": False},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_export_seismic_zgy_zero_gui,
    ),
    "petrel_survey_geometry": Tool(
        "petrel_survey_geometry",
        "Read-only seismic survey geometry report from a Petrel-authored SEG-Y export: origin, inline/xline unit vectors, corners, rotation, bin size, and CRS sidecar metadata. No Petrel launch, no writes.",
        schema(
            {
                "export_package": {"type": "string"},
                "segy_path": {
                    "type": "string",
                    "description": "SEG-Y path, absolute or relative to the export package. Defaults to the saved donor export.",
                },
            }
        ),
        tool_survey_geometry,
    ),
    "petrel_grid_convert": Tool(
        "petrel_grid_convert",
        "Convert a gridded surface file between ZMAP+ .dat and XYZ CSV using the project's zmapio conventions (null 1e30). Fails closed on irregular scatter; XYZ output lists live nodes only, so a reconstructed ZMAP canvas shrinks to the live-data bounding box.",
        schema(
            {
                "input_path": {"type": "string", "description": "Source grid file (.dat/.zmap or .csv/.xyz)."},
                "output_path": {"type": "string", "description": "Destination file; format inferred from extension unless overridden."},
                "input_format": {"type": "string", "enum": ["zmap", "xyz_csv"]},
                "output_format": {"type": "string", "enum": ["zmap", "xyz_csv"]},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "timeout_seconds": {"type": "integer", "default": 300},
            },
            required=["input_path", "output_path"],
        ),
        tool_grid_convert,
    ),
    "petrel_export_well_tops_native_probe": Tool(
        "petrel_export_well_tops_native_probe",
        "Probe Petrel native binaries for clean well-top evidence and parse any local Petrel Well Tops ASCII source file without launching Petrel, then register and validate the package.",
        schema(
            {
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "project_file": {"type": "string"},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "source_well_tops_file": {"type": "string"},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_export_well_tops_native_probe,
    ),
    "petrel_import_gui_well_tops_table": Tool(
        "petrel_import_gui_well_tops_table",
        "Import a pasted Petrel GUI Well Tops table as a validation artifact, compare it to the source-ASCII fallback, then register and validate without launching Petrel.",
        schema(
            {
                "gui_table_paste": {"type": "string"},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "source_ascii_csv": {"type": "string"},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "numeric_tolerance": {"type": "number", "default": 0.05},
                "no_register": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 900},
            }
        ),
        tool_import_gui_well_tops_table,
    ),
    "petrel_register_and_validate": Tool(
        "petrel_register_and_validate",
        "Register Petrel-written files and workflow reports into the manifest, then validate/checksum the export package.",
        schema(
            {
                "export_package": {"type": "string"},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "inventory_package": {"type": "string"},
            }
        ),
        tool_register_and_validate,
    ),
    "petrel_native_map_workflow": Tool(
        "petrel_native_map_workflow",
        "Map BXML/LZ4 markers and selected command terms in Petrel native workflow store files.",
        schema(
            {
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string"},
                "store_file": {"type": "string", "default": "Data.ptd"},
                "terms": {"type": "array", "items": {"type": "string"}},
                "compare_store_file": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 600},
            }
        ),
        tool_native_map,
    ),
    "petrel_native_snapshot": Tool(
        "petrel_native_snapshot",
        "Copy the Petrel .pet plus selected .ptd store files into a timestamped snapshot with hashes for before/after workflow experiments.",
        schema(
            {
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string"},
                "label": {"type": "string", "default": "snapshot"},
                "store_files": {"type": "array", "items": {"type": "string"}},
                "output_root": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 300},
            }
        ),
        tool_native_snapshot,
    ),
    "petrel_native_compare_snapshots": Tool(
        "petrel_native_compare_snapshots",
        "Compare before/after Petrel native workflow snapshots, emit byte diff ranges/previews, and map after Data.ptd against the before store.",
        schema(
            {
                "before_snapshot": {"type": "string"},
                "after_snapshot": {"type": "string"},
                "project_stem": {"type": "string"},
                "store_files": {"type": "array", "items": {"type": "string"}},
                "terms": {"type": "array", "items": {"type": "string"}},
                "output_root": {"type": "string"},
                "python_path": {
                    "type": "string",
                    "description": "Optional explicit python.exe path. Defaults to the Python executable running the MCP server.",
                },
                "timeout_seconds": {"type": "integer", "default": 900},
            },
            required=["before_snapshot", "after_snapshot"],
        ),
        tool_native_compare_snapshots,
    ),
    "petrel_native_patch_string": Tool(
        "petrel_native_patch_string",
        "Dry-run or apply a guarded same-length ASCII string patch in a Petrel native workflow store file. Defaults to dry-run unless apply is true.",
        schema(
            {
                "store_file": {"type": "string", "default": "Model.ptd"},
                "search": {"type": "string"},
                "replace": {"type": "string"},
                "apply": {"type": "boolean", "default": False},
                "allow_multiple": {"type": "boolean", "default": False},
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string"},
            },
            required=["search", "replace"],
        ),
        tool_patch_string,
    ),
    "petrel_native_patch_offset": Tool(
        "petrel_native_patch_offset",
        "Dry-run or apply a guarded same-length exact-offset patch in a Petrel native workflow store file. Defaults to dry-run unless apply is true.",
        schema(
            {
                "store_file": {"type": "string", "default": "Data.ptd"},
                "offset": {"type": "integer"},
                "expected": {"type": "string"},
                "replace": {"type": "string"},
                "apply": {"type": "boolean", "default": False},
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string"},
            },
            required=["offset", "expected", "replace"],
        ),
        tool_patch_offset,
    ),
    "petrel_export_segy_filename_patch": Tool(
        "petrel_export_segy_filename_patch",
        "Patch the saved ExportSeismicCmd SEG-Y filename tail, run the ExportPiloX workflow, register/validate the package, and restore the Petrel binary patch.",
        schema(
            {
                "replacement_tail": {
                    "type": "string",
                    "description": "Same-length replacement for the saved SEG-Y filename tail, for example _mcp01.sgy.",
                },
                "expected_tail": {"type": "string", "default": "_donor.sgy"},
                "offset": {"type": "integer", "default": 173201036},
                "store_file": {"type": "string", "default": "Data.ptd"},
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "project_file": {"type": "string"},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "output_prefix": {"type": "string", "default": "orig_amp_exportpilot"},
                "output_subfolder": {"type": "string", "default": "03_seismic\\segy"},
                "output_root": {"type": "string"},
                "keep_patch": {"type": "boolean", "default": False},
                "skip_run": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "include_manifest_rows": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 4200},
            },
            required=["replacement_tail"],
        ),
        tool_export_segy_filename_patch,
    ),
    "petrel_export_segy_token_patch": Tool(
        "petrel_export_segy_token_patch",
        "Patch a same-length token inside a saved ExportSeismicCmd payload by exact offset, run ExportPiloX, register/validate the package, and restore the Petrel binary patch.",
        schema(
            {
                "offset": {"type": "integer", "description": "Exact Data.ptd byte offset to patch."},
                "expected_token": {"type": "string", "description": "ASCII token expected at offset, for example sgy2."},
                "replacement_token": {
                    "type": "string",
                    "description": "Same-length ASCII replacement token, for example sgy3.",
                },
                "expected_output_file_name": {
                    "type": "string",
                    "description": "Optional current output file name; if it contains expected_token, the target output is inferred by replacement.",
                },
                "target_output_file_name": {
                    "type": "string",
                    "description": "Optional explicit expected Petrel output file name, for example orig_amp_exportpilot_sgy3.sgy.",
                },
                "store_file": {"type": "string", "default": "Data.ptd"},
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "project_file": {"type": "string"},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "output_prefix": {"type": "string", "default": "orig_amp_exportpilot_"},
                "output_subfolder": {"type": "string", "default": "03_seismic\\segy"},
                "output_root": {"type": "string"},
                "keep_patch": {"type": "boolean", "default": False},
                "skip_run": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "include_manifest_rows": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 4200},
            },
            required=["offset", "expected_token", "replacement_token"],
        ),
        tool_export_segy_token_patch,
    ),
    "petrel_analyze_exportseismiccmd_records": Tool(
        "petrel_analyze_exportseismiccmd_records",
        "Read-only analyzer for saved ExportSeismicCmd records, BXML/LZ4 envelopes, and nearby output-token candidates in the current Petrel native workflow store.",
        schema(
            {
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "terms": {
                    "type": "string",
                    "description": "Pipe-delimited search terms. Defaults to ExportSeismicCmd and known SEG-Y output tokens.",
                },
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_analyze_exportseismiccmd_records,
    ),
    "petrel_analyze_workflow_command_clone_readiness": Tool(
        "petrel_analyze_workflow_command_clone_readiness",
        "Read-only analyzer that reports whether saved Workflow Editor command donor evidence is sufficient for safe zero-GUI command cloning. It does not write native stores.",
        schema(
            {
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "first_donor_compare_report": {"type": "string"},
                "second_donor_compare_report": {"type": "string"},
                "filename_patch_proof": {"type": "string"},
                "token_patch_proof": {"type": "string"},
                "terms": {"type": "string"},
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_analyze_workflow_command_clone_readiness,
    ),
    "petrel_analyze_workflow_clone_side_effects": Tool(
        "petrel_analyze_workflow_clone_side_effects",
        "Read-only analyzer that classifies Data.ptd and Model.ptd side effects from Petrel-authored command donor diffs before any zero-GUI command clone is attempted.",
        schema(
            {
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "first_donor_compare_report": {"type": "string"},
                "second_donor_compare_report": {"type": "string"},
                "terms": {"type": "string"},
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_analyze_workflow_clone_side_effects,
    ),
    "petrel_analyze_workflow_clone_storage_blocks": Tool(
        "petrel_analyze_workflow_clone_storage_blocks",
        "Read-only analyzer that splits mixed ExportSeismicCmd command payload bytes from Data.ptd store-growth blocks before any zero-GUI command clone is attempted.",
        schema(
            {
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "first_donor_compare_report": {"type": "string"},
                "second_donor_compare_report": {"type": "string"},
                "terms": {"type": "string"},
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_analyze_workflow_clone_storage_blocks,
    ),
    "petrel_extract_workflow_command_clone_recipe": Tool(
        "petrel_extract_workflow_command_clone_recipe",
        "Read-only extractor that saves candidate ExportSeismicCmd clone payloads from Petrel-authored donor diffs and reports whether a clone recipe is safe to apply. It does not write native stores.",
        schema(
            {
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "first_donor_compare_report": {"type": "string"},
                "second_donor_compare_report": {"type": "string"},
                "terms": {"type": "string"},
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_extract_workflow_command_clone_recipe,
    ),
    "petrel_export_systemcmd_token_patch": Tool(
        "petrel_export_systemcmd_token_patch",
        "Patch a same-length token inside the saved SystemCmd bridge payload by exact offset, run ExportPiloX, require the bridge proof JSON/probe to reflect the patched StepName, and restore the Petrel binary patch.",
        schema(
            {
                "offset": {"type": "integer", "description": "Exact Data.ptd byte offset to patch."},
                "expected_token": {"type": "string", "description": "ASCII token expected at offset, for example register_validate."},
                "replacement_token": {
                    "type": "string",
                    "description": "Same-length ASCII replacement token, for example register_validatf.",
                },
                "expected_bridge_step_name": {
                    "type": "string",
                    "default": "post_export_register_validate",
                    "description": "Current StepName value expected from the saved System command.",
                },
                "target_bridge_step_name": {
                    "type": "string",
                    "description": "Optional explicit StepName expected after patch. If omitted and expected_bridge_step_name contains expected_token, it is inferred.",
                },
                "store_file": {"type": "string", "default": "Data.ptd"},
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "project_file": {"type": "string"},
                "project_name": {"type": "string", "default": DEFAULT_PROJECT_NAME},
                "petrel_version": {"type": "string", "default": DEFAULT_PETREL_VERSION},
                "workflow_name": {"type": "string", "default": DEFAULT_WORKFLOW_NAME},
                "license_package": {"type": "string", "default": "BatchProfile"},
                "export_package": {"type": "string"},
                "inventory_package": {"type": "string"},
                "output_root": {"type": "string"},
                "keep_patch": {"type": "boolean", "default": False},
                "skip_run": {"type": "boolean", "default": False},
                "no_validate": {"type": "boolean", "default": False},
                "include_manifest_rows": {"type": "boolean", "default": False},
                "timeout_seconds": {"type": "integer", "default": 4200},
            },
            required=["offset", "expected_token", "replacement_token"],
        ),
        tool_export_systemcmd_token_patch,
    ),
    "petrel_analyze_systemcmd_records": Tool(
        "petrel_analyze_systemcmd_records",
        "Read-only analyzer for saved SystemCmd bridge records, BXML/LZ4 envelopes, and nearby command/argument token candidates in the current Petrel native workflow store.",
        schema(
            {
                "project_directory": {"type": "string"},
                "project_stem": {"type": "string", "default": "Petrel2010 demo project ExportPilot"},
                "output_root": {"type": "string"},
                "terms": {
                    "type": "string",
                    "description": "Pipe-delimited search terms. Defaults to SystemCmd and known bridge command tokens.",
                },
                "include_context": {"type": "boolean", "default": False},
            }
        ),
        tool_analyze_systemcmd_records,
    ),
    "petrel_generate_workflow_from_okf": Tool(
        "petrel_generate_workflow_from_okf",
        "Generate a version-aware Workflow Editor workflow scaffold from OKF/wiki retrieval evidence, preserving review_status, confidence, and version_scope.",
        schema(
            {
                "workflow_goal": {"type": "string"},
                "object_classes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expected Petrel source_object_type values to plan for. Defaults to the universal project export set.",
                },
                "top_k": {"type": "integer", "default": 6},
                "write_wiki_draft": {"type": "boolean", "default": False},
                "draft_relative_path": {
                    "type": "string",
                    "description": "Optional vault-root-relative Markdown path when write_wiki_draft is true.",
                },
                "overwrite": {"type": "boolean", "default": False},
                "timestamp": {"type": "string"},
            },
            required=["workflow_goal"],
        ),
        tool_generate_workflow_from_okf,
    ),
    "petrel_validate_workflow_coverage": Tool(
        "petrel_validate_workflow_coverage",
        "Validate a workflow/export package manifest against version-aware expected object classes, universal formats, validation status, and Petrel version.",
        schema(
            {
                "export_package": {"type": "string"},
                "expected_object_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Manifest source_object_type values expected for coverage validation.",
                },
                "required_formats": {
                    "type": "object",
                    "description": "Map of source_object_type to acceptable export_format values.",
                },
                "require_version_match": {"type": "boolean", "default": True},
                "include_rows": {"type": "boolean", "default": False},
            }
        ),
        tool_validate_workflow_coverage,
    ),
    "petrel_query_kb": Tool(
        "petrel_query_kb",
        "Query the local Petrel knowledge index for version-scoped workflow/export evidence before planning an automation action.",
        schema({"query": {"type": "string"}, "top_k": {"type": "integer", "default": 8}}, required=["query"]),
        tool_query_kb,
    ),
}

apply_version_aware_inputs(TOOLS)


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if request_id is None and method and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [tool.mcp_shape() for tool in TOOLS.values()]}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS:
                raise McpError(f"Unknown tool: {name}", code=-32602)
            if not isinstance(arguments, dict):
                raise McpError("tools/call arguments must be an object", code=-32602)
            arguments = dict(arguments)
            arguments.setdefault("petrel_version", DEFAULT_PETREL_VERSION)
            arguments.setdefault("version_scope", DEFAULT_VERSION_SCOPE)
            arguments.setdefault("target_versions", [arguments["petrel_version"]])
            result = annotate_tool_response(name, TOOLS[name].handler(arguments))
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "prompts/list":
            result = {"prompts": []}
        else:
            raise McpError(f"Unknown method: {method}", code=-32601)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except McpError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": str(exc)}}
    except Exception as exc:  # pragma: no cover - defensive server boundary
        print(traceback.format_exc(), file=sys.stderr)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
