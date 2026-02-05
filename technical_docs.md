# Documentação Técnica - Sistema de Auditoria Mater Dei

## Arquitetura do Sistema

### Padrão MVC Adaptado

O sistema segue uma arquitetura baseada em MVC (Model-View-Controller), adaptada para aplicação CLI:

```
┌─────────────────────────────────────────────┐
│           Scripts de Entrada                │
│  extract_rules.py | audit_surgeries.py      │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│            CONTROLLERS                       │
│  ┌─────────────────────────────────────┐   │
│  │ ProtocolExtractor                    │   │
│  │  - extract_all_rules()               │   │
│  │  - save_rules()                      │   │
│  └─────────────────────────────────────┘   │
│                                              │
│  ┌─────────────────────────────────────┐   │
│  │ SurgeryAuditor                       │   │
│  │  - load_surgeries_from_excel()       │   │
│  │  - audit_all_surgeries()             │   │
│  │  - audit_surgery()                   │   │
│  └─────────────────────────────────────┘   │
│                                              │
│  ┌─────────────────────────────────────┐   │
│  │ ReportGenerator                      │   │
│  │  - export_excel()                    │   │
│  │  - export_csv()                      │   │
│  │  - export_json()                     │   │
│  └─────────────────────────────────────┘   │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│              MODELS                          │
│  ┌─────────────────────────────────────┐   │
│  │ ProtocolRule                         │   │
│  │  + rule_id: str                      │   │
│  │  + procedure: str                    │   │
│  │  + primary_recommendation            │   │
│  │  + allergy_recommendation            │   │
│  └─────────────────────────────────────┘   │
│                                              │
│  ┌─────────────────────────────────────┐   │
│  │ SurgeryRecord                        │   │
│  │  + procedure: str                    │   │
│  │  + atb_name: str                     │   │
│  │  + incision_time: str                │   │
│  └─────────────────────────────────────┘   │
│                                              │
│  ┌─────────────────────────────────────┐   │
│  │ AuditResult                          │   │
│  │  + surgery_record: SurgeryRecord     │   │
│  │  + matched_rule_id: str              │   │
│  │  + conf_final: str                   │   │
│  └─────────────────────────────────────┘   │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│              UTILS                           │
│  - text_utils: Normalização e fuzzy match   │
│  - validation: Validação de dados           │
└─────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│              CONFIG                          │
│  - settings.py: Todas as configurações      │
└─────────────────────────────────────────────┘
```

## Fluxo de Dados

### 1. Extração de Regras (PDF → JSON)

```
PDF do Protocolo
      │
      ▼
┌──────────────────┐
│ Camelot/         │ Extrai tabelas do PDF
│ pdfplumber       │ usando múltiplas estratégias
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ProtocolExtractor│ Parseia tabelas em objetos
│                  │ ProtocolRule
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ProtocolRules    │ Valida e salva regras
│ Repository       │ em JSON + índice
└────────┬─────────┘
         │
         ▼
   rules.json
   rules_index.json
   rules.meta.json
```

### 2. Auditoria de Cirurgias (Excel → Relatórios)

```
Excel de Cirurgias + rules.json
           │
           ▼
┌──────────────────────┐
│ SurgeryAuditor       │ Carrega Excel e rules
│ .load_surgeries()    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Para cada cirurgia:  │
│                      │
│ 1. Match com         │ Fuzzy matching
│    protocolo         │ procedure → rule
│                      │
│ 2. Valida escolha    │ ATB no protocolo?
│                      │
│ 3. Valida dose       │ Dose correta?
│                      │
│ 4. Valida timing     │ Dentro de 1h?
│                      │
│ 5. Conformidade      │ Combina critérios
│    final             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ ReportGenerator      │ Gera relatórios em
│                      │ múltiplos formatos
└──────────┬───────────┘
           │
           ▼
  Excel, CSV, JSON, TXT
```

## Algoritmos Principais

### 1. Fuzzy Matching de Procedimentos

```python
def fuzzy_match_score(text1: str, text2: str) -> float:
    """
    Usa rapidfuzz.token_set_ratio para comparação
    resistente a ordem de palavras e stopwords.
    
    Exemplo:
    "Colecistectomia videolaparoscópica"
    vs
    "colecistectomia video laparoscopica"
    → Score: 0.95 (match)
    """
    norm1 = normalize_text(text1)  # Remove acentos, lowercase
    norm2 = normalize_text(text2)
    
    score = fuzz.token_set_ratio(norm1, norm2) / 100.0
    return score
```

### 2. Detecção de Medicamentos

