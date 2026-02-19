#!/usr/bin/env python3
"""
Script para extracao de regras do protocolo PDF.

Uso:
    python extract_rules.py <caminho_pdf> [--output <diretorio_saida>]
"""
import argparse
import logging
from pathlib import Path
import sys

# Adiciona o diretorio raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from controllers import ProtocolExtractor
from config import OUTPUT_DIR, EXTRACTION_CONFIG, LOGGING_CONFIG
from logging.config import dictConfig

# Configura logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


def main():
    """Funcao principal."""
    parser = argparse.ArgumentParser(
        description="Extrai regras do protocolo de profilaxia antimicrobiana de PDF"
    )
    parser.add_argument(
        "pdf_path",
        type=str,
        help="Caminho para o arquivo PDF do protocolo",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(OUTPUT_DIR),
        help="Diretorio de saida para os arquivos gerados",
    )
    parser.add_argument(
        "--pages",
        "-p",
        type=str,
        default=EXTRACTION_CONFIG["pages_to_extract"],
        help='Paginas a extrair (ex: "8-35")',
    )
    parser.add_argument(
        "--backend",
        "-b",
        type=str,
        choices=["gemini", "langextract"],
        default=EXTRACTION_CONFIG.get("llm_backend", "gemini"),
        help="Backend LLM para extracao (gemini ou langextract)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Extrai do PDF e salva raw_extractions.json para revisao (NAO gera rules.json)",
    )
    parser.add_argument(
        "--from-raw",
        type=str,
        default=None,
        metavar="ARQUIVO",
        help="Carrega raw_extractions.json revisado e converte para rules.json (pula LLM)",
    )

    args = parser.parse_args()

    # Valida PDF
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        logger.error(f"Arquivo PDF nao encontrado: {pdf_path}")
        sys.exit(1)

    # Diretorio de saida
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info("EXTRACAO DE REGRAS DO PROTOCOLO")
    logger.info("=" * 70)
    logger.info(f"PDF: {pdf_path}")
    logger.info(f"Saida: {output_dir}")
    logger.info(f"Paginas: {args.pages}")
    logger.info(f"Backend: {args.backend}")

    if args.preview:
        logger.info("Modo: PREVIEW (salvar raw_extractions.json)")
    elif args.from_raw:
        logger.info(f"Modo: FROM-RAW (carregar {args.from_raw})")
    else:
        logger.info("Modo: COMPLETO (PDF -> LLM -> rules.json)")
    logger.info("")

    try:
        # Cria extrator
        config = EXTRACTION_CONFIG.copy()
        config["pages_to_extract"] = args.pages
        config["llm_backend"] = args.backend

        extractor = ProtocolExtractor(pdf_path, config)

        # MODO PREVIEW
        if args.preview:
            raw_path = extractor.extract_preview(output_dir)

            logger.info("")
            logger.info("=" * 70)
            logger.info("PREVIEW CONCLUIDO")
            logger.info("=" * 70)
            logger.info(f"Arquivo bruto salvo em: {raw_path}")
            logger.info("")
            logger.info("Proximos passos:")
            logger.info(f"  1. Revise e edite: {raw_path}")
            logger.info(
                f"  2. Execute: python extract_rules.py \"{pdf_path}\" --from-raw \"{raw_path}\""
            )
            return 0

        # MODO FROM-RAW
        if args.from_raw:
            raw_path = Path(args.from_raw)
            if not raw_path.exists():
                logger.error(f"Arquivo raw nao encontrado: {raw_path}")
                sys.exit(1)

            rules = extractor.build_from_raw(raw_path)

            logger.info("Salvando resultados...")
            extractor.save_rules(output_dir)

            logger.info("")
            logger.info("=" * 70)
            logger.info("CONVERSAO CONCLUIDA COM SUCESSO")
            logger.info("=" * 70)
            logger.info(f"Total de regras convertidas: {len(rules)}")
            logger.info("")
            logger.info("Arquivos gerados:")
            logger.info("  - rules.json")
            logger.info("  - rules_index.json")
            logger.info("  - rules.meta.json")
            logger.info(f"Diretorio: {output_dir}")
            return 0

        # MODO COMPLETO (padrao)
        logger.info("Iniciando extracao...")
        rules = extractor.extract_all_rules()

        # Salva resultados
        logger.info("Salvando resultados...")
        extractor.save_rules(output_dir)

        # Gera relatorio de validacao
        validation = extractor.get_validation_report()

        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRACAO CONCLUIDA COM SUCESSO")
        logger.info("=" * 70)
        logger.info(f"Total de regras extraidas: {validation['total_rules']}")
        logger.info(f"  - Requerem profilaxia: {validation['with_prophylaxis']}")
        logger.info(f"  - Nao requerem profilaxia: {validation['without_prophylaxis']}")
        logger.info(f"  - Precisam validacao: {validation['needs_validation']}")
        logger.info("")
        logger.info("Arquivos gerados:")
        logger.info("  - rules.json")
        logger.info("  - rules_index.json")
        logger.info("  - rules.meta.json")
        logger.info("")
        logger.info(f"Diretorio: {output_dir}")

        # Verifica se extracao foi completa
        if validation["total_rules"] < 100:
            logger.warning("")
            logger.warning("[!] ATENCAO: Menos de 100 regras extraidas!")
            logger.warning("  Esperado: >150 regras")
            logger.warning("  Revisar PDF ou parametros de extracao")

        return 0

    except Exception as e:
        logger.error(f"Erro durante extracao: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
