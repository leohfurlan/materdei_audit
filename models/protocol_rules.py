"""
Model para regras do protocolo de profilaxia antimicrobiana
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import hashlib
from datetime import datetime
from enum import Enum

@dataclass
class AntibioticRule:
    """Regra para antibiótico específico."""
    name: str
    dose: str
    route: str
    time: str

class SurgeryType(Enum):
    """Tipos de cirurgia (classificação de contaminação)."""
    CLEAN = "Limpa"
    CLEAN_CONTAMINATED = "Limpa-contaminada"
    CONTAMINATED = "Contaminada"
    INFECTED = "Infectada"
    DIRTY = "Sura/Infectada"  # Ajuste conforme necessidade



@dataclass
class Drug:
    """Representa um medicamento."""
    name: str
    dose: Optional[str] = None
    route: Optional[str] = None
    timing: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'dose': self.dose,
            'route': self.route,
            'timing': self.timing,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Drug':
        return cls(
            name=data.get('name', ''),
            dose=data.get('dose'),
            route=data.get('route'),
            timing=data.get('timing'),
        )


@dataclass
class Recommendation:
    """Representa uma recomendação de profilaxia."""
    drugs: List[Drug] = field(default_factory=list)
    raw_text: str = ""
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'drugs': [d.to_dict() for d in self.drugs],
            'raw_text': self.raw_text,
            'notes': self.notes,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Recommendation':
        drugs = [Drug.from_dict(d) for d in data.get('drugs', [])]
        return cls(
            drugs=drugs,
            raw_text=data.get('raw_text', ''),
            notes=data.get('notes', ''),
        )

@dataclass
class ProtocolRule:
    """Representa uma regra do protocolo."""
    rule_id: str = ""
    section: str = ""
    procedure: str = ""
    procedure_normalized: str = ""
    is_prophylaxis_required: bool = False
    primary_recommendation: Recommendation = field(default_factory=Recommendation)
    allergy_recommendation: Recommendation = field(default_factory=Recommendation)
    postoperative: str = ""
    audit_category: str = "OK"
    original_row_index: int = -1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Novos campos para suporte a LLM
    surgery_name: List[str] = field(default_factory=list)
    surgery_type: Optional[SurgeryType] = None
    antibiotics: List[AntibioticRule] = field(default_factory=list)
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'rule_id': self.rule_id,
            'section': self.section,
            'procedure': self.procedure,
            'procedure_normalized': self.procedure_normalized,
            'is_prophylaxis_required': self.is_prophylaxis_required,
            'primary_recommendation': self.primary_recommendation.to_dict(),
            'allergy_recommendation': self.allergy_recommendation.to_dict(),
            'postoperative': self.postoperative,
            'audit_category': self.audit_category,
            'original_row_index': self.original_row_index,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProtocolRule':
        return cls(
            rule_id=data.get('rule_id', ''),
            section=data.get('section', ''),
            procedure=data.get('procedure', ''),
            procedure_normalized=data.get('procedure_normalized', ''),
            is_prophylaxis_required=data.get('is_prophylaxis_required', False),
            primary_recommendation=Recommendation.from_dict(data.get('primary_recommendation', {})),
            allergy_recommendation=Recommendation.from_dict(data.get('allergy_recommendation', {})),
            postoperative=data.get('postoperative', ''),
            audit_category=data.get('audit_category', 'OK'),
            original_row_index=data.get('original_row_index', -1),
            metadata=data.get('metadata', {}),
        )


class ProtocolRulesRepository:
    """Repositório para gerenciar regras do protocolo."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.rules: List[ProtocolRule] = []
        self._index: Dict[str, List[str]] = {}  # normalized_procedure -> [rule_ids]
        self._metadata: Dict[str, Any] = {}
        self._is_loaded: bool = False
        self._initialized = True
    
    def load_from_json(self, filepath: Path) -> None:
        """
        Carrega regras de um arquivo JSON.
        
        Args:
            filepath: Caminho para o arquivo rules.json
        """
        if self._is_loaded:
            return
        with open(filepath, 'r', encoding='utf-8') as f:
            rules_data = json.load(f)
        
        self.rules = [ProtocolRule.from_dict(r) for r in rules_data]
        self._build_index()
        self._load_metadata(filepath)
        self._is_loaded = True
    
    def save_to_json(self, filepath: Path) -> None:
        """
        Salva regras em arquivo JSON.
        
        Args:
            filepath: Caminho para salvar rules.json
        """
        rules_data = [r.to_dict() for r in self.rules]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(rules_data, f, ensure_ascii=False, indent=2)
        
        # Salva também o índice e metadados
        self._save_index(filepath.parent / 'rules_index.json')
        self._save_metadata(filepath.parent / 'rules.meta.json', filepath)
    
    def _build_index(self) -> None:
        """Constrói índice para busca rápida."""
        self._index = {}
        for rule in self.rules:
            key = rule.procedure_normalized
            if key:
                self._index.setdefault(key, []).append(rule.rule_id)
    
    def _save_index(self, filepath: Path) -> None:
        """Salva índice em arquivo JSON."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
    
    def _load_metadata(self, rules_filepath: Path) -> None:
        """Carrega metadados do arquivo."""
        meta_path = rules_filepath.parent / 'rules.meta.json'
        if meta_path.exists():
            with open(meta_path, 'r', encoding='utf-8') as f:
                self._metadata = json.load(f)
    
    def _save_metadata(self, filepath: Path, rules_filepath: Path) -> None:
        """Salva metadados."""
        # Calcula hash SHA256 das regras
        with open(rules_filepath, 'rb') as f:
            sha256_hash = hashlib.sha256(f.read()).hexdigest()
        
        metadata = {
            'sha256': sha256_hash,
            'rules_count': len(self.rules),
            'index_keys': len(self._index),
            'generated_at': datetime.utcnow().isoformat(),
            'extraction_method': 'camelot_multi_strategy',
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        self._metadata = metadata
    
    def find_by_procedure(self, procedure: str) -> List[ProtocolRule]:
        """
        Busca regras por nome de procedimento normalizado.
        
        Args:
            procedure: Nome do procedimento normalizado
            
        Returns:
            Lista de regras que correspondem ao procedimento
        """
        rule_ids = self._index.get(procedure, [])
        return [r for r in self.rules if r.rule_id in rule_ids]
    
    def get_by_id(self, rule_id: str) -> Optional[ProtocolRule]:
        """
        Busca regra por ID.
        
        Args:
            rule_id: ID da regra
            
        Returns:
            Regra encontrada ou None
        """
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None
    
    def get_all_procedures(self) -> List[str]:
        """
        Retorna lista de todos os procedimentos normalizados.
        
        Returns:
            Lista de procedimentos
        """
        return list(self._index.keys())
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas das regras.
        
        Returns:
            Dicionário com estatísticas
        """
        total = len(self.rules)
        prophylaxis_required = sum(1 for r in self.rules if r.is_prophylaxis_required)
        
        sections = {}
        for rule in self.rules:
            sections[rule.section] = sections.get(rule.section, 0) + 1
        
        return {
            'total_rules': total,
            'prophylaxis_required': prophylaxis_required,
            'prophylaxis_not_required': total - prophylaxis_required,
            'sections': sections,
            'metadata': self._metadata,
        }