```python
def extract_drug_names(text: str, drug_dict: dict) -> List[str]:
    """
    Busca por aliases de medicamentos em texto normalizado.
    
    Exemplo:
    "KEFAZOL 2G" → ["CEFAZOLINA"]
    "Cefazolina 2g + Metronidazol 500mg" → ["CEFAZOLINA", "METRONIDAZOL"]
    """
    normalized = normalize_text(text)
    found_drugs = []
    
    for standard_name, aliases in drug_dict.items():
        for alias in aliases:
            if normalize_text(alias) in normalized:
                found_drugs.append(standard_name)
                break
    
    return found_drugs
```

### 3. Validação de Dose

```python
def _validate_dose(record, rule, result):
    """
    Compara dose administrada com dose recomendada.
    Usa tolerância configurável para classificar.
    
    Lógica:
    - ≤10% diferença → CONFORME
    - 10-15% diferença → ALERTA
    - >15% diferença → NAO_CONFORME
    """
    diff_pct = abs((admin - recom) / recom * 100)
    
    if diff_pct <= 10:
        return 'CONFORME'
    elif diff_pct <= 15:
        return 'ALERTA'
    else:
        return 'NAO_CONFORME'
```

### 4. Validação de Timing

```python
def _validate_timing(record, result):
    """
    Verifica se ATB foi dado 0-60 minutos antes da incisão.
    
    Lógica:
    - ATB após incisão → NAO_CONFORME
    - ATB 0-60min antes → CONFORME
    - ATB >60min antes → NAO_CONFORME
    """
    diff_min = calc_time_diff(atb_time, incision_time)
    
    if diff_min < 0:
        return 'NAO_CONFORME'  # Após incisão
    elif 0 <= diff_min <= 60:
        return 'CONFORME'
    else:
        return 'NAO_CONFORME'  # Muito antes
```

## Estruturas de Dados

### ProtocolRule (JSON)

```json
{
  "rule_id": "rule_ORTOPEDIA_5_12",
  "section": "ORTOPEDIA",
  "procedure": "Artroscopia",
  "procedure_normalized": "artroscopia",
  "is_prophylaxis_required": true,
  "primary_recommendation": {
    "drugs": [
      {
        "name": "CEFAZOLINA",
        "dose": "2g",
        "route": "IV",
        "timing": null
      }
    ],
    "raw_text": "Cefazolina 2g IV",
    "notes": ""
  },
  "allergy_recommendation": {
    "drugs": [
      {
        "name": "CLINDAMICINA",
        "dose": "600mg",
        "route": "IV",
        "timing": null
      }
    ],
    "raw_text": "Clindamicina 600mg IV",
    "notes": ""
  },
  "postoperative": "",
  "audit_category": "OK"
}
```

### AuditResult (exportado)

```json
{
  "data": "2025-12-01",
  "procedimento": "Colecistectomia videolaparoscópica",
  "atb_administrado": "SIM",
  "atb_detectado": "CEFAZOLINA",
  "dose_administrada_mg": 2000.0,
  "match_rule_id": "rule_CIRURGIA_GERAL_3_8",
  "match_score": 0.95,
  "protocolo_atb_recomendados": "CEFAZOLINA",
  "protocolo_dose_esperada": "2g",
  "conf_escolha": "CONFORME",
  "conf_dose": "CONFORME",
  "conf_timing": "CONFORME",
  "conf_final": "CONFORME",
  "dose_diferenca_mg": 0.0,
  "dose_diferenca_pct": 0.0,
  "timing_diferenca_minutos": 45
}
```

## Performance

### Benchmarks Estimados

- **Extração de regras**: ~30-60 segundos para PDF de 30 páginas
- **Auditoria**: ~0.1-0.2 segundos por cirurgia
- **Geração de relatórios**: ~2-5 segundos para 1000 cirurgias

### Otimizações Implementadas

1. **Índice de procedimentos**: Busca O(1) por procedimento normalizado
2. **Caching de normalização**: Evita processar mesmo texto múltiplas vezes
3. **Fuzzy matching otimizado**: Usa rapidfuzz (C implementation)
4. **Processamento em lote**: pandas para operações vetorizadas

## Testes

### Estrutura de Testes (futuro)

```
tests/
├── test_text_utils.py       # Testes de normalização
├── test_validation.py        # Testes de validação
├── test_protocol_rules.py    # Testes de modelo de regras
├── test_audit_data.py        # Testes de modelo de auditoria
├── test_extractor.py         # Testes de extração
├── test_auditor.py           # Testes de auditoria
└── test_report_generator.py  # Testes de relatórios
```

### Executar testes (quando implementados)

```bash
pytest tests/ -v
```

## Segurança e Privacidade

### Dados Sensíveis

