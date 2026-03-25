import unittest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from controllers.protocol_extractor import ProtocolExtractor, ProtocolRule, AntibioticRule, SurgeryType


class TestLLMExtraction(unittest.TestCase):
    def test_extract_rules_from_text(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "APENDICECTOMIA",
                "attributes": {
                    "surgery_name": ["Apendicectomia"],
                    "surgery_type": "Limpa-contaminada",
                    "antibiotics": [
                        {
                            "name": "Cefazolina",
                            "dose": "2g",
                            "route": "EV",
                            "time": "na inducao",
                        }
                    ],
                    "notes": "Nota de teste",
                },
            }
        ]
        mock_client.models.generate_content.return_value = mock_response
        extractor._gemini_client = mock_client

        rules = extractor.extract_rules_from_text("Texto simulado do protocolo")

        self.assertEqual(len(rules), 1)
        rule = rules[0]

        self.assertIsInstance(rule, ProtocolRule)
        self.assertEqual(rule.surgery_name, ["Apendicectomia"])
        self.assertEqual(rule.surgery_type, SurgeryType.CLEAN_CONTAMINATED)
        self.assertEqual(len(rule.antibiotics), 1)

        antibiotic = rule.antibiotics[0]
        self.assertIsInstance(antibiotic, AntibioticRule)
        self.assertEqual(antibiotic.name, "CEFAZOLINA")
        self.assertEqual(antibiotic.dose, "2000mg")
        self.assertEqual(antibiotic.route, "EV")

        mock_client.models.generate_content.assert_called()
    
    def test_extract_rules_from_text_langextract_backend(self):
        config = {
            "llm_backend": "langextract",
            "langextract_model": "gemini-2.5-flash",
        }

        fake_extraction = SimpleNamespace(
            extraction_class="regra_cirurgia",
            extraction_text="APENDICECTOMIA",
            attributes={
                "surgery_name": ["Apendicectomia"],
                "surgery_type": "Limpa-contaminada",
                "antibiotic_names": ["Cefazolina"],
                "antibiotic_doses": ["2g"],
                "antibiotic_routes": ["EV"],
                "antibiotic_times": ["na inducao"],
                "notes": "Nota de teste",
            },
        )
        fake_document = SimpleNamespace(extractions=[fake_extraction])

        with patch("controllers.protocol_extractor.lx") as mock_lx:
            mock_lx.extract.return_value = fake_document
            extractor = ProtocolExtractor(Path("dummy.pdf"), config=config)
            rules = extractor.extract_rules_from_text("Texto simulado do protocolo")

        self.assertEqual(extractor.llm_backend, "langextract")
        self.assertEqual(len(rules), 1)
        rule = rules[0]

        self.assertEqual(rule.surgery_name, ["Apendicectomia"])
        self.assertEqual(rule.surgery_type, SurgeryType.CLEAN_CONTAMINATED)
        self.assertEqual(len(rule.antibiotics), 1)
        self.assertEqual(rule.antibiotics[0].name, "CEFAZOLINA")
        self.assertEqual(rule.antibiotics[0].dose, "2000mg")
        self.assertEqual(rule.antibiotics[0].route, "EV")

    def test_convert_raw_to_rules_normalizes_complex_dose_and_combo(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))
        raw = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "TESTE",
                "attributes": {
                    "surgery_name": ["Procedimento teste"],
                    "surgery_type": "Limpa",
                    "antibiotics": [
                        {
                            "name": "Ampicilina/Sulbactam",
                            "dose": "15 a 20mg/kg (nao exceder 2g)",
                            "route": "iv",
                            "time": "na inducao",
                        }
                    ],
                    "notes": "",
                },
            }
        ]

        rules = extractor.convert_raw_to_rules(raw)
        self.assertEqual(len(rules), 1)
        self.assertEqual(len(rules[0].antibiotics), 1)
        self.assertEqual(rules[0].antibiotics[0].name, "AMPICILINA_SULBACTAM")
        self.assertEqual(
            rules[0].antibiotics[0].dose,
            "15 a 20mg/kg (nao exceder 2000mg)",
        )
        self.assertEqual(rules[0].antibiotics[0].route, "EV")

    def test_convert_raw_to_rules_repairs_shifted_columns(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))
        raw = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "TESTE SHIFT",
                "attributes": {
                    "surgery_name": ["Procedimento com shift"],
                    "surgery_type": "Limpa",
                    "antibiotics": [
                        {
                            # Simula colunas deslocadas para esquerda.
                            "name": "2g",
                            "dose": "EV",
                            "route": "na inducao",
                            "time": "Cefazolina",
                        }
                    ],
                    "notes": "",
                },
            }
        ]

        rules = extractor.convert_raw_to_rules(raw)
        self.assertEqual(len(rules), 1)
        self.assertEqual(len(rules[0].antibiotics), 1)
        self.assertEqual(rules[0].antibiotics[0].name, "CEFAZOLINA")
        self.assertEqual(rules[0].antibiotics[0].dose, "2000mg")
        self.assertEqual(rules[0].antibiotics[0].route, "EV")
        self.assertEqual(rules[0].antibiotics[0].time, "na inducao")

    def test_convert_raw_to_rules_separates_primary_and_allergy_regimens(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))
        raw = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "Cirurgia limpa, com implantes",
                "attributes": {
                    "surgery_name": ["Cirurgia limpa, com implantes"],
                    "surgery_type": "Limpa",
                    "primary_recommendation_text": "Cefazolina 2g EV",
                    "allergy_recommendation_text": "Clindamicina 900mg EV",
                    "postoperative_text": "Manter por até 24h",
                    "notes": "",
                },
            }
        ]

        rules = extractor.convert_raw_to_rules(raw)

        self.assertEqual(rules[0].primary_recommendation.acceptable_regimens, [["CEFAZOLINA"]])
        self.assertEqual(rules[0].allergy_recommendation.acceptable_regimens, [["CLINDAMICINA"]])
        self.assertEqual(rules[0].postoperative, "Manter por até 24h")

    def test_convert_raw_to_rules_preserves_optional_and_conditional_additions(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))
        raw = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "Cirurgia potencialmente contaminada para câncer",
                "attributes": {
                    "surgery_name": ["Cirurgia potencialmente contaminada para câncer"],
                    "surgery_type": "Contaminada",
                    "primary_recommendation_text": "Cefazolina + Metronidazol",
                    "allergy_recommendation_text": "Clindamicina",
                    "allergy_notes": "Associação com gentamicina opcional, pois não é definido na literatura.",
                    "notes": "Adicionar Vancomicina se alto risco de MRSA.",
                },
            }
        ]

        rules = extractor.convert_raw_to_rules(raw)
        primary = rules[0].primary_recommendation
        allergy = rules[0].allergy_recommendation

        self.assertEqual(primary.acceptable_regimens, [["CEFAZOLINA", "METRONIDAZOL"]])
        self.assertEqual(
            allergy.metadata["optional_additions"][0]["regimens"],
            [["GENTAMICINA"]],
        )
        self.assertEqual(
            primary.metadata["conditional_additions"][0]["regimens"],
            [["VANCOMICINA"]],
        )

    def test_convert_raw_to_rules_keeps_weight_and_imc_text_out_of_drug_set(self):
        extractor = ProtocolExtractor(Path("dummy.pdf"))
        raw = [
            {
                "extraction_class": "regra_cirurgia",
                "extraction_text": "Cirurgia bariátrica com manipulação de alças abaixo do duodeno",
                "attributes": {
                    "surgery_name": ["Cirurgia bariátrica com manipulação de alças abaixo do duodeno"],
                    "surgery_type": "Limpa-contaminada",
                    "primary_recommendation_text": "Ceftriaxona/Cefazolina + Metronidazol",
                    "allergy_recommendation_text": "Metronidazol + Gentamicina 5 mg/kg EV com base no peso ajustado",
                    "notes": "IMC ≥30 e peso >= 120 Kg devem ajustar a dose, sem mudar o regime.",
                },
            }
        ]

        rules = extractor.convert_raw_to_rules(raw)
        primary_regimens = {tuple(regimen) for regimen in rules[0].primary_recommendation.acceptable_regimens}
        allergy_regimens = {tuple(regimen) for regimen in rules[0].allergy_recommendation.acceptable_regimens}

        self.assertEqual(
            primary_regimens,
            {
                ("CEFAZOLINA", "METRONIDAZOL"),
                ("CEFTRIAXONE", "METRONIDAZOL"),
            },
        )
        self.assertEqual(allergy_regimens, {("GENTAMICINA", "METRONIDAZOL")})
        self.assertEqual(
            {drug.name for drug in rules[0].primary_recommendation.drugs},
            {"CEFAZOLINA", "CEFTRIAXONE", "METRONIDAZOL"},
        )


if __name__ == "__main__":
    unittest.main()
