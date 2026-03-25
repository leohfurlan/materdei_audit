"""
Utilitarios para normalizacao, parsing e comparacao de regimes de antibioticos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from functools import lru_cache
from itertools import product
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from rapidfuzz import fuzz

from config import DRUG_DICTIONARY


Regimen = Tuple[str, ...]


OPTIONAL_KEYWORDS = (
    "opcional",
    "opcionalmente",
    "pode ser associado",
    "associacao com",
    "associado a",
)

CONDITIONAL_KEYWORDS = (
    " se ",
    " quando ",
    "alto risco",
    "risco elevado",
    "mrsa",
    "resistente",
    "oxacilina resistente",
    "colonizado",
    "colonizacao",
    "adicionar",
    "associar",
    "considerar",
)


@dataclass
class StructuredRecommendationParse:
    """Resultado estruturado do parsing de uma recomendacao."""

    acceptable_regimens: List[Regimen] = field(default_factory=list)
    optional_additions: List[Dict[str, Any]] = field(default_factory=list)
    conditional_additions: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence: str = "none"
    cleaned_text: str = ""


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
        variants.add(normalized.replace(" + ", "+").replace(" / ", "/"))
        variants.add(normalized.replace(" + ", "/").replace(" / ", "/"))
        variants.add(normalized.replace(" / ", "+").replace(" + ", "+"))

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
    if re.search(r"[a-z]", normalized):
        return "UNKNOWN"
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
        elif operator == "UNKNOWN":
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


def _normalize_regimen_list(regimens: Iterable[Regimen]) -> List[Regimen]:
    """Normaliza e remove duplicatas de uma lista de regimes."""
    normalized: List[Regimen] = []
    for regimen in regimens:
        normalized_regimen = _normalize_regimen_components(regimen)
        if normalized_regimen and normalized_regimen not in normalized:
            normalized.append(normalized_regimen)
    return normalized


def _regimens_from_text_fragment(text: str) -> List[Regimen]:
    """Extrai regimes de um fragmento curto, preservando fallback seguro."""
    regimens = parse_protocol_antibiotic_regimens(text)
    if regimens:
        return regimens

    mentions = [canonical for _, _, canonical in _find_antibiotic_mentions(text)]
    if len(mentions) == 1:
        return [_normalize_regimen_components(mentions)]

    return []


def _classify_modifier_clause(text: str) -> str:
    """Classifica um trecho como adicao opcional ou condicional."""
    normalized = f" {normalize_antibiotic_text(text, preserve_operators=True)} "
    if not normalized.strip():
        return ""

    has_drug = bool(_find_antibiotic_mentions(text))
    if not has_drug:
        return ""

    if any(keyword in normalized for keyword in OPTIONAL_KEYWORDS):
        return "optional"
    if any(keyword in normalized for keyword in CONDITIONAL_KEYWORDS):
        return "conditional"
    return ""


def _extract_condition_text(text: str) -> str:
    """Extrai a condicao explicita de um trecho condicional."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip(" .;:,()")
    if not cleaned:
        return ""

    normalized = normalize_antibiotic_text(cleaned, preserve_operators=True)
    condition_match = re.search(r"\bse\b\s+(.+)", cleaned, flags=re.IGNORECASE)
    if condition_match:
        return condition_match.group(1).strip(" .;:,()")

    for marker in (
        "alto risco",
        "risco elevado",
        "mrsa",
        "resistente",
        "oxacilina resistente",
        "colonizado",
        "colonizacao",
        "quando",
    ):
        if marker in normalized:
            return cleaned

    return cleaned


def _build_modifier_payload(text: str, modifier_type: str) -> Dict[str, Any]:
    """Converte um trecho opcional/condicional em payload serializavel."""
    regimens = [list(regimen) for regimen in _regimens_from_text_fragment(text)]
    payload: Dict[str, Any] = {
        "raw_text": re.sub(r"\s+", " ", str(text or "")).strip(),
        "regimens": regimens,
        "combine_with_base": True,
    }

    if modifier_type == "conditional":
        payload["condition"] = _extract_condition_text(text)

    return payload


