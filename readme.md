# Sistema de Auditoria de Profilaxia Antimicrobiana - Mater Dei

## Visão Geral

Sistema CLI para:

1. extrair regras do protocolo institucional a partir de PDF;
2. montar e revisar o mapeamento entre nomenclaturas do Excel e procedimentos do protocolo;
3. auditar cirurgias realizadas comparando escolha de antibiótico, dose, timing e repique com as regras extraídas.

Estado da documentação: revisada em 2026-03-24.

## Fluxo Atual do Projeto

```text
PDF do protocolo
  -> extract_rules.py
  -> rules.json / rules_index.json / rules.meta.json

Planilha Excel + rules.json
  -> build_procedure_map.py (apoio à revisão de nomenclatura)
  -> revisão manual / versionamento de procedimentos.json

Planilha Excel + rules.json|raw_extractions.json + procedimentos.json
  -> audit_surgeries.py
  -> auditoria_resultado.xlsx / .csv / .json / auditoria_resumo.txt
```

## Principais Funcionalidades

- Extração de regras com backend LLM `gemini` ou `langextract`.
- Modo `preview` para gerar `raw_extractions.json` antes de consolidar `rules.json`.
- Conversão de `raw_extractions.json` revisado para `rules.json`.
- Auditoria de 4 critérios: escolha do antibiótico, dose, timing e repique.
- Uso opcional de `procedimentos.json` para tradução de nomenclaturas do Excel.
- Resolução versionada do mapa de procedimentos (`current`, `latest` ou versão numérica).
- Geração de candidatos de mapeamento com suporte a especialidade e inferência via cirurgião.
- Relatórios em Excel, CSV, JSON e TXT.
- Suíte automatizada de testes com `pytest`.

## Estrutura do Repositório

```text
materdei_audit/
├── audit_surgeries.py
├── build_procedure_map.py
├── extract_rules.py
├── config/
│   └── settings.py
├── controllers/
│   ├── protocol_extractor.py
│   ├── report_generator.py
│   └── surgery_auditor.py
├── models/
│   ├── audit_data.py
│   ├── inputs.py
│   └── protocol_rules.py
├── utils/
│   ├── antibiotic_regimens.py
│   ├── input_loader.py
│   ├── text_utils.py
│   └── validation.py
├── tests/
├── data/
│   ├── input/
│   ├── output/
│   └── temp/
└── logs/
```

## Instalação

### Requisitos

- Python 3.10+
- Dependências de `requirements.txt`
- Ghostscript para o fluxo de extração de PDF com Camelot
- Chave de API para os backends LLM de extração

### Ambiente virtual

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows:

```powershell
.\.venv\Scripts\activate
```

### Dependências

```bash
pip install -r requirements.txt
```

### Variáveis de ambiente

O extractor tenta ler a chave de API nesta ordem:

- `LANGEXTRACT_API_KEY`
- `GEMINI_API_KEY`
- `GOOGLE_API_KEY`
- `API_KEY_GOOGLE_AI_STUDIO`

Exemplo de `.env`:

```env
GEMINI_API_KEY=seu-token-aqui
```

### Ghostscript

Necessário para o fluxo de extração de PDF.

Linux/Ubuntu:

```bash
sudo apt-get install ghostscript python3-tk
```

macOS:

```bash
brew install ghostscript
```

Windows:

- baixar em <https://www.ghostscript.com/download/gsdnld.html>;
- instalar e adicionar ao `PATH`.

## Uso

### 1. Extrair regras do protocolo

Fluxo completo:

```bash
python extract_rules.py ./data/input/protocolo.pdf --output ./data/output
```

Parâmetros principais:

- `pdf_path`: PDF do protocolo.
- `--output, -o`: diretório de saída.
- `--pages, -p`: páginas a extrair.
- `--backend, -b`: `gemini` ou `langextract`.
- `--preview`: gera `raw_extractions.json` e não consolida regras.
- `--from-raw ARQUIVO`: converte `raw_extractions.json` revisado para `rules.json`.

Exemplos:

Preview para revisão manual:

```bash
python extract_rules.py ./data/input/protocolo.pdf \
  --output ./data/output/langextract_preview \
  --backend langextract \
  --preview
```

Conversão de um `raw_extractions.json` revisado:

```bash
python extract_rules.py ./data/input/protocolo.pdf \
  --output ./data/output/langextract_preview_full \
  --from-raw ./data/output/langextract_preview/raw_extractions.json
```

