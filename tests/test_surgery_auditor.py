import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from controllers.report_generator import ReportGenerator
from controllers.surgery_auditor import SurgeryAuditor
from models import (
    ProtocolRulesRepository,
    ProtocolRule,
    Recommendation,
    Drug,
    SurgeryRecord,
    AuditResult,
)
from config import AUDIT_CONFIG
from utils import extract_documented_antibiotics


class TestSurgeryAuditorCalibration(unittest.TestCase):
    def setUp(self):
        # Reset singleton state for deterministic tests.
        self.repo = ProtocolRulesRepository()
        self.repo.rules = []
        self.repo._index = {}
        self.repo._metadata = {}
        self.repo._is_loaded = True

    def _build_auditor_with_rule(self, rule: ProtocolRule) -> SurgeryAuditor:
        self.repo.rules = [rule]
        self.repo._build_index()
        return SurgeryAuditor(self.repo, AUDIT_CONFIG)

    def _build_auditor_with_rules(
        self,
        rules: list[ProtocolRule],
        procedure_translation_map: dict[str, str] | None = None,
    ) -> SurgeryAuditor:
        self.repo.rules = rules
        self.repo._build_index()
        return SurgeryAuditor(
            self.repo,
            AUDIT_CONFIG,
            procedure_translation_map=procedure_translation_map,
        )

    def _build_auditor_with_rule_and_map(
        self,
        rule: ProtocolRule,
        procedure_translation_map: dict[str, str],
    ) -> SurgeryAuditor:
        self.repo.rules = [rule]
        self.repo._build_index()
        return SurgeryAuditor(
            self.repo,
            AUDIT_CONFIG,
            procedure_translation_map=procedure_translation_map,
        )

    def test_no_match_without_antibiotic_is_conforme(self):
        auditor = SurgeryAuditor(self.repo, AUDIT_CONFIG)
        record = SurgeryRecord(
            procedure="Procedimento sem match",
            atb_given="NAO",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_escolha_razao, "sem_match_sem_atb")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_rule_with_drugs_and_false_flag_still_validates_choice(self):
        rule = ProtocolRule(
            rule_id="rule_1",
            procedure="Cesariana",
            procedure_normalized="cesariana",
            is_prophylaxis_required=False,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cesariana",
            atb_given="SIM",
            atb_detected=["CEFAZOLINA"],
            atb_name="Cefazolina 2g",
            dose_administered_mg=2000.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_escolha_razao, "atb_recomendado")

    def test_no_match_with_antibiotic_becomes_alert(self):
        auditor = SurgeryAuditor(self.repo, AUDIT_CONFIG)
        record = SurgeryRecord(
            procedure="Procedimento desconhecido",
            atb_given="SIM",
            atb_detected=["CEFAZOLINA"],
            atb_name="Cefazolina 2g",
            dose_administered_mg=2000.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_final, "ALERTA")
        self.assertEqual(result.conf_final_razao, "sem_match_protocolo")

    def test_required_prophylaxis_without_documented_administration_becomes_alert(self):
        rule = ProtocolRule(
            rule_id="rule_missing_admin",
            procedure="Cesariana",
            procedure_normalized="cesariana",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cesariana",
            atb_given="NAO",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "ALERTA")
        self.assertEqual(result.conf_escolha_razao, "sem_registro_administracao")
        self.assertEqual(result.conf_final, "ALERTA")

    def test_antibiotic_outside_protocol_list_becomes_nao_conforme(self):
        rule = ProtocolRule(
            rule_id="rule_alert_choice",
            procedure="Cesariana",
            procedure_normalized="cesariana",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cesariana",
            atb_given="SIM",
            atb_detected=["CLINDAMICINA"],
            atb_name="Clindamicina 900mg",
            dose_administered_mg=900.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "NAO_CONFORME")
        self.assertEqual(result.conf_escolha_razao, "atb_nao_recomendado")
        self.assertEqual(result.conf_final, "NAO_CONFORME")

    def test_required_prophylaxis_with_recommended_antibiotic_is_conforme(self):
        rule = ProtocolRule(
            rule_id="rule_conforme_choice",
            procedure="Cesariana",
            procedure_normalized="cesariana",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cesariana",
            atb_given="SIM",
            atb_detected=["CEFAZOLINA"],
            atb_name="Cefazolina 2g",
            dose_administered_mg=2000.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_combination_regimen_is_conforme_when_all_agents_are_documented(self):
        rule = ProtocolRule(
            rule_id="rule_combo",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Cefazolina + Metronidazol",
                acceptable_regimens=[["CEFAZOLINA", "METRONIDAZOL"]],
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Cefazolina + Metronidazol",
            atb_detected=extract_documented_antibiotics("Cefazolina + Metronidazol"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_combination_regimen_is_conforme_regardless_of_documentation_order(self):
        rule = ProtocolRule(
            rule_id="rule_combo_order",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Cefazolina + Metronidazol",
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Metronidazol + Cefazolina",
            atb_detected=extract_documented_antibiotics("Metronidazol + Cefazolina"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_combination_regimen_with_partial_documentation_is_nao_conforme(self):
        rule = ProtocolRule(
            rule_id="rule_combo_partial",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Cefazolina + Metronidazol",
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Cefazolina",
            atb_detected=extract_documented_antibiotics("Cefazolina"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "NAO_CONFORME")
        self.assertEqual(result.conf_escolha_razao, "atb_regime_incompleto")
        self.assertEqual(result.conf_final, "NAO_CONFORME")

    def test_combination_regimen_with_insufficient_documentation_is_alert(self):
        rule = ProtocolRule(
            rule_id="rule_combo_insufficient",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Cefazolina + Metronidazol",
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Cefazolina + ???",
            atb_detected=extract_documented_antibiotics("Cefazolina + ???"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "ALERTA")
        self.assertEqual(result.conf_escolha_razao, "atb_regime_ambiguo")
        self.assertEqual(result.conf_final, "ALERTA")

    def test_alternative_combination_regimen_is_conforme_when_one_complete_regime_matches(self):
        rule = ProtocolRule(
            rule_id="rule_combo_alternatives",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFTRIAXONE", dose="1000mg", route="EV", timing="na inducao"),
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Ceftriaxona/Cefazolina + Metronidazol",
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Cefazolina + Metronidazol",
            atb_detected=extract_documented_antibiotics("Cefazolina + Metronidazol"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_allergy_combination_regimen_is_conforme_when_complete_regime_matches(self):
        rule = ProtocolRule(
            rule_id="rule_combo_allergy",
            procedure="Cirurgia colorretal",
            procedure_normalized="cirurgia colorretal",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[
                    Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao"),
                    Drug(name="METRONIDAZOL", dose="500mg", route="EV", timing="na inducao"),
                ],
                raw_text="Cefazolina + Metronidazol",
            ),
            allergy_recommendation=Recommendation(
                drugs=[
                    Drug(name="CLINDAMICINA", dose="900mg", route="EV", timing="na inducao"),
                    Drug(name="GENTAMICINA", dose="5mg/kg", route="EV", timing="na inducao"),
                ],
                raw_text="Clindamicina + Gentamicina",
            ),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Cirurgia colorretal",
            atb_given="SIM",
            atb_name="Clindamicina + Gentamicina",
            atb_detected=extract_documented_antibiotics("Clindamicina + Gentamicina"),
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "CONFORME")
        self.assertEqual(result.conf_final, "CONFORME")

    def test_prophylaxis_not_indicated_with_antibiotic_is_nao_conforme(self):
        rule = ProtocolRule(
            rule_id="rule_no_prophylaxis",
            procedure="Pequeno procedimento",
            procedure_normalized="pequeno procedimento",
            is_prophylaxis_required=False,
            primary_recommendation=Recommendation(drugs=[]),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Pequeno procedimento",
            atb_given="SIM",
            atb_detected=["CEFAZOLINA"],
            atb_name="Cefazolina 2g",
            dose_administered_mg=2000.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_escolha, "NAO_CONFORME")
        self.assertEqual(result.conf_escolha_razao, "profilaxia_nao_recomendada")
        self.assertEqual(result.conf_final, "NAO_CONFORME")

    def test_prefix_np_is_ignored_for_protocol_match(self):
        rule = ProtocolRule(
            rule_id="rule_prefix",
            procedure="Reparo ou sutura de um menisco joelho",
            procedure_normalized="reparo ou sutura de um menisco joelho",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)

        matched_rule, score, method = auditor._match_with_protocol(
            SurgeryRecord(procedure="N.P.REPARO OU SUTURA DE UM MENISCO (JOELHO)")
        )

        self.assertIsNotNone(matched_rule)
        self.assertEqual(matched_rule.rule_id, "rule_prefix")
        self.assertEqual(score, 1.0)
        self.assertEqual(method, "exact_match")

    def test_specialty_disambiguates_ambiguous_exact_match(self):
        ortho_rule = ProtocolRule(
            rule_id="rule_ortho",
            section="Ortopedia",
            procedure="Revisao de implante",
            procedure_normalized="revisao de implante",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        cardio_rule = ProtocolRule(
            rule_id="rule_cardio",
            section="Cardiologia",
            procedure="Revisao de implante",
            procedure_normalized="revisao de implante",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="VANCOMICINA", dose="1000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rules([ortho_rule, cardio_rule])

        matched_rule, score, method = auditor._match_with_protocol(
            SurgeryRecord(
                procedure="Revisao de implante",
                specialty="Cardiologia",
            )
        )

        self.assertIsNotNone(matched_rule)
        self.assertEqual(matched_rule.rule_id, "rule_cardio")
        self.assertEqual(score, 1.0)
        self.assertEqual(method, "exact_match_specialty")

    def test_curated_translation_map_is_trusted_even_with_low_lexical_similarity(self):
        rule = ProtocolRule(
            rule_id="rule_map",
            procedure="Cirurgias limpas sem implantes",
            procedure_normalized="cirurgias limpas sem implantes",
            is_prophylaxis_required=False,
            primary_recommendation=Recommendation(drugs=[]),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule_and_map(
            rule,
            {"TIREOIDECTOMIA TOTAL": "Cirurgias limpas sem implantes"},
        )

        matched_rule, score, method = auditor._match_with_protocol(
            SurgeryRecord(procedure="N.P.TIREOIDECTOMIA TOTAL")
        )

        self.assertIsNotNone(matched_rule)
        self.assertEqual(matched_rule.rule_id, "rule_map")
        self.assertEqual(score, 1.0)
        self.assertEqual(method, "translated_exact_match")

    def test_translation_map_prioritizes_specialty_plus_procedure_key(self):
        ortho_rule = ProtocolRule(
            rule_id="rule_implante_ortho",
            section="Ortopedia",
            procedure="Artroplastia",
            procedure_normalized="artroplastia",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFAZOLINA", dose="2000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        cardio_rule = ProtocolRule(
            rule_id="rule_implante_cardio",
            section="Cardiologia",
            procedure="Implante de dispositivo cardiaco",
            procedure_normalized="implante de dispositivo cardiaco",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="VANCOMICINA", dose="1000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rules(
            [ortho_rule, cardio_rule],
            procedure_translation_map={
                "IMPLANTE": "Artroplastia",
                "Cardiologia | IMPLANTE": "Implante de dispositivo cardiaco",
            },
        )

        matched_rule, score, method = auditor._match_with_protocol(
            SurgeryRecord(
                procedure="Implante",
                specialty="Cardiologia",
            )
        )

        self.assertIsNotNone(matched_rule)
        self.assertEqual(matched_rule.rule_id, "rule_implante_cardio")
        self.assertEqual(score, 1.0)
        self.assertEqual(method, "translated_exact_match_specialty")

    def test_large_dose_gap_up_to_100_percent_is_alert(self):
        rule = ProtocolRule(
            rule_id="rule_2",
            procedure="Ureterorrenoscopia",
            procedure_normalized="ureterorrenoscopia",
            is_prophylaxis_required=True,
            primary_recommendation=Recommendation(
                drugs=[Drug(name="CEFTRIAXONE", dose="1000mg", route="EV", timing="na inducao")]
            ),
            allergy_recommendation=Recommendation(drugs=[]),
        )
        auditor = self._build_auditor_with_rule(rule)
        record = SurgeryRecord(
            procedure="Ureterorrenoscopia",
            atb_given="SIM",
            atb_detected=["CEFTRIAXONE"],
            atb_name="Ceftriaxona 2g",
            dose_administered_mg=2000.0,
            atb_time="07:00",
            incision_time="07:30",
            repique_done="NAO",
        )

        result = auditor.audit_surgery(record)

        self.assertEqual(result.conf_dose, "ALERTA")
        self.assertEqual(result.conf_dose_razao, "dose_fora_referencia")

    def test_load_surgeries_from_excel_keeps_cod_atendimento(self):
        auditor = SurgeryAuditor(self.repo, AUDIT_CONFIG)
        df = pd.DataFrame(
            [
                {
                    "Cod Atendimento": 12345.0,
                    "Cirurgia": "Cesariana",
                    "Administração de Antibiotico": "SIM",
                    "Antibiótico": "Cefazolina 2g",
                }
            ]
        )

        with patch("controllers.surgery_auditor.pd.read_excel", return_value=df):
            count = auditor.load_surgeries_from_excel(Path("dummy.xlsx"))

        self.assertEqual(count, 1)
        self.assertEqual(auditor.surgery_records[0].attendance_code, "12345")
        self.assertEqual(auditor.surgery_records[0].surgeon, "")

    def test_load_surgeries_from_excel_reads_surgeon_alias(self):
        auditor = SurgeryAuditor(self.repo, AUDIT_CONFIG)
        df = pd.DataFrame(
            [
                {
                    "Cod Atendimento": 12345.0,
                    "Cirurgia": "Cesariana",
                    "Nome do Cirurgião": "Dra. Maria Silva",
                    "AdministraÃ§Ã£o de Antibiotico": "SIM",
                    "AntibiÃ³tico": "Cefazolina 2g",
                }
            ]
        )

        with patch("controllers.surgery_auditor.pd.read_excel", return_value=df):
            count = auditor.load_surgeries_from_excel(Path("dummy.xlsx"))

        self.assertEqual(count, 1)
        self.assertEqual(auditor.surgery_records[0].surgeon, "Dra. Maria Silva")

    def test_report_dataframe_includes_cod_atendimento_and_map_version(self):
        result = AuditResult(
            surgery_record=SurgeryRecord(
                procedure="Cesariana",
                attendance_code="ATD-001",
                surgeon="Dr. Joao",
                repique_done="NAO",
            ),
            procedure_map_version="v2",
        )

        df = ReportGenerator([result]).prepare_dataframe()

        self.assertIn("cod_atendimento", df.columns)
        self.assertIn("cirurgiao", df.columns)
        self.assertIn("versao_mapeamento_procedimentos", df.columns)
        self.assertEqual(df.loc[0, "cod_atendimento"], "ATD-001")
        self.assertEqual(df.loc[0, "cirurgiao"], "Dr. Joao")
        self.assertEqual(df.loc[0, "versao_mapeamento_procedimentos"], "v2")


if __name__ == "__main__":
    unittest.main()
