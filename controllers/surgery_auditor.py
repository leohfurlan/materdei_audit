"""
Controller para auditoria de cirurgias comparando com protocolo
"""
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
import pandas as pd
import numpy as np

from models import (
    SurgeryRecord,
    AuditResult,
    ProtocolRulesRepository,
    ProtocolRule,
)
from utils import (
    normalize_text,
    extract_drug_names,
    fuzzy_match_score,
    extract_dose_from_text,
    parse_time,
    calculate_time_diff_minutes,
    clean_procedure_name,
    normalize_yes_no,
    validate_excel_structure,
)
from config import EXCEL_COLUMNS, DRUG_DICTIONARY, AUDIT_CONFIG, REDOSING_INTERVALS

logger = logging.getLogger(__name__)


class SurgeryAuditor:
    """Audita cirurgias comparando com protocolo institucional."""
    
    def __init__(
        self,
        rules_repository: ProtocolRulesRepository,
        config: Dict[str, Any] = None,
        procedure_translation_map: Optional[Dict[str, str]] = None,
    ):
        """
        Inicializa o auditor.
        
        Args:
            rules_repository: Repositório com regras do protocolo
            config: Configurações de auditoria (usa AUDIT_CONFIG se None)
        """
        self.rules_repo = rules_repository
        self.config = config or AUDIT_CONFIG
        self.surgery_records: List[SurgeryRecord] = []
        self.audit_results: List[AuditResult] = []
        self.procedure_translation_map: Dict[str, str] = {}

        if procedure_translation_map:
            for excel_name, protocol_name in procedure_translation_map.items():
                if not excel_name or not protocol_name:
                    continue
                key_norm = normalize_text(str(excel_name))
                if key_norm:
                    self.procedure_translation_map[key_norm] = str(protocol_name).strip()
        
    def load_surgeries_from_excel(self, excel_path: Path, sheet_name: str = None) -> int:
        """
        Carrega registros de cirurgias de planilha Excel.
        
        Args:
            excel_path: Caminho para arquivo Excel
            sheet_name: Nome da aba (None = primeira aba)
            
        Returns:
            Número de registros carregados
        """
        logger.info(f"Carregando cirurgias de: {excel_path}")
        
        # Lê Excel
        df = pd.read_excel(excel_path, sheet_name=sheet_name or 0)
        
        # Valida estrutura
        is_valid, missing = validate_excel_structure(df, EXCEL_COLUMNS)
        if not is_valid:
            logger.warning(f"Colunas faltantes na planilha: {missing}")
        
        # Processa cada linha
        self.surgery_records = []
        for idx, row in df.iterrows():
            try:
                record = self._parse_row_to_surgery(row, idx)
                if record:
                    self.surgery_records.append(record)
            except Exception as e:
                logger.warning(f"Erro ao processar linha {idx}: {e}")
        
        logger.info(f"Carregados {len(self.surgery_records)} registros de cirurgias")
        
        return len(self.surgery_records)
    
    def _parse_row_to_surgery(self, row: pd.Series, idx: int) -> Optional[SurgeryRecord]:
        """
        Parseia linha do Excel para SurgeryRecord.
        
        Args:
            row: Linha do DataFrame
            idx: Índice da linha
            
        Returns:
            SurgeryRecord ou None se inválida
        """
        # Extrai dados
        procedure = str(row.get(EXCEL_COLUMNS['procedure'], '')).strip()
        
        if not procedure or len(procedure) < 3:
            return None
        
        # Data
        date_val = row.get(EXCEL_COLUMNS['date'])
        if isinstance(date_val, str):
            parsed = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%d-%m-%Y'):
                try:
                    parsed = datetime.strptime(date_val.strip(), fmt).date()
                    break
                except:
                    continue
            date_val = parsed
        elif isinstance(date_val, datetime):
            date_val = date_val.date()
        elif isinstance(date_val, pd.Timestamp):
            date_val = date_val.date()
        else:
            # Excel pode fornecer data como número (serial)
            if pd.isna(date_val):
                date_val = None
            elif isinstance(date_val, (int, float, np.number)):
                try:
                    date_val = pd.to_datetime(date_val, unit='D', origin='1899-12-30').date()
                except:
                    date_val = None
        
        # Antibiótico dado
        atb_given = normalize_yes_no(row.get(EXCEL_COLUMNS['atb_given'], 'NAO'))
        atb_name = str(row.get(EXCEL_COLUMNS['atb_name'], '')).strip()
        
        # Detecta medicamentos
        atb_detected = extract_drug_names(atb_name, DRUG_DICTIONARY) if atb_name else []
        
        # Extrai dose
        dose_mg = extract_dose_from_text(atb_name) if atb_name else None
        
        # Horários
        incision_time = parse_time(str(row.get(EXCEL_COLUMNS['incision_time'], '')))
        atb_time = parse_time(str(row.get(EXCEL_COLUMNS['atb_time'], '')))
        repique_time = parse_time(str(row.get(EXCEL_COLUMNS['repique_time'], '')))
        
        # Repique
        repique_done = normalize_yes_no(row.get(EXCEL_COLUMNS['repique'], 'NAO'))
        
        # Peso do paciente
        weight = row.get(EXCEL_COLUMNS.get('patient_weight'))
        if pd.notna(weight):
            try:
                weight = float(weight)
            except:
                weight = None
        else:
            weight = None
        
        # Cria registro
        record = SurgeryRecord(
            date=date_val,
            procedure=procedure,
            specialty=str(row.get(EXCEL_COLUMNS.get('specialty', ''), '')).strip(),
            incision_time=incision_time,
            atb_time=atb_time,
            repique_time=repique_time,
            atb_given=atb_given,
            atb_name=atb_name,
            atb_detected=atb_detected,
            dose_administered_mg=dose_mg,
            repique_done=repique_done,
            patient_weight=weight,
            row_index=int(idx),
        )
        
        return record
    
    def audit_all_surgeries(self) -> List[AuditResult]:
        """
        Audita todas as cirurgias carregadas.
        
        Returns:
            Lista de resultados de auditoria
        """
        logger.info(f"Iniciando auditoria de {len(self.surgery_records)} cirurgias")
        
        self.audit_results = []
        
        for record in self.surgery_records:
            try:
                result = self.audit_surgery(record)
                self.audit_results.append(result)
            except Exception as e:
                logger.error(f"Erro ao auditar cirurgia {record.procedure}: {e}")
                # Cria resultado com erro
                result = AuditResult(surgery_record=record)
                result.conf_final = 'INDETERMINADO'
                result.conf_final_razao = f'Erro na auditoria: {str(e)}'
                self.audit_results.append(result)
        
        logger.info(f"Auditoria concluída: {len(self.audit_results)} resultados")
        
        return self.audit_results
    
    def audit_surgery(self, record: SurgeryRecord) -> AuditResult:
        """
        Audita uma cirurgia individual.
        
        Args:
            record: Registro da cirurgia
            
        Returns:
            Resultado da auditoria
        """
        # Cria resultado
        result = AuditResult(surgery_record=record)
        
        # 1. Faz match com protocolo
        matched_rule, score, method = self._match_with_protocol(record.procedure)
        
        if matched_rule:
            result.matched_rule_id = matched_rule.rule_id
            result.match_score = score
            result.match_method = method
            result.protocolo_secao = matched_rule.section
            result.protocolo_procedimento = matched_rule.procedure
            result.protocolo_requer_profilaxia = matched_rule.is_prophylaxis_required
            
            # Extrai medicamentos recomendados
            result.protocolo_atb_recomendados = [
                drug.name for drug in matched_rule.primary_recommendation.drugs
            ]
            
            # Extrai dose esperada
            if matched_rule.primary_recommendation.drugs:
                result.protocolo_dose_esperada = matched_rule.primary_recommendation.drugs[0].dose or ""
        else:
            result.match_score = 0.0
            result.add_observacao("Procedimento não encontrado no protocolo")
        
        # 2. Valida escolha do antibiótico
        if record.atb_given == 'SIM':
            result.conf_escolha, result.conf_escolha_razao = self._validate_choice(
                record, matched_rule
            )
        else:
            if matched_rule and matched_rule.is_prophylaxis_required:
                result.conf_escolha = 'NAO_CONFORME'
                result.conf_escolha_razao = 'atb_nao_administrado'
            else:
                result.conf_escolha = 'CONFORME'
                result.conf_escolha_razao = 'Profilaxia não requerida'
        
        # 3. Valida dose
        if record.atb_given == 'SIM' and record.dose_administered_mg:
            result.conf_dose, result.conf_dose_razao = self._validate_dose(
                record, matched_rule, result
            )
        else:
            result.conf_dose = 'INDETERMINADO'
            result.conf_dose_razao = 'dose_nao_informada'
        
        # 4. Valida timing
        if record.atb_given == 'SIM':
            result.conf_timing, result.conf_timing_razao = self._validate_timing(
                record, result
            )
        else:
            result.conf_timing = 'INDETERMINADO'
            result.conf_timing_razao = 'atb_nao_administrado'

        # 5. Valida repique (redosing)
        if record.atb_given == 'SIM':
            result.conf_repique, result.conf_repique_razao = self._validate_redosing(
                record, result
            )
        else:
            result.conf_repique = 'INDETERMINADO'
            result.conf_repique_razao = 'atb_nao_administrado'
        
        # 6. Calcula conformidade final
        result.conf_final, result.conf_final_razao = self._calculate_final_conformity(result)
        
        return result
    
    def _match_with_protocol(self, procedure: str) -> Tuple[Optional[ProtocolRule], float, str]:
        """
        Faz match do procedimento com regra do protocolo.
        
        Args:
            procedure: Nome do procedimento
            
        Returns:
            Tupla (regra_matched, score, método)
        """
        if not procedure:
            return None, 0.0, "no_procedure"

        # Prioriza tradução direta (Excel -> nomenclatura do protocolo)
        translated = self._translate_procedure_name(procedure)
        if translated:
            translated_rule, translated_score, translated_method = self._match_translated_procedure(translated)
            if translated_rule:
                return translated_rule, translated_score, translated_method
        
        procedure_clean = clean_procedure_name(procedure)
        
        # Busca exata por procedimento normalizado
        exact_matches = self.rules_repo.find_by_procedure(procedure_clean)
        if exact_matches:
            return exact_matches[0], 1.0, "exact_match"
        
        # Busca fuzzy
        best_rule = None
        best_score = 0.0
        
        threshold = self.config.get('match_threshold', 0.70)
        
        for rule in self.rules_repo.rules:
            score = fuzzy_match_score(procedure_clean, rule.procedure_normalized)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_rule = rule
        
        if best_rule:
            return best_rule, best_score, "fuzzy_match"
        
        return None, 0.0, "no_match"
    

    def _translate_procedure_name(self, procedure: str) -> str:
        """Traduz o procedimento do Excel para nomenclatura do protocolo."""
        if not self.procedure_translation_map:
            return ""

        return self.procedure_translation_map.get(normalize_text(procedure), "")

    def _match_translated_procedure(self, translated_procedure: str) -> Tuple[Optional[ProtocolRule], float, str]:
        """
        Faz match a partir do texto traduzido (procedimentos.json).
        Aceita multiplos alvos separados por "/".
        """
        candidates = [c.strip() for c in re.split(r"/", translated_procedure) if c and c.strip()]
        if not candidates:
            candidates = [translated_procedure]

        for candidate in candidates:
            exact_matches = self.rules_repo.find_by_procedure(normalize_text(candidate))
            if exact_matches:
                return exact_matches[0], 1.0, "translated_exact_match"

        threshold = self.config.get('match_threshold', 0.70)
        best_rule = None
        best_score = 0.0

        for candidate in candidates:
            for rule in self.rules_repo.rules:
                score = fuzzy_match_score(candidate, rule.procedure_normalized)
                if score > best_score and score >= threshold:
                    best_score = score
                    best_rule = rule

        if best_rule:
            return best_rule, best_score, "translated_fuzzy_match"

        return None, 0.0, "translated_no_match"

    def _validate_choice(self, record: SurgeryRecord, 
                        rule: Optional[ProtocolRule]) -> Tuple[str, str]:
        """
        Valida escolha do antibiótico.
        
        Args:
            record: Registro da cirurgia
            rule: Regra do protocolo matched
            
        Returns:
            Tupla (status, razão)
        """
        if not rule:
            return 'INDETERMINADO', 'sem_match_protocolo'
        
        if not rule.is_prophylaxis_required:
            return 'NAO_CONFORME', 'profilaxia_nao_recomendada'
        
        if not record.atb_detected:
            return 'INDETERMINADO', 'atb_nao_identificado'
        
        # Verifica se antibiótico está nas recomendações
        recommended_drugs = [drug.name for drug in rule.primary_recommendation.drugs]
        
        # Também aceita alternativa para alergia
        allergy_drugs = [drug.name for drug in rule.allergy_recommendation.drugs]
        
        all_acceptable = recommended_drugs + allergy_drugs
        
        for detected_drug in record.atb_detected:
            if detected_drug in all_acceptable:
                return 'CONFORME', 'atb_recomendado'
        
        return 'NAO_CONFORME', 'atb_nao_recomendado'
    
    def _validate_dose(self, record: SurgeryRecord, rule: Optional[ProtocolRule],
                      result: AuditResult) -> Tuple[str, str]:
        """
        Valida dose administrada.
        
        Args:
            record: Registro da cirurgia
            rule: Regra do protocolo
            result: Resultado parcial (para preencher dados)
            
        Returns:
            Tupla (status, razão)
        """
        if not rule or not rule.primary_recommendation.drugs:
            return 'INDETERMINADO', 'dose_sem_referencia'
        
        # Pega dose recomendada
        recommended_dose_text = rule.primary_recommendation.drugs[0].dose
        if not recommended_dose_text:
            return 'INDETERMINADO', 'dose_sem_referencia'

        # Converte para mg (inclui dose ponderal mg/kg)
        recommended_dose_mg = None
        mgkg_pattern = r'(\d+(?:\.\d+)?)\s*(MG|G)\s*/\s*KG'
        mgkg_match = re.search(mgkg_pattern, recommended_dose_text, re.IGNORECASE)
        if mgkg_match:
            mg_per_kg = float(mgkg_match.group(1))
            unit = mgkg_match.group(2).upper()
            if unit == 'G':
                mg_per_kg *= 1000

            if not record.patient_weight or record.patient_weight <= 0:
                return 'INDETERMINADO', 'dose_sem_referencia_peso'

            expected_mg = mg_per_kg * record.patient_weight

            # Aplica teto para Cefazolina
            drug_name = rule.primary_recommendation.drugs[0].name if rule.primary_recommendation.drugs else ""
            if drug_name == 'CEFAZOLINA':
                cap_mg = 3000 if record.patient_weight >= 120 else 2000
                expected_mg = min(expected_mg, cap_mg)

            recommended_dose_mg = expected_mg
        else:
            recommended_dose_mg = extract_dose_from_text(recommended_dose_text)
            if not recommended_dose_mg:
                return 'INDETERMINADO', 'dose_sem_referencia'
        
        administered_mg = record.dose_administered_mg
        if not administered_mg:
            return 'INDETERMINADO', 'dose_nao_informada'
        
        # Calcula diferença
        diff_mg = administered_mg - recommended_dose_mg
        diff_pct = (diff_mg / recommended_dose_mg * 100) if recommended_dose_mg > 0 else 0
        
        result.dose_diferenca_mg = diff_mg
        result.dose_diferenca_pct = diff_pct
        
        # Tolerâncias
        alert_tolerance = self.config.get('alert_dose_tolerance_percent', 10)
        tolerance = self.config.get('dose_tolerance_percent', 15)
        
        if abs(diff_pct) <= alert_tolerance:
            return 'CONFORME', 'dose_correta'
        elif abs(diff_pct) <= tolerance:
            return 'ALERTA', 'dose_pequena_diferenca'
        elif diff_pct < -tolerance:
            return 'NAO_CONFORME', 'dose_muito_baixa'
        else:
            return 'NAO_CONFORME', 'dose_muito_alta'
    
    def _validate_timing(self, record: SurgeryRecord, 
                        result: AuditResult) -> Tuple[str, str]:
        """
        Valida timing da administração (1 hora antes da incisão).
        
        Args:
            record: Registro da cirurgia
            result: Resultado parcial
            
        Returns:
            Tupla (status, razão)
        """
        if not record.incision_time or not record.atb_time:
            return 'INDETERMINADO', 'horarios_nao_informados'
        
        # Calcula diferença
        diff_min = calculate_time_diff_minutes(record.atb_time, record.incision_time)
        
        if diff_min is None:
            return 'INDETERMINADO', 'erro_calculo_horario'
        
        result.timing_diferenca_minutos = diff_min
        
        # ATB deve ser dado ANTES da incisão
        if diff_min < 0:
            return 'NAO_CONFORME', 'timing_apos_incisao'
        
        # Janela ideal: até 60 minutos antes
        timing_window = self.config.get('timing_window_minutes', 60)
        
        if 0 <= diff_min <= timing_window:
            return 'CONFORME', 'timing_correto'
        else:
            return 'NAO_CONFORME', 'timing_fora_janela'

    def _validate_redosing(self, record: SurgeryRecord,
                           result: AuditResult) -> Tuple[str, str]:
        """
        Valida repique (redosing) baseado em meia-vida do antibiótico.
        
        Args:
            record: Registro da cirurgia
            result: Resultado parcial
            
        Returns:
            Tupla (status, razão)
        """
        if record.repique_done != 'SIM':
            return 'CONFORME', 'repique_nao_aplicavel'

        drug_name = None
        if record.atb_detected:
            drug_name = record.atb_detected[0]
        elif result.protocolo_atb_recomendados:
            drug_name = result.protocolo_atb_recomendados[0]

        if not drug_name:
            return 'INDETERMINADO', 'atb_nao_identificado'

        interval = REDOSING_INTERVALS.get(drug_name)
        if not interval or interval <= 0:
            return 'CONFORME', 'repique_nao_aplicavel'

        if not record.atb_time or not record.repique_time:
            return 'INDETERMINADO', 'repique_horarios_nao_informados'

        diff_min = calculate_time_diff_minutes(record.atb_time, record.repique_time)
        if diff_min is None:
            return 'INDETERMINADO', 'repique_horarios_nao_informados'

        result.repique_diferenca_minutos = diff_min

        lower = interval - 30
        upper = interval + 30

        if lower <= diff_min <= upper:
            return 'CONFORME', 'repique_no_intervalo'
        return 'NAO_CONFORME', 'repique_fora_intervalo'
    
    def _calculate_final_conformity(self, result: AuditResult) -> Tuple[str, str]:
        """
        Calcula conformidade final com base em todos os critérios.
        
        Args:
            result: Resultado da auditoria
            
        Returns:
            Tupla (status_final, razão)
        """
        # Se não tem match, indeterminado
        if result.match_score == 0.0:
            return 'INDETERMINADO', 'sem_match_protocolo'
        
        # Coleta status de cada critério
        statuses = [
            result.conf_escolha,
            result.conf_dose,
            result.conf_timing,
            result.conf_repique,
        ]
        
        # Se qualquer critério for NAO_CONFORME, final é NAO_CONFORME
        if 'NAO_CONFORME' in statuses:
            reasons = []
            if result.conf_escolha == 'NAO_CONFORME':
                reasons.append(result.conf_escolha_razao)
            if result.conf_dose == 'NAO_CONFORME':
                reasons.append(result.conf_dose_razao)
            if result.conf_timing == 'NAO_CONFORME':
                reasons.append(result.conf_timing_razao)
            if result.conf_repique == 'NAO_CONFORME':
                reasons.append(result.conf_repique_razao)
            
            return 'NAO_CONFORME', ', '.join(reasons)
        
        # Se algum INDETERMINADO
        if 'INDETERMINADO' in statuses:
            return 'INDETERMINADO', 'dados_insuficientes'

        # Se tem ALERTA, final é ALERTA
        if 'ALERTA' in statuses:
            return 'ALERTA', result.conf_dose_razao
        
        # Todos conformes
        return 'CONFORME', 'todos_criterios_conformes'
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Gera estatísticas dos resultados de auditoria.
        
        Returns:
            Dicionário com estatísticas
        """
        if not self.audit_results:
            return {}
        
        total = len(self.audit_results)
        
        # Conformidade final
        conforme = sum(1 for r in self.audit_results if r.conf_final == 'CONFORME')
        alerta = sum(1 for r in self.audit_results if r.conf_final == 'ALERTA')
        nao_conforme = sum(1 for r in self.audit_results if r.conf_final == 'NAO_CONFORME')
        indeterminado = sum(1 for r in self.audit_results if r.conf_final == 'INDETERMINADO')
        
        # Por critério
        escolha_conf = sum(1 for r in self.audit_results if r.conf_escolha == 'CONFORME')
        dose_conf = sum(1 for r in self.audit_results if r.conf_dose == 'CONFORME')
        dose_alert = sum(1 for r in self.audit_results if r.conf_dose == 'ALERTA')
        timing_conf = sum(1 for r in self.audit_results if r.conf_timing == 'CONFORME')
        repique_conf = sum(1 for r in self.audit_results if r.conf_repique == 'CONFORME')
        
        # Match
        perfect_match = sum(1 for r in self.audit_results if r.match_score >= 0.9)
        good_match = sum(1 for r in self.audit_results if 0.7 <= r.match_score < 0.9)
        weak_match = sum(1 for r in self.audit_results if 0 < r.match_score < 0.7)
        no_match = sum(1 for r in self.audit_results if r.match_score == 0)
        
        return {
            'total_cirurgias': total,
            'conformidade_final': {
                'conforme': conforme,
                'alerta': alerta,
                'nao_conforme': nao_conforme,
                'indeterminado': indeterminado,
            },
            'por_criterio': {
                'escolha_conforme': escolha_conf,
                'dose_conforme': dose_conf,
                'dose_alerta': dose_alert,
                'timing_conforme': timing_conf,
                'repique_conforme': repique_conf,
            },
            'qualidade_match': {
                'perfeito': perfect_match,
                'bom': good_match,
                'fraco': weak_match,
                'sem_match': no_match,
            },
            'taxas': {
                'conformidade_total_pct': (conforme + alerta) / total * 100 if total > 0 else 0,
                'conformidade_estrita_pct': conforme / total * 100 if total > 0 else 0,
            }
        }
