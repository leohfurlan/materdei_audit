"""
Controller para extração de regras do protocolo a partir do PDF
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import camelot
import pdfplumber

from ..models import ProtocolRule, Recommendation, Drug, ProtocolRulesRepository
from ..utils import normalize_text, extract_drug_names
from ..config import EXTRACTION_CONFIG, DRUG_DICTIONARY

logger = logging.getLogger(__name__)


class ProtocolExtractor:
    """Extrai regras do protocolo a partir de PDF."""
    
    def __init__(self, pdf_path: Path, config: Dict[str, Any] = None):
        """
        Inicializa o extrator.
        
        Args:
            pdf_path: Caminho para o PDF do protocolo
            config: Configurações de extração (usa EXTRACTION_CONFIG se None)
        """
        self.pdf_path = pdf_path
        self.config = config or EXTRACTION_CONFIG
        self.rules: List[ProtocolRule] = []
        
    def extract_all_rules(self) -> List[ProtocolRule]:
        """
        Extrai todas as regras do protocolo.
        
        Returns:
            Lista de regras extraídas
        """
        logger.info(f"Iniciando extração de regras de: {self.pdf_path}")
        
        # Extrai tabelas do PDF
        tables = self._extract_tables()
        logger.info(f"Extraídas {len(tables)} tabelas do PDF")
        
        # Processa cada tabela
        all_rules = []
        for i, table in enumerate(tables):
            logger.debug(f"Processando tabela {i+1}/{len(tables)}")
            rules = self._process_table(table, i)
            all_rules.extend(rules)
        
        # Remove duplicatas
        self.rules = self._deduplicate_rules(all_rules)
        
        logger.info(f"Extração concluída: {len(self.rules)} regras únicas")
        
        return self.rules
    
    def _extract_tables(self) -> List[pd.DataFrame]:
        """
        Extrai tabelas do PDF usando múltiplas estratégias.
        
        Returns:
            Lista de DataFrames
        """
        pages = self.config.get('pages_to_extract', '8-35')
        
        tables = []
        
        # Estratégia 1: Camelot lattice (tabelas com bordas)
        try:
            logger.debug("Tentando extração com Camelot (lattice)")
            camelot_tables = camelot.read_pdf(
                str(self.pdf_path),
                pages=pages,
                flavor='lattice',
                edge_tol=self.config.get('camelot_edge_tol', 50),
                row_tol=self.config.get('camelot_row_tol', 10),
                column_tol=self.config.get('camelot_column_tol', 10),
            )
            
            for table in camelot_tables:
                df = table.df
                if len(df) >= self.config.get('min_table_rows', 2):
                    tables.append(df)
                    
            logger.debug(f"Camelot lattice: {len(tables)} tabelas")
        except Exception as e:
            logger.warning(f"Erro na extração com Camelot lattice: {e}")
        
        # Estratégia 2: Camelot stream (tabelas sem bordas completas)
        try:
            logger.debug("Tentando extração com Camelot (stream)")
            camelot_tables = camelot.read_pdf(
                str(self.pdf_path),
                pages=pages,
                flavor='stream',
            )
            
            for table in camelot_tables:
                df = table.df
                if len(df) >= self.config.get('min_table_rows', 2):
                    # Verifica se já não temos tabela similar
                    if not self._is_duplicate_table(df, tables):
                        tables.append(df)
                        
            logger.debug(f"Total após Camelot stream: {len(tables)} tabelas")
        except Exception as e:
            logger.warning(f"Erro na extração com Camelot stream: {e}")
        
        return tables
    
    def _is_duplicate_table(self, df: pd.DataFrame, existing_tables: List[pd.DataFrame]) -> bool:
        """
        Verifica se uma tabela já existe na lista.
        
        Args:
            df: DataFrame a verificar
            existing_tables: Lista de tabelas existentes
            
        Returns:
            True se é duplicata
        """
        for existing_df in existing_tables:
            if df.shape == existing_df.shape:
                # Compara primeiras células
                if df.iloc[0, 0] == existing_df.iloc[0, 0]:
                    return True
        return False
    
    def _process_table(self, df: pd.DataFrame, table_index: int) -> List[ProtocolRule]:
        """
        Processa uma tabela e extrai regras.
        
        Args:
            df: DataFrame da tabela
            table_index: Índice da tabela
            
        Returns:
            Lista de regras extraídas
        """
        rules = []
        
        # Detecta seção da tabela
        section = self._detect_section(df)
        
        # Processa cada linha da tabela
        for idx, row in df.iterrows():
            try:
                rule = self._parse_row_to_rule(row, section, table_index, idx)
                if rule:
                    rules.append(rule)
            except Exception as e:
                logger.warning(f"Erro ao processar linha {idx} da tabela {table_index}: {e}")
        
        return rules
    
    def _detect_section(self, df: pd.DataFrame) -> str:
        """
        Detecta a seção/categoria da tabela.
        
        Args:
            df: DataFrame da tabela
            
        Returns:
            Nome da seção
        """
        # Procura por palavras-chave nas primeiras linhas
        keywords = {
            'CABEÇA E PESCOÇO': ['cabeca', 'pescoco'],
            'CIRURGIA CARDIOVASCULAR': ['cardiovascular', 'cardiaca'],
            'CIRURGIA GERAL': ['cirurgia geral', 'abdomen'],
            'GINECOLOGIA': ['ginecologia', 'ginecologica'],
            'NEUROCIRURGIA': ['neurocirurgia', 'neurocirug'],
            'OFTALMOLOGIA': ['oftalmologia', 'oftalmo'],
            'ORTOPEDIA': ['ortopedia', 'ortopedica'],
            'OTORRINOLARINGOLOGIA': ['otorrino', 'orl'],
            'UROLOGIA': ['urologia', 'urologica'],
        }
        
        # Examina primeiras 3 linhas
        text = ' '.join([str(cell) for row in df.head(3).values for cell in row])
        text_norm = normalize_text(text)
        
        for section_name, section_keywords in keywords.items():
            for keyword in section_keywords:
                if keyword in text_norm:
                    return section_name
        
        return "OUTROS"
    
    def _parse_row_to_rule(self, row: pd.Series, section: str, 
                          table_index: int, row_index: int) -> Optional[ProtocolRule]:
        """
        Parseia uma linha da tabela para uma regra do protocolo.
        
        Args:
            row: Série pandas representando a linha
            section: Seção da tabela
            table_index: Índice da tabela
            row_index: Índice da linha
            
        Returns:
            ProtocolRule ou None se inválida
        """
        # Extrai dados básicos (assume formato padrão do protocolo)
        # Colunas esperadas: Procedimento | 1ª Opção | Alergia | Pós-operatório
        
        if len(row) < 3:
            return None
        
        procedure = str(row.iloc[0]).strip()
        
        # Ignora linhas de cabeçalho ou vazias
        if not procedure or len(procedure) < 3:
            return None
        if normalize_text(procedure) in ['procedimento', 'cirurgia', '']:
            return None
        
        # Recomendação primária
        primary_text = str(row.iloc[1]).strip() if len(row) > 1 else ""
        
        # Recomendação para alergia
        allergy_text = str(row.iloc[2]).strip() if len(row) > 2 else ""
        
        # Pós-operatório
        postop = str(row.iloc[3]).strip() if len(row) > 3 else ""
        
        # Verifica se requer profilaxia
        is_prophylaxis_required = self._requires_prophylaxis(primary_text)
        
        # Parseia recomendações
        primary_rec = self._parse_recommendation(primary_text)
        allergy_rec = self._parse_recommendation(allergy_text)
        
        # Gera ID único
        rule_id = f"rule_{section}_{table_index}_{row_index}"
        
        # Normaliza nome do procedimento
        procedure_norm = normalize_text(procedure)
        
        # Cria regra
        rule = ProtocolRule(
            rule_id=rule_id,
            section=section,
            procedure=procedure,
            procedure_normalized=procedure_norm,
            is_prophylaxis_required=is_prophylaxis_required,
            primary_recommendation=primary_rec,
            allergy_recommendation=allergy_rec,
            postoperative=postop,
            audit_category=self._categorize_rule(primary_rec, allergy_rec),
            original_row_index=int(row_index),
        )
        
        return rule
    
    def _requires_prophylaxis(self, text: str) -> bool:
        """
        Determina se o texto indica que profilaxia é requerida.
        
        Args:
            text: Texto da recomendação
            
        Returns:
            True se profilaxia é requerida
        """
        text_norm = normalize_text(text)
        
        negative_patterns = [
            'nao recomendado',
            'sem profilaxia',
            'dispensavel',
            'desnecessario',
        ]
        
        for pattern in negative_patterns:
            if pattern in text_norm:
                return False
        
        # Se menciona medicamento, provavelmente requer
        if extract_drug_names(text, DRUG_DICTIONARY):
            return True
        
        return True  # Default: requer
    
    def _parse_recommendation(self, text: str) -> Recommendation:
        """
        Parseia texto de recomendação em objeto Recommendation.
        
        Args:
            text: Texto da recomendação
            
        Returns:
            Objeto Recommendation
        """
        if not text or len(text) < 3:
            return Recommendation(raw_text=text)
        
        # Extrai medicamentos
        drug_names = extract_drug_names(text, DRUG_DICTIONARY)
        
        # Cria objetos Drug
        drugs = []
        for drug_name in drug_names:
            # Tenta extrair dose do texto
            dose = self._extract_dose_from_context(text, drug_name)
            
            drug = Drug(
                name=drug_name,
                dose=dose,
                route='IV',  # Assume IV como padrão
            )
            drugs.append(drug)
        
        return Recommendation(
            drugs=drugs,
            raw_text=text,
        )
    
    def _extract_dose_from_context(self, text: str, drug_name: str) -> Optional[str]:
        """
        Extrai dose do contexto em torno do nome do medicamento.
        
        Args:
            text: Texto completo
            drug_name: Nome do medicamento
            
        Returns:
            Texto da dose ou None
        """
        # Procura por padrão de dose próximo ao medicamento
        # Ex: "Cefazolina 2g" ou "2g de Cefazolina"
        pattern = r'(\d+(?:\.\d+)?\s*(?:g|mg|mcg))'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            return matches[0]
        
        return None
    
    def _categorize_rule(self, primary: Recommendation, allergy: Recommendation) -> str:
        """
        Categoriza a regra para auditoria.
        
        Args:
            primary: Recomendação primária
            allergy: Recomendação para alergia
            
        Returns:
            Categoria da regra
        """
        if not primary.drugs:
            return "REQUIRES_VALIDATION"
        
        if not allergy.drugs:
            return "REQUIRES_VALIDATION"
        
        return "OK"
    
    def _deduplicate_rules(self, rules: List[ProtocolRule]) -> List[ProtocolRule]:
        """
        Remove regras duplicadas.
        
        Args:
            rules: Lista de regras
            
        Returns:
            Lista sem duplicatas
        """
        seen = set()
        unique_rules = []
        
        for rule in rules:
            # Usa procedimento normalizado como chave
            key = rule.procedure_normalized
            
            if key and key not in seen:
                seen.add(key)
                unique_rules.append(rule)
        
        return unique_rules
    
    def save_rules(self, output_dir: Path) -> None:
        """
        Salva regras extraídas em arquivos.
        
        Args:
            output_dir: Diretório de saída
        """
        if not self.rules:
            logger.warning("Nenhuma regra para salvar")
            return
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cria repositório e salva
        repo = ProtocolRulesRepository()
        repo.rules = self.rules
        repo.save_to_json(output_dir / 'rules.json')
        
        logger.info(f"Regras salvas em: {output_dir}")
    
    def get_validation_report(self) -> Dict[str, Any]:
        """
        Gera relatório de validação das regras extraídas.
        
        Returns:
            Dicionário com estatísticas de validação
        """
        total = len(self.rules)
        
        with_prophylaxis = sum(1 for r in self.rules if r.is_prophylaxis_required)
        without_prophylaxis = total - with_prophylaxis
        
        needs_validation = sum(1 for r in self.rules if r.audit_category == "REQUIRES_VALIDATION")
        
        with_primary_drugs = sum(1 for r in self.rules if r.primary_recommendation.drugs)
        with_allergy_drugs = sum(1 for r in self.rules if r.allergy_recommendation.drugs)
        
        sections = {}
        for rule in self.rules:
            sections[rule.section] = sections.get(rule.section, 0) + 1
        
        return {
            'total_rules': total,
            'with_prophylaxis': with_prophylaxis,
            'without_prophylaxis': without_prophylaxis,
            'needs_validation': needs_validation,
            'with_primary_drugs': with_primary_drugs,
            'with_allergy_drugs': with_allergy_drugs,
            'sections': sections,
        }