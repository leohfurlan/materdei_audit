# CLAUDE.md — Contexto e Regras do Projeto

Sistema de auditoria de profilaxia antimicrobiana cirúrgica — Hospital Mater Dei / Santa Genoveva.

---

## Pipeline

```
PDF do protocolo
  -> extract_rules.py
  -> data/output/langextract_preview_full/rules.json  ← gerado por LLM, NÃO editar manualmente

Planilha Excel (cirurgias) + rules.json
  -> build_procedure_map.py  (gera candidatos de mapeamento para revisão)
  -> data/input/procedimentos.json  ← ESTE arquivo é editável; é aqui que se melhora o matching

procedimentos.json + rules.json + Excel
  -> audit_surgeries.py
  -> data/output/<run>/auditoria_resultado.{xlsx,csv,json} + auditoria_resumo.txt
```

---

## Regra crítica: rules.json NÃO deve ser editado manualmente

`data/output/langextract_preview_full/rules.json` é gerado automaticamente por `extract_rules.py`
a partir do PDF do protocolo institucional. Edições manuais são sobrescritas na próxima extração
e criam divergência entre o código e o documento oficial.

**Para corrigir uma regra do protocolo:** editar o `raw_extractions.json` gerado com `--preview`
e regenerar via `--from-raw`. Nunca editar `rules.json` diretamente.

**Para melhorar o matching de um procedimento da planilha com o protocolo:** editar
`data/input/procedimentos.json` adicionando ou corrigindo a entrada
`"NOME NA PLANILHA": "Nome da regra no protocolo"`.

O valor deve ser o nome **exato** de um `procedure` em `rules.json`. Use `build_procedure_map.py`
para gerar candidatos e escolher o mais correto.

---

## Regras de negócio (acordadas com equipe CCIH — reunião 23/03/2026)

### Quando classificar como NAO_CONFORME

Apenas erros **inequivocamente lógicos**:

- Antibiótico administrado **após** a incisão (`timing_apos_incisao`)
- Antibiótico administrado **fora da janela** de 1 hora antes da incisão (`timing_fora_janela`)
- **Dose muito acima** do recomendado (`dose_muito_alta`)
- **Dose muito abaixo** do recomendado (`dose_muito_baixa`)
- Antibiótico **claramente inadequado** para um protocolo que exige profilaxia e especifica o medicamento (`atb_nao_recomendado`)
- Regime combinado **claramente incompleto** (`atb_regime_incompleto`)

### Quando classificar como ALERTA (não como NAO_CONFORME)

- Antibiótico administrado quando o **protocolo não indica profilaxia** (`profilaxia_nao_recomendada`): o cirurgião pode ter avaliado fatores de risco do paciente não registrados na planilha; não é erro inequívoco.
- **Sem registro** de administração quando o protocolo exigiria (`sem_registro_administracao`): requer dupla conferência com outras fontes (evolução do anestesista, transoperatório de enfermagem).
- **Procedimento não encontrado** no protocolo (`sem_match_protocolo`): requer análise humana.
- Dados insuficientes para validar (horários ausentes, dose não informada, antibiótico não identificado).

### Lógica de conformidade final

O status final segue a pior situação entre os 4 critérios (escolha, dose, timing, repique):
`NAO_CONFORME > ALERTA > INDETERMINADO > CONFORME`.

---

## Critérios de conformidade por dimensão

| Critério | CONFORME | ALERTA | NAO_CONFORME |
|---|---|---|---|
| Escolha | ATB compatível com protocolo | Dados ambíguos, sem registro, sem match | ATB errado quando protocolo é claro |
| Dose | Dentro de ±10% | Entre ±10% e ±100% | Além de ±100% (hard tolerance) |
| Timing | 0–60 min antes da incisão | — | Após incisão ou além de 60 min antes |
| Repique | Dentro do intervalo ±30 min | — | Fora do intervalo |

---

## Melhorando o matching de procedimentos

### Problema típico

A planilha usa nomes de faturamento (ex.: `N.P.REPARO OU SUTURA DE UM MENISCO (JOELHO)`)
que não coincidem com os nomes do protocolo (ex.: `Artroscopia em geral`).

O sistema tenta resolver isso em 3 etapas:
1. Lookup direto em `procedimentos.json` (melhor qualidade)
2. Matching exato normalizado contra `rules.json`
3. Fuzzy matching com limiar de 0.70

### Como adicionar um mapeamento

