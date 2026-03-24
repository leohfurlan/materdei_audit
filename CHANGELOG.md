# Changelog

Todas as mudanças relevantes do projeto devem ser registradas aqui.

O formato segue a convenção de [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)
e o projeto usa versionamento semântico.

## [Não Lançado]

### Adicionado

- Geração de candidatos de mapeamento com `build_procedure_map.py`.
- Suporte a `--output-simple` no formato `ProcedureMapItem`.
- Resolução versionada de `procedimentos.json` (`current`, `latest` e versões numéricas).
- Suporte a `raw_extractions.json` como entrada da auditoria.
- Modos `--preview` e `--from-raw` no fluxo de extração.
- Backend `langextract` além do backend `gemini`.
- Inferência de especialidade por cirurgião no `build_procedure_map.py` quando a planilha vier sem `Especialidade`.
- Suíte automatizada cobrindo auditoria, extração LLM, carregamento de mapas e geração de candidatos de mapeamento.

### Corrigido

- Documentação principal (`README`, documentação técnica e changelog) alinhada ao estado atual do repositório.

## [1.0.0] - 2025-01-XX

### Adicionado

- Extração de regras do protocolo institucional a partir de PDF.
- Auditoria de cirurgias comparando dados do Excel com o protocolo.
- Validação de quatro critérios: escolha do antibiótico, dose, timing e repique.
- Geração de relatórios em Excel, CSV, JSON e TXT.
- Fuzzy matching para localizar procedimentos no protocolo.
- Detecção automática de medicamentos em texto livre.
- Configuração centralizada em `config/settings.py`.
- Logging de execução em console e arquivo.

### Estrutura

- Arquitetura modular com scripts, controllers, models, utils e config.
- Repositório de regras com serialização em `rules.json`, `rules_index.json` e `rules.meta.json`.

## Roadmap

Itens ainda possíveis para evolução futura:

- interface web;
- API de integração;
- dashboard interativo;
- histórico de auditorias;
- exportações adicionais;
- melhorias contínuas no mapeamento de procedimentos.
