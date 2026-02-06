"""
Model para dados de auditoria de cirurgias
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, date


@dataclass
class SurgeryRecord:
    """Representa um registro de cirurgia para auditoria."""
    
    # Dados básicos
    date: Optional[date] = None
    procedure: str = ""
    specialty: str = ""
    
    # Horários
    incision_time: Optional[str] = None  # HH:MM
    atb_time: Optional[str] = None  # HH:MM
    repique_time: Optional[str] = None  # HH:MM
    
    # Antibiótico
    atb_given: str = "NAO"  # SIM ou NAO
    atb_name: str = ""
    atb_detected: List[str] = field(default_factory=list)  # Nomes detectados
    dose_administered_mg: Optional[float] = None
    
    # Repique
    repique_done: str = "NAO"  # SIM ou NAO
    
    # Dados do paciente
    patient_weight: Optional[float] = None
    
    # Conformidade (se já calculada na planilha)
    conf_timing: Optional[str] = None
    conf_dose: Optional[str] = None
    conf_choice: Optional[str] = None
    conf_final: Optional[str] = None
    
    # Metadados
    row_index: int = -1  # Índice da linha no Excel original
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            'date': self.date.isoformat() if self.date else None,
            'procedure': self.procedure,
            'specialty': self.specialty,
            'incision_time': self.incision_time,
            'atb_time': self.atb_time,
            'repique_time': self.repique_time,
            'atb_given': self.atb_given,
            'atb_name': self.atb_name,
            'atb_detected': self.atb_detected,
            'dose_administered_mg': self.dose_administered_mg,
            'repique_done': self.repique_done,
            'patient_weight': self.patient_weight,
            'conf_timing': self.conf_timing,
            'conf_dose': self.conf_dose,
            'conf_choice': self.conf_choice,
            'conf_final': self.conf_final,
            'row_index': self.row_index,
        }


@dataclass
class AuditResult:
    """Representa o resultado da auditoria de uma cirurgia."""
    
    # Referência ao registro original
    surgery_record: SurgeryRecord
    
    # Match com protocolo
    matched_rule_id: Optional[str] = None
    match_score: float = 0.0
    match_method: str = ""
    
    # Conformidade calculada
    conf_escolha: str = "INDETERMINADO"
    conf_escolha_razao: str = ""
    
    conf_dose: str = "INDETERMINADO"
    conf_dose_razao: str = ""
    
    conf_timing: str = "INDETERMINADO"
    conf_timing_razao: str = ""

    conf_repique: str = "INDETERMINADO"
    conf_repique_razao: str = ""
    
    conf_final: str = "INDETERMINADO"
    conf_final_razao: str = ""
    
    # Dados do protocolo (para referência)
    protocolo_secao: str = ""
    protocolo_procedimento: str = ""
    protocolo_requer_profilaxia: bool = False
    protocolo_atb_recomendados: List[str] = field(default_factory=list)
    protocolo_dose_esperada: str = ""
    
    # Análise de dose
    dose_diferenca_mg: Optional[float] = None
    dose_diferenca_pct: Optional[float] = None
    
    # Análise de timing
    timing_diferenca_minutos: Optional[int] = None

    # Análise de repique
    repique_diferenca_minutos: Optional[int] = None
    
    # Observações
    observacoes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        result = {
            # Dados do registro original
            'data': self.surgery_record.date.isoformat() if self.surgery_record.date else None,
            'procedimento': self.surgery_record.procedure,
            'especialidade': self.surgery_record.specialty,
            'hr_incisao': self.surgery_record.incision_time,
            'atb_administrado': self.surgery_record.atb_given,
            'atb_nome': self.surgery_record.atb_name,
            'atb_detectado': ', '.join(self.surgery_record.atb_detected),
            'hr_atb': self.surgery_record.atb_time,
            'dose_administrada_mg': self.surgery_record.dose_administered_mg,
            'peso_paciente_kg': self.surgery_record.patient_weight,
            'repique': self.surgery_record.repique_done,
            'hr_repique': self.surgery_record.repique_time,
            
            # Match
            'match_rule_id': self.matched_rule_id,
            'match_score': self.match_score,
            'match_method': self.match_method,
            
            # Protocolo
            'protocolo_secao': self.protocolo_secao,
            'protocolo_procedimento': self.protocolo_procedimento,
            'protocolo_requer_profilaxia': self.protocolo_requer_profilaxia,
            'protocolo_atb_recomendados': ', '.join(self.protocolo_atb_recomendados),
            'protocolo_dose_esperada': self.protocolo_dose_esperada,
            
            # Conformidade
            'conf_escolha': self.conf_escolha,
            'conf_escolha_razao': self.conf_escolha_razao,
            'conf_dose': self.conf_dose,
            'conf_dose_razao': self.conf_dose_razao,
            'conf_timing': self.conf_timing,
            'conf_timing_razao': self.conf_timing_razao,
            'conf_repique': self.conf_repique,
            'conf_repique_razao': self.conf_repique_razao,
            'conf_final': self.conf_final,
            'conf_final_razao': self.conf_final_razao,
            
            # Análises
            'dose_diferenca_mg': self.dose_diferenca_mg,
            'dose_diferenca_pct': self.dose_diferenca_pct,
            'timing_diferenca_minutos': self.timing_diferenca_minutos,
            'repique_diferenca_minutos': self.repique_diferenca_minutos,
            
            # Observações
            'observacoes': '; '.join(self.observacoes),
            
            # Metadados
            'row_index': self.surgery_record.row_index,
        }
        
        return result
    
    def add_observacao(self, obs: str) -> None:
        """Adiciona uma observação ao resultado."""
        if obs and obs not in self.observacoes:
            self.observacoes.append(obs)
    
    def is_conforme(self) -> bool:
        """Verifica se o resultado está conforme (incluindo alertas)."""
        return self.conf_final in ['CONFORME', 'ALERTA']
    
    def is_nao_conforme(self) -> bool:
        """Verifica se o resultado está não conforme."""
        return self.conf_final == 'NAO_CONFORME'
