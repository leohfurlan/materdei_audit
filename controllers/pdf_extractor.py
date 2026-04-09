"""
Extrator determinístico de regras de profilaxia antimicrobiana a partir do PDF institucional.

Substitui o pipeline LLM (Gemini/LangExtract) por parsing baseado em pdfplumber.
O PDF do protocolo usa tabelas com 4 colunas fixas, adequadas para parsing direto.

Schema de saída: compatível com rules.json consumido por surgery_auditor.py
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de mapeamento
# ---------------------------------------------------------------------------

# Mapeamento de seções do protocolo para nomes canônicos
SECTION_ALIASES: Dict[str, str] = {
    "cabeça e pescoço": "CABEÇA E PESCOÇO",
    "cabeca e pescoco": "CABEÇA E PESCOÇO",
    "cabeça": "CABEÇA E PESCOÇO",
    "cardíaca": "CARDÍACA",
    "cardiaca": "CARDÍACA",
    "cardiac": "CARDÍACA",
    "vascular": "VASCULAR",
    "gastrointestinal": "GASTROINTESTINAL",
    "trato gastrointestinal": "GASTROINTESTINAL",
    "torácica": "TORÁCICA",
    "toracica": "TORÁCICA",
    "neurocirurgia": "NEUROCIRURGIA",
    "neuro": "NEUROCIRURGIA",
    "ginecológica": "GINECOLÓGICA",
    "ginecologica": "GINECOLÓGICA",
    "obstetrícia": "OBSTETRÍCIA",
    "obstetricia": "OBSTETRÍCIA",
    "ortopédica": "ORTOPÉDICA",
    "ortopedica": "ORTOPÉDICA",
    "ortopedia": "ORTOPÉDICA",
    "neonatal": "NEONATAL E PEDIÁTRICA",
    "pediátrica": "NEONATAL E PEDIÁTRICA",
    "pediatrica": "NEONATAL E PEDIÁTRICA",
    "plástica": "PLÁSTICA",
    "plastica": "PLÁSTICA",
    "urológica": "UROLÓGICA",
    "urologica": "UROLÓGICA",
    "urologia": "UROLÓGICA",
    "trauma": "TRAUMA",
    "limpa": "LIMPA",
    "não requer": "SEM_PROFILAXIA",
    "nao requer": "SEM_PROFILAXIA",
    "não recomendado": "SEM_PROFILAXIA",
    "nao recomendado": "SEM_PROFILAXIA",
    "não se recomenda": "SEM_PROFILAXIA",
}

# Padrões regex para extrair droga + dose de textos como "Cefazolina 2g EV"
DRUG_DOSE_PATTERN = re.compile(
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-\/\+]+?)"   # nome do medicamento
    r"\s+"
    r"([\d][.,\d]*\s*(?:mg/kg|mg|g|UI|MUI|mcg))"  # dose com unidade
    r"(?:\s*(?:EV|IV|IM|VO|SC|SL))?"           # via opcional
    ,
    re.IGNORECASE,
)

# Padrões para via de administração
ROUTE_PATTERN = re.compile(r"\b(EV|IV|IM|VO|SC|SL)\b", re.IGNORECASE)

# Frases que indicam "sem profilaxia"
NO_PROPHYLAXIS_MARKERS = [
    "não recomendado",
    "nao recomendado",
    "não se recomenda",
    "nao se recomenda",
    "não indicado",
    "nao indicado",
    "profilaxia não recomendada",
    "sem profilaxia",
]

# Separadores de múltiplos antibióticos na mesma célula
DRUG_SEPARATOR_PATTERN = re.compile(
    r"\n|(?<!\d)\+(?!\d)|(?<![A-Za-z])ou(?![A-Za-z])|(?<![A-Za-z])and(?![A-Za-z])",
    re.IGNORECASE,
)

# Normalização de nomes de drogas (variações → canônico)
DRUG_NAME_NORMALIZATION: Dict[str, str] = {
    "cefazolina": "CEFAZOLINA",
    "cefazolin": "CEFAZOLINA",
    "cefuroxima": "CEFUROXIMA",
    "cefuroxime": "CEFUROXIMA",
    "ceftriaxone": "CEFTRIAXONE",
    "ceftriaxona": "CEFTRIAXONE",
    "cefoxitina": "CEFOXITINA",
    "clindamicina": "CLINDAMICINA",
    "clindamycin": "CLINDAMICINA",
    "gentamicina": "GENTAMICINA",
    "gentamicin": "GENTAMICINA",
    "vancomicina": "VANCOMICINA",
    "vancomycin": "VANCOMICINA",
    "metronidazol": "METRONIDAZOL",
    "metronidazole": "METRONIDAZOL",
    "ciprofloxacino": "CIPROFLOXACINO",
    "ciprofloxacin": "CIPROFLOXACINO",
    "ampicilina": "AMPICILINA",
    "ampicillin": "AMPICILINA",
    "amoxicilina": "AMOXICILINA",
    "amoxicillin": "AMOXICILINA",
    "azitromicina": "AZITROMICINA",
    "azithromycin": "AZITROMICINA",
    "doxiciclina": "DOXICICLINA",
    "doxycycline": "DOXICICLINA",
    "sulfametoxazol": "SULFAMETOXAZOL_TRIMETOPRIM",
    "sulfametoxazol-trimetoprim": "SULFAMETOXAZOL_TRIMETOPRIM",
    "smz/tmp": "SULFAMETOXAZOL_TRIMETOPRIM",
    "cotrimoxazol": "SULFAMETOXAZOL_TRIMETOPRIM",
    "bactrim": "SULFAMETOXAZOL_TRIMETOPRIM",
    "teicoplanina": "TEICOPLANINA",
    "teicoplanin": "TEICOPLANINA",
    "penicilina g": "PENICILINA_G_CRISTALINA",
    "benzilpenicilina": "PENICILINA_G_CRISTALINA",
}


# ---------------------------------------------------------------------------
# Utilitários de texto
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Remove acentos, caracteres de controle PDF, converte para minúsculas e colapsa espaços."""
    if not text:
        return ""
    # Remove caracteres de uso privado Unicode comuns em PDFs (ex.: \uf0a0, \uf0b7)
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower().strip())