O sistema NÃO armazena:
- Nomes de pacientes
- Prontuários
- Dados clínicos além do necessário para auditoria

### Logs

- Logs não contêm dados identificáveis de pacientes
- Apenas procedimentos e resultados de auditoria

### Recomendações

1. Mantenha arquivos Excel e relatórios em local seguro
2. Limite acesso ao sistema apenas à equipe autorizada
3. Faça backup regular dos arquivos de regras (rules.json)
4. Revise logs periodicamente para detectar anomalias

## Manutenção

### Atualização do Protocolo

Quando o protocolo institucional mudar:

1. Execute novamente a extração:
   ```bash
   python extract_rules.py novo_protocolo.pdf --output ./data/output
   ```

2. Verifique o arquivo `rules.validation.json` para confirmar extração completa

3. Teste com amostra de cirurgias antigas para comparar resultados

4. Faça backup da versão anterior de `rules.json`

### Adição de Novos Medicamentos

Edite `materdei_audit/config/settings.py`:

```python
DRUG_DICTIONARY = {
    # ... existentes ...
    "NOVO_MEDICAMENTO": ["ALIAS1", "ALIAS2", "NOME_COMERCIAL"],
}
```

### Ajuste de Tolerâncias

Edite `materdei_audit/config/settings.py`:

```python
AUDIT_CONFIG = {
    "dose_tolerance_percent": 20,  # Aumentar se muitos alertas
    "timing_window_minutes": 90,   # Expandir janela se necessário
}
```

## Integração com Flask (Futuro)

### Estrutura Planejada

```python
# app.py (futuro)
from flask import Flask, request, jsonify
from materdei_audit.controllers import SurgeryAuditor
from materdei_audit.models import ProtocolRulesRepository

app = Flask(__name__)

@app.route('/api/audit', methods=['POST'])
def audit_surgery():
    """Endpoint para auditoria via API."""
    data = request.json
    # ... lógica de auditoria ...
    return jsonify(result)

@app.route('/api/upload/excel', methods=['POST'])
def upload_excel():
    """Endpoint para upload de planilha."""
    file = request.files['file']
    # ... processamento ...
    return jsonify({"status": "success"})
```

### Endpoints Planejados

- `POST /api/audit` - Audita cirurgia individual
- `POST /api/audit/batch` - Audita lote de cirurgias
- `POST /api/upload/excel` - Upload de planilha
- `GET /api/reports/{id}` - Baixa relatório
- `GET /api/protocol/rules` - Lista regras do protocolo
- `GET /api/statistics` - Estatísticas gerais

## Extensibilidade

### Adicionando Novo Critério de Conformidade

1. Adicione método em `controllers/surgery_auditor.py`:
```python
def _validate_novo_criterio(self, record, rule, result):
    # Sua lógica aqui
    return status, razao
```

2. Chame no método `audit_surgery()`:
```python
result.conf_novo = self._validate_novo_criterio(record, rule, result)
```

3. Atualize `_calculate_final_conformity()` para incluir novo critério

### Adicionando Novo Formato de Relatório

1. Adicione método em `controllers/report_generator.py`:
```python
def export_novo_formato(self, output_path: Path):
    df = self.prepare_dataframe()
    # Gera arquivo no novo formato
```

2. Chame no script `audit_surgeries.py`:
```python
report_gen.export_novo_formato(output_dir / 'relatorio.ext')
```

## Troubleshooting Avançado

### Problema: Extração Incompleta

**Sintoma**: Menos de 100 regras extraídas

**Diagnóstico**:
```python
# Teste uma única página
python extract_rules.py protocolo.pdf --pages "15"
```

**Soluções**:
1. Ajuste parâmetros do Camelot em `settings.py`
2. Tente flavor 'stream' ao invés de 'lattice'
3. Verifique se PDF não está protegido ou corrompido

### Problema: Muitos Casos Sem Match

**Sintoma**: >20% de casos com match_score = 0

**Diagnóstico**:
```python
# Adicione log de procedimentos não matched
logger.debug(f"Procedimento não matched: {procedure}")
```

**Soluções**:
1. Reduza `match_threshold` em `settings.py`
2. Adicione sinônimos de procedimentos
3. Normalize melhor os nomes de procedimentos no Excel

### Problema: Performance Lenta

**Sintoma**: >1 segundo por cirurgia

**Diagnóstico**:
```python
import time
start = time.time()
result = auditor.audit_surgery(record)
print(f"Tempo: {time.time() - start:.2f}s")
```

**Soluções**:
1. Verifique se índice está sendo usado corretamente
2. Profile o código com cProfile
3. Considere processamento paralelo para lotes grandes

---

**Documentação atualizada em: Janeiro 2025**