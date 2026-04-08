# CLAUDE.md — Sistema de Auditoria de Profilaxia Antimicrobiana Cirúrgica (Mater Dei)

## 1. Visão Geral e Princípios do Sistema

Este sistema realiza auditoria automatizada da conformidade de profilaxia antimicrobiana cirúrgica do Hospital Mater Dei. Valida se os antibióticos administrados em cirurgias estão de acordo com o protocolo institucional, em relação a **escolha do fármaco**, **dose**, **tempo de administração** e **redosagem (repique)**.

### Princípios Fundamentais

- **Rastreabilidade:** Toda decisão de conformidade deve ter razão documentada (`_razao` fields).
- **Tolerância configurável:** Thresholds de dose e timing são centralizados em `config/settings.py`; nunca hardcode valores críticos em lógica de negócio.
- **Fail-safe:** Dado insuficiente gera `INDETERMINADO`, não `CONFORME`. Jamais assumir conformidade na ausência de dados.
- **Normalização consistente:** Todo texto (procedimentos, fármacos) deve passar por `utils/text_utils.py` antes de comparação.
- **Singleton de repositório:** `ProtocolRulesRepository` é singleton; nunca instanciar diretamente — use `ProtocolRulesRepository.get_instance()`.
- **Separação de responsabilidades:** extração de regras, mapeamento de procedimentos e auditoria são pipelines independentes e não devem ser acoplados.

---

## 2. Arquitetura e Aplicações

```
materdei_audit/
├── extract_rules.py          # CLI: PDF do protocolo → rules.json
├── audit_surgeries.py        # CLI: Excel de cirurgias + rules.json → relatório
├── build_procedure_map.py    # Utilitário: gera candidatos para mapeamento
├── example_usage.py          # Exemplos de uso programático
│
├── config/settings.py        # ÚNICA fonte de configuração do sistema
│
├── models/
│   ├── protocol_rules.py     # ProtocolRule, Recommendation, Drug
│   ├── audit_data.py         # SurgeryRecord, AuditResult
│   └── inputs.py             # Schemas Pydantic de validação de entrada
│
├── controllers/
│   ├── protocol_extractor.py # Extrai regras do PDF via LLM
│   ├── surgery_auditor.py    # Lógica central de auditoria
│   └── report_generator.py  # Gera relatórios Excel/CSV/JSON/TXT
│
└── utils/
    ├── text_utils.py          # Normalização, fuzzy matching
    ├── antibiotic_regimens.py # Parsing e comparação de regimes
    ├── input_loader.py        # Carregamento e versionamento de JSONs
    └── validation.py          # Validações auxiliares
```

### Fluxo Principal

```
PDF do Protocolo
      │
      ▼
[extract_rules.py]
  LLM (Gemini / Langextract) extrai regras por chunks de páginas
      │
      ▼
rules.json + rules_index.json + rules.meta.json
      │
      ├── [build_procedure_map.py]  (opcional, revisão manual)
      │         │
      │         ▼
      │   procedimentos.json   (mapeamento Excel → Protocolo)
      │
      ▼
[audit_surgeries.py]
  Carrega Excel → valida escolha, dose, timing, repique por cirurgia
      │
      ▼
auditoria_resultado.xlsx / .csv / .json + auditoria_resumo.txt
```

---

## 3. Entradas do Sistema

### 3.1 PDF do Protocolo (`extract_rules.py`)

- **Arquivo:** PDF institucional de profilaxia antimicrobiana
- **Configuração relevante (`config/settings.py`):**
  - `EXTRACTION_CONFIG["pages_to_extract"]` — páginas com tabelas do protocolo (default: `"8-35"`)
  - `EXTRACTION_CONFIG["llm_backend"]` — `"langextract"` ou `"gemini"`
  - `EXTRACTION_CONFIG["llm_pages_per_chunk"]` — páginas por chamada LLM (default: `3`)
- **Variável de ambiente obrigatória:** `GOOGLE_API_KEY` (ou equivalente do backend)

