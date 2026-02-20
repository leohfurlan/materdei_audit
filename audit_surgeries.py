#!/usr/bin/env python3
"""
Script para auditoria de cirurgias.

Uso:
    python audit_surgeries.py <planilha_excel> <protocolo_json> [--output <diretorio_saida>]
"""
import argparse
import logging
from logging.config import dictConfig
from pathlib import Path
import sys
from typing import Any

# Adiciona o diretorio raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR, AUDIT_CONFIG, LOGGING_CONFIG
from controllers import SurgeryAuditor, ReportGenerator, ProtocolExtractor
from models import ProtocolRulesRepository
from utils.input_loader import load_json

# Configura logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


def _looks_like_raw_extractions(payload: Any) -> bool:
    """Detecta se o JSON possui formato de raw_extractions do extractor."""
    if not isinstance(payload, list) or not payload:
        return False
    sample = payload[0] if isinstance(payload[0], dict) else {}
    return (
        isinstance(sample, dict)
        and "attributes" in sample
        and "extraction_text" in sample
        and "rule_id" not in sample
    )


def _load_rules_repository(protocol_path: Path) -> ProtocolRulesRepository:
    """
    Carrega repositorio de regras aceitando:
    - rules.json
    - raw_extractions.json (convertido automaticamente)
    """
    payload = load_json(str(protocol_path))
    rules_repo = ProtocolRulesRepository()

    # Reseta estado interno (singleton) para evitar cache entre execucoes no mesmo processo.
    rules_repo.rules = []
    rules_repo._index = {}
    rules_repo._metadata = {}
    rules_repo._is_loaded = False

    if _looks_like_raw_extractions(payload):
        logger.info("  Detectado formato raw_extractions.json - convertendo para regras...")
        extractor = ProtocolExtractor(protocol_path)
        rules_repo.rules = extractor.convert_raw_to_rules(payload)
        rules_repo._build_index()
        rules_repo._metadata = {
            "source_file": str(protocol_path),
            "source_format": "raw_extractions",
            "extraction_method": "langextract",
            "rules_count": len(rules_repo.rules),
        }
        rules_repo._is_loaded = True
    else:
        logger.info("  Detectado formato rules.json")
        rules_repo.load_from_json(protocol_path)

    return rules_repo