def normalize_drug_name(raw: str) -> str:
    """Normaliza nome do medicamento para forma canônica."""
    key = normalize_text(raw)
    for pattern, canonical in DRUG_NAME_NORMALIZATION.items():
        if key.startswith(pattern) or pattern in key:
            return canonical
    return raw.upper().strip()


def normalize_dose(raw: str) -> str:
    """Converte dose para mg quando possível; mantém original caso contrário."""
    raw = raw.strip().replace(",", ".")
    m = re.match(r"([\d.]+)\s*(g|mg/kg|mg|UI|MUI|mcg)", raw, re.IGNORECASE)
    if not m:
        return raw
    value, unit = float(m.group(1)), m.group(2).lower()
    if unit == "g":
        return f"{int(value * 1000)}mg"
    return f"{int(value) if value == int(value) else value}{unit}"


def is_section_header(row: List[Optional[str]]) -> bool:
    """
    Detecta se uma linha de tabela é um cabeçalho de seção.
    Critérios: primeira célula com texto em caps/negrito, demais vazias.
    """
    if not row or not row[0]:
        return False
    first = (row[0] or "").strip()
    rest = [c for c in row[1:] if c and c.strip()]
    if not first or rest:
        return False
    # Verifica se está em maiúsculas (seção) ou contém palavras-chave de seção
    return (
        first == first.upper()
        or any(kw in normalize_text(first) for kw in [
            "cirurgia", "procedimento", "ortopedia", "urologia", "ginecol",
            "obstet", "neonatal", "pediatr", "trauma", "cardiac", "vascular",
            "toraci", "neuro", "plastica", "cabeca",
        ])
    )


def is_table_header_row(row: List[Optional[str]]) -> bool:
    """Detecta linha de cabeçalho da tabela (ex.: PROCEDIMENTOS | 1ª OPÇÃO ...)."""
    if not row or not row[0]:
        return False
    first = normalize_text(row[0] or "")
    return "procedimento" in first or "1" in (row[1] or "") or "op" in normalize_text(row[1] or "")


def is_no_prophylaxis(text: str) -> bool:
    """Verifica se o texto indica ausência de recomendação de profilaxia."""
    t = normalize_text(text)
    return any(marker in t for marker in NO_PROPHYLAXIS_MARKERS)


# ---------------------------------------------------------------------------
# Parser de antibióticos
# ---------------------------------------------------------------------------