Artefatos gerados no modo consolidado:

- `rules.json`
- `rules_index.json`
- `rules.meta.json`

Artefato gerado no modo preview:

- `raw_extractions.json`

### 2. Gerar candidatos de mapeamento de procedimentos

`build_procedure_map.py` é um utilitário de apoio para revisão do mapeamento entre a planilha e o protocolo. Ele não substitui diretamente o `procedimentos.json` consumido pela auditoria; o uso esperado é revisar os candidatos gerados e consolidar o mapa de tradução.

```bash
python build_procedure_map.py \
  --excel ./data/input/cirurgias.xlsx \
  --rules ./data/output/rules.json \
  --output ./data/output/procedure_map_review.json \
  --output-simple ./data/output/procedure_map_review_simple.json \
  --use-specialty
```

Parâmetros principais:

- `--excel`: planilha de cirurgias.
- `--rules`: `rules.json`.
- `--output`: JSON detalhado com status e candidatos.
- `--output-simple`: JSON opcional no formato `ProcedureMapItem`.
- `--sheet`: aba do Excel.
- `--top-k`: quantidade de candidatos por procedimento.
- `--min-auto`: score mínimo para status `AUTO`.
- `--min-review`: score mínimo para status `REVIEW`.
- `--use-specialty`: considera especialidade no match.
- `--synonyms`: JSON opcional de sinônimos.

Comportamento relevante do script:

- resolve colunas por nome configurado e aliases;
- usa `Especialidade` quando presente;
- quando `Especialidade` estiver vazia, tenta inferi-la pela especialidade predominante do `Cirurgião` na própria planilha;
- utiliza a especialidade efetiva tanto na chave do mapeamento quanto no `combo_norm` usado no fuzzy match.

### 3. Auditar cirurgias

```bash
python audit_surgeries.py \
  ./data/input/cirurgias.xlsx \
  ./data/output/rules.json \
  --output ./data/output \
  --procedures-map ./data/input/procedimentos.json \
  --procedures-map-version current
```

`rules_path` aceita:

- `rules.json`
- `raw_extractions.json` (convertido automaticamente em memória)

Parâmetros principais:

- `excel_path`: planilha Excel com as cirurgias.
- `rules_path`: `rules.json` ou `raw_extractions.json`.
- `--output, -o`: diretório de saída.
- `--sheet, -s`: aba do Excel.
- `--procedures-map`: arquivo JSON com tradução Excel -> protocolo.
- `--procedures-map-version`: `current`, `latest` ou uma versão numérica.

Saídas:

- `auditoria_resultado.xlsx`
- `auditoria_resultado.csv`
- `auditoria_resultado.json`
- `auditoria_resumo.txt`

## Arquivos de Entrada

### Planilha Excel

O sistema resolve colunas pelo nome configurado em `config/settings.py` e por aliases normalizados. As colunas mais relevantes são:

| Campo canônico | Coluna típica | Observação |
|---|---|---|
| procedimento | `Cirurgia` | obrigatória |
| especialidade | `Especialidade` | recomendada |
| cirurgião | `Cirurgiao` / `Nome do Cirurgião` | recomendada para melhorar o mapeamento |
| data | `Dt Cirurgia` | opcional para auditoria consolidada |
| atendimento | `Cod Atendimento` | opcional |
| incisão | `Hr Incisão` | usada em timing |
| antibiótico administrado | `Administração de Antibiotico` | usada em escolha |
| antibiótico | `Antibiótico` | usada em escolha e dose |
| horário do antibiótico | `Hr Antibiótico` | usada em timing |
| repique | `Repique` | usada em redosing |
| horário do repique | `Hora Repique` | usada em redosing |
| peso | `Peso (kg)` | necessário para regras em mg/kg |

Observações:

- `Especialidade` pode vir vazia na planilha, mas o `build_procedure_map.py` consegue inferi-la a partir do cirurgião quando houver histórico suficiente no próprio arquivo.
- Para melhorar a qualidade do match, manter a coluna do cirurgião preenchida é fortemente recomendado.

### `procedimentos.json`

Formato simples:

```json
{
  "APENDICECTOMIA POR VIDEOLAPAROSCOPIA": "Apendicectomia não complicada",
  "CESARIANA": "Parto cesariana"
}
```

Formato versionado:

