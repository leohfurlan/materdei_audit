import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml  # type: ignore

from models.inputs import AuditJobConfig, ColumnMap, ProcedureMapItem


_PROCEDURE_MAP_VERSION_RE = re.compile(r"^(?P<base>.+)_v(?P<version>\d+)$", re.IGNORECASE)


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_audit_job(path: str) -> AuditJobConfig:
    data = load_yaml(path)
    return AuditJobConfig.model_validate(data)


def load_column_map(path: str) -> ColumnMap:
    data = load_yaml(path)
    return ColumnMap.model_validate(data)


def load_procedure_map(path: str) -> dict:
    raw = load_json(path)
    out = {}
    for k, v in raw.items():
        out[k] = ProcedureMapItem.model_validate(v)
    return out


def _split_versioned_map_name(path: Path) -> Tuple[str, Optional[int]]:
    match = _PROCEDURE_MAP_VERSION_RE.match(path.stem)
    if not match:
        return path.stem, None
    return match.group("base"), int(match.group("version"))


def _format_map_version(version: Any) -> str:
    if version in (None, ""):
        return ""
    if isinstance(version, int):
        return f"v{version}"

    version_str = str(version).strip()
    if not version_str:
        return ""
    if version_str.lower().startswith("v"):
        return version_str
    if version_str.isdigit():
        return f"v{version_str}"
    return version_str


def resolve_procedure_translation_map_path(
    path: str | Path,
    version: Optional[str] = None,
) -> Tuple[Path, Dict[str, Any]]:
    requested_path = Path(path)
    requested_version = str(version or "current").strip().lower()
    base_stem, _ = _split_versioned_map_name(requested_path)
    suffix = requested_path.suffix or ".json"
    versioned_candidates = []

    for candidate in requested_path.parent.glob(f"{base_stem}_v*{suffix}"):
        _, candidate_version = _split_versioned_map_name(candidate)
        if candidate_version is not None:
            versioned_candidates.append((candidate_version, candidate))

    versioned_candidates.sort(key=lambda item: item[0])

    if requested_version in {"", "current"}:
        if not requested_path.exists():
            raise FileNotFoundError(f"Arquivo de mapeamento nao encontrado: {requested_path}")
        return requested_path, {
            "requested_version": "current",
            "resolved_version": "current",
        }

    if requested_version == "latest":
        if not versioned_candidates:
            raise FileNotFoundError(
                f"Nenhuma versao encontrada para o mapeamento base: {requested_path}"
            )
        latest_version, latest_path = versioned_candidates[-1]
        return latest_path, {
            "requested_version": "latest",
            "resolved_version": _format_map_version(latest_version),
        }

    normalized_version = requested_version[1:] if requested_version.startswith("v") else requested_version
    if not normalized_version.isdigit():
        raise ValueError(
            "Versao de mapeamento invalida. Use 'current', 'latest' ou um numero inteiro."
        )

    version_number = int(normalized_version)
    resolved_path = requested_path.with_name(f"{base_stem}_v{version_number}{suffix}")
    if not resolved_path.exists():
        raise FileNotFoundError(f"Versao solicitada do mapeamento nao encontrada: {resolved_path}")

    return resolved_path, {
        "requested_version": _format_map_version(version_number),
        "resolved_version": _format_map_version(version_number),
    }


def load_procedure_translation_map(
    path: str | Path,
    version: Optional[str] = None,
) -> Tuple[Dict[str, str], Dict[str, Any]]:
    resolved_path, resolution = resolve_procedure_translation_map_path(path, version)
    raw = load_json(str(resolved_path))

    metadata: Dict[str, Any] = {
        "requested_path": str(path),
        "resolved_path": str(resolved_path),
        "requested_version": resolution.get("requested_version", "current"),
        "map_version": resolution.get("resolved_version", "current"),
        "format": "legacy",
    }

    mappings: Dict[str, Any]
    if isinstance(raw, dict) and isinstance(raw.get("mappings"), dict):
        mappings = raw["mappings"]
        metadata["format"] = "versioned"

        raw_metadata = raw.get("metadata")
        if isinstance(raw_metadata, dict):
            explicit_version = raw_metadata.get("version")
            if explicit_version not in (None, ""):
                metadata["map_version"] = _format_map_version(explicit_version)
            for key in ("description", "generated_at", "source_file"):
                if raw_metadata.get(key):
                    metadata[key] = raw_metadata[key]
    elif isinstance(raw, dict):
        mappings = raw
    else:
        raise ValueError(f"Formato invalido para mapeamento de procedimentos: {resolved_path}")

    cleaned_mappings = {
        str(key).strip(): str(value).strip()
        for key, value in mappings.items()
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip()
    }

    return cleaned_mappings, metadata
