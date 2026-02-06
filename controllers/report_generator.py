"""
Controller para geração de relatórios de auditoria
"""
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd
import json

from models import AuditResult
from utils import format_conformity_reason

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Gera relatórios de auditoria em diversos formatos."""
    
    def __init__(self, audit_results: List[AuditResult]):
        """
        Inicializa o gerador de relatórios.
        
        Args:
            audit_results: Lista de resultados de auditoria
        """
        self.audit_results = audit_results
        self.df_results = None
        
    def prepare_dataframe(self) -> pd.DataFrame:
        """
        Prepara DataFrame com resultados de auditoria.
        
        Returns:
            DataFrame com todos os resultados
        """
        if self.df_results is not None:
            return self.df_results
        
        # Converte resultados para dicionários
        data = [result.to_dict() for result in self.audit_results]
        
        # Cria DataFrame
        self.df_results = pd.DataFrame(data)
        
        # Formata razões de conformidade para texto legível
        for col in [
            'conf_escolha_razao',
            'conf_dose_razao',
            'conf_timing_razao',
            'conf_repique_razao',
            'conf_final_razao',
        ]:
            if col in self.df_results.columns:
                self.df_results[f'{col}_legivel'] = self.df_results[col].apply(
                    lambda x: format_conformity_reason(x) if isinstance(x, str) else ''
                )
        
        return self.df_results
    
    def export_excel(self, output_path: Path) -> None:
        """
        Exporta relatório completo em Excel com múltiplas abas.
        
        Args:
            output_path: Caminho para arquivo de saída
        """
        logger.info(f"Gerando relatório Excel: {output_path}")
        
        df = self.prepare_dataframe()
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Aba 1: Todos os casos
            df.to_excel(writer, sheet_name='Todos os Casos', index=False)
            
            # Aba 2: Não conformes
            df_nao_conforme = df[df['conf_final'] == 'NAO_CONFORME']
            if len(df_nao_conforme) > 0:
                df_nao_conforme.to_excel(writer, sheet_name='Não Conformes', index=False)
            
            # Aba 3: Alertas
            df_alerta = df[df['conf_final'] == 'ALERTA']
            if len(df_alerta) > 0:
                df_alerta.to_excel(writer, sheet_name='Alertas', index=False)
            
            # Aba 4: Problemas de dose
            df_dose_problem = df[
                (df['conf_dose'] == 'NAO_CONFORME') & 
                (df['conf_escolha'] == 'CONFORME')
            ]
            if len(df_dose_problem) > 0:
                df_dose_problem.to_excel(writer, sheet_name='Problemas de Dose', index=False)
            
            # Aba 5: Sem match
            df_sem_match = df[df['match_score'] == 0]
            if len(df_sem_match) > 0:
                df_sem_match.to_excel(writer, sheet_name='Sem Match Protocolo', index=False)
            
            # Aba 6: Estatísticas
            df_stats = self._create_statistics_df(df)
            df_stats.to_excel(writer, sheet_name='Estatísticas', index=False)
        
        logger.info(f"Relatório Excel exportado: {output_path}")
    
    def _create_statistics_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Cria DataFrame com estatísticas.
        
        Args:
            df: DataFrame com resultados
            
        Returns:
            DataFrame com estatísticas
        """
        total = len(df)
        
        stats_data = [
            ['RESUMO GERAL', ''],
            ['Total de Cirurgias', total],
            ['', ''],
            ['CONFORMIDADE FINAL', ''],
            ['Conforme', (df['conf_final'] == 'CONFORME').sum()],
            ['Alerta (pequena diferença)', (df['conf_final'] == 'ALERTA').sum()],
            ['Não Conforme', (df['conf_final'] == 'NAO_CONFORME').sum()],
            ['Indeterminado', (df['conf_final'] == 'INDETERMINADO').sum()],
            ['', ''],
            ['CONFORMIDADE POR CRITÉRIO', ''],
            ['Escolha - Conforme', (df['conf_escolha'] == 'CONFORME').sum()],
            ['Escolha - Não Conforme', (df['conf_escolha'] == 'NAO_CONFORME').sum()],
            ['Dose - Conforme', (df['conf_dose'] == 'CONFORME').sum()],
            ['Dose - Alerta', (df['conf_dose'] == 'ALERTA').sum()],
            ['Dose - Não Conforme', (df['conf_dose'] == 'NAO_CONFORME').sum()],
            ['Timing - Conforme', (df['conf_timing'] == 'CONFORME').sum()],
            ['Timing - Não Conforme', (df['conf_timing'] == 'NAO_CONFORME').sum()],
            ['Repique - Conforme', (df['conf_repique'] == 'CONFORME').sum()],
            ['Repique - Não Conforme', (df['conf_repique'] == 'NAO_CONFORME').sum()],
            ['', ''],
            ['QUALIDADE DO MATCH', ''],
            ['Match Perfeito (≥0.9)', (df['match_score'] >= 0.9).sum()],
            ['Match Bom (0.7-0.9)', ((df['match_score'] >= 0.7) & (df['match_score'] < 0.9)).sum()],
            ['Match Fraco (<0.7)', ((df['match_score'] > 0) & (df['match_score'] < 0.7)).sum()],
            ['Sem Match', (df['match_score'] == 0).sum()],
            ['', ''],
            ['TAXAS', ''],
            ['Taxa de Conformidade (com alertas)', f"{((df['conf_final'].isin(['CONFORME', 'ALERTA'])).sum() / total * 100):.1f}%"],
            ['Taxa de Conformidade Estrita', f"{((df['conf_final'] == 'CONFORME').sum() / total * 100):.1f}%"],
        ]
        
        return pd.DataFrame(stats_data, columns=['Métrica', 'Valor'])
    
    def export_csv(self, output_path: Path) -> None:
        """
        Exporta resultados em CSV simples.
        
        Args:
            output_path: Caminho para arquivo de saída
        """
        logger.info(f"Gerando relatório CSV: {output_path}")
        
        df = self.prepare_dataframe()
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        logger.info(f"Relatório CSV exportado: {output_path}")
    
    def export_json(self, output_path: Path) -> None:
        """
        Exporta resultados em JSON.
        
        Args:
            output_path: Caminho para arquivo de saída
        """
        logger.info(f"Gerando relatório JSON: {output_path}")
        
        df = self.prepare_dataframe()
        
        # Converte para dict records
        data = df.to_dict(orient='records')
        
        # Salva JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info(f"Relatório JSON exportado: {output_path}")
    
    def export_summary_report(self, output_path: Path) -> None:
        """
        Exporta relatório resumido em texto.
        
        Args:
            output_path: Caminho para arquivo de saída
        """
        logger.info(f"Gerando relatório resumido: {output_path}")
        
        df = self.prepare_dataframe()
        total = len(df)
        
        # Monta relatório
        lines = []
        lines.append("=" * 70)
        lines.append("RELATÓRIO DE AUDITORIA - PROFILAXIA ANTIMICROBIANA")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"Data do Relatório: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        lines.append(f"Total de Cirurgias Auditadas: {total}")
        lines.append("")
        
        lines.append("-" * 70)
        lines.append("RESUMO DE CONFORMIDADE")
        lines.append("-" * 70)
        
        conforme = (df['conf_final'] == 'CONFORME').sum()
        alerta = (df['conf_final'] == 'ALERTA').sum()
        nao_conforme = (df['conf_final'] == 'NAO_CONFORME').sum()
        indeterminado = (df['conf_final'] == 'INDETERMINADO').sum()
        
        lines.append(f"  Conforme:              {conforme:4d} ({conforme/total*100:5.1f}%)")
        lines.append(f"  Alerta:                {alerta:4d} ({alerta/total*100:5.1f}%)")
        lines.append(f"  Não Conforme:          {nao_conforme:4d} ({nao_conforme/total*100:5.1f}%)")
        lines.append(f"  Indeterminado:         {indeterminado:4d} ({indeterminado/total*100:5.1f}%)")
        lines.append("")
        
        taxa_total = (conforme + alerta) / total * 100 if total > 0 else 0
        taxa_estrita = conforme / total * 100 if total > 0 else 0
        
        lines.append(f"  Taxa de Conformidade Total:   {taxa_total:.1f}%")
        lines.append(f"  Taxa de Conformidade Estrita: {taxa_estrita:.1f}%")
        lines.append("")
        
        lines.append("-" * 70)
        lines.append("CONFORMIDADE POR CRITÉRIO")
        lines.append("-" * 70)
        
        escolha_conf = (df['conf_escolha'] == 'CONFORME').sum()
        dose_conf = (df['conf_dose'] == 'CONFORME').sum()
        timing_conf = (df['conf_timing'] == 'CONFORME').sum()
        repique_conf = (df['conf_repique'] == 'CONFORME').sum()
        
        lines.append(f"  Escolha de Antibiótico:  {escolha_conf}/{total} ({escolha_conf/total*100:.1f}%)")
        lines.append(f"  Dose Correta:            {dose_conf}/{total} ({dose_conf/total*100:.1f}%)")
        lines.append(f"  Timing Adequado:         {timing_conf}/{total} ({timing_conf/total*100:.1f}%)")
        lines.append(f"  Repique Adequado:        {repique_conf}/{total} ({repique_conf/total*100:.1f}%)")
        lines.append("")
        
        # Principais problemas
        lines.append("-" * 70)
        lines.append("PRINCIPAIS NÃO CONFORMIDADES")
        lines.append("-" * 70)
        
        if nao_conforme > 0:
            df_nc = df[df['conf_final'] == 'NAO_CONFORME']
            
            # Conta razões mais comuns
            razoes_escolha = df_nc['conf_escolha_razao'].value_counts()
            razoes_dose = df_nc['conf_dose_razao'].value_counts()
            razoes_timing = df_nc['conf_timing_razao'].value_counts()
            
            if len(razoes_escolha) > 0:
                lines.append("")
                lines.append("  Problemas de Escolha:")
                for razao, count in razoes_escolha.head(3).items():
                    lines.append(f"    - {format_conformity_reason(razao)}: {count} casos")
            
            if len(razoes_dose) > 0:
                lines.append("")
                lines.append("  Problemas de Dose:")
                for razao, count in razoes_dose.head(3).items():
                    lines.append(f"    - {format_conformity_reason(razao)}: {count} casos")
            
            if len(razoes_timing) > 0:
                lines.append("")
                lines.append("  Problemas de Timing:")
                for razao, count in razoes_timing.head(3).items():
                    lines.append(f"    - {format_conformity_reason(razao)}: {count} casos")
        else:
            lines.append("  ✓ Nenhuma não conformidade detectada!")
        
        lines.append("")
        lines.append("=" * 70)
        
        # Salva arquivo
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Relatório resumido exportado: {output_path}")
        
        # Retorna também as linhas para print
        return '\n'.join(lines)
    
    def get_non_conformities_summary(self) -> List[Dict[str, Any]]:
        """
        Retorna resumo de não conformidades.
        
        Returns:
            Lista de dicionários com resumo de cada não conformidade
        """
        df = self.prepare_dataframe()
        df_nc = df[df['conf_final'] == 'NAO_CONFORME']
        
        summary = []
        
        for _, row in df_nc.iterrows():
            summary.append({
                'data': row['data'],
                'procedimento': row['procedimento'],
                'atb_administrado': row['atb_detectado'],
                'problemas': [
                    format_conformity_reason(row['conf_escolha_razao']) if row['conf_escolha'] == 'NAO_CONFORME' else None,
                    format_conformity_reason(row['conf_dose_razao']) if row['conf_dose'] == 'NAO_CONFORME' else None,
                    format_conformity_reason(row['conf_timing_razao']) if row['conf_timing'] == 'NAO_CONFORME' else None,
                    format_conformity_reason(row['conf_repique_razao']) if row['conf_repique'] == 'NAO_CONFORME' else None,
                ],
            })
        
        return summary
