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
            rules_repository: RepositÃ³rio com regras do protocolo
            config: ConfiguraÃ§Ãµes de auditoria (usa AUDIT_CONFIG se None)
        """
        self.rules_repo = rules_repository
        self.config = config or AUDIT_CONFIG
        self.surgery_records: List[SurgeryRecord] = []
        self.audit_results: List[AuditResult] = []
        self.procedure_translation_map: Dict[str, str] = {}
        self.excel_columns: Dict[str, str] = {}

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
            NÃºmero de registros carregados
        """
        logger.info(f"Carregando cirurgias de: {excel_path}")
        
        # LÃª Excel
        df = pd.read_excel(excel_path, sheet_name=sheet_name or 0)

        # Resolve mapeamento de colunas por nome exato + nome normalizado
        self.excel_columns = self._resolve_excel_columns(df.columns.tolist())

        required_keys = ["procedure"]
        missing_required = [
            f"{key} ({EXCEL_COLUMNS[key]})" for key in required_keys if key not in self.excel_columns
        ]
        if missing_required:
            raise ValueError(f"Colunas obrigatorias ausentes: {missing_required}")

        optional_keys = [
            "date",
            "specialty",
            "incision_time",
            "atb_given",
            "atb_name",
            "atb_time",
            "repique",
            "repique_time",
            "patient_weight",
        ]
        missing_optional = [
            f"{key} ({EXCEL_COLUMNS[key]})" for key in optional_keys if key not in self.excel_columns
        ]
        if missing_optional:
            logger.warning(f"Colunas opcionais ausentes na planilha: {missing_optional}")
        
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

    def _resolve_excel_columns(self, dataframe_columns: List[Any]) -> Dict[str, str]:
        """Resolve colunas da planilha para as chaves internas esperadas."""
        resolved: Dict[str, str] = {}

        all_columns = [str(col).strip() for col in dataframe_columns]
        exact_lookup = {col: col for col in all_columns if col}

        normalized_lookup: Dict[str, str] = {}
        for col in all_columns:
            norm_col = normalize_text(col)
            if norm_col and norm_col not in normalized_lookup:
                normalized_lookup[norm_col] = col

        aliases = {
            "date": ["dt cirurgia", "data cirurgia", "data da cirurgia"],
            "procedure": ["cirurgia", "procedimento"],
            "specialty": ["especialidade"],
            "incision_time": ["hr incisao", "hora incisao", "hora da incisao"],
            "atb_given": [
                "administracao de antibiotico",
                "administracao de antibioticos",
                "administracao do antibiotico",
            ],
            "atb_name": ["antibiotico", "nome do antibiotico", "atb"],
            "atb_time": [
                "hr antibiotico",
                "hora antibiotico",
                "hora da administracao do atb",
                "hora da administracao de antibiotico",
            ],
            "repique": ["repique"],
            "repique_time": ["hora repique", "hr repique"],
            "patient_weight": ["peso kg", "peso", "peso paciente"],
            "conf_timing": ["conformidade 1 hora"],
            "conf_dose": ["conformidade de dose"],
            "conf_choice": ["conformidade escolha"],
            "conf_final": ["conformidade final"],
        }

        for key, configured_name in EXCEL_COLUMNS.items():
            configured = str(configured_name).strip()

            if configured in exact_lookup:
                resolved[key] = exact_lookup[configured]
                continue

            normalized_configured = normalize_text(configured)
            if normalized_configured in normalized_lookup:
                resolved[key] = normalized_lookup[normalized_configured]
                continue

            for alias in aliases.get(key, []):
                normalized_alias = normalize_text(alias)
                if normalized_alias in normalized_lookup:
                    resolved[key] = normalized_lookup[normalized_alias]
                    break

        return resolved

    def _get_row_value(self, row: pd.Series, key: str, default: Any = None) -> Any:
        """ObtÃ©m valor da linha respeitando mapeamento de coluna resolvido."""
        col_name = self.excel_columns.get(key)
        if not col_name:
            return default

        value = row.get(col_name, default)
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass
        return value

    def _parse_excel_date(self, value: Any) -> Optional[date]:
        """Converte valor de data do Excel para date."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, date):
            return value

        if isinstance(value, (int, float, np.number)):
            try:
                return pd.to_datetime(value, unit="D", origin="1899-12-30").date()
            except Exception:
                return None

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None

            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(cleaned, fmt).date()
                except Exception:
                    continue

            parsed = pd.to_datetime(cleaned, errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                return parsed.date()

        return None

    def _parse_excel_time(self, value: Any) -> Optional[str]:
        """Converte horario do Excel para HH:MM."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.strftime("%H:%M")
        if isinstance(value, pd.Timestamp):
            return value.strftime("%H:%M")
        if hasattr(value, "hour") and hasattr(value, "minute"):
            return f"{int(value.hour):02d}:{int(value.minute):02d}"

        if isinstance(value, (int, float, np.number)):
            fraction = float(value)
            if fraction >= 1:
                fraction = fraction % 1
            if 0 <= fraction < 1:
                total_minutes = int(round(fraction * 24 * 60)) % 1440
                hour = total_minutes // 60
                minute = total_minutes % 60
                return f"{hour:02d}:{minute:02d}"

        return parse_time(str(value))
    
    def _parse_row_to_surgery(self, row: pd.Series, idx: int) -> Optional[SurgeryRecord]:
        """
        Parseia linha do Excel para SurgeryRecord.
        
        Args:
            row: Linha do DataFrame
            idx: Ãndice da linha
            
        Returns:
            SurgeryRecord ou None se invÃ¡lida
        """
        # Extrai dados
        procedure = str(self._get_row_value(row, "procedure", "")).strip()
        
        if not procedure or len(procedure) < 3:
            return None
        
        # Data
        date_val = self._parse_excel_date(self._get_row_value(row, "date"))
        
        # AntibiÃ³tico dado
        atb_given = normalize_yes_no(self._get_row_value(row, "atb_given", "NAO"))
        atb_name = str(self._get_row_value(row, "atb_name", "")).strip()
        
        # Detecta medicamentos
        atb_detected = extract_drug_names(atb_name, DRUG_DICTIONARY) if atb_name else []
        
        # Extrai dose
        dose_mg = extract_dose_from_text(atb_name) if atb_name else None
        
        # HorÃ¡rios
        incision_time = self._parse_excel_time(self._get_row_value(row, "incision_time"))
        atb_time = self._parse_excel_time(self._get_row_value(row, "atb_time"))
        repique_time = self._parse_excel_time(self._get_row_value(row, "repique_time"))
        
        # Repique
        repique_done = normalize_yes_no(self._get_row_value(row, "repique", "NAO"))
        
        # Peso do paciente
        weight = self._get_row_value(row, "patient_weight")
        if weight is not None:
            try:
                weight = float(weight)
            except Exception:
                weight = None
        else:
            weight = None
        
        # Cria registro
        record = SurgeryRecord(
            date=date_val,
            procedure=procedure,
            specialty=str(self._get_row_value(row, "specialty", "")).strip(),
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
        
        logger.info(f"Auditoria concluÃ­da: {len(self.audit_results)} resultados")
        
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
            
            # Extrai medicamentos recomendados (inclui alternativa de alergia)
            primary_drugs = matched_rule.primary_recommendation.drugs if matched_rule.primary_recommendation else []
            allergy_drugs = matched_rule.allergy_recommendation.drugs if matched_rule.allergy_recommendation else []
            result.protocolo_atb_recomendados = [
                drug.name for drug in (primary_drugs + allergy_drugs) if getattr(drug, "name", "")
            ]
            
            # Extrai dose esperada da recomendacao primaria (para referencia em relatorio)
            if primary_drugs:
                result.protocolo_dose_esperada = primary_drugs[0].dose or ""
        else:
            result.match_score = 0.0
            result.add_observacao("Procedimento nao encontrado no protocolo")
        
        # 2. Valida escolha do antibiotico
        if record.atb_given == 'SIM':
            result.conf_escolha, result.conf_escolha_razao = self._validate_choice(
                record, matched_rule
            )
        else:
            if matched_rule and self._rule_requires_prophylaxis(matched_rule):
                result.conf_escolha = 'NAO_CONFORME'
                result.conf_escolha_razao = 'atb_nao_administrado'
            elif not matched_rule:
                result.conf_escolha = 'CONFORME'
                result.conf_escolha_razao = 'sem_match_sem_atb'
            else:
                result.conf_escolha = 'CONFORME'
                result.conf_escolha_razao = 'Profilaxia nao requerida'
        
        # 3. Valida dose
        if record.atb_given == 'SIM' and record.dose_administered_mg:
            result.conf_dose, result.conf_dose_razao = self._validate_dose(
                record, matched_rule, result
            )
        elif record.atb_given == 'SIM':
            result.conf_dose = 'INDETERMINADO'
            result.conf_dose_razao = 'dose_nao_informada'
        else:
            result.conf_dose = 'CONFORME'
            result.conf_dose_razao = 'criterio_nao_aplicavel'
        
        # 4. Valida timing
        if record.atb_given == 'SIM':
            result.conf_timing, result.conf_timing_razao = self._validate_timing(
                record, result
            )
        else:
            result.conf_timing = 'CONFORME'
            result.conf_timing_razao = 'criterio_nao_aplicavel'

        # 5. Valida repique (redosing)
        if record.atb_given == 'SIM':
            result.conf_repique, result.conf_repique_razao = self._validate_redosing(
                record, result
            )
        else:
            result.conf_repique = 'CONFORME'
            result.conf_repique_razao = 'criterio_nao_aplicavel'
        
        # 6. Calcula conformidade final
        result.conf_final, result.conf_final_razao = self._calculate_final_conformity(result)
        
        return result
    def _match_with_protocol(self, procedure: str) -> Tuple[Optional[ProtocolRule], float, str]:
        """
        Faz match do procedimento com regra do protocolo.
        
        Args:
            procedure: Nome do procedimento
            
        Returns:
            Tupla (regra_matched, score, mÃ©todo)
        """
        if not procedure:
            return None, 0.0, "no_procedure"

        # Prioriza traduÃ§Ã£o direta (Excel -> nomenclatura do protocolo)
        translated = self._translate_procedure_name(procedure)
        if translated:
            translated_rule, translated_score, translated_method = self._match_translated_procedure(
                translated_procedure=translated,
                source_procedure=procedure,
            )
            if translated_rule:
                return translated_rule, translated_score, translated_method
        
        procedure_clean = clean_procedure_name(procedure)
        
        # Busca exata por procedimento normalizado
        exact_matches = self.rules_repo.find_by_procedure(procedure_clean)
        if exact_matches:
            return exact_matches[0], 1.0, "exact_match"

        # Busca exata por aliases das regras extraidas por LLM (quando disponiveis).
        for rule in self.rules_repo.rules:
            aliases = getattr(rule, "surgery_name", []) or []
            for alias in aliases:
                if normalize_text(str(alias)) == procedure_clean:
                    return rule, 1.0, "alias_match"
        
        # Busca fuzzy
        best_rule = None
        best_score = 0.0
        
        threshold = self.config.get('match_threshold', 0.70)
        
        for rule in self.rules_repo.rules:
            targets = [rule.procedure_normalized]
            aliases = getattr(rule, "surgery_name", []) or []
            targets.extend(normalize_text(str(alias)) for alias in aliases if str(alias).strip())

            for target in targets:
                score = fuzzy_match_score(procedure_clean, target)
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

    def _is_translation_candidate_plausible(self, source_procedure: str, candidate: str) -> bool:
        """
        Evita matches absurdos vindos de traducao de procedimentos.
        """
        source_clean = clean_procedure_name(source_procedure)
        candidate_clean = clean_procedure_name(candidate)

        if not source_clean or not candidate_clean:
            return False

        if source_clean in candidate_clean or candidate_clean in source_clean:
            return True

        similarity = fuzzy_match_score(source_clean, candidate_clean)
        threshold = float(self.config.get("translation_match_similarity_threshold", 0.45))
        return similarity >= threshold

    def _match_translated_procedure(
        self,
        translated_procedure: str,
        source_procedure: Optional[str] = None,
    ) -> Tuple[Optional[ProtocolRule], float, str]:
        """
        Faz match a partir do texto traduzido (procedimentos.json).
        Aceita multiplos alvos separados por "/".
        """
        candidates = [c.strip() for c in re.split(r"/", translated_procedure) if c and c.strip()]
        if not candidates:
            candidates = [translated_procedure]

        for candidate in candidates:
            if source_procedure and not self._is_translation_candidate_plausible(source_procedure, candidate):
                continue
            exact_matches = self.rules_repo.find_by_procedure(normalize_text(candidate))
            if exact_matches:
                return exact_matches[0], 1.0, "translated_exact_match"

        # Busca exata por aliases (surgery_name), quando disponiveis nas regras LLM.
        for candidate in candidates:
            if source_procedure and not self._is_translation_candidate_plausible(source_procedure, candidate):
                continue
            candidate_norm = normalize_text(candidate)
            for rule in self.rules_repo.rules:
                aliases = getattr(rule, "surgery_name", []) or []
                for alias in aliases:
                    if normalize_text(str(alias)) == candidate_norm:
                        return rule, 1.0, "translated_alias_match"

        threshold = self.config.get('match_threshold', 0.70)
        best_rule = None
        best_score = 0.0

        for candidate in candidates:
            if source_procedure and not self._is_translation_candidate_plausible(source_procedure, candidate):
                continue
            for rule in self.rules_repo.rules:
                targets = [rule.procedure_normalized]
                aliases = getattr(rule, "surgery_name", []) or []
                targets.extend(normalize_text(str(alias)) for alias in aliases if str(alias).strip())

                for target in targets:
                    score = fuzzy_match_score(candidate, target)
                    if score > best_score and score >= threshold:
                        best_score = score
                        best_rule = rule

        if best_rule:
            return best_rule, best_score, "translated_fuzzy_match"

        return None, 0.0, "translated_no_match"

    def _validate_choice(self, record: SurgeryRecord, 
                        rule: Optional[ProtocolRule]) -> Tuple[str, str]:
        """
        Valida escolha do antibiotico.
        
        Args:
            record: Registro da cirurgia
            rule: Regra do protocolo matched
            
        Returns:
            Tupla (status, razao)
        """
        if not rule:
            return 'INDETERMINADO', 'sem_match_protocolo'

        recommended_drugs = self._get_recommendation_drugs(rule)
        if not recommended_drugs:
            if not self._rule_requires_prophylaxis(rule):
                return 'ALERTA', 'profilaxia_potencial_sem_indicacao'
            return 'INDETERMINADO', 'atb_sem_referencia_protocolo'
        
        if not record.atb_detected:
            return 'INDETERMINADO', 'atb_nao_identificado'

        acceptable_names = [drug.name for drug in recommended_drugs]
        for detected_drug in record.atb_detected:
            if detected_drug in acceptable_names:
                return 'CONFORME', 'atb_recomendado'

        if not self._rule_requires_prophylaxis(rule):
            return 'ALERTA', 'profilaxia_potencial_sem_indicacao'

        return 'NAO_CONFORME', 'atb_nao_recomendado'

    def _get_recommendation_drugs(self, rule: Optional[ProtocolRule]) -> List[Any]:
        """Retorna lista consolidada de antibioticos das recomendacoes primaria e alergia."""
        if not rule:
            return []

        primary = rule.primary_recommendation.drugs if rule.primary_recommendation else []
        allergy = rule.allergy_recommendation.drugs if rule.allergy_recommendation else []
        return [drug for drug in (primary + allergy) if getattr(drug, "name", "")]

    def _rule_requires_prophylaxis(self, rule: Optional[ProtocolRule]) -> bool:
        """Infere necessidade de profilaxia considerando flags e recomendacoes preenchidas."""
        if not rule:
            return False
        if rule.is_prophylaxis_required:
            return True
        return bool(self._get_recommendation_drugs(rule))

    def _select_reference_drug(self, record: SurgeryRecord, rule: Optional[ProtocolRule]) -> Optional[Any]:
        """
        Seleciona o antibiotico de referencia para comparar dose.
        Prioriza antibiotico administrado identificado na prescricao.
        """
        candidates = self._get_recommendation_drugs(rule)
        if not candidates:
            return None

        if record.atb_detected:
            for detected in record.atb_detected:
                for drug in candidates:
                    if drug.name == detected:
                        return drug

        return candidates[0]

    def _validate_dose(self, record: SurgeryRecord, rule: Optional[ProtocolRule],
                      result: AuditResult) -> Tuple[str, str]:
        """
        Valida dose administrada.
        
        Args:
            record: Registro da cirurgia
            rule: Regra do protocolo
            result: Resultado parcial (para preencher dados)
            
        Returns:
            Tupla (status, razao)
        """
        if not rule:
            return 'INDETERMINADO', 'dose_sem_referencia'

        reference_drug = self._select_reference_drug(record, rule)
        if not reference_drug:
            return 'INDETERMINADO', 'dose_sem_referencia'

        # Pega dose recomendada para o antibiotico efetivamente administrado.
        recommended_dose_text = reference_drug.dose
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
            if reference_drug.name == 'CEFAZOLINA':
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
        
        # Calcula diferenca
        diff_mg = administered_mg - recommended_dose_mg
        diff_pct = (diff_mg / recommended_dose_mg * 100) if recommended_dose_mg > 0 else 0
        
        result.dose_diferenca_mg = diff_mg
        result.dose_diferenca_pct = diff_pct
        
        # Tolerancias
        alert_tolerance = self.config.get('alert_dose_tolerance_percent', 10)
        tolerance = self.config.get('dose_tolerance_percent', 15)
        hard_tolerance = self.config.get('hard_dose_tolerance_percent', 100)
        
        if abs(diff_pct) <= alert_tolerance:
            return 'CONFORME', 'dose_correta'
        elif abs(diff_pct) <= tolerance:
            return 'ALERTA', 'dose_pequena_diferenca'
        elif abs(diff_pct) <= hard_tolerance:
            return 'ALERTA', 'dose_fora_referencia'
        elif diff_pct < -tolerance:
            return 'NAO_CONFORME', 'dose_muito_baixa'
        else:
            return 'NAO_CONFORME', 'dose_muito_alta'
    def _validate_timing(self, record: SurgeryRecord, 
                        result: AuditResult) -> Tuple[str, str]:
        """
        Valida timing da administraÃ§Ã£o (1 hora antes da incisÃ£o).
        
        Args:
            record: Registro da cirurgia
            result: Resultado parcial
            
        Returns:
            Tupla (status, razÃ£o)
        """
        if not record.incision_time or not record.atb_time:
            return 'INDETERMINADO', 'horarios_nao_informados'
        
        # Calcula diferenÃ§a
        diff_min = calculate_time_diff_minutes(record.atb_time, record.incision_time)
        
        if diff_min is None:
            return 'INDETERMINADO', 'erro_calculo_horario'
        
        result.timing_diferenca_minutos = diff_min
        
        # ATB deve ser dado ANTES da incisÃ£o
        if diff_min < 0:
            return 'NAO_CONFORME', 'timing_apos_incisao'
        
        # Janela ideal: atÃ© 60 minutos antes
        timing_window = self.config.get('timing_window_minutes', 60)
        
        if 0 <= diff_min <= timing_window:
            return 'CONFORME', 'timing_correto'
        else:
            return 'NAO_CONFORME', 'timing_fora_janela'

    def _validate_redosing(self, record: SurgeryRecord,
                           result: AuditResult) -> Tuple[str, str]:
        """
        Valida repique (redosing) baseado em meia-vida do antibiÃ³tico.
        
        Args:
            record: Registro da cirurgia
            result: Resultado parcial
            
        Returns:
            Tupla (status, razÃ£o)
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
        Calcula conformidade final com base em todos os criterios.
        
        Args:
            result: Resultado da auditoria
            
        Returns:
            Tupla (status_final, razao)
        """
        # Coleta status de cada criterio
        statuses = [
            result.conf_escolha,
            result.conf_dose,
            result.conf_timing,
            result.conf_repique,
        ]

        # Escolha do ATB e match do procedimento sao criterios gate.
        if result.conf_escolha == 'INDETERMINADO':
            if result.match_score == 0.0:
                return 'ALERTA', 'sem_match_protocolo'
            return 'ALERTA', result.conf_escolha_razao or 'dados_insuficientes'
        
        # Se qualquer criterio for NAO_CONFORME, final e NAO_CONFORME
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

        # Se tem ALERTA, final e ALERTA
        if 'ALERTA' in statuses:
            if result.conf_dose == 'ALERTA':
                return 'ALERTA', result.conf_dose_razao
            if result.conf_escolha == 'ALERTA':
                return 'ALERTA', result.conf_escolha_razao
            return 'ALERTA', 'alerta_validacao'
        
        # INDETERMINADO em criterios secundarios (dose/timing/repique) nao derruba o status final.
        return 'CONFORME', 'todos_criterios_conformes'
    def get_statistics(self) -> Dict[str, Any]:
        """
        Gera estatÃ­sticas dos resultados de auditoria.
        
        Returns:
            DicionÃ¡rio com estatÃ­sticas
        """
        if not self.audit_results:
            return {}
        
        total = len(self.audit_results)
        
        # Conformidade final
        conforme = sum(1 for r in self.audit_results if r.conf_final == 'CONFORME')
        alerta = sum(1 for r in self.audit_results if r.conf_final == 'ALERTA')
        nao_conforme = sum(1 for r in self.audit_results if r.conf_final == 'NAO_CONFORME')
        indeterminado = sum(1 for r in self.audit_results if r.conf_final == 'INDETERMINADO')
        
        # Por critÃ©rio
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

