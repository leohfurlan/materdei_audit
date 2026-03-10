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

    def test_report_dataframe_includes_cod_atendimento_and_map_version(self):
        result = AuditResult(
            surgery_record=SurgeryRecord(
                procedure="Cesariana",
                attendance_code="ATD-001",
                repique_done="NAO",
            ),
            procedure_map_version="v2",
        )

        df = ReportGenerator([result]).prepare_dataframe()

        self.assertIn("cod_atendimento", df.columns)
        self.assertIn("versao_mapeamento_procedimentos", df.columns)
        self.assertEqual(df.loc[0, "cod_atendimento"], "ATD-001")
        self.assertEqual(df.loc[0, "versao_mapeamento_procedimentos"], "v2")


if __name__ == "__main__":
    unittest.main()
