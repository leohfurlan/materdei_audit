"""
UtilitÃ¡rios para normalizaÃ§Ã£o e processamento de texto
"""
import re
import unicodedata
from typing import List, Optional
from rapidfuzz import fuzz


def normalize_text(text: str) -> str:
    """
    Normaliza texto para comparaÃ§Ã£o.
    
    Args:
        text: Texto a ser normalizado
        
    Returns:
        Texto normalizado (sem acentos, minÃºsculo, sem espaÃ§os extras)
    """
    if not isinstance(text, str):
        return ""
    
    # Remove acentos
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ASCII', 'ignore').decode('ASCII')
    
    # Converte para minÃºsculo
    text = text.lower()
    
    # Remove caracteres especiais, mantÃ©m espaÃ§os e nÃºmeros
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    
    # Remove espaÃ§os extras
    text = ' '.join(text.split())
    
    return text


def extract_drug_names(text: str, drug_dict: dict) -> List[str]:
    """
    Extrai nomes de medicamentos de um texto.
    
    Args:
        text: Texto contendo nomes de medicamentos
        drug_dict: Dicionario de medicamentos {NOME_PADRAO: [ALIASES]}
        
    Returns:
        Lista de nomes padronizados de medicamentos encontrados
    """
    if not text or not isinstance(text, str):
        return []
    
    normalized = normalize_text(text)
    found_drugs = []
    
    # Busca direta por aliases conhecidos.
    for standard_name, aliases in drug_dict.items():
        for alias in aliases:
            if normalize_text(alias) in normalized:
                if standard_name not in found_drugs:
                    found_drugs.append(standard_name)
                break

    # Fallback fuzzy para capturar erros de digitacao comuns.
    if not found_drugs:
        tokens = [token for token in re.split(r"\s+", normalized) if len(token) >= 5]
        compact_text = normalized.replace(" ", "")
        if len(compact_text) >= 5:
            tokens.append(compact_text)

        for standard_name, aliases in drug_dict.items():
            if standard_name in found_drugs:
                continue

            matched = False
            for alias in aliases:
                alias_norm = normalize_text(alias).replace(" ", "")
                if len(alias_norm) < 5:
                    continue

                for token in tokens:
                    score = fuzz.ratio(token, alias_norm) / 100.0
                    if score >= 0.84:
                        found_drugs.append(standard_name)
                        matched = True
                        break

                if matched:
                    break
    
    return found_drugs

def fuzzy_match_score(text1: str, text2: str) -> float:
    """
    Calcula score de similaridade entre dois textos.
    
    Args:
        text1: Primeiro texto
        text2: Segundo texto
        
    Returns:
        Score de 0.0 a 1.0 (1.0 = idÃªntico)
    """
    if not text1 or not text2:
        return 0.0
    
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if norm1 == norm2:
        return 1.0
    
    # Usa token_set_ratio para melhor matching de termos fora de ordem
    score = fuzz.token_set_ratio(norm1, norm2) / 100.0
    
    return score


def extract_dose_from_text(text: str) -> Optional[float]:
    """
    Extrai dosagem em mg de um texto.
    
    Exemplos:
        "KEFAZOL 2G" -> 2000.0
        "500MG" -> 500.0
        "1,5G" -> 1500.0
    
    Args:
        text: Texto contendo dosagem
        
    Returns:
        Dose em mg ou None se nao encontrado
    """
    if not text or not isinstance(text, str):
        return None
    
    text = text.upper().replace(",", ".")
    candidates_mg: List[float] = []

    # Padroes para gramas (inclui "GR", "GRAMA", "GRAMAS").
    g_pattern = r'(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*(?:G|GR|GRAMA|GRAMAS)\b'
    for match in re.finditer(g_pattern, text):
        try:
            candidates_mg.append(float(match.group(1)) * 1000)
        except ValueError:
            continue

    # Padroes para miligramas.
    mg_pattern = r'(?<![A-Z0-9])(\d+(?:\.\d+)?)\s*MG\b'
    for match in re.finditer(mg_pattern, text):
        try:
            candidates_mg.append(float(match.group(1)))
        except ValueError:
            continue

    if not candidates_mg:
        return None

    # Em esquemas combinados (ex: 2g + 500mg), usa a maior dose.
    return max(candidates_mg)

