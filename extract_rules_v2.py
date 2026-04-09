"""
extract_rules_v2.py — Extração determinística de regras do protocolo de profilaxia.

Substitui o pipeline LLM (Gemini/LangExtract) por parsing direto do PDF via pdfplumber.
Custo: zero (sem chamadas a APIs externas).

Uso:
    python extract_rules_v2.py \\
        --pdf "data/input/PROFILAXIA ANTIMICROBIANA PARA PREVENÇÃO DE SÍTIO CIRÚRGICO VS 03.pdf" \\
        --output data/output/langextract_preview_full/rules_v2.json \\
        [--pages 8-35] \\
        [--dosing-tables data/input/dosing_tables.json] \\
        [--compare data/output/langextract_preview_full/rules.json]
"""

import argparse
import json
import logging
import logging.config
import sys
from pathlib import Path

# Garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import LOGGING_CONFIG, OUTPUT_DIR, INPUT_DIR
from controllers.pdf_extractor import DeterministicPDFExtractor, extract_dosing_tables


def setup_logging() -> None:
    logging.config.dictConfig(LOGGING_CONFIG)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai regras de profilaxia do PDF institucional sem usar LLM."
    )
    parser.add_argument(
        "--pdf",
        required=True,
        help="Caminho para o PDF do protocolo de profilaxia.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "langextract_preview_full" / "rules_v2.json"),
        help="Caminho de saída do rules.json gerado.",
    )
    parser.add_argument(
        "--pages",
        default="8-35",
        help="Intervalo de páginas do PDF com as tabelas (ex.: 8-35).",
    )
    parser.add_argument(
        "--dosing-tables",
        default=str(INPUT_DIR / "dosing_tables.json"),
        help="Caminho de saída para dosing_tables.json.",
    )
    parser.add_argument(
        "--compare",
        default=None,
        help="Caminho de um rules.json existente para comparação (opcional).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Ativa logging detalhado.",
    )
    return parser.parse_args()


def compare_rules(new_rules: list, existing_path: str) -> None:
    """Exibe comparativo entre regras novas e existentes."""
    logger = logging.getLogger(__name__)
    try:
        with open(existing_path, encoding="utf-8") as f:
            existing = json.load(f)
    except Exception as e:
        logger.warning(f"Não foi possível carregar arquivo de comparação: {e}")
        return

    existing_procs = {r.get("procedure_normalized", "") for r in existing}
    new_procs = {r.get("procedure_normalized", "") for r in new_rules}

    only_existing = existing_procs - new_procs
    only_new = new_procs - existing_procs
    common = existing_procs & new_procs

    print("\n" + "=" * 60)
    print("COMPARATIVO DE REGRAS")
    print("=" * 60)
    print(f"  Regras no arquivo existente:  {len(existing)}")
    print(f"  Regras no arquivo novo:       {len(new_rules)}")
    print(f"  Procedimentos em comum:       {len(common)}")
    print(f"  Somente no existente:         {len(only_existing)}")
    print(f"  Somente no novo:              {len(only_new)}")

    if only_existing:
        print("\n  [!] Procedimentos presentes no existente mas AUSENTES no novo:")
        for p in sorted(only_existing)[:20]:
            print(f"      - {p}")
        if len(only_existing) > 20:
            print(f"      ... e mais {len(only_existing) - 20}")

    if only_new:
        print("\n  [+] Procedimentos novos não presentes no existente:")
        for p in sorted(only_new)[:20]:
            print(f"      + {p}")

    # Cobertura
    coverage = len(common) / len(existing_procs) * 100 if existing_procs else 0
    print(f"\n  Cobertura em relação ao existente: {coverage:.1f}%")
    if coverage >= 95:
        print("  [OK] Meta de >=95% de cobertura atingida.")
    else:
        print(f"  [!] Abaixo da meta de 95%. Verifique paginas extraidas.")
    print("=" * 60 + "\n")


def print_summary(rules: list) -> None:
    """Exibe resumo das regras extraídas."""
    total = len(rules)
    with_prophylaxis = sum(1 for r in rules if r.get("is_prophylaxis_required"))
    without_prophylaxis = total - with_prophylaxis
    sections = {}
    for r in rules:
        sec = r.get("section", "DESCONHECIDO")
        sections[sec] = sections.get(sec, 0) + 1

    print("\n" + "=" * 60)
    print("RESUMO DA EXTRAÇÃO")
    print("=" * 60)
    print(f"  Total de regras:              {total}")
    print(f"  Com profilaxia obrigatória:   {with_prophylaxis}")
    print(f"  Sem profilaxia:               {without_prophylaxis}")
    print("\n  Por seção:")
    for sec, count in sorted(sections.items(), key=lambda x: -x[1]):
        print(f"    {sec:<35} {count:>4}")
    print("=" * 60 + "\n")


def main() -> int:
    args = parse_args()
    setup_logging()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger = logging.getLogger(__name__)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        logger.error(f"PDF não encontrado: {pdf_path}")
        return 1

    # --- Extração de regras ---
    logger.info("Iniciando extração determinística (sem LLM)...")
    extractor = DeterministicPDFExtractor(pdf_path, pages=args.pages)
    rules = extractor.extract()

    if not rules:
        logger.error("Nenhuma regra extraída. Verifique o intervalo de páginas.")
        return 1

    # --- Salva rules.json ---
    output_path = extractor.save(args.output)
    print(f"\nRules salvas em: {output_path}")

    # --- Extrai e salva tabelas de dosagem ---
    logger.info("Extraindo tabelas de dosagem por peso...")
    dosing = extract_dosing_tables(pdf_path)
    dosing_path = Path(args.dosing_tables)
    dosing_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dosing_path, "w", encoding="utf-8") as f:
        json.dump(dosing, f, ensure_ascii=False, indent=2)
    print(f"Tabelas de dosagem salvas em: {dosing_path}")

    # --- Resumo e comparativo ---
    print_summary(rules)

    if args.compare:
        compare_rules(rules, args.compare)

    return 0


if __name__ == "__main__":
    sys.exit(main())
