# Documentação Técnica - Sistema de Auditoria Mater Dei

Documentação revisada em 2026-03-24.

## Visão Geral Técnica

O repositório implementa um pipeline CLI dividido em três frentes:

1. extração de regras do protocolo a partir de PDF;
2. preparação e revisão do mapa de tradução de procedimentos do Excel para o protocolo;
3. auditoria das cirurgias com geração de relatórios.

## Módulos Principais

### Scripts de entrada

- `extract_rules.py`: extrai regras do protocolo e salva artefatos em JSON.
- `build_procedure_map.py`: gera candidatos de mapeamento entre planilha e protocolo.
- `audit_surgeries.py`: executa a auditoria completa.

### Controllers

- `controllers/protocol_extractor.py`
  - extrai texto e tabelas do PDF;
  - chama backend `gemini` ou `langextract`;
  - suporta preview em `raw_extractions.json`;
  - converte `raw_extractions.json` revisado para `rules.json`.
- `controllers/surgery_auditor.py`
  - carrega registros do Excel;
  - aplica tradução opcional via `procedimentos.json`;
  - faz match com o protocolo;
  - avalia escolha, dose, timing e repique.
- `controllers/report_generator.py`
  - exporta relatórios em Excel, CSV, JSON e TXT.

### Models

- `models/protocol_rules.py`
  - `ProtocolRule`
  - `Recommendation`
  - `Drug`
  - `ProtocolRulesRepository`
- `models/audit_data.py`
  - `SurgeryRecord`
  - `AuditResult`
- `models/inputs.py`
  - schemas Pydantic para arquivos auxiliares de configuração e formatos de mapa.

### Utils

- `utils/text_utils.py`
  - normalização de texto;
  - fuzzy matching;
  - parsing de dose e horário.
- `utils/antibiotic_regimens.py`
  - extração e comparação de regimes antibióticos.
- `utils/input_loader.py`
  - carga de YAML/JSON;
  - resolução versionada de `procedimentos.json`.
- `utils/validation.py`
  - validações de apoio.

### Configuração

- `config/settings.py`
  - thresholds de matching;
  - tolerâncias de dose e timing;
  - intervalos de repique;
  - nomes canônicos e aliases de colunas;
  - configurações dos backends de extração.

## Arquitetura de Fluxo

### 1. Extração do protocolo

```text
PDF
  -> ProtocolExtractor
  -> raw_extractions.json (modo preview)
  -> convert_raw_to_rules / build_from_raw
  -> ProtocolRulesRepository
  -> rules.json + rules_index.json + rules.meta.json
```

Pontos relevantes:

- o extractor carrega `.env` automaticamente;
- a API key é procurada em `LANGEXTRACT_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY` ou `API_KEY_GOOGLE_AI_STUDIO`;
- o backend configurável em runtime é `gemini` ou `langextract`;
- `audit_surgeries.py` também aceita `raw_extractions.json` como entrada e faz a conversão em memória.

### 2. Construção do mapa de procedimentos

```text
Excel + rules.json
  -> build_procedure_map.py
  -> candidatos AUTO / REVIEW / NO_MATCH
  -> revisão manual
  -> procedimentos.json
```

O script não produz automaticamente o arquivo final consumido pela auditoria. Ele produz material de apoio para revisão do mapeamento.

### 3. Auditoria

```text
Excel + rules.json|raw_extractions.json + procedimentos.json
  -> SurgeryAuditor
  -> AuditResult[]
  -> ReportGenerator
  -> xlsx / csv / json / txt
```

## Fluxo Atual das CLIs

### `extract_rules.py`

Argumentos relevantes:

- `pdf_path`
- `--output`
- `--pages`
- `--backend`
- `--preview`
- `--from-raw`

Modos operacionais:

- completo: `PDF -> LLM -> rules.json`
- preview: `PDF -> raw_extractions.json`
- from-raw: `raw_extractions.json -> rules.json`

Arquivos produzidos:

- `rules.json`
- `rules_index.json`
- `rules.meta.json`
- `raw_extractions.json` no modo preview

### `build_procedure_map.py`

Argumentos relevantes:

