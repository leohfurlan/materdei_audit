import json
from pathlib import Path
import yaml # type: ignore

from models.inputs import AuditJobConfig, ColumnMap, ProcedureMapItem


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
    # valida item a item (pra não explodir o job todo)
    out = {}
    for k, v in raw.items():
        out[k] = ProcedureMapItem.model_validate(v)
    return out