def parse_time(time_str: str) -> Optional[str]:
    """
    Parseia string de tempo para formato HH:MM.
    
    Args:
        time_str: String contendo tempo (vÃ¡rios formatos aceitos)
        
    Returns:
        Tempo no formato HH:MM ou None se invÃ¡lido
    """
    if not time_str or not isinstance(time_str, str):
        return None
    
    time_str = str(time_str).strip()
    
    # Remove espaÃ§os e caracteres especiais
    time_str = re.sub(r'[^\d:]', '', time_str)
    
    # Tenta match HH:MM
    match = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    # Tenta match HHMM
    match = re.match(r'(\d{2})(\d{2})', time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    
    return None


def calculate_time_diff_minutes(time1: str, time2: str) -> Optional[int]:
    """
    Calcula diferenÃ§a em minutos entre dois horÃ¡rios.
    
    Args:
        time1: Primeiro horÃ¡rio (HH:MM)
        time2: Segundo horÃ¡rio (HH:MM)
        
    Returns:
        DiferenÃ§a em minutos (time2 - time1) ou None se invÃ¡lido
    """
    try:
        t1_parts = time1.split(':')
        t2_parts = time2.split(':')
        
        t1_minutes = int(t1_parts[0]) * 60 + int(t1_parts[1])
        t2_minutes = int(t2_parts[0]) * 60 + int(t2_parts[1])
        
        diff = t2_minutes - t1_minutes
        
        # Ajusta para casos que cruzam meia-noite
        if diff < -720:  # Mais de 12h negativo
            diff += 1440  # Adiciona 24h
        elif diff > 720:  # Mais de 12h positivo
            diff -= 1440  # Subtrai 24h
        
        return diff
    except:
        return None


def clean_procedure_name(procedure: str) -> str:
    """
    Limpa e padroniza nome de procedimento.
    
    Args:
        procedure: Nome do procedimento
        
    Returns:
        Nome limpo e padronizado
    """
    if not procedure or not isinstance(procedure, str):
        return ""
    
    # Normaliza
    clean = normalize_text(procedure)
    
    # Remove palavras muito comuns que nÃ£o agregam
    stop_words = ['cirurgia', 'procedimento', 'de', 'do', 'da', 'em', 'com', 'para']
    words = [w for w in clean.split() if w not in stop_words]
    
    return ' '.join(words)


def format_conformity_reason(reason_code: str) -> str:
    """
    Formata codigo de razao de nao conformidade em texto legivel.
    
    Args:
        reason_code: Codigo da razao
        
    Returns:
        Descricao legivel da razao
    """
    reasons = {
        "atb_nao_recomendado": "Antibiotico nao recomendado pelo protocolo",
        "profilaxia_nao_recomendada": "Profilaxia nao recomendada para o procedimento",
        "profilaxia_potencial_sem_indicacao": "Profilaxia potencialmente sem indicacao no protocolo",
        "atb_sem_referencia_protocolo": "Protocolo sem antibiotico de referencia para validar escolha",
        "dose_incorreta": "Dose administrada diferente da recomendada",
        "dose_muito_baixa": "Dose significativamente abaixo da recomendada",
        "dose_muito_alta": "Dose significativamente acima da recomendada",
        "dose_fora_referencia": "Dose fora da referencia, requer revisao",
        "timing_fora_janela": "Antibiotico administrado fora da janela de 1 hora",
        "timing_apos_incisao": "Antibiotico administrado apos a incisao",
        "atb_nao_administrado": "Antibiotico nao foi administrado",
        "sem_match_protocolo": "Procedimento nao encontrado no protocolo",
        "sem_match_sem_atb": "Procedimento sem match e sem antibiotico administrado",
        "criterio_nao_aplicavel": "Criterio nao aplicavel para o caso",
        "dados_insuficientes": "Dados insuficientes para avaliar conformidade",
        "alerta_validacao": "Caso com alerta para validacao manual",
        "dose_pequena_diferenca": "Pequena diferenca de dose detectada (revisar)",
        "dose_sem_referencia_peso": "Nao foi possivel validar dose (falta peso do paciente)",
        "multiplos_criterios": "Multiplas nao conformidades detectadas",
        "repique_nao_aplicavel": "Repique nao aplicavel para este antibiotico",
        "repique_horarios_nao_informados": "Horarios de repique nao informados",
        "repique_no_intervalo": "Repique realizado dentro do intervalo recomendado",
        "repique_fora_intervalo": "Repique fora do intervalo recomendado",
    }
    
    return reasons.get(reason_code, reason_code)

