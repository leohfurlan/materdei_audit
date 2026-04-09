# Plano de Desenvolvimento — Sistema de Auditoria de Profilaxia Antimicrobiana

**Versão:** 1.1 — 26/03/2026
**Autor:** Leonardo Furlan

---

## 1. Contexto

O sistema nasceu como ferramenta CLI para auditar profilaxia antimicrobiana cirúrgica no Hospital
Mater Dei. O motor de regras já está operacional e validado com dados reais (Santa Genoveva,
Fevereiro/2026): 793 cirurgias auditadas, 98.5% de conformidade total, 12 não conformidades reais.

O próximo passo é transformar essa ferramenta em um produto SaaS web, contratado inicialmente
em modelo piloto de 4 meses por R$ 600/mês.

---

## 2. Estado atual do motor (baseline do piloto)

| Métrica | Valor |
|---|---|
| Cirurgias auditadas (fev/2026) | 793 |
| Conformes | 170 (21.4%) |
| Alertas (revisão recomendada) | 611 (77.0%) |
| Não conformes (erros reais) | 12 (1.5%) |
| Taxa de conformidade total | 98.5% |

Os 12 não conformes são erros inequivocamente lógicos: 8 antibióticos após incisão, 2 fora da
janela de 1 hora e 2 doses muito acima do recomendado.

Pendências no motor:
- Aguardando retorno da CCIH sobre revisão do arquivo de mapeamento de procedimentos
- Aguardando planilha de profissionais x especialidades para melhorar inferência de especialidade
- Melhorar cobertura de procedimentos de hemodinâmica (cateterismos, angioplastias)

---

## 3. Modelo comercial

### Piloto (4 meses)
- **Valor:** R$ 600/mês
- **Unidade principal:** Santa Clara (mapeamento já validado)
- **Unidade secundária:** Santa Genoveva — incluída como validação adicional sem custo extra se o
  retorno da CCIH vier ainda no mês 1. Mantida fora do preço atual; entra como primeira unidade
  de expansão na contratação ampla caso não caiba no piloto.
- **Entregáveis:** motor refinado, web app com upload/download, dashboard com histórico mensal
- **Marco final:** estudo de caso com ROI + apresentação para a gerência

> **Nota estratégica:** não aumentar o preço agora. Incluir Genoveva no piloto como bônus
> fortalece o estudo de caso (duas unidades = evidência mais robusta para a diretoria) e
> o retorno financeiro vem na contratação ampla com precificação por unidade.

### Contratação ampla (pós-piloto)
- Base: evidência de horas economizadas e erros prevenidos documentados no piloto
- Expansão para outras unidades do Mater Dei
- Precificação a definir com base no número de unidades e volume mensal

### Estudo de caso (entrega do mês 4)
- Horas de trabalho economizadas pela equipe
- Erros de profilaxia identificados e prevenidos
- Evolução dos indicadores mês a mês durante o piloto
- Documento conjunto com a CCIH, destacando a iniciativa da equipe

---

## 4. Arquitetura técnica

```
Usuário (browser)
  -> Frontend (Streamlit ou React simples)
  -> Backend (FastAPI — Python)
       -> Anonimizador (remove dados pessoais antes de qualquer persistência)
  -> Motor de auditoria (código atual reutilizado como biblioteca)
  -> Banco de dados (PostgreSQL) — armazena apenas dados clínicos anonimizados
  -> Hospedagem (Railway ou Render — nuvem pública liberada pela anonimização)
```

### Estratégia LGPD — anonimização na entrada

Os arquivos Excel contêm dados pessoais de pacientes e médicos (nomes, possivelmente CPF),
classificados como **dados sensíveis de saúde** pela LGPD (Art. 11).

**Solução adotada:** anonimizar no momento do upload, antes de qualquer persistência.

O backend remove ou substitui por hash os campos com dados pessoais antes de salvar no banco.
O que fica armazenado é apenas o dado clínico necessário para a auditoria:

| Campo mantido | Campo removido/hasheado |
|---|---|
| Procedimento | Nome do paciente |
| Especialidade | CPF / RG |
| Antibiótico, dose, horários | Nome do médico (substituído por hash) |
| Código de atendimento (hasheado) | Qualquer outro dado identificador |

O arquivo Excel original **nunca é persistido no servidor** — é processado em memória e descartado.

**Cláusula contratual recomendada:** incluir no contrato que o sistema aplica anonimização
automática dos dados pessoais no momento do upload, que nenhum dado identificador de paciente
ou profissional é armazenado nos servidores, e que o prestador (Leonardo Furlan) atua como
operador de dados conforme LGPD Art. 39, sob as instruções do controlador (Hospital Mater Dei).

### Stack escolhida para o piloto

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Backend | FastAPI (Python) | Reutiliza todo o código atual; baixa curva |
| Banco | PostgreSQL (Railway/Render) | Persistência de histórico; tier gratuito/barato |
| Frontend | Streamlit (piloto) | Entrega rápida; substitutível por React no futuro |
| Hospedagem | Railway ou Render | Simples, sem overhead de AWS; ~R$ 25–50/mês |
| Autenticação | JWT básico + controle por unidade | Mínimo exigido pelo hospital |