def parse_drugs_from_cell(cell_text: str) -> List[Dict[str, Any]]:
    """
    Extrai lista de medicamentos de uma célula da tabela.
    Retorna lista de dicts: {name, dose, route, timing}
    """
    if not cell_text or is_no_prophylaxis(cell_text):
        return []

    drugs: List[Dict[str, Any]] = []
    segments = DRUG_SEPARATOR_PATTERN.split(cell_text)

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        # Tenta extrair nome + dose via regex
        matches = list(DRUG_DOSE_PATTERN.finditer(seg))
        if matches:
            for m in matches:
                raw_name = m.group(1).strip()
                raw_dose = m.group(2).strip()
                route_m = ROUTE_PATTERN.search(seg[m.end():m.end() + 10])
                route = route_m.group(0).upper() if route_m else "EV"
                drugs.append({
                    "name": normalize_drug_name(raw_name),
                    "dose": normalize_dose(raw_dose),
                    "route": route,
                    "timing": "na inducao",
                })
        else:
            # Só nome sem dose explícita (ex.: "Clindamicina")
            seg_clean = ROUTE_PATTERN.sub("", seg).strip()
            seg_clean = re.sub(r"\b\d[\d.,]*\b", "", seg_clean).strip()
            if len(seg_clean) > 3 and not re.match(r"^\d", seg_clean):
                route_m = ROUTE_PATTERN.search(seg)
                drugs.append({
                    "name": normalize_drug_name(seg_clean),
                    "dose": None,
                    "route": route_m.group(0).upper() if route_m else "EV",
                    "timing": "na inducao",
                })

    return drugs


def build_acceptable_regimens(drugs: List[Dict[str, Any]]) -> List[List[str]]:
    """Constrói lista de regimes aceitos a partir dos medicamentos extraídos."""
    if not drugs:
        return []
    # Regimes individuais (cada droga sozinha) + combinação de todas
    names = [d["name"] for d in drugs]
    regimens = [[n] for n in names]
    if len(names) > 1:
        regimens.append(sorted(names))
    return regimens


# ---------------------------------------------------------------------------
# Detecção de seção
# ---------------------------------------------------------------------------

