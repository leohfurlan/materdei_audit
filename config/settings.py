"""
Configurações do Sistema de Auditoria Mater Dei
"""
from pathlib import Path
from typing import Dict, Any
import os

# Diretórios base
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = DATA_DIR / "temp"
LOGS_DIR = BASE_DIR / "logs"

# Garantir que os diretórios existem
for directory in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Configurações de extração de regras
EXTRACTION_CONFIG = {
    "pages_to_extract": "8-35",  # Páginas do PDF com tabelas
    "camelot_flavor": "lattice",  # lattice ou stream
    # Parâmetros específicos do lattice
    "camelot_lattice_line_scale": 40,
    "camelot_lattice_line_tol": 2,
    "camelot_lattice_joint_tol": 2,
    "camelot_lattice_process_background": False,
    # Parâmetros específicos do stream (mantidos para fallback)
    "camelot_stream_edge_tol": 50,
    "camelot_stream_row_tol": 10,
    "camelot_stream_column_tol": 10,
    "min_table_rows": 2,
    "similarity_threshold": 0.7,  # Para fuzzy matching
}

# Configurações de auditoria
AUDIT_CONFIG = {
    "match_threshold": 0.70,  # Score mínimo para match de procedimento
    "dose_tolerance_percent": 15,  # Tolerância de dose em %
    "timing_window_minutes": 60,  # Janela de 1 hora antes da incisão
    "alert_dose_tolerance_percent": 10,  # Tolerância para alertas
}

# Intervalos de repique (redosing) em minutos
REDOSING_INTERVALS = {
    "CEFAZOLINA": 240,
    "CEFUROXIMA": 240,
    "CEFOXITINA": 120,
    "CLINDAMICINA": 360,
    "VANCOMICINA": 0,
    "GENTAMICINA": 0,
    "CIPROFLOXACINO": 0,
}

# Mapeamento de colunas da planilha Excel
EXCEL_COLUMNS = {
    "date": "Dt Cirurgia",
    "procedure": "Cirurgia",
    "specialty": "Especialidade",
    "incision_time": "Hr Incisão",
    "atb_given": "Administração de Antibiotico",
    "atb_name": "Antibiótico",
    "atb_time": "Hr Antibiótico",
    "repique": "Repique",
    "repique_time": "Hora Repique",
    "patient_weight": "Peso (kg)",
    # Colunas de conformidade (se existirem)
    "conf_timing": "Conformidade 1° hora",
    "conf_dose": "Conformidade de Dose",
    "conf_choice": "Conformidade Escolha",
    "conf_final": "Conformidade Final",
}

# Dicionário de medicamentos conhecidos
DRUG_DICTIONARY = {
    # Cefalosporinas
    "CEFAZOLINA": ["KEFAZOL", "CEFAZOLINA", "ANCEF"],
    "CEFUROXIMA": ["ZINACEF", "CEFUROXIMA"],
    "CEFTRIAXONE": ["ROCEFIN", "CEFTRIAXONA", "CEFTRIAXONE"],
    "CEFOXITINA": ["MEFOXIN", "CEFOXITINA"],
    
    # Aminoglicosídeos
    "GENTAMICINA": ["GENTAMICINA", "GARAMICINA"],
    "AMICACINA": ["AMICACINA", "NOVAMIN"],
    
    # Glicopeptídeos
    "VANCOMICINA": ["VANCOMICINA", "VANCOCINA"],
    
    # Quinolonas
    "CIPROFLOXACINO": ["CIPROFLOXACINO", "CIPRO"],
    
    # Penicilinas
    "AMOXICILINA_CLAVULANATO": ["CLAVULIN", "AMOXICILINA+CLAVULANATO"],
    "AMPICILINA_SULBACTAM": ["UNASYN", "AMPICILINA+SULBACTAM"],
    
    # Nitroimidazóis
    "METRONIDAZOL": ["METRONIDAZOL", "FLAGYL"],
    
    # Outros
    "CLINDAMICINA": ["CLINDAMICINA", "DALACIN"],
}

# Categorias de conformidade
CONFORMITY_STATUS = {
    "CONFORME": "Procedimento em conformidade com o protocolo",
    "NAO_CONFORME": "Procedimento não conforme - requer ação corretiva",
    "ALERTA": "Pequena diferença detectada - revisar",
    "INDETERMINADO": "Não foi possível determinar conformidade",
    "SEM_MATCH": "Procedimento não encontrado no protocolo",
}

# Configurações de logging
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": str(LOGS_DIR / "audit.log"),
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["console", "file"],
    },
}

# Versão do sistema
SYSTEM_VERSION = "1.0.0"
SYSTEM_NAME = "Mater Dei - Sistema de Auditoria de Profilaxia Antimicrobiana"
