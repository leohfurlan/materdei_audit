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
        self.assertEqual(antibiotic.name, "Cefazolina")
        self.assertEqual(antibiotic.dose, "2g")
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
        self.assertEqual(rule.antibiotics[0].name, "Cefazolina")
        self.assertEqual(rule.antibiotics[0].dose, "2g")
        self.assertEqual(rule.antibiotics[0].route, "EV")


if __name__ == "__main__":
    unittest.main()
