#!/usr/bin/env python3
"""
Script para auditoria de cirurgias

Uso:
    python audit_surgeries.py <planilha_excel> <rules_json> [--output <diretorio_saida>]
"""
import argparse
import logging
from pathlib import Path
import sys

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from controllers import SurgeryAuditor, ReportGenerator
from models import ProtocolRulesRepository
from config import OUTPUT_DIR, AUDIT_CONFIG, LOGGING_CONFIG
from logging.config import dictConfig

# Configura logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Audita cirurgias comparando com protocolo de profilaxia'
    )
    parser.add_argument(
        'excel_path',
        type=str,
        help='Caminho para planilha Excel com cirurgias'
    )
    parser.add_argument(
        'rules_path',
        type=str,
        help='Caminho para arquivo rules.json com protocolo'
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        default=str(OUTPUT_DIR),
        help='Diretório de saída para relatórios'
    )
    parser.add_argument(
        '--sheet',
        '-s',
        type=str,
        default=None,
        help='Nome da aba do Excel (padrão: primeira aba)'
    )
    
    args = parser.parse_args()
    
    # Valida arquivos
    excel_path = Path(args.excel_path)
    if not excel_path.exists():
        logger.error(f"Arquivo Excel não encontrado: {excel_path}")
        sys.exit(1)
    
    rules_path = Path(args.rules_path)
    if not rules_path.exists():
        logger.error(f"Arquivo rules.json não encontrado: {rules_path}")
        sys.exit(1)
    
    # Diretório de saída
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 70)
    logger.info("AUDITORIA DE PROFILAXIA ANTIMICROBIANA")
    logger.info("=" * 70)
    logger.info(f"Planilha: {excel_path}")
    logger.info(f"Protocolo: {rules_path}")
    logger.info(f"Saída: {output_dir}")
    if args.sheet:
        logger.info(f"Aba: {args.sheet}")
    logger.info("")
    
    try:
        # Carrega regras do protocolo
        logger.info("Carregando protocolo...")
        rules_repo = ProtocolRulesRepository()
        rules_repo.load_from_json(rules_path)
        
        stats = rules_repo.get_statistics()
        logger.info(f"  OK {stats['total_rules']} regras carregadas")
        logger.info("")
        
        # Cria auditor
        auditor = SurgeryAuditor(rules_repo, AUDIT_CONFIG)
        
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
        
        # Gera relatórios
        logger.info("Gerando relatórios...")
        report_gen = ReportGenerator(results)
        
        # Excel completo
        excel_output = output_dir / 'auditoria_resultado.xlsx'
        report_gen.export_excel(excel_output)
        logger.info(f"  OK Excel: {excel_output.name}")
        
        # CSV
        csv_output = output_dir / 'auditoria_resultado.csv'
        report_gen.export_csv(csv_output)
        logger.info(f"  OK CSV: {csv_output.name}")
        
        # JSON
        json_output = output_dir / 'auditoria_resultado.json'
        report_gen.export_json(json_output)
        logger.info(f"  OK JSON: {json_output.name}")
        
        # Relatório resumido
        summary_output = output_dir / 'auditoria_resumo.txt'
        summary_text = report_gen.export_summary_report(summary_output)
        logger.info(f"  OK Resumo: {summary_output.name}")
        logger.info("")
        
        # Exibe estatísticas
        audit_stats = auditor.get_statistics()
        
        logger.info("=" * 70)
        logger.info("RESULTADOS DA AUDITORIA")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Total de cirurgias: {audit_stats['total_cirurgias']}")
        logger.info("")
        logger.info("Conformidade Final:")
        for status, count in audit_stats['conformidade_final'].items():
            pct = count / audit_stats['total_cirurgias'] * 100 if audit_stats['total_cirurgias'] > 0 else 0
            logger.info(f"  {status.upper():15s}: {count:4d} ({pct:5.1f}%)")
        logger.info("")
        logger.info(f"Taxa de Conformidade Total:   {audit_stats['taxas']['conformidade_total_pct']:.1f}%")
        logger.info(f"Taxa de Conformidade Estrita: {audit_stats['taxas']['conformidade_estrita_pct']:.1f}%")
        logger.info("")
        logger.info("=" * 70)
        logger.info("")
        logger.info(f"Relatórios salvos em: {output_dir}")
        
        # Alerta se muitas não conformidades
        nao_conforme = audit_stats['conformidade_final']['nao_conforme']
        if nao_conforme > 0:
            logger.warning("")
            logger.warning(f"ATENCAO: {nao_conforme} casos nao conformes detectados!")
            logger.warning("  Revise a aba 'Nao Conformes' no Excel para detalhes.")
        
        return 0
        
    except Exception as e:
        logger.error(f"Erro durante auditoria: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