### 3.2 Excel de Cirurgias (`audit_surgeries.py`)

Colunas esperadas (nomes canônicos definidos em `EXCEL_COLUMNS` no settings):

| Campo canônico     | Coluna Excel esperada          | Obrigatório |
|--------------------|--------------------------------|-------------|
| `procedure`        | Cirurgia                       | Sim         |
| `specialty`        | Especialidade                  | Recomendado |
| `surgeon`          | Cirurgiao / Nome do Cirurgião  | Recomendado |
| `surgery_date`     | Dt Cirurgia                    | Recomendado |
| `incision_time`    | Hr Incisão                     | Para timing |
| `atb_given`        | Antibiótico administrado (SIM/NAO) | Para escolha |
| `atb_name`         | Antibiótico                    | Para escolha |
| `atb_time`         | Hr Antibiótico                 | Para timing |
| `patient_weight`   | Peso (kg)                      | Para dose mg/kg |
| `repique`          | Repique                        | Para repique |
| `repique_time`     | Hora Repique                   | Para repique |

### 3.3 Arquivos de Suporte

- **`data/input/rules.json`** — Regras do protocolo (gerado por `extract_rules.py`)
- **`data/input/procedimentos.json`** — Mapeamento nome Excel → nome no protocolo (revisão manual)
- **`data/input/drug_aliases.json`** — Aliases opcionais de medicamentos

---

## 4. Saídas do Sistema

### 4.1 Extração de Regras (`extract_rules.py`)

| Arquivo                  | Conteúdo                                          |
|--------------------------|---------------------------------------------------|
| `rules.json`             | Lista de `ProtocolRule` serializada               |
| `rules_index.json`       | `{ "nome_normalizado": ["rule_001", ...] }`       |
| `rules.meta.json`        | SHA256 do rules.json, total de regras, timestamp  |
| `raw_extractions.json`   | Saída bruta do LLM (modo `--preview`)             |

### 4.2 Auditoria (`audit_surgeries.py`)

| Arquivo                       | Conteúdo                                              |
|-------------------------------|-------------------------------------------------------|
| `auditoria_resultado.xlsx`    | Multi-abas: Todos, Não Conformes, Alertas, Dose, Sem Match, Estatísticas |
| `auditoria_resultado.csv`     | Exportação plana de todos os casos                    |
| `auditoria_resultado.json`    | Resultados detalhados em formato legível por máquina  |
| `auditoria_resumo.txt`        | Resumo textual para leitura humana                    |

### 4.3 Estrutura do `AuditResult`

```python
{
  "surgery_id": str,
  "procedure": str,
  "matched_rule_id": str | None,
  "match_score": float,
  "match_method": str,            # "exact", "fuzzy", "no_match"

  # Conformidade por critério (valores: CONFORME | NAO_CONFORME | ALERTA | INDETERMINADO | N/A)
  "conf_escolha": str,
  "conf_escolha_razao": str,
  "conf_dose": str,
  "conf_dose_razao": str,
  "conf_timing": str,
  "conf_timing_razao": str,
  "conf_repique": str,
  "conf_repique_razao": str,

  # Resultado final
  "conf_final": str,
  "conf_final_razao": str
}
```

---

## 5. Regras de Negócio

### 5.1 Conformidade de Escolha do Antibiótico (`conf_escolha`)

- `CONFORME`: ATB administrado está na lista de regimes aceitáveis do protocolo (`acceptable_regimens`)
- `NAO_CONFORME`: ATB errado, ou administrado quando protocolo indica ausência de profilaxia, ou ausente quando protocolo exige
- `INDETERMINADO`: ATB não identificável, procedimento sem match ou dados insuficientes
- Comparação usa `DRUG_DICTIONARY` (aliases) + fallback fuzzy (threshold: 84%)

### 5.2 Conformidade de Dose (`conf_dose`)

