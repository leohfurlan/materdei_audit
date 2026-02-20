import unittest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from controllers.surgery_auditor import SurgeryAuditor
from models import (
    ProtocolRulesRepository,
    ProtocolRule,
    Recommendation,
    Drug,
    SurgeryRecord,
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


if __name__ == "__main__":
    unittest.main()
