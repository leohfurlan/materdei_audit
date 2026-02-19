from __future__ import annotations

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator


class MatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_score_auto: float = Field(default=0.45, ge=0, le=1)
    min_score_review: float = Field(default=0.35, ge=0, le=1)
    top_k_candidates: int = Field(default=5, ge=1, le=20)
    use_specialty: bool = True


class NormalizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strip_accents: bool = True
    lowercase: bool = True
    remove_stopwords: bool = True


class AliasesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    procedure_aliases_path: Optional[str] = None
    drug_aliases_path: Optional[str] = None
    procedure_map_path: Optional[str] = None


class ColumnsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    map_path: str


class AuditJobConfig(BaseModel):
    """
    Input principal do job de auditoria.
    """
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    excel_path: str
    sheet_name: Optional[str] = None
    rules_path: str
    output_dir: str = "./data/output"

    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)
    aliases: AliasesConfig = Field(default_factory=AliasesConfig)
    columns: ColumnsConfig

    @field_validator("excel_path", "rules_path", "output_dir")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("campo obrigatório vazio")
        return v


class ColumnMap(BaseModel):
    """
    Mapa de colunas do Excel -> campos canônicos.
    """
    model_config = ConfigDict(extra="forbid")

    procedure: str
    specialty: Optional[str] = None

    incision_datetime: Optional[str] = None

    antibiotic_name: Optional[str] = None
    antibiotic_dose: Optional[str] = None
    antibiotic_dose_unit: Optional[str] = None
    antibiotic_route: Optional[str] = None
    admin_datetime: Optional[str] = None

    patient_weight_kg: Optional[str] = None
    patient_age_years: Optional[str] = None
    patient_sex: Optional[str] = None

    redose_1_datetime: Optional[str] = None
    redose_2_datetime: Optional[str] = None


class CandidateRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: Any
    score: float = Field(ge=0, le=1)
    procedure: Optional[str] = None


class ProcedureMapItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    best_rule_id: Optional[Any] = None
    best_score: Optional[float] = Field(default=None, ge=0, le=1)
    candidates: List[CandidateRule] = Field(default_factory=list)


ProcedureMap = Dict[str, ProcedureMapItem]
DrugAliases = Dict[str, List[str]]
ProcedureAliases = Dict[str, List[str]]