def _extract_parenthetical_modifiers(text: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Remove trechos parenteticos opcionais/condicionais do texto base."""
    if not text:
        return "", [], []

    optional_additions: List[Dict[str, Any]] = []
    conditional_additions: List[Dict[str, Any]] = []
    pieces: List[str] = []
    last_end = 0

    for match in re.finditer(r"\(([^()]*)\)", text):
        clause = match.group(1).strip()
        modifier_type = _classify_modifier_clause(clause)
        if modifier_type:
            pieces.append(text[last_end:match.start()])
            payload = _build_modifier_payload(clause, modifier_type)
            if payload["regimens"]:
                if modifier_type == "optional":
                    optional_additions.append(payload)
                else:
                    conditional_additions.append(payload)
            last_end = match.end()

    pieces.append(text[last_end:])
    cleaned_text = re.sub(r"\s+", " ", "".join(pieces)).strip(" ,;")
    return cleaned_text, optional_additions, conditional_additions


def _extract_note_modifiers(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Identifica adicoes opcionais/condicionais em observacoes."""
    optional_additions: List[Dict[str, Any]] = []
    conditional_additions: List[Dict[str, Any]] = []

    if not text:
        return optional_additions, conditional_additions

    segments = [
        segment.strip(" .;:,")
        for segment in re.split(r"[\n;]+|(?<=[.])\s+", text)
        if segment and segment.strip(" .;:,")
    ]

    for segment in segments:
        modifier_type = _classify_modifier_clause(segment)
        if not modifier_type:
            continue

        payload = _build_modifier_payload(segment, modifier_type)
        if not payload["regimens"]:
            continue

        if modifier_type == "optional":
            optional_additions.append(payload)
        else:
            conditional_additions.append(payload)

    return optional_additions, conditional_additions


def parse_structured_recommendation(text: str, notes: str = "") -> StructuredRecommendationParse:
    """
    Parseia uma recomendacao preservando regimes base e adicoes opcionais/condicionais.
    """
    raw_text = re.sub(r"\s+", " ", str(text or "")).strip()
    raw_notes = re.sub(r"\s+", " ", str(notes or "")).strip()

    if not raw_text and not raw_notes:
        return StructuredRecommendationParse(cleaned_text="")

    cleaned_text, optional_from_text, conditional_from_text = _extract_parenthetical_modifiers(raw_text)
    optional_from_notes, conditional_from_notes = _extract_note_modifiers(raw_notes)

    acceptable_regimens = _normalize_regimen_list(_regimens_from_text_fragment(cleaned_text))
    optional_additions = optional_from_text + optional_from_notes
    conditional_additions = conditional_from_text + conditional_from_notes

    warnings: List[str] = []
    confidence = "none"

    if acceptable_regimens:
        confidence = "high"
    elif _find_antibiotic_mentions(cleaned_text):
        confidence = "low"
        warnings.append("raw_text_sem_semantica_suficiente")

    if optional_additions or conditional_additions:
        confidence = "high" if acceptable_regimens else "low"

    return StructuredRecommendationParse(
        acceptable_regimens=acceptable_regimens,
        optional_additions=optional_additions,
        conditional_additions=conditional_additions,
        warnings=warnings,
        confidence=confidence,
        cleaned_text=cleaned_text,
    )


def infer_recommendation_structure(
    raw_text: str,
    notes: str = "",
    drug_names: Sequence[str] = (),
    recommendation_kind: str = "",
) -> Dict[str, Any]:
    """
    Infere semantica segura de uma recomendacao.

    Nunca promove uma lista plana de multiplas drogas a combo obrigatorio sem
    evidencia textual suficiente.
    """
    parsed = parse_structured_recommendation(raw_text, notes)
    normalized_drug_names = [
        normalize_antibiotic_name(name)
        for name in drug_names
        if normalize_antibiotic_name(name)
    ]
    normalized_drug_names = list(dict.fromkeys(normalized_drug_names))

    acceptable_regimens = [list(regimen) for regimen in parsed.acceptable_regimens]
    parse_source = "raw_text"
    legacy_flattened_ambiguous = False

    if not acceptable_regimens:
        if len(normalized_drug_names) == 1:
            acceptable_regimens = [
                list(regimen)
                for regimen in recommendation_regimens_from_drugs(normalized_drug_names)
            ]
            parse_source = "single_drug_fallback"
        elif len(normalized_drug_names) > 1:
            parse_source = "legacy_drug_list_ambiguous"
            legacy_flattened_ambiguous = True

    metadata = {
        "recommendation_kind": recommendation_kind,
        "parsing_confidence": parsed.confidence,
        "parsing_source": parse_source,
        "legacy_flattened_ambiguous": legacy_flattened_ambiguous,
        "parsing_warnings": parsed.warnings,
        "optional_additions": parsed.optional_additions,
        "conditional_additions": parsed.conditional_additions,
    }

    return {
        "acceptable_regimens": acceptable_regimens,
        "metadata": metadata,
    }
