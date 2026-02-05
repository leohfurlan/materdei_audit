#!/usr/bin/env python3
"""
Script para extração de regras do protocolo PDF

Uso:
    python extract_rules.py <caminho_pdf> [--output <diretorio_saida>]
"""
import argparse
import logging
from pathlib import Path
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from materdei_audit.controllers import ProtocolExtractor
from materdei_audit.config import OUTPUT_DIR, EXTRACTION_CONFIG, LOGGING_CONFIG
from logging.config import dictConfig

# Configura logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Extrai regras do protocolo de profilaxia antimicrobiana de PDF'
    )
    parser.add_argument(
        'pdf_path',
        type=str,
        help='Caminho para o arquivo PDF do protocolo'
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        default=str(OUTPUT_DIR),
        help='Diretório de saída para os arquivos gerados'
    )
    parser.add_argument(
        '--pages',
        '-p',
        type=str,
        default=EXTRACTION_CONFIG['pages_to_extract'],
        help='Páginas a extrair (ex: "8-35")'
    )
    
    args = parser.parse_args()
    
    # Valida PDF
    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        logger.error(f"Arquivo PDF não encontrado: {pdf_path}")
        sys.exit(1)
    
    # Diretório de saída
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info("EXTRAÇÃO DE REGRAS DO PROTOCOLO")
    logger.info("=" * 70)
    logger.info(f"PDF: {pdf_path}")
    logger.info(f"Saída: {output_dir}")
    logger.info(f"Páginas: {args.pages}")
    logger.info("")
    
    try:
        # Cria extrator
        config = EXTRACTION_CONFIG.copy()
        config['pages_to_extract'] = args.pages
        
        extractor = ProtocolExtractor(pdf_path, config)
        
        # Extrai regras
        logger.info("Iniciando extração...")
        rules = extractor.extract_all_rules()
        
        # Salva resultados
        logger.info("Salvando resultados...")
        extractor.save_rules(output_dir)
        
        # Gera relatório de validação
        validation = extractor.get_validation_report()
        
        logger.info("")
        logger.info("=" * 70)
        logger.info("EXTRAÇÃO CONCLUÍDA COM SUCESSO")
        logger.info("=" * 70)
        logger.info(f"Total de regras extraídas: {validation['total_rules']}")
        logger.info(f"  - Requerem profilaxia: {validation['with_prophylaxis']}")
        logger.info(f"  - Não requerem profilaxia: {validation['without_prophylaxis']}")
        logger.info(f"  - Precisam validação: {validation['needs_validation']}")
        logger.info("")
        logger.info("Arquivos gerados:")
        logger.info(f"  - rules.json")
        logger.info(f"  - rules_index.json")
        logger.info(f"  - rules.meta.json")
        logger.info("")
        logger.info(f"Diretório: {output_dir}")
        
        # Verifica se extração foi completa
        if validation['total_rules'] < 100:
            logger.warning("")
            logger.warning("⚠ ATENÇÃO: Menos de 100 regras extraídas!")
            logger.warning("  Esperado: >150 regras")
            logger.warning("  Revisar PDF ou parâmetros de extração")
        
        return 0
        
    except Exception as e:
        logger.error(f"Erro durante extração: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())