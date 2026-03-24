"""
Utilitarios para normalizacao, parsing e comparacao de regimes de antibioticos.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from itertools import product
from typing import Dict, Iterable, List, Sequence, Tuple

from rapidfuzz import fuzz

from config import DRUG_DICTIONARY


Regimen = Tuple[str, ...]


def _strip_accents(text: str) -> str:
    """Remove acentos preservando ASCII simples."""
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ASCII", "ignore").decode("ASCII")


def normalize_antibiotic_text(text: str, preserve_operators: bool = True) -> str:
    """
    Normaliza texto de antibioticos preservando operadores semanticos quando desejado.
    """
    if not isinstance(text, str):
        return ""

    normalized = _strip_accents(text).lower()
    normalized = normalized.replace("\n", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    if preserve_operators:
        normalized = re.sub(r"\s*\+\s*", " + ", normalized)
        normalized = re.sub(r"\s*/\s*", "/", normalized)
        normalized = re.sub(r"\bou\b", " ou ", normalized)
        normalized = re.sub(r"[^a-z0-9+/ ]", " ", normalized)
    else:
        normalized = re.sub(r"[^a-z0-9 ]", " ", normalized)

    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _expand_alias_variants(alias: str) -> List[str]:
    """Cria variantes seguras de alias que usam '+' ou '/' dentro do nome."""
    normalized = normalize_antibiotic_text(alias, preserve_operators=True)
    if not normalized:
        return []

    variants = {normalized}

    if "+" in normalized or "/" in normalized:
        variants.add(normalized.replace("+", "/"))
        variants.add(normalized.replace("/", "+"))
        variants.add(normalized.replace("+", " ").replace("/", " "))

    return [variant.strip() for variant in variants if variant.strip()]


@lru_cache(maxsize=1)
def _get_alias_entries() -> Tuple[Tuple[str, str], ...]:
    """Retorna aliases normalizados ordenados por tamanho para matching guloso."""
    entries = set()

    for canonical, aliases in DRUG_DICTIONARY.items():
        raw_aliases = list(aliases or [])
        raw_aliases.append(canonical.replace("_", " "))
        raw_aliases.append(canonical)

        for raw_alias in raw_aliases:
            for alias_variant in _expand_alias_variants(raw_alias):
                entries.add((alias_variant, canonical))

    return tuple(
        sorted(
            entries,
            key=lambda item: (-len(item[0]), item[0], item[1]),
        )
    )


def normalize_antibiotic_name(name: str) -> str:
    """
    Normaliza um nome de antibiotico para a forma canonica do projeto quando possivel.
    """
    normalized = normalize_antibiotic_text(name, preserve_operators=True)
    if not normalized:
        return ""

    compact_normalized = normalized.replace(" ", "")

    for alias, canonical in _get_alias_entries():
        alias_compact = alias.replace(" ", "")
        if normalized == alias or compact_normalized == alias_compact:
            return canonical

    best_match = ""
    best_score = 0.0
    for alias, canonical in _get_alias_entries():
        score = fuzz.ratio(compact_normalized, alias.replace(" ", "")) / 100.0
        if score > best_score:
            best_score = score
            best_match = canonical

    if best_score >= 0.9:
        return best_match

    return normalized.upper().replace(" ", "_").replace("+", "_").replace("/", "_")


def _find_antibiotic_mentions(text: str) -> List[Tuple[int, int, str]]:
    """Encontra antibioticos conhecidos em ordem textual, resolvendo sobreposicoes."""
    normalized = normalize_antibiotic_text(text, preserve_operators=True)
    if not normalized:
        return []

    matches: List[Tuple[int, int, str, int]] = []

    for alias, canonical in _get_alias_entries():
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        for match in re.finditer(pattern, normalized):
            matches.append((match.start(), match.end(), canonical, len(alias)))

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0]), -item[3], item[2]))

    selected: List[Tuple[int, int, str]] = []
    occupied: List[Tuple[int, int]] = []

    for start, end, canonical, _ in matches:
        if any(start < taken_end and end > taken_start for taken_start, taken_end in occupied):
            continue
        selected.append((start, end, canonical))
        occupied.append((start, end))

    selected.sort(key=lambda item: item[0])
    return selected


def _fuzzy_match_segment(segment: str) -> str:
    """Tenta reconhecer um antibiotico em um segmento sem match exato."""
    normalized = normalize_antibiotic_text(segment, preserve_operators=False)
    if not normalized:
        return ""

    candidates = [normalized]
    compact = normalized.replace(" ", "")
    if compact and compact not in candidates:
        candidates.append(compact)

    best_match = ""
    best_score = 0.0
    for alias, canonical in _get_alias_entries():
        alias_compact = alias.replace(" ", "").replace("+", "").replace("/", "")
        for candidate in candidates:
            candidate_compact = candidate.replace(" ", "")
            score = fuzz.ratio(candidate_compact, alias_compact) / 100.0
            if score > best_score:
                best_score = score
                best_match = canonical

    if best_score >= 0.84:
        return best_match

    return ""


def _iter_documentation_segments(text: str) -> Iterable[str]:
    """Segmenta o texto documental em provaveis componentes de administracao."""
    normalized = normalize_antibiotic_text(text, preserve_operators=True)
    if not normalized:
        return []

    return [
        segment.strip()
        for segment in re.split(r"\s*(?:\+|,|;|\be\b)\s*", normalized)
        if segment.strip()
    ]


def extract_documented_antibiotics(text: str) -> List[str]:
    """
    Extrai antibioticos documentados no registro, suportando varios agentes.
    """
    mentions = _find_antibiotic_mentions(text)
    detected: List[str] = []

    for _, _, canonical in mentions:
        if canonical not in detected:
            detected.append(canonical)

    for segment in _iter_documentation_segments(text):
        exact_mentions = _find_antibiotic_mentions(segment)
        if exact_mentions:
            for _, _, canonical in exact_mentions:
                if canonical not in detected:
                    detected.append(canonical)
            continue

        fuzzy_match = _fuzzy_match_segment(segment)
        if fuzzy_match and fuzzy_match not in detected:
            detected.append(fuzzy_match)

    if detected:
        return detected

    # Fallback para textos curtos com um unico antibiotico mal grafado.
    fuzzy_match = _fuzzy_match_segment(text)
    return [fuzzy_match] if fuzzy_match else []


def has_ambiguous_documented_antibiotics(text: str, detected_antibiotics: Sequence[str]) -> bool:
    """
    Sinaliza quando o texto sugere multiplos componentes, mas nem todos foram reconhecidos.
    """
    normalized = normalize_antibiotic_text(text, preserve_operators=True)
    if not normalized:
        return False

    raw_segments = re.split(r"\s*(?:\+|,|;|\be\b)\s*", normalized)
    segments = [segment.strip() for segment in raw_segments if segment.strip()]

    if len(raw_segments) > len(segments) and len(raw_segments) > 1:
        return True

    if len(segments) <= 1:
        return False

    exact_segment_hits = 0
    for segment in segments:
        segment_matches = _find_antibiotic_mentions(segment)
        if segment_matches or _fuzzy_match_segment(segment):
            exact_segment_hits += 1

    return exact_segment_hits < len(segments) or len(detected_antibiotics) < len(segments)


def _classify_separator(separator_text: str) -> str:
    """Classifica o separador entre dois antibioticos no texto do protocolo."""
    normalized = normalize_antibiotic_text(separator_text, preserve_operators=True)

    if not normalized:
        return "PLUS"
    if re.search(r"\bou\b", normalized):
        return "OR"
    if "+" in normalized:
        return "PLUS"
    if "/" in normalized:
        return "SLASH"
    if re.fullmatch(r"[\s,;:()\-]+", separator_text or ""):
        return "PLUS"
    return "PLUS"


def _normalize_regimen_components(components: Iterable[str]) -> Regimen:
    """Remove duplicatas e ordena um regime para comparacao deterministica."""
    unique = sorted({component for component in components if component})
    return tuple(unique)


def parse_protocol_antibiotic_regimens(text: str) -> List[Regimen]:
    """
    Converte o texto do protocolo em regimes aceitaveis normalizados.
    """
    mentions = _find_antibiotic_mentions(text)
    if not mentions:
        return []

    normalized_text = normalize_antibiotic_text(text, preserve_operators=True)
    regime_specs: List[List[List[str]]] = []
    current_regime: List[List[str]] = [[mentions[0][2]]]

    for current_mention, next_mention in zip(mentions, mentions[1:]):
        separator = normalized_text[current_mention[1]:next_mention[0]]
        operator = _classify_separator(separator)
        next_antibiotic = next_mention[2]

        if operator == "SLASH":
            if next_antibiotic not in current_regime[-1]:
                current_regime[-1].append(next_antibiotic)
        elif operator == "OR":
            regime_specs.append(current_regime)
            current_regime = [[next_antibiotic]]
        else:
            current_regime.append([next_antibiotic])

    regime_specs.append(current_regime)

    expanded_regimens: List[Regimen] = []
    for regime_spec in regime_specs:
        normalized_components = []
        for component_alternatives in regime_spec:
            normalized_component = list(dict.fromkeys(component_alternatives))
            if normalized_component:
                normalized_components.append(normalized_component)

        if not normalized_components:
            continue

        for expanded in product(*normalized_components):
            regimen = _normalize_regimen_components(expanded)
            if regimen and regimen not in expanded_regimens:
                expanded_regimens.append(regimen)

    return expanded_regimens


def recommendation_regimens_from_drugs(drug_names: Sequence[str]) -> List[Regimen]:
    """Cria um regime unico obrigatorio a partir da lista de drogas ja estruturadas."""
    regimen = _normalize_regimen_components(normalize_antibiotic_name(name) for name in drug_names)
    return [regimen] if regimen else []
