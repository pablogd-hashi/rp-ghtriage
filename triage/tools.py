"""Read-only tools the investigator may call. Tests use the fixture record and catalog.

Nothing here opens a socket. A missing file or an unknown package is a value
the caller records, not a guess.
"""

from __future__ import annotations


class ToolError(Exception):
    """The tool ran and refused. Distinct from a policy refusal."""


TOOL_SPECS = [
    {
        "name": "list_changed_files",
        "description": "Filenames changed in this pull request.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "read_file",
        "description": "The patch for one changed file. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "osv_lookup",
        "description": "Known advisories for a package version. Read-only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "version": {"type": "string"},
            },
            "required": ["package"],
        },
    },
]


def list_changed_files(record: dict, catalog: dict | None = None) -> list[str]:
    return [f["filename"] for f in (record.get("files") or []) if f.get("filename")]


def read_file(record: dict, path: str, catalog: dict | None = None) -> str:
    for item in record.get("files") or []:
        if item.get("filename") == path:
            return item.get("patch") or ""
    extra = (catalog or {}).get("files") or {}
    if path in extra:
        return extra[path]
    raise ToolError(f"no such file: {path}")


def osv_lookup(record: dict, package: str, version: str = "", catalog: dict | None = None) -> dict:
    advisories = (catalog or {}).get("osv") or {}
    key = f"{package}@{version}" if version else package
    if key in advisories:
        return advisories[key]
    if package in advisories:
        return advisories[package]
    return {"package": package, "version": version, "vulns": []}


def dispatch(name: str, record: dict, payload: dict, catalog: dict | None = None):
    if name == "list_changed_files":
        return list_changed_files(record, catalog)
    if name == "read_file":
        return read_file(record, payload.get("path") or "", catalog)
    if name == "osv_lookup":
        return osv_lookup(record, payload.get("package") or "", payload.get("version") or "", catalog)
    raise ToolError(f"unknown tool: {name}")