```json
{
  "metadata": {
    "version": 2,
    "description": "mapa revisado",
    "generated_at": "2026-03-24T10:00:00"
  },
  "mappings": {
    "PROC A": "MAP A"
  }
}
```

Resolução de versão:

- `current`: usa exatamente o arquivo informado em `--procedures-map`;
- `latest`: procura o maior sufixo `_vN.json`;
- `3`: resolve para `*_v3.json`.

## Critérios de Conformidade

### Escolha do antibiótico

- `CONFORME`: antibiótico compatível com o protocolo.
- `NAO_CONFORME`: antibiótico inadequado, não administrado quando necessário ou regime incompleto.
- `INDETERMINADO`: dados insuficientes.

### Dose

- `CONFORME`: dentro da tolerância configurada.
- `ALERTA`: pequena diferença.
- `NAO_CONFORME`: diferença relevante.
- `INDETERMINADO`: sem dose utilizável ou sem referência.

Regras ponderais em mg/kg usam o peso do paciente. Para cefazolina, aplica-se teto de 2 g para pacientes com menos de 120 kg e 3 g para pacientes com 120 kg ou mais.

### Timing

- `CONFORME`: antibiótico administrado de 0 a 60 minutos antes da incisão.
- `NAO_CONFORME`: fora da janela ou após a incisão.
- `INDETERMINADO`: horários ausentes ou inválidos.

### Repique

- `CONFORME`: repique dentro do intervalo configurado.
- `NAO_CONFORME`: repique fora do intervalo.
- `INDETERMINADO`: horários ausentes quando o critério é aplicável.
- `NÃO APLICÁVEL`: implícito quando o antibiótico não exige redosing.

## Configuração

As configurações centrais estão em `config/settings.py`.

### Auditoria

```python
AUDIT_CONFIG = {
    "match_threshold": 0.70,
    "translation_match_similarity_threshold": 0.45,
    "specialty_match_threshold": 0.60,
    "dose_tolerance_percent": 15,
    "hard_dose_tolerance_percent": 100,
    "timing_window_minutes": 60,
    "alert_dose_tolerance_percent": 10,
}
```

### Extração

```python
EXTRACTION_CONFIG = {
    "pages_to_extract": "8-35",
    "llm_backend": "langextract",
    "gemini_model": "gemini-2.5-flash",
    "langextract_model": "gemini-2.5-flash",
    "llm_pages_per_chunk": 3,
    "langextract_batch_length": 4,
    "langextract_max_workers": 4,
    "langextract_extraction_passes": 2,
    "camelot_flavor": "lattice",
}
```

### Intervalos de repique

```python
REDOSING_INTERVALS = {
    "CEFAZOLINA": 240,
    "CEFUROXIMA": 240,
    "CEFOXITINA": 120,
    "CLINDAMICINA": 360,
    "VANCOMICINA": 0,
    "GENTAMICINA": 0,
    "CIPROFLOXACINO": 0,
}
```

## Relatórios

O Excel exportado contém as abas:

- `Todos os Casos`
- `Não Conformes`
- `Alertas`
- `Problemas de Dose`
- `Sem Match Protocolo`
- `Estatísticas`

O sistema também gera logs em `logs/audit.log` e replica as mensagens principais no console.

## Testes

Executar a suíte:

```bash
pytest -q
```

Atualmente o repositório possui testes para:

- auditoria de cirurgias;
- extração com LLM;
- carregamento de mapas de procedimentos;
- geração de candidatos de `build_procedure_map`;
- utilitários de regimes antibióticos.

## Solução de Problemas

### Muitos casos sem match

- revise e atualize `procedimentos.json`;
- gere candidatos com `build_procedure_map.py`;
- prefira preencher `Especialidade` e `Cirurgião` na planilha;
- revise nomenclaturas que estejam muito distantes do protocolo.

### Mapa de procedimentos não encontrado

`audit_surgeries.py` continua a execução sem o mapa, mas a qualidade do matching tende a cair. Verifique:

- caminho de `--procedures-map`;
- versão pedida em `--procedures-map-version`;
- existência dos arquivos `*_vN.json` quando usar `latest` ou uma versão específica.

### Extração incompleta

- teste com menos páginas em `--pages`;
- use `--preview` para inspecionar o bruto antes da consolidação;
- revise `raw_extractions.json` e use `--from-raw`;
- confirme a presença da API key e do Ghostscript.

## Licença

Uso interno Hospital Mater Dei.