def main() -> int:
    """Funcao principal."""
    parser = argparse.ArgumentParser(
        description="Audita cirurgias comparando com protocolo de profilaxia"
    )
    parser.add_argument(
        "excel_path",
        type=str,
        help="Caminho para planilha Excel com cirurgias",
    )
    parser.add_argument(
        "rules_path",
        type=str,
        help="Caminho para rules.json ou raw_extractions.json do protocolo",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(OUTPUT_DIR),
        help="Diretorio de saida para relatorios",
    )
    parser.add_argument(
        "--sheet",
        "-s",
        type=str,
        default=None,
        help="Nome da aba do Excel (padrao: primeira aba)",
    )
    parser.add_argument(
        "--procedures-map",
        type=str,
        default="./data/input/procedimentos.json",
        help="Caminho do JSON de traducao de procedimentos (Excel -> protocolo)",
    )

    args = parser.parse_args()

    # Valida arquivos
    excel_path = Path(args.excel_path)
    if not excel_path.exists():
        logger.error(f"Arquivo Excel nao encontrado: {excel_path}")
        return 1

    rules_path = Path(args.rules_path)
    if not rules_path.exists():
        logger.error(f"Arquivo de protocolo nao encontrado: {rules_path}")
        return 1

    # Diretorio de saida
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info("AUDITORIA DE PROFILAXIA ANTIMICROBIANA")
    logger.info("=" * 70)
    logger.info(f"Planilha: {excel_path}")
    logger.info(f"Protocolo: {rules_path}")
    logger.info(f"Saida: {output_dir}")
    if args.sheet:
        logger.info(f"Aba: {args.sheet}")
    logger.info("")

    try:
        # Carrega regras do protocolo
        logger.info("Carregando protocolo...")
        rules_repo = _load_rules_repository(rules_path)

        stats = rules_repo.get_statistics()
        logger.info(f"  OK {stats['total_rules']} regras carregadas")

        # Carrega dicionario de traducao de procedimentos
        procedure_translation_map = {}
        procedures_map_path = Path(args.procedures_map)
        if procedures_map_path.exists():
            raw_map = load_json(str(procedures_map_path))
            if isinstance(raw_map, dict):
                procedure_translation_map = {
                    str(k).strip(): str(v).strip()
                    for k, v in raw_map.items()
                    if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()
                }
                logger.info(
                    f"  OK {len(procedure_translation_map)} traducoes carregadas de {procedures_map_path}"
                )
            else:
                logger.warning(
                    f"Dicionario de procedimentos invalido (nao e objeto JSON): {procedures_map_path}"
                )
        else:
            logger.warning(f"Dicionario de procedimentos nao encontrado: {procedures_map_path}")
        logger.info("")

        # Cria auditor
        auditor = SurgeryAuditor(
            rules_repo,
            AUDIT_CONFIG,
            procedure_translation_map=procedure_translation_map,
        )

        # Carrega cirurgias
        logger.info("Carregando cirurgias da planilha...")
        count = auditor.load_surgeries_from_excel(excel_path, args.sheet)
        logger.info(f"  OK {count} cirurgias carregadas")
        logger.info("")

        # Executa auditoria
        logger.info("Executando auditoria...")
        results = auditor.audit_all_surgeries()
        logger.info(f"  OK {len(results)} cirurgias auditadas")
        logger.info("")

        # Gera relatorios
        logger.info("Gerando relatorios...")
        report_gen = ReportGenerator(results)

        excel_output = output_dir / "auditoria_resultado.xlsx"
        report_gen.export_excel(excel_output)
        logger.info(f"  OK Excel: {excel_output.name}")

        csv_output = output_dir / "auditoria_resultado.csv"
        report_gen.export_csv(csv_output)
        logger.info(f"  OK CSV: {csv_output.name}")

        json_output = output_dir / "auditoria_resultado.json"
        report_gen.export_json(json_output)
        logger.info(f"  OK JSON: {json_output.name}")

        summary_output = output_dir / "auditoria_resumo.txt"
        report_gen.export_summary_report(summary_output)
        logger.info(f"  OK Resumo: {summary_output.name}")
        logger.info("")

        # Exibe estatisticas
        audit_stats = auditor.get_statistics()

        logger.info("=" * 70)
        logger.info("RESULTADOS DA AUDITORIA")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Total de cirurgias: {audit_stats['total_cirurgias']}")
        logger.info("")
        logger.info("Conformidade Final:")
        for status, count in audit_stats["conformidade_final"].items():
            pct = count / audit_stats["total_cirurgias"] * 100 if audit_stats["total_cirurgias"] > 0 else 0
            logger.info(f"  {status.upper():15s}: {count:4d} ({pct:5.1f}%)")
        logger.info("")
        logger.info(f"Taxa de Conformidade Total:   {audit_stats['taxas']['conformidade_total_pct']:.1f}%")
        logger.info(f"Taxa de Conformidade Estrita: {audit_stats['taxas']['conformidade_estrita_pct']:.1f}%")
        logger.info("")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Relatorios salvos em: {output_dir}")

        # Alerta se muitas nao conformidades
        nao_conforme = audit_stats["conformidade_final"]["nao_conforme"]
        if nao_conforme > 0:
            logger.warning("")
            logger.warning(f"ATENCAO: {nao_conforme} casos nao conformes detectados!")
            logger.warning("  Revise a aba 'Nao Conformes' no Excel para detalhes.")

        return 0

    except Exception as e:
        logger.error(f"Erro durante auditoria: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