def detect_section(text: str) -> Optional[str]:
    """Mapeia texto de uma linha de seção para nome canônico."""
    normalized = normalize_text(text)
    for pattern, canonical in SECTION_ALIASES.items():
        if pattern in normalized:
            return canonical
    # Fallback: retorna uppercase do texto limpo
    cleaned = re.sub(r"[^\w\s]", "", text).strip()
    if cleaned:
        return cleaned.upper()
    return None


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class DeterministicPDFExtractor:
    """
    Extrai regras de profilaxia do PDF institucional usando pdfplumber.
    Sem chamadas a APIs externas — parsing puramente determinístico.
    """

    def __init__(self, pdf_path: str | Path, pages: str = "8-35"):
        self.pdf_path = Path(pdf_path)
        self.pages = self._parse_page_range(pages)
        self.rules: List[Dict[str, Any]] = []
        self._rule_counter = 0
        self._current_section = "NAO_CLASSIFICADO"

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def extract(self) -> List[Dict[str, Any]]:
        """Executa a extração completa e retorna lista de regras."""
        logger.info(f"Iniciando extração determinística: {self.pdf_path}")
        logger.info(f"Páginas: {self.pages[0]+1}–{self.pages[-1]+1}")

        with pdfplumber.open(self.pdf_path) as pdf:
            for page_idx in self.pages:
                if page_idx >= len(pdf.pages):
                    break
                page = pdf.pages[page_idx]
                self._process_page(page, page_idx + 1)

        # Deduplica por nome normalizado de procedimento
        self.rules = self._deduplicate(self.rules)
        logger.info(f"Extração concluída: {len(self.rules)} regras")
        return self.rules

    def save(self, output_path: str | Path) -> Path:
        """Salva rules.json no caminho especificado."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.rules, f, ensure_ascii=False, indent=2)
        logger.info(f"rules.json salvo em: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Processamento de página
    # ------------------------------------------------------------------

    def _process_page(self, page: Any, page_number: int) -> None:
        """Processa uma página do PDF, extraindo tabelas."""
        tables = page.extract_tables()
        if not tables:
            # Tenta extrair texto plano como fallback
            text = page.extract_text() or ""
            self._process_plain_text(text, page_number)
            return

        for table in tables:
            self._process_table(table, page_number)

    def _process_table(self, table: List[List[Optional[str]]], page_number: int) -> None:
        """Processa uma tabela extraída pelo pdfplumber."""
        for row in table:
            if not row or all(not c for c in row):
                continue

            # Normaliza células None para string vazia
            row = [c or "" for c in row]

            # Pula cabeçalho da tabela
            if is_table_header_row(row):
                continue

            # Detecta seção
            if is_section_header(row):
                section_name = detect_section(row[0])
                if section_name:
                    self._current_section = section_name
                    logger.debug(f"Seção detectada (p.{page_number}): {section_name}")
                continue

            # Processa linha de procedimento
            rule = self._row_to_rule(row, page_number)
            if rule:
                self.rules.append(rule)

    def _process_plain_text(self, text: str, page_number: int) -> None:
        """Fallback: processa páginas sem tabelas detectáveis."""
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if is_no_prophylaxis(line):
                continue
            # Tenta detectar seção por texto puro
            if line == line.upper() and len(line) > 5:
                sec = detect_section(line)
                if sec:
                    self._current_section = sec

    # ------------------------------------------------------------------
    # Conversão de linha em regra
    # ------------------------------------------------------------------

    def _row_to_rule(
        self, row: List[str], page_number: int
    ) -> Optional[Dict[str, Any]]:
        """Converte uma linha da tabela em um dict de regra."""
        # Precisamos de pelo menos 2 colunas: procedimento e 1ª opção
        if len(row) < 2:
            return None

        # Strip PDF private-use chars and standard whitespace
        _clean = lambda s: re.sub(r"[\ue000-\uf8ff]", "", (s or "")).strip()
        procedure_text = _clean(row[0])
        first_choice_text = _clean(row[1])
        allergy_text = _clean(row[2]) if len(row) > 2 else ""
        postop_text = _clean(row[3]) if len(row) > 3 else ""

        if not procedure_text:
            return None

        # Ignora linhas que parecem notas de rodapé (começa com *)
        if procedure_text.startswith("*") or procedure_text.startswith("Nota"):
            return None

        # Sem profilaxia?
        no_prophylaxis = (
            is_no_prophylaxis(first_choice_text)
            or (not first_choice_text and self._current_section == "SEM_PROFILAXIA")
        )

        # Parse drogas
        primary_drugs = [] if no_prophylaxis else parse_drugs_from_cell(first_choice_text)
        allergy_drugs = [] if no_prophylaxis else parse_drugs_from_cell(allergy_text)

        # Audit category
        audit_category = "NO_PROPHYLAXIS" if no_prophylaxis else "OK"

        rule_id = f"det_rule_{self._rule_counter:04d}"
        self._rule_counter += 1

        return {
            "rule_id": rule_id,
            "section": self._current_section,
            "procedure": procedure_text,
            "procedure_normalized": normalize_text(procedure_text),
            "is_prophylaxis_required": not no_prophylaxis,
            "primary_recommendation": {
                "drugs": primary_drugs,
                "raw_text": first_choice_text,
                "notes": postop_text,
                "acceptable_regimens": build_acceptable_regimens(primary_drugs),
                "metadata": {},
            },
            "allergy_recommendation": {
                "drugs": allergy_drugs,
                "raw_text": allergy_text,
                "notes": "",
                "acceptable_regimens": build_acceptable_regimens(allergy_drugs),
                "metadata": {},
            },
            "postoperative": postop_text,
            "audit_category": audit_category,
            "original_row_index": -1,
            "metadata": {
                "source": "deterministic_pdf",
                "backend": "pdfplumber",
                "dose_unit_standard": "mg",
                "page": page_number,
            },
        }

    # ------------------------------------------------------------------
    # Utilitários internos
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_page_range(pages: str) -> List[int]:
        """Converte string '8-35' em lista de índices 0-based [7, 8, ..., 34]."""
        parts = pages.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            return list(range(start - 1, end))
        return [int(p) - 1 for p in pages.split(",")]

    @staticmethod
    def _deduplicate(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove regras duplicadas por procedure_normalized, mantendo a primeira."""
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for rule in rules:
            key = rule.get("procedure_normalized", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(rule)
            elif not key:
                unique.append(rule)
        return unique


# ---------------------------------------------------------------------------
# Extrator de tabelas de dosagem por peso
# ---------------------------------------------------------------------------

def extract_dosing_tables(pdf_path: str | Path) -> Dict[str, Any]:
    """
    Extrai tabelas de dose por peso do paciente (adulto, pediátrico, neonatal).
    Retorna dict estruturado para uso em WEIGHT_DOSE_RULES do settings.py.
    """
    dosing_tables: Dict[str, Any] = {
        "adult": {},
        "pediatric": {},
        "neonatal": {},
        "_source": "deterministic_pdf",
        "_note": "Doses extraídas das tabelas de referência do protocolo",
    }

    # Regras hard-coded do protocolo (páginas de referência)
    # Extraídas diretamente da leitura do PDF institucional (VS 03, 28/08/2025)
    dosing_tables["adult"] = {
        "CEFAZOLINA": {
            "standard_dose_mg": 2000,
            "weight_threshold_kg": 120,
            "high_weight_dose_mg": 3000,
            "route": "EV",
            "timing": "na inducao",
            "redose_interval_min": 240,
            "weight_based_mg_per_kg": None,
        },
        "CEFUROXIMA": {
            "standard_dose_mg": 1500,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "na inducao",
            "redose_interval_min": 240,
            "weight_based_mg_per_kg": None,
        },
        "CLINDAMICINA": {
            "standard_dose_mg": 900,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "na inducao",
            "redose_interval_min": 360,
            "weight_based_mg_per_kg": 10,
        },
        "GENTAMICINA": {
            "standard_dose_mg": None,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "na inducao",
            "redose_interval_min": 0,
            "weight_based_mg_per_kg": 5,
            "note": "Dose ajustada pelo peso. Usar peso ideal em obesos.",
        },
        "VANCOMICINA": {
            "standard_dose_mg": None,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": 2000,
            "route": "EV",
            "timing": "60-120 min antes da incisao",
            "redose_interval_min": 0,
            "weight_based_mg_per_kg": 15,
            "infusion_min": 60,
            "note": "Infundir em no mínimo 60 min. Iniciar 60-120 min antes da incisão.",
        },
        "METRONIDAZOL": {
            "standard_dose_mg": 500,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "na inducao",
            "redose_interval_min": 0,
            "weight_based_mg_per_kg": 5,
        },
        "CIPROFLOXACINO": {
            "standard_dose_mg": 400,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "60-120 min antes da incisao",
            "redose_interval_min": 0,
            "weight_based_mg_per_kg": None,
            "note": "Iniciar 60-120 min antes da incisão.",
        },
        "AZITROMICINA": {
            "standard_dose_mg": 500,
            "weight_threshold_kg": None,
            "high_weight_dose_mg": None,
            "route": "EV",
            "timing": "60 min antes da incisao",
            "redose_interval_min": 0,
            "weight_based_mg_per_kg": None,
        },
    }

    dosing_tables["pediatric"] = {
        "CEFAZOLINA": {
            "weight_based_mg_per_kg": 30,
            "max_dose_mg": 2000,
            "route": "EV",
            "redose_interval_min": 240,
        },
        "CEFUROXIMA": {
            "weight_based_mg_per_kg": 30,
            "max_dose_mg": 2000,
            "route": "EV",
            "redose_interval_min": 240,
        },
        "CLINDAMICINA": {
            "weight_based_mg_per_kg": 10,
            "max_dose_mg": 900,
            "route": "EV",
            "redose_interval_min": 360,
        },
        "GENTAMICINA": {
            "weight_based_mg_per_kg": 2.5,
            "max_dose_mg": None,
            "route": "EV",
            "redose_interval_min": 0,
        },
        "METRONIDAZOL": {
            "weight_based_mg_per_kg": 2.5,
            "max_dose_mg": None,
            "route": "EV",
            "redose_interval_min": 0,
        },
        "VANCOMICINA": {
            "weight_based_mg_per_kg": 15,
            "max_dose_mg": 2000,
            "route": "EV",
            "infusion_min": 60,
            "redose_interval_min": 0,
        },
    }

    dosing_tables["neonatal"] = {
        "METRONIDAZOL": {
            "note": "Neonatos <1200g: 7.5 mg/kg. Neonatos >1200g: 15 mg/kg.",
            "weight_based_low_g": {"threshold_g": 1200, "mg_per_kg": 7.5},
            "weight_based_high_g": {"threshold_g": 1200, "mg_per_kg": 15},
        },
        "GENTAMICINA": {
            "weight_based_mg_per_kg": 2.5,
            "route": "EV",
        },
        "VANCOMICINA": {
            "weight_based_mg_per_kg": 15,
            "max_dose_mg": 2000,
            "infusion_min": 60,
        },
    }

    return dosing_tables