- `--excel`
- `--rules`
- `--output`
- `--sheet`
- `--top-k`
- `--min-auto`
- `--min-review`
- `--use-specialty`
- `--synonyms`
- `--output-simple`

Saídas:

- JSON detalhado com status por chave;
- JSON opcional no formato `ProcedureMapItem`.

### `audit_surgeries.py`

Argumentos relevantes:

- `excel_path`
- `rules_path`
- `--output`
- `--sheet`
- `--procedures-map`
- `--procedures-map-version`

Comportamento operacional:

- aceita `rules.json` ou `raw_extractions.json`;
- carrega `procedimentos.json` quando disponível;
- continua executando sem mapa de procedimentos, emitindo warning;
- grava relatórios e estatísticas no diretório de saída.

## Algoritmos e Regras de Negócio

### Normalização e fuzzy matching

`utils.text_utils.normalize_text()`:

- remove acentos;
- converte para minúsculo;
- remove pontuação;
- compacta espaços.

`utils.text_utils.clean_procedure_name()`:

- aplica `normalize_text()`;
- remove stopwords comuns de procedimentos.

`utils.text_utils.fuzzy_match_score()`:

- usa `rapidfuzz.fuzz.token_set_ratio`;
- retorna score entre 0 e 1.

### Resolução do mapa de tradução de procedimentos

`utils.input_loader.load_procedure_translation_map()` suporta dois formatos:

1. legado:

```json
{
  "PROC EXCEL": "PROC PROTOCOLO"
}
```

2. versionado:

```json
{
  "metadata": {
    "version": 2
  },
  "mappings": {
    "PROC EXCEL": "PROC PROTOCOLO"
  }
}
```

Regras de resolução:

- `current`: usa o caminho informado;
- `latest`: escolhe o maior `_vN.json`;
- `N`: resolve para `_vN.json`.

### Construção do mapa em `build_procedure_map.py`

Etapas principais:

1. resolve colunas reais do Excel usando `EXCEL_COLUMNS` e `EXCEL_COLUMN_ALIASES`;
2. constrói um conjunto de especialidades observadas para evitar matches com cabeçalhos genéricos;
3. indexa regras combinando `section + procedure`;
4. percorre o Excel e avalia candidatos por score;
5. classifica cada item como `AUTO`, `REVIEW` ou `NO_MATCH`.

#### Inferência de especialidade via cirurgião

Estado atual do script:

- antes do `iterrows()`, é criado um dicionário `cirurgião normalizado -> especialidade predominante`;
- em caso de empate, vence a primeira especialidade não nula encontrada;
- se a linha atual vier sem `Especialidade`, o script tenta inferi-la usando o cirurgião;
- a especialidade inferida passa a compor:
  - a chave de agrupamento;
  - o `combo_norm` usado no fuzzy match;
  - o campo exportado de especialidade.

Esse comportamento melhora o matching quando a planilha está incompleta em `Especialidade`, mas possui `Cirurgião` consistente.

### Auditoria de cirurgias

O `SurgeryAuditor` executa as etapas abaixo para cada registro:

1. traduz o nome do procedimento com `procedimentos.json`, se houver mapa;
2. tenta localizar a melhor regra do protocolo;
3. avalia antibiótico documentado e recomendações primárias/alergia;
4. valida dose, incluindo regras ponderais em mg/kg;
5. valida timing em relação ao horário de incisão;
6. valida repique conforme `REDOSING_INTERVALS`;
7. calcula `conf_final`.

### Critérios de conformidade

#### Escolha

- considera compatibilidade do antibiótico ou regime documentado com o protocolo;
- trata explicitamente cenários como:
  - antibiótico não recomendado;
  - profilaxia não requerida;
  - procedimento sem match;
  - registro insuficiente.

#### Dose

- usa `dose_tolerance_percent` e `alert_dose_tolerance_percent`;
- aceita cálculo ponderal por peso;
- aplica regra especial para cefazolina:
  - até 2 g para peso abaixo de 120 kg;
  - até 3 g para peso igual ou acima de 120 kg.

#### Timing

