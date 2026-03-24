import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class TestBuildProcedureMap(unittest.TestCase):
    def test_build_procedure_map_exports_specialty_and_surgeon(self):
        project_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            excel_path = tmp_path / "cirurgias.xlsx"
            rules_path = tmp_path / "rules.json"
            output_path = tmp_path / "procedure_map.json"
            output_simple_path = tmp_path / "procedure_map_simple.json"

            pd.DataFrame(
                [
                    {
                        "Cirurgia": "Revisao de implante",
                        "Especialidade": "Cardiologia",
                        "Nome do Cirurgião": "Dr. Joao",
                    }
                ]
            ).to_excel(excel_path, index=False)

            rules_path.write_text(
                json.dumps(
                    [
                        {
                            "rule_id": "rule_1",
                            "section": "Cardiologia",
                            "procedure": "Implante de dispositivo cardiaco",
                            "procedure_normalized": "implante de dispositivo cardiaco",
                            "is_prophylaxis_required": True,
                            "primary_recommendation": {"drugs": []},
                            "allergy_recommendation": {"drugs": []},
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "build_procedure_map.py"),
                    "--excel",
                    str(excel_path),
                    "--rules",
                    str(rules_path),
                    "--output",
                    str(output_path),
                    "--output-simple",
                    str(output_simple_path),
                    "--use-specialty",
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)

            mapping = json.loads(output_path.read_text(encoding="utf-8"))
            simple_mapping = json.loads(output_simple_path.read_text(encoding="utf-8"))

        self.assertIn("Cardiologia | Revisao de implante", mapping)
        self.assertEqual(
            mapping["Cardiologia | Revisao de implante"]["especialidade"],
            "Cardiologia",
        )
        self.assertEqual(
            mapping["Cardiologia | Revisao de implante"]["cirurgiao"],
            "Dr. Joao",
        )
        self.assertEqual(
            simple_mapping["Cardiologia | Revisao de implante"]["specialty"],
            "Cardiologia",
        )
        self.assertEqual(
            simple_mapping["Cardiologia | Revisao de implante"]["surgeon"],
            "Dr. Joao",
        )

    def test_build_procedure_map_infers_specialty_from_surgeon(self):
        project_root = Path(__file__).parent.parent

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            excel_path = tmp_path / "cirurgias.xlsx"
            rules_path = tmp_path / "rules.json"
            output_path = tmp_path / "procedure_map.json"
            output_simple_path = tmp_path / "procedure_map_simple.json"

            pd.DataFrame(
                [
                    {
                        "Cirurgia": "Revisao de implante",
                        "Especialidade": None,
                        "Nome do CirurgiÃ£o": "Dr. Joao",
                    },
                    {
                        "Cirurgia": "Revisao de implante",
                        "Especialidade": "Cardiologia",
                        "Nome do CirurgiÃ£o": "DR JOAO",
                    },
                ]
            ).to_excel(excel_path, index=False)

            rules_path.write_text(
                json.dumps(
                    [
                        {
                            "rule_id": "rule_1",
                            "section": "Cardiologia",
                            "procedure": "Revisao de implante",
                            "procedure_normalized": "revisao de implante",
                            "is_prophylaxis_required": True,
                            "primary_recommendation": {"drugs": []},
                            "allergy_recommendation": {"drugs": []},
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "build_procedure_map.py"),
                    "--excel",
                    str(excel_path),
                    "--rules",
                    str(rules_path),
                    "--output",
                    str(output_path),
                    "--output-simple",
                    str(output_simple_path),
                    "--use-specialty",
                ],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)

            mapping = json.loads(output_path.read_text(encoding="utf-8"))
            simple_mapping = json.loads(output_simple_path.read_text(encoding="utf-8"))

        self.assertEqual(len(mapping), 1)
        self.assertIn("Cardiologia | Revisao de implante", mapping)
        self.assertEqual(
            mapping["Cardiologia | Revisao de implante"]["especialidade"],
            "Cardiologia",
        )
        self.assertEqual(
            mapping["Cardiologia | Revisao de implante"]["cirurgiao"],
            "Dr. Joao",
        )
        self.assertEqual(
            simple_mapping["Cardiologia | Revisao de implante"]["specialty"],
            "Cardiologia",
        )


if __name__ == "__main__":
    unittest.main()
