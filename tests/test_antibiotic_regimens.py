import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    normalize_antibiotic_name,
    extract_documented_antibiotics,
    has_ambiguous_documented_antibiotics,
    infer_recommendation_structure,
    parse_protocol_antibiotic_regimens,
    parse_structured_recommendation,
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

    def test_parse_protocol_antibiotic_regimens_keeps_alternative_complete_regimens(self):
        regimens = parse_protocol_antibiotic_regimens(
            "Cefazolina + Metronidazol OU Ceftriaxona + Metronidazol"
        )

        self.assertEqual(
            set(regimens),
            {
                ("CEFAZOLINA", "METRONIDAZOL"),
                ("CEFTRIAXONE", "METRONIDAZOL"),
            },
        )

    def test_parse_protocol_antibiotic_regimens_supports_or_with_compound_drug_name(self):
        regimens = parse_protocol_antibiotic_regimens(
            "Ciprofloxacino 400mg EV OU Ampicilina/Sulbactam 3 g EV"
        )

        self.assertEqual(
            set(regimens),
            {
                ("CIPROFLOXACINO",),
                ("AMPICILINA_SULBACTAM",),
            },
        )

    def test_parse_structured_recommendation_does_not_turn_optional_addition_into_mandatory_combo(self):
        parsed = parse_structured_recommendation(
            "Clindamicina (associação com gentamicina opcional, pois não é definido na literatura)"
        )

        self.assertEqual(parsed.acceptable_regimens, [("CLINDAMICINA",)])
        self.assertEqual(parsed.optional_additions[0]["regimens"], [["GENTAMICINA"]])

    def test_parse_structured_recommendation_extracts_conditional_addition(self):
        parsed = parse_structured_recommendation(
            "Cefazolina 2g EV",
            notes="Adicionar Vancomicina 1g EV em 1h se alto risco de infecção por Staphylococcus oxacilina resistente.",
        )

        self.assertEqual(parsed.acceptable_regimens, [("CEFAZOLINA",)])
        self.assertEqual(parsed.conditional_additions[0]["regimens"], [["VANCOMICINA"]])
        self.assertIn("alto risco", parsed.conditional_additions[0]["condition"].lower())

    def test_infer_recommendation_structure_marks_flat_legacy_lists_as_ambiguous(self):
        structured = infer_recommendation_structure(
            raw_text="Cirurgia limpa, com implantes",
            notes="",
            drug_names=["CEFAZOLINA", "CLINDAMICINA"],
            recommendation_kind="primary",
        )

        self.assertEqual(structured["acceptable_regimens"], [])
        self.assertTrue(structured["metadata"]["legacy_flattened_ambiguous"])

    def test_infer_recommendation_structure_keeps_primary_and_allergy_separate(self):
        primary = infer_recommendation_structure(
            raw_text="Cefazolina 2g EV",
            notes="",
            drug_names=["CEFAZOLINA"],
            recommendation_kind="primary",
        )
        allergy = infer_recommendation_structure(
            raw_text="Clindamicina 900mg EV",
            notes="",
            drug_names=["CLINDAMICINA"],
            recommendation_kind="allergy",
        )

        self.assertEqual(primary["acceptable_regimens"], [["CEFAZOLINA"]])
        self.assertEqual(allergy["acceptable_regimens"], [["CLINDAMICINA"]])
        self.assertEqual(primary["metadata"]["recommendation_kind"], "primary")
        self.assertEqual(allergy["metadata"]["recommendation_kind"], "allergy")


if __name__ == "__main__":
    unittest.main()