**Custo estimado de infra:** R$ 25–50/mês, dentro da margem do contrato.

### Modelo de dados (schema central)

```
units          — unidades hospitalares (Santa Clara, Santa Genoveva...)
users          — usuários com vínculo a uma ou mais unidades
audit_runs     — cada upload = um run (unidade + período + data do upload)
audit_results  — resultados individuais por cirurgia (FK para audit_runs)
```

Esse schema permite acúmulo histórico desde o primeiro run e sustenta todos os indicadores
do dashboard sem reestruturação futura.

---

## 5. Roadmap — 4 meses

### Mês 1 — Fundação

**Objetivo:** resolver pendências críticas e entregar a primeira auditoria oficial.

Técnico:
- [ ] Fechar escopo do contrato: Santa Clara como unidade principal; Genoveva como secundária se feedback da CCIH chegar a tempo
- [ ] Processar feedback da CCIH no mapeamento de procedimentos (`procedimentos.json`) quando disponível
- [ ] Incorporar planilha de profissionais x especialidades quando disponível
- [ ] Implementar módulo de anonimização (identificar campos sensíveis nas planilhas de cada unidade)
- [ ] Definir e documentar o schema do banco de dados
- [ ] Configurar ambiente de hospedagem e banco

Entrega ao hospital:
- [ ] Primeira auditoria oficial (mês de referência a combinar) em formato Excel/PDF
- [ ] Relatório de baseline documentando o estado atual dos indicadores

---

### Mês 2 — Web MVP com histórico

**Objetivo:** o hospital para de depender do desenvolvedor para rodar a auditoria.

- [ ] Backend FastAPI operacional com banco de dados
- [ ] Endpoint de upload de Excel → anonimização → auditoria → salva no banco
- [ ] Download de resultados (xlsx + resumo txt) — relatório sem dados pessoais
- [ ] Autenticação (login) com controle de acesso por unidade
- [ ] Interface web funcional (Streamlit): upload, status do processamento, download
- [ ] Deploy em produção

Entrega ao hospital:
- [ ] Acesso ao sistema web
- [ ] Treinamento da equipe para uso autônomo

---

### Mês 3 — Dashboard

**Objetivo:** substituir o Power BI com painel integrado, simples e sem manutenção externa.

Indicadores propostos:

**Visão geral (mensal)**
- Taxa de conformidade total (%)
- Distribuição: Conforme / Alerta / Não Conforme (gráfico de pizza ou barra)
- Volume de cirurgias auditadas

**Por critério (mensal)**
- Conformidade de escolha do antibiótico
- Conformidade de dose
- Conformidade de timing (1ª hora)
- Conformidade de repique

**Evolução histórica**
- Taxa de conformidade total mês a mês (linha)
- Evolução dos não conformes por tipo (barras empilhadas)

**Análise de não conformidades**
- Principais tipos de erro (ranking)
- Distribuição por especialidade cirúrgica
- Casos para revisão manual (sem match no protocolo)

Técnico:
- [ ] Queries de agregação histórica no banco
- [ ] Componentes de visualização no frontend
- [ ] Filtro por unidade e por período

---

### Mês 4 — ROI e fechamento

**Objetivo:** construir a evidência para a contratação ampla.

- [ ] Compilar métricas do piloto: evolução mês a mês, horas economizadas (estimativa), erros identificados
- [ ] Redigir estudo de caso conjunto com a CCIH
- [ ] Preparar apresentação para a gerência/diretoria
- [ ] Proposta de contratação ampla (novas unidades, novo preço)
- [ ] Planejar roadmap da fase seguinte (histórico cross-unidade, alertas automáticos, etc.)

---

## 6. Riscos e dependências

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Campos sensíveis variam entre planilhas de unidades diferentes | Alta | Médio | Mapear colunas de cada planilha no mês 1; módulo de anonimização configurável por unidade |
| Escopo expande para múltiplas unidades sem ajuste de preço | Alta | Médio | Contrato cobre Santa Clara; Genoveva entra como bônus se caber; demais unidades = aditivo |
| Feedback da CCIH demora e prejudica qualidade do motor | Média | Médio | Motor já está em 98.5%; iniciar sem o feedback e incorporar incrementalmente |
| Dashboard cresce e consome o mês 3 inteiro | Alta | Médio | Fixar escopo dos indicadores no início do mês 3; extras = escopo do pós-piloto |
| Streamlit vira limitação de UX | Baixa (no piloto) | Baixo | Aceitável para piloto; substituível por React na contratação ampla |

---

## 7. Próximos passos imediatos (esta semana)

1. Confirmar com o hospital que o piloto cobre Santa Clara; alinhar se Genoveva entra como secundária
2. Incluir cláusula de anonimização e operação de dados (LGPD) no contrato
3. Aguardar retorno da CCIH sobre o arquivo de mapeamento de procedimentos da Genoveva
4. Assinar contrato antes de iniciar o desenvolvimento da web app
5. Mapear quais colunas das planilhas do Santa Clara contêm dados pessoais (preparação para o módulo de anonimização)
