"""
Utilitários para validação de dados
"""
from typing import Dict, List, Any, Tuple
import pandas as pd


def validate_excel_structure(df: pd.DataFrame, required_columns: Dict[str, str]) -> Tuple[bool, List[str]]:
    """
    Valida se o DataFrame do Excel possui as colunas necessárias.
    
    Args:
        df: DataFrame a validar
        required_columns: Dicionário {key: nome_coluna_esperado}
        
    Returns:
        Tupla (is_valid, missing_columns)
    """
    missing = []
    
    for key, col_name in required_columns.items():
        if col_name not in df.columns:
            missing.append(f"{key} ({col_name})")
    
    return len(missing) == 0, missing


def validate_rules_structure(rules: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """
    Valida estrutura das regras extraídas do protocolo.
    
    Args:
        rules: Lista de regras
        
    Returns:
        Tupla (is_valid, errors)
    """
    errors = []
    
    if not rules:
        errors.append("Nenhuma regra fornecida")
        return False, errors
    
    required_fields = [
        'rule_id',
        'section',
        'procedure',
        'procedure_normalized',
        'is_prophylaxis_required',
        'primary_recommendation',
        'allergy_recommendation',
    ]
    
    for i, rule in enumerate(rules):
        for field in required_fields:
            if field not in rule:
                errors.append(f"Regra {i}: campo '{field}' ausente")
        
        # Valida estrutura de recomendação
        if 'primary_recommendation' in rule:
            if 'drugs' not in rule['primary_recommendation']:
                errors.append(f"Regra {i}: primary_recommendation sem 'drugs'")
    
    return len(errors) == 0, errors


def validate_row_data(row: pd.Series, required_fields: List[str]) -> Tuple[bool, List[str]]:
    """
    Valida se uma linha do Excel possui dados válidos.
    
    Args:
        row: Série do pandas representando uma linha
        required_fields: Lista de campos obrigatórios
        
    Returns:
        Tupla (is_valid, missing_fields)
    """
    missing = []
    
    for field in required_fields:
        if field not in row or pd.isna(row[field]) or str(row[field]).strip() == '':
            missing.append(field)
    
    return len(missing) == 0, missing


def is_valid_yes_no(value: Any) -> bool:
    """
    Verifica se um valor é um sim/não válido.
    
    Args:
        value: Valor a verificar
        
    Returns:
        True se é sim/não válido
    """
    if pd.isna(value):
        return False
    
    value_str = str(value).strip().upper()
    return value_str in ['SIM', 'NAO', 'NÃO', 'S', 'N', 'YES', 'NO', 'Y']


def normalize_yes_no(value: Any) -> str:
    """
    Normaliza valor sim/não.
    
    Args:
        value: Valor a normalizar
        
    Returns:
        'SIM' ou 'NAO'
    """
    if pd.isna(value):
        return 'NAO'
    
    value_str = str(value).strip().upper()
    
    if value_str in ['SIM', 'S', 'YES', 'Y']:
        return 'SIM'
    else:
        return 'NAO'


def check_data_completeness(df: pd.DataFrame, columns: List[str]) -> Dict[str, Any]:
    """
    Verifica completude dos dados em colunas específicas.
    
    Args:
        df: DataFrame
        columns: Lista de colunas para verificar
        
    Returns:
        Dicionário com estatísticas de completude
    """
    stats = {
        'total_rows': len(df),
        'columns': {}
    }
    
    for col in columns:
        if col in df.columns:
            non_null = df[col].notna().sum()
            null_count = df[col].isna().sum()
            stats['columns'][col] = {
                'non_null': int(non_null),
                'null': int(null_count),
                'completeness_pct': float(non_null / len(df) * 100) if len(df) > 0 else 0.0
            }
    
    return stats