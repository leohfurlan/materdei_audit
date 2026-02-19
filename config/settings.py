"""
ConfiguraÃ§Ãµes do Sistema de Auditoria Mater Dei
"""
from pathlib import Path
from typing import Dict, Any
import os

# DiretÃ³rios base
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
TEMP_DIR = DATA_DIR / "temp"
LOGS_DIR = BASE_DIR / "logs"

# Garantir que os diretÃ³rios existem
for directory in [INPUT_DIR, OUTPUT_DIR, TEMP_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ConfiguraÃ§Ãµes de extraÃ§Ã£o de regras
EXTRACTION_CONFIG = {
    "pages_to_extract": "8-35",  # Paginas do PDF com tabelas
    "llm_backend": "gemini",
    "gemini_model": "gemini-2.5-flash",
    "langextract_model": "gemini-2.5-flash",
    "llm_max_chunk_chars": 12000,
    "llm_pages_per_chunk": 3,
    "gemini_max_output_tokens": 8192,
    "langextract_batch_length": 4,
    "langextract_max_workers": 4,
    "langextract_extraction_passes": 2,
    "camelot_flavor": "lattice",  # lattice ou stream
    # ParÃ¢metros especÃ­ficos do lattice
    "camelot_lattice_line_scale": 40,
    "camelot_lattice_line_tol": 2,
    "camelot_lattice_joint_tol": 2,
    "camelot_lattice_process_background": False,
    # ParÃ¢metros especÃ­ficos do stream (mantidos para fallback)
    "camelot_stream_edge_tol": 50,
    "camelot_stream_row_tol": 10,
    "camelot_stream_column_tol": 10,
    "min_table_rows": 2,
    "similarity_threshold": 0.7,  # Para fuzzy matching
}

# ConfiguraÃ§Ãµes de auditoria
AUDIT_CONFIG = {
    "match_threshold": 0.70,  # Score mÃ­nimo para match de procedimento
    "dose_tolerance_percent": 15,  # TolerÃ¢ncia de dose em %
    "timing_window_minutes": 60,  # Janela de 1 hora antes da incisÃ£o
    "alert_dose_tolerance_percent": 10,  # TolerÃ¢ncia para alertas
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
    "incision_time": "Hr IncisÃ£o",
    "atb_given": "AdministraÃ§Ã£o de Antibiotico",
    "atb_name": "AntibiÃ³tico",
    "atb_time": "Hr AntibiÃ³tico",
    "repique": "Repique",
    "repique_time": "Hora Repique",
    "patient_weight": "Peso (kg)",
    # Colunas de conformidade (se existirem)
    "conf_timing": "Conformidade 1Â° hora",
    "conf_dose": "Conformidade de Dose",
    "conf_choice": "Conformidade Escolha",
    "conf_final": "Conformidade Final",
}

# DicionÃ¡rio de medicamentos conhecidos
DRUG_DICTIONARY = {
    # Cefalosporinas
    "CEFAZOLINA": ["KEFAZOL", "CEFAZOLINA", "ANCEF"],
    "CEFUROXIMA": ["ZINACEF", "CEFUROXIMA"],
    "CEFTRIAXONE": ["ROCEFIN", "CEFTRIAXONA", "CEFTRIAXONE"],
    "CEFOXITINA": ["MEFOXIN", "CEFOXITINA"],
    
    # AminoglicosÃ­deos
    "GENTAMICINA": ["GENTAMICINA", "GARAMICINA"],
    "AMICACINA": ["AMICACINA", "NOVAMIN"],
    
    # GlicopeptÃ­deos
    "VANCOMICINA": ["VANCOMICINA", "VANCOCINA"],
    
    # Quinolonas
    "CIPROFLOXACINO": ["CIPROFLOXACINO", "CIPRO"],
    
    # Penicilinas
    "AMOXICILINA_CLAVULANATO": ["CLAVULIN", "AMOXICILINA+CLAVULANATO"],
    "AMPICILINA_SULBACTAM": ["UNASYN", "AMPICILINA+SULBACTAM"],
    
    # NitroimidazÃ³is
    "METRONIDAZOL": ["METRONIDAZOL", "FLAGYL"],
    
    # Outros
    "CLINDAMICINA": ["CLINDAMICINA", "DALACIN"],
}

# Categorias de conformidade
CONFORMITY_STATUS = {
    "CONFORME": "Procedimento em conformidade com o protocolo",
    "NAO_CONFORME": "Procedimento nÃ£o conforme - requer aÃ§Ã£o corretiva",
    "ALERTA": "Pequena diferenÃ§a detectada - revisar",
    "INDETERMINADO": "NÃ£o foi possÃ­vel determinar conformidade",
    "SEM_MATCH": "Procedimento nÃ£o encontrado no protocolo",
}

# ConfiguraÃ§Ãµes de logging
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
            "level": "INFO",
            "formatter": "detailed",
            "filename": str(LOGS_DIR / "audit.log"),
            "maxBytes": 104857600,  # 100MB
            "backupCount": 5,
        },
    },
    "loggers": {
        "pdfminer": {"level": "WARNING", "propagate": True},
        "pdfplumber": {"level": "WARNING", "propagate": True},
        "httpx": {"level": "WARNING", "propagate": True},
        "google_genai": {"level": "WARNING", "propagate": True},
        "absl": {"level": "WARNING", "propagate": True},
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
}

# VersÃ£o do sistema
SYSTEM_VERSION = "1.0.0"
SYSTEM_NAME = "Mater Dei - Sistema de Auditoria de Profilaxia Antimicrobiana"