- Tolerância aceitável: `±AUDIT_CONFIG["dose_tolerance_percent"]` (default: **15%**)
- Alerta: entre `alert_dose_tolerance_percent` (10%) e `dose_tolerance_percent` (15%)
- Falha: diferença > `hard_dose_tolerance_percent` (100%)
- **Regra especial Cefazolina:**
  - Peso < 120 kg → dose máxima = **2g**
  - Peso ≥ 120 kg → dose máxima = **3g**
- Dose em mg/kg: `dose_esperada = dose_protocolo_por_kg × peso_paciente_kg`

### 5.3 Conformidade de Timing (`conf_timing`)

- Janela aceitável: **0 a 60 minutos antes da incisão** (`timing_window_minutes`)
- `diff_min = incision_time − atb_time`
- `CONFORME`: `0 ≤ diff_min ≤ 60`
- `NAO_CONFORME`: ATB após incisão (`diff_min < 0`) ou muito antecipado (`diff_min > 60`)
- `INDETERMINADO`: Horários ausentes ou inválidos

### 5.4 Conformidade de Repique (`conf_repique`)

Intervalos de redosagem definidos em `REDOSING_INTERVALS`:

| Antibiótico    | Intervalo (min) |
|----------------|-----------------|
| CEFAZOLINA     | 240 (4h)        |
| CEFUROXIMA     | 240 (4h)        |
| CEFOXITINA     | 120 (2h)        |
| CLINDAMICINA   | 360 (6h)        |
| VANCOMICINA    | 0 (não redosa)  |
| GENTAMICINA    | 0 (não redosa)  |
| CIPROFLOXACINO | 0 (não redosa)  |

- Intervalo = 0: status = `N/A` (repique não aplicável)
- Repique documentado: valida diff entre repique e incisão dentro do intervalo ± tolerância
- Repique requerido mas não documentado: `INDETERMINADO`

### 5.5 Conformidade Final (`conf_final`)

Agregação dos 4 critérios, em ordem de prioridade decrescente:

1. Qualquer `NAO_CONFORME` → `conf_final = NAO_CONFORME`
2. Qualquer `ALERTA` (sem NAO_CONFORME) → `conf_final = ALERTA`
3. Qualquer `INDETERMINADO` (sem NC ou ALERTA) → `conf_final = INDETERMINADO`
4. Sem match + sem ATB administrado → `conf_final = CONFORME` (profilaxia não aplicável)
5. Todos conformes → `conf_final = CONFORME`

### 5.6 Mapeamento de Procedimentos

- Match automático (score > 0.45): marcado como `AUTO`
- Revisão necessária (0.35–0.45): marcado como `REVIEW`
- Sem match (< 0.35): marcado como `NO_MATCH`
- O `procedimentos.json` definitivo deve ser mantido com revisão humana

### 5.7 Versionamento do `procedimentos.json`

- `current` → usa caminho exato informado
- `latest` → seleciona versão mais alta disponível (`procedimentos_vN.json`)
- `N` (número) → seleciona `procedimentos_vN.json` explicitamente

---

## 6. Critérios de Aceite para Avanço no Desenvolvimento

### 6.1 Testes Automatizados

Todo PR deve passar em toda a suíte pytest sem erros:

```bash
pytest -q
```

Arquivos de teste existentes (não remover, não reduzir cobertura):

| Arquivo                         | Cobre                              |
|---------------------------------|------------------------------------|
| `tests/test_surgery_auditor.py` | Lógica de conformidade             |
| `tests/test_llm_extraction.py`  | Pipeline de extração PDF/LLM       |
| `tests/test_input_loader.py`    | Versionamento e carregamento JSON  |
| `tests/test_build_procedure_map.py` | Geração de candidatos         |
| `tests/test_antibiotic_regimens.py` | Parsing e comparação de ATBs  |

Qualquer nova lógica de negócio (critérios de conformidade, parsing, regras especiais) deve incluir testes unitários correspondentes.

### 6.2 Configuração Centralizada

