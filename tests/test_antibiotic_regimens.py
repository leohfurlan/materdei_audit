import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    normalize_antibiotic_name,
    extract_documented_antibiotics,
    has_ambiguous_documented_antibiotics,
    parse_protocol_antibiotic_regimens,
)


class TestAntibioticRegimens(unittest.TestCase):
    def test_normalize_antibiotic_name_is_tolerant_to_case_accents_and_spacing(self):
        self.assertEqual(normalize_antibiotic_name("  cefazolina "), "CEFAZOLINA")
        self.assertEqual(normalize_antibiotic_name("metronidazól"), "METRONIDAZOL")

    def test_normalize_antibiotic_name_preserves_valid_compound_names(self):
        self.assertEqual(normalize_antibiotic_name("ampicilina/sulbactam"), "AMPICILINA_SULBACTAM")

    def test_extract_documented_antibiotics_supports_multiple_agents(self):
        detected = extract_documented_antibiotics("Cefazolina + Metronidazol")

        self.assertEqual(detected, ["CEFAZOLINA", "METRONIDAZOL"])

    def test_extract_documented_antibiotics_is_tolerant_to_simple_typos(self):
        detected = extract_documented_antibiotics("cefazolibna + metronidazol")

        self.assertEqual(detected, ["CEFAZOLINA", "METRONIDAZOL"])

    def test_has_ambiguous_documented_antibiotics_when_multiple_segments_are_not_fully_identified(self):
        detected = extract_documented_antibiotics("cefazolina + ???")

        self.assertTrue(has_ambiguous_documented_antibiotics("cefazolina + ???", detected))

    def test_parse_protocol_antibiotic_regimens_supports_single_drug(self):
        regimens = parse_protocol_antibiotic_regimens("Cefazolina")

        self.assertEqual(regimens, [("CEFAZOLINA",)])

    def test_parse_protocol_antibiotic_regimens_supports_combination(self):
        regimens = parse_protocol_antibiotic_regimens("Cefazolina + Metronidazol")

        self.assertEqual(regimens, [("CEFAZOLINA", "METRONIDAZOL")])

    def test_parse_protocol_antibiotic_regimens_expands_slash_and_ou(self):
        regimens = parse_protocol_antibiotic_regimens(
            "Ceftriaxona/Cefazolina + Metronidazol OU Clindamicina + Gentamicina"
        )

        self.assertEqual(
            set(regimens),
            {
                ("CEFAZOLINA", "METRONIDAZOL"),
                ("CEFTRIAXONE", "METRONIDAZOL"),
                ("CLINDAMICINA", "GENTAMICINA"),
            },
        )


if __name__ == "__main__":
    unittest.main()