- janela padrão de 0 a 60 minutos antes da incisão;
- classifica como não conforme quando após a incisão ou fora da janela.

#### Repique

- usa `REDOSING_INTERVALS`;
- considera tolerância operacional em torno do intervalo esperado;
- devolve status apropriado para antibióticos sem necessidade de redosing ou com dados ausentes.

## Artefatos Persistidos

### Regras do protocolo

- `rules.json`: lista de regras serializadas.
- `rules_index.json`: índice por procedimento normalizado.
- `rules.meta.json`: hash, contagem e metadados de geração.

Observação:

- `ProtocolExtractor.get_validation_report()` retorna estatísticas em memória;
- o repositório não gera `rules.validation.json`.

### Relatórios de auditoria

- `auditoria_resultado.xlsx`
- `auditoria_resultado.csv`
- `auditoria_resultado.json`
- `auditoria_resumo.txt`

### Mapeamentos auxiliares

- `procedimentos.json`: mapa consumido pela auditoria;
- saídas do `build_procedure_map.py`: base de revisão para manter esse mapa.

## Configuração

### `AUDIT_CONFIG`

Parâmetros mais relevantes:

- `match_threshold`
- `translation_match_similarity_threshold`
- `specialty_match_threshold`
- `dose_tolerance_percent`
- `hard_dose_tolerance_percent`
- `timing_window_minutes`
- `alert_dose_tolerance_percent`

### `EXTRACTION_CONFIG`

Parâmetros mais relevantes:

- `pages_to_extract`
- `llm_backend`
- `gemini_model`
- `langextract_model`
- `llm_max_chunk_chars`
- `llm_pages_per_chunk`
- `langextract_batch_length`
- `langextract_max_workers`
- `langextract_extraction_passes`
- `camelot_flavor`
- parâmetros finos de `lattice` e `stream`

### `EXCEL_COLUMNS` e aliases

O sistema não depende apenas de nomes exatos. Há resolução por alias para colunas como:

- procedimento;
- especialidade;
- cirurgião;
- horários de incisão e antibiótico;
- repique;
- peso.

## Testes

Estado atual:

- a suíte é executável com `pytest`;
- o repositório já possui testes automatizados, não é mais um item futuro.

Arquivos de teste presentes:

- `tests/test_antibiotic_regimens.py`
- `tests/test_build_procedure_map.py`
- `tests/test_input_loader.py`
- `tests/test_llm_extraction.py`
- `tests/test_surgery_auditor.py`

Cobertura qualitativa atual:

- extração de regras com Gemini e Langextract;
- carregamento de versões do mapa de procedimentos;
- regras de auditoria e calibragem;
- geração de candidatos de mapeamento, incluindo inferência de especialidade por cirurgião.

## Operação e Manutenção

### Atualizar o protocolo institucional

1. rodar `extract_rules.py` no modo completo ou preview;
2. revisar `raw_extractions.json` quando necessário;
3. consolidar `rules.json`;
4. validar resultados com um conjunto conhecido de cirurgias.

### Atualizar o mapa de procedimentos

1. rodar `build_procedure_map.py` sobre uma amostra recente do Excel;
2. revisar itens `AUTO`, `REVIEW` e `NO_MATCH`;
3. consolidar o mapa final em `data/input/procedimentos.json` ou em versão `*_vN.json`;
4. executar a auditoria apontando para a versão desejada.

### Quando a taxa de sem-match aumenta

Checklist prático:

- verificar se `procedimentos.json` está desatualizado;
- validar se a planilha está preenchendo `Especialidade` e `Cirurgião`;
- revisar novos nomes comerciais ou abreviações;
- reexecutar `build_procedure_map.py` com `--use-specialty`.

### Logs

O logging é centralizado em `LOGGING_CONFIG` e grava em:

- console;
- `logs/audit.log`.

## Limitações Conhecidas

- o mapa final consumido pela auditoria ainda depende de revisão manual;
- a qualidade da extração do protocolo depende de PDF, backend LLM e API key válidos;
- planilhas com horários ausentes ou texto muito inconsistente aumentam `INDETERMINADO` e `SEM_MATCH`.
