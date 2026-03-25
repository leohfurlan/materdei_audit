#!/usr/bin/env python3
"""
Gera um dicionário de mapeamento entre procedimentos do Excel e regras do protocolo.

Uso:
    python build_procedure_map.py --excel <planilha.xlsx> --rules <rules.json> --output <map.json>
"""
import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd

from config import EXCEL_COLUMNS, EXCEL_COLUMN_ALIASES
from utils import normalize_text, clean_procedure_name, fuzzy_match_score


def _load_synonyms(path: Optional[str]) -> Dict[str, List[str]]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
    return {}


def _apply_synonyms(text: str, synonyms: Dict[str, List[str]]) -> str:
    """
    Se encontrar sinônimos no texto, adiciona o termo canônico para reforçar o match.
    """
    if not text or not synonyms:
        return text
    text_norm = normalize_text(text)
    tokens = [text_norm]
    for canonical, syns in synonyms.items():
        canon_norm = normalize_text(canonical)
        for s in syns:
            s_norm = normalize_text(s)
            if s_norm and s_norm in text_norm and canon_norm not in text_norm:
                tokens.append(canon_norm)
                break
    return " ".join(tokens)


def _cell_text(value: Any) -> str:
    """Converte valores de célula para texto, tratando nulos do pandas."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _build_surgeon_specialty_map(
    df: pd.DataFrame,
    col_surgeon: Optional[str],
    col_spec: Optional[str],
) -> Dict[str, str]:
    """
    Mapeia cirurgião -> especialidade predominante.

    Em caso de empate, usa a primeira especialidade não nula encontrada.
    """
    if not col_surgeon or not col_spec:
        return {}

    specialty_counts: Dict[str, Dict[str, int]] = {}
    first_seen_order: Dict[str, Dict[str, int]] = {}
    specialty_labels: Dict[str, Dict[str, str]] = {}

    source = df[[col_surgeon, col_spec]].itertuples(index=False, name=None)
    for row_idx, (surgeon_value, spec_value) in enumerate(source):
        surgeon = _cell_text(surgeon_value)
        spec = _cell_text(spec_value)
        surgeon_norm = normalize_text(surgeon)
        spec_norm = normalize_text(spec)
        if not surgeon_norm or not spec_norm:
            continue

        surgeon_counts = specialty_counts.setdefault(surgeon_norm, {})
        surgeon_counts[spec_norm] = surgeon_counts.get(spec_norm, 0) + 1

        surgeon_orders = first_seen_order.setdefault(surgeon_norm, {})
        surgeon_orders.setdefault(spec_norm, row_idx)

        surgeon_labels = specialty_labels.setdefault(surgeon_norm, {})
        surgeon_labels.setdefault(spec_norm, spec)

    surgeon_specialty_map: Dict[str, str] = {}
    for surgeon_norm, surgeon_counts in specialty_counts.items():
        surgeon_orders = first_seen_order[surgeon_norm]
        best_spec_norm = max(
            surgeon_counts,
            key=lambda spec_norm: (surgeon_counts[spec_norm], -surgeon_orders[spec_norm]),
        )
        surgeon_specialty_map[surgeon_norm] = specialty_labels[surgeon_norm][best_spec_norm]

    return surgeon_specialty_map


def _build_rule_index(rules: List[Dict[str, Any]], specialty_set: Optional[set] = None) -> List[Dict[str, Any]]:
    out = []
    specialty_set = specialty_set or set()
    for idx, r in enumerate(rules):
        proc = str(r.get("procedure", "")).strip()
        proc_norm = r.get("procedure_normalized") or normalize_text(proc)
        section = str(r.get("section", "")).strip()
        # ignora cabeçalhos genéricos (ex.: "UROLOGIA" em OUTROS)
        if proc_norm in specialty_set and normalize_text(section) == "outros":
            continue
        combo = f"{section} {proc}".strip()
        combo_norm = clean_procedure_name(combo)
        out.append({
            "rule_id": r.get("rule_id"),
            "procedure": proc,
            "procedure_norm": proc_norm,
            "section": section,
            "combo_norm": combo_norm,
            "rule_index": idx,
        })
    return out


def _resolve_excel_columns(dataframe_columns: List[Any]) -> Dict[str, str]:
    """Resolve colunas do Excel por nome configurado e aliases conhecidos."""
    resolved: Dict[str, str] = {}

    all_columns = [str(col).strip() for col in dataframe_columns]
    exact_lookup = {col: col for col in all_columns if col}
    normalized_lookup = {
        normalize_text(col): col
        for col in all_columns
        if col and normalize_text(col)
    }

    for key, configured_name in EXCEL_COLUMNS.items():
        configured = str(configured_name).strip()
        if configured in exact_lookup:
            resolved[key] = exact_lookup[configured]
            continue

        normalized_configured = normalize_text(configured)
        if normalized_configured in normalized_lookup:
            resolved[key] = normalized_lookup[normalized_configured]
            continue

        for alias in EXCEL_COLUMN_ALIASES.get(key, []):
            normalized_alias = normalize_text(alias)
            if normalized_alias in normalized_lookup:
                resolved[key] = normalized_lookup[normalized_alias]
                break

    return resolved


def _detect_excel_header_row(excel_path: Path, sheet_name: Any, preview_rows: int = 10) -> int:
    """
    Detecta a linha de cabeçalho mais provável analisando as primeiras linhas.

    Prioriza linhas que contenham a coluna de procedimento e o maior número de
    cabeçalhos reconhecidos pela configuração.
    """
    preview_df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, nrows=preview_rows)
    best_row_idx = 0
    best_score = -1
    best_has_procedure = False

    for row_idx, row in preview_df.iterrows():
        row_values = [_cell_text(value) for value in row.tolist()]
        resolved = _resolve_excel_columns(row_values)
        score = len(resolved)
        has_procedure = "procedure" in resolved

        if has_procedure and not best_has_procedure:
            best_row_idx = int(row_idx)
            best_score = score
            best_has_procedure = True
            continue

        if has_procedure == best_has_procedure and score > best_score:
            best_row_idx = int(row_idx)
            best_score = score

    return best_row_idx


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria mapa de procedimentos (Excel -> rules.json)")
    parser.add_argument("--excel", required=True, help="Caminho do Excel")
    parser.add_argument("--rules", required=True, help="Caminho do rules.json")
    parser.add_argument("--output", required=True, help="Saída do mapeamento (JSON)")
    parser.add_argument("--sheet", default=None, help="Nome da aba do Excel (default: primeira)")
    parser.add_argument("--top-k", type=int, default=5, help="Número de candidatos por procedimento")
    parser.add_argument("--min-auto", type=float, default=0.45, help="Score mínimo para AUTO")
    parser.add_argument("--min-review", type=float, default=0.35, help="Score mínimo para REVIEW")
    parser.add_argument("--use-specialty", action="store_true", help="Considerar especialidade no match")
    parser.add_argument("--synonyms", default=None, help="JSON de sinônimos (opcional)")
    parser.add_argument("--output-simple", default=None, help="Saída opcional no formato ProcedureMapItem")

    args = parser.parse_args()

    excel_path = Path(args.excel)
    rules_path = Path(args.rules)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel não encontrado: {excel_path}")
    if not rules_path.exists():
        raise FileNotFoundError(f"rules.json não encontrado: {rules_path}")

    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)

    synonyms = _load_synonyms(args.synonyms)

    sheet_name = args.sheet or 0
    header_row = _detect_excel_header_row(excel_path, sheet_name)
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row)

    resolved_columns = _resolve_excel_columns(df.columns.tolist())
    col_proc = resolved_columns.get("procedure")
    col_spec = resolved_columns.get("specialty")
    col_surgeon = resolved_columns.get("surgeon")

    if not col_proc:
        raise ValueError(
            f"Coluna de procedimento não encontrada: {EXCEL_COLUMNS.get('procedure', 'Cirurgia')}"
        )

    # Gera chaves únicas procedimento + especialidade (se houver)
    specialty_set = set()
    if col_spec:
        for v in df[col_spec].dropna().unique():
            v_str = _cell_text(v)
            if v_str:
                specialty_set.add(normalize_text(v_str))

    surgeon_specialty_map = _build_surgeon_specialty_map(df, col_surgeon, col_spec)
    rule_index = _build_rule_index(rules, specialty_set)
    mapping: Dict[str, Any] = {}
    simple_map: Dict[str, Any] = {}

    for _, row in df.iterrows():
        proc = _cell_text(row.get(col_proc, ""))
        if not proc or len(proc) < 3:
            continue
        spec = _cell_text(row.get(col_spec, "")) if col_spec else ""
        surgeon = _cell_text(row.get(col_surgeon, "")) if col_surgeon else ""
        if not spec and surgeon:
            spec = surgeon_specialty_map.get(normalize_text(surgeon), "")

        key = f"{spec} | {proc}" if spec else proc
        if key in mapping:
            continue

        proc_norm = clean_procedure_name(_apply_synonyms(proc, synonyms))
        combo_norm = proc_norm
        if args.use_specialty and spec:
            combo_norm = clean_procedure_name(_apply_synonyms(f"{spec} {proc}", synonyms))

        candidates = []
        for r in rule_index:
            score_proc = fuzzy_match_score(proc_norm, r["procedure_norm"])
            score_combo = score_proc
            if args.use_specialty and spec:
                score_combo = fuzzy_match_score(combo_norm, r["combo_norm"])
            score = max(score_proc, score_combo)
            candidates.append({
                "score": round(float(score), 4),
                "rule_id": r["rule_id"],
                "rule_index": r["rule_index"],
                "procedure": r["procedure"],
                "section": r["section"],
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        top = candidates[: max(1, args.top_k)]
        best = top[0] if top else {"score": 0, "rule_id": None}

        if best["score"] >= args.min_auto:
            status = "AUTO"
        elif best["score"] >= args.min_review:
            status = "REVIEW"
        else:
            status = "NO_MATCH"

        mapping[key] = {
            "cirurgia": proc,
            "especialidade": spec or None,
            "cirurgiao": surgeon or None,
            "status": status,
            "best_rule_id": best["rule_id"],
            "best_score": best["score"],
            "candidates": top,
        }

        simple_map[key] = {
            "best_rule_id": best["rule_id"],
            "best_score": best["score"],
            "procedure": proc,
            "specialty": spec or None,
            "surgeon": surgeon or None,
            "candidates": [
                {
                    "rule_id": c["rule_id"],
                    "score": c["score"],
                    "procedure": c["procedure"],
                }
                for c in top
            ],
        }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    if args.output_simple:
        out_simple = Path(args.output_simple)
        out_simple.parent.mkdir(parents=True, exist_ok=True)
        with open(out_simple, "w", encoding="utf-8") as f:
            json.dump(simple_map, f, ensure_ascii=False, indent=2)

    print(f"Mapa gerado: {output_path} ({len(mapping)} itens)")
    if args.output_simple:
        print(f"Mapa simples gerado: {args.output_simple}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