- Nenhum threshold (score, tolerância, janela de tempo, intervalo de repique) pode ser hardcoded fora de `config/settings.py`.
- Mudanças em thresholds devem ser refletidas nos testes correspondentes.

### 6.3 Normalização e Matching

- Toda comparação de texto (procedimento, fármaco) deve passar por `normalize_text()` de `utils/text_utils.py`.
- Novas entradas no `DRUG_DICTIONARY` devem ter pelo menos 3 aliases validados.
- Score de fuzzy match deve usar `rapidfuzz.fuzz.token_set_ratio` para manter consistência.

### 6.4 Modelos de Dados

- Novos campos em `AuditResult` devem incluir campo `_razao` correspondente.
- Valores de status de conformidade são restritos ao enum: `CONFORME`, `NAO_CONFORME`, `ALERTA`, `INDETERMINADO`, `N/A`, `SEM_MATCH`.
- Schemas Pydantic em `models/inputs.py` devem validar novas entradas externas.

### 6.5 Relatórios

- Novos campos de saída devem aparecer em todas as saídas (`.xlsx`, `.csv`, `.json`, `.txt`) de forma consistente.
- O relatório `.xlsx` deve manter as abas: Todos os Casos, Não Conformes, Alertas, Problemas de Dose, Sem Match Protocolo, Estatísticas.

### 6.6 Extração de Regras

- O pipeline de extração deve ser validado com o arquivo `tests/test_llm_extraction.py`.
- Novos backends LLM devem implementar a mesma interface de saída (lista de `ProtocolRule`).
- O modo `--preview` + `--from-raw` deve continuar funcional para permitir revisão humana antes de consolidação.

### 6.7 Compatibilidade de Colunas Excel

- Novas colunas de entrada devem ser mapeadas em `EXCEL_COLUMNS` (settings) com pelo menos um alias.
- A ausência de coluna não-obrigatória não deve causar exceção — retornar `None`/`INDETERMINADO`.

### 6.8 Tratamento de Erros

- Dados ausentes ou inválidos em campos de auditoria → sempre `INDETERMINADO` com razão descritiva, nunca exceção não tratada.
- Exceções de IO (arquivo não encontrado, PDF corrompido) devem logar em `logs/audit.log` e retornar mensagem clara ao usuário.

---

## 7. Comandos de Desenvolvimento

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar testes
pytest -q

# Extrair regras do protocolo (modo completo)
python extract_rules.py ./data/input/protocolo.pdf --output ./data/output --backend langextract

# Extrair regras (modo preview — salva raw_extractions.json para revisão)
python extract_rules.py ./data/input/protocolo.pdf --output ./data/output --preview

# Gerar mapa de candidatos de procedimentos
python build_procedure_map.py --excel ./data/input/cirurgias.xlsx --rules ./data/output/rules.json --output ./data/output/candidatos.json

# Auditar cirurgias
python audit_surgeries.py ./data/input/cirurgias.xlsx ./data/output/rules.json \
  --output ./data/output \
  --procedures-map ./data/input/procedimentos.json
```

---

## 8. Variáveis de Ambiente

| Variável          | Uso                                          | Obrigatória |
|-------------------|----------------------------------------------|-------------|
| `GOOGLE_API_KEY`  | Autenticação Gemini / Langextract            | Para extração |

Arquivo `.env` suportado via `python-dotenv` (não commitar `.env` no repositório).

---

## 9. Decisões Arquiteturais Relevantes

- **Sem interface web por enquanto:** imports Flask estão comentados; não adicionar endpoints HTTP sem alinhamento explícito.
- **Extração é offline após geração:** `rules.json` gerado uma vez por versão de protocolo. A auditoria em si não requer API externa.
- **Qualidade depende do PDF:** PDFs com tabelas bem definidas usam `camelot` (lattice); PDFs mal formatados podem requerer ajuste do `camelot_flavor` para `stream`.
- **Revisão humana no loop:** `procedimentos.json` é o artefato que requer curadoria manual para alta precisão de match.
