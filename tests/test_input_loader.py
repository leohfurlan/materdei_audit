import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.input_loader import load_procedure_translation_map


class TestProcedureTranslationMapLoader(unittest.TestCase):
    def test_load_latest_versioned_map(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "procedimentos_v1.json").write_text(
                json.dumps({"PROC A": "MAP A"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (tmp_path / "procedimentos_v2.json").write_text(
                json.dumps(
                    {
                        "metadata": {"version": 2, "description": "mapa revisado"},
                        "mappings": {"PROC B": "MAP B"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            mapping, metadata = load_procedure_translation_map(
                tmp_path / "procedimentos.json",
                "latest",
            )

        self.assertEqual(mapping, {"PROC B": "MAP B"})
        self.assertEqual(metadata["map_version"], "v2")
        self.assertEqual(metadata["format"], "versioned")

    def test_load_specific_legacy_versioned_map(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            (tmp_path / "procedimentos_v3.json").write_text(
                json.dumps({"PROC C": "MAP C"}, ensure_ascii=False),
                encoding="utf-8",
            )

            mapping, metadata = load_procedure_translation_map(
                tmp_path / "procedimentos.json",
                "3",
            )

        self.assertEqual(mapping, {"PROC C": "MAP C"})
        self.assertEqual(metadata["map_version"], "v3")
        self.assertEqual(metadata["format"], "legacy")


if __name__ == "__main__":
    unittest.main()