```bash
# 1. Gerar candidatos para a planilha
python build_procedure_map.py \
  --excel "data/input/PROFILAXIA GENOVEVA Fevereiro.xlsx" \
  --rules data/output/langextract_preview_full/rules.json \
  --output data/output/procedure_map_review.json \
  --output-simple data/output/procedure_map_review_simple.json \
  --use-specialty

# 2. Revisar os candidatos e editar procedimentos.json
# 3. Rodar a auditoria com o mapa atualizado
python audit_surgeries.py \
  "data/input/PROFILAXIA GENOVEVA Fevereiro.xlsx" \
  data/output/langextract_preview_full/rules.json \
  --output data/output/<nova_run> \
  --procedures-map data/input/procedimentos.json
```

O valor em `procedimentos.json` deve ser o campo `procedure` de uma entrada de `rules.json`.
Usar o `build_procedure_map.py` para identificar qual é o nome correto.

### Inferência por cirurgião

`build_procedure_map.py` infere a especialidade quando a coluna `Especialidade` está vazia,
usando o histórico do cirurgião na própria planilha. Isso melhora o matching em planilhas
que omitem essa coluna.

---

## Arquivos de dados chave

| Arquivo | Papel | Editável? |
|---|---|---|
| `data/output/langextract_preview_full/rules.json` | Regras extraídas do protocolo (fonte da verdade) | NÃO — regerar via `extract_rules.py` |
| `data/input/procedimentos.json` | Mapa Excel → protocolo (461 entradas atualmente) | SIM — principal alavanca de qualidade |
| `data/input/drug_aliases.json` | Aliases de medicamentos | SIM |
| `data/input/procedure_aliases.json` | Aliases de procedimentos para fuzzy match | SIM |
| `config/settings.py` | Configurações de limiares e colunas | SIM |

---

## Estado atual (25/03/2026) — run genoveva_match_fix_review_v4

793 cirurgias auditadas (Fevereiro/2026 — Santa Genoveva):

| Status | Qtd | % |
|---|---|---|
| CONFORME | 170 | 21.4% |
| ALERTA | 497 | 62.7% |
| NAO_CONFORME | 126 | 15.9% |

Dos 126 NAO_CONFORME:
- **114** são `profilaxia_nao_recomendada` — antibiótico dado quando protocolo não exige.
  Esses deveriam ser **ALERTA** conforme acordo da reunião de 23/03/2026.
  Fix: alterar `_validate_choice` em `controllers/surgery_auditor.py` (linhas 1007 e 1030).
- **10** são erros reais de timing (8 pós-incisão + 2 fora da janela).
- **2** são dose muito acima do recomendado.

### Próximo passo técnico imediato

Alterar as linhas 1007 e 1030 de `controllers/surgery_auditor.py`:

```python
# ANTES
return 'NAO_CONFORME', 'profilaxia_nao_recomendada'

# DEPOIS
return 'ALERTA', 'profilaxia_nao_recomendada'
```

Isso reduziria NAO_CONFORME de 126 para ~12, elevando a taxa de conformidade total de 84% para ~98%.

---

## Visão de produto — Modelo Cowork (pós-piloto, mês 5+)

Após o piloto, o sistema evoluirá para um modelo conversacional onde a CCIH interage com um
agente LLM especializado em vez de editar JSONs e rodar CLIs.

**Princípio:** motor de regras permanece determinístico e intacto. LLM encapsula a interação.

### Roadmap

| Fase | Quando | O que muda |
|---|---|---|
| 1 | Mês 5-6 | Motor empacotado como tools + chat integrado ao web app |
| 2 | Mês 7 | Revisão de mapeamentos via conversa (sem edição manual de `procedimentos.json`) |
| 3 | Mês 8 | Explicação de casos e comparativo entre períodos em linguagem clínica |
| 4 | Mês 9-10 | Atualização de protocolo via upload de PDF diretamente no chat |

**Critério de entrada:** < 20 procedimentos sem match por mês (cobertura estável do `procedimentos.json`).

**Restrições de design:**
- LLM nunca calcula conformidade — apenas explica e propõe
- Toda confirmação de mapeamento via chat é logada (usuário + timestamp)
- `procedimentos.json` passa a ser versionado para rastreabilidade regulatória

---

## Próximas etapas acordadas com CCIH (23/03/2026)

- [ ] CCIH vai revisar o arquivo de mapeamento de procedimentos e corrigir classificações incorretas.
- [ ] CCIH vai enviar planilha de profissionais x especialidades (sem dados sensíveis) para melhorar inferência de especialidade.
- [ ] Aplicar fix de `profilaxia_nao_recomendada` → ALERTA.
- [ ] Melhorar mapeamento de procedimentos de hemodinâmica (cateterismos, angioplastias) e outros sem match confiável.
