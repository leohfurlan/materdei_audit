# PRD — Sistema de Auditoria de Profilaxia Antimicrobiana
## Product Requirements Document

**Versão:** 1.0 — 26/03/2026
**Autor:** Leonardo Furlan
**Status:** Rascunho

---

## 1. Problema

Equipes de CCIH hospitalares realizam auditorias mensais de profilaxia antimicrobiana de forma
inteiramente manual: baixam uma planilha do sistema do hospital, analisam caso a caso no Excel e
preenchem os resultados à mão. O processo é lento, sujeito a inconsistências humanas e não gera
histórico estruturado para acompanhamento de tendências.

Não existe hoje uma ferramenta que automatize essa análise, produza indicadores consolidados e
permita à equipe focar no que exige julgamento clínico — em vez de trabalho repetitivo de
classificação.

---

## 2. Solução

Plataforma web que recebe a planilha mensal de cirurgias, aplica automaticamente as regras do
protocolo institucional de profilaxia e devolve o resultado da auditoria com indicadores visuais
e histórico acumulado entre meses.

A equipe para de fazer análise manual de casos triviais e passa a revisar apenas os casos que o
sistema sinaliza como incertos ou problemáticos.

---

## 3. Usuários

### Auditora CCIH
Profissional de saúde que realiza a auditoria mensal. Faz o upload da planilha, acompanha o
processamento e baixa os resultados. Não tem perfil técnico — espera uma interface simples,
sem instalação, que funcione no navegador.

**Necessidade central:** subir o arquivo e ter o resultado pronto em minutos, sem precisar de
suporte técnico.

### Coordenadora CCIH
Responsável pelo programa de profilaxia da unidade. Acompanha os indicadores do dashboard,
identifica tendências e usa os dados para reportar à gerência e sustentar decisões clínicas.

**Necessidade central:** visão consolidada da evolução dos indicadores ao longo dos meses,
sem depender de ferramentas externas de BI.

---

## 4. Fluxo atual (como é hoje)

```
1. Equipe baixa planilha de resultados do sistema do hospital (Excel)
2. Auditora analisa linha a linha, consultando o protocolo impresso ou em PDF
3. Preenche manualmente colunas de conformidade na planilha
4. Coordenadora consolida os dados para relatório mensal
5. Indicadores são alimentados manualmente no Power BI (com dificuldades de manutenção)
```

Problemas: processo lento, inconsistente entre auditoras, sem rastreabilidade histórica
estruturada, dependência de ferramenta de BI externa de difícil manutenção.

---

## 5. Fluxo futuro (como será)

```
1. Auditora baixa planilha do sistema do hospital (Excel) — sem mudança
2. Auditora faz upload da planilha no sistema web
3. Sistema anonimiza dados pessoais, processa a auditoria e salva no banco
4. Auditora baixa o resultado (Excel + resumo) em menos de 2 minutos
5. Coordenadora acessa o dashboard e visualiza indicadores do mês + histórico
```

---

## 6. Objetivos e métricas de sucesso

### Qualidade dos resultados
| Métrica | Meta para o piloto |
|---|---|
| Taxa de classificação automática confiável | ≥ 95% dos casos classificados sem revisão manual |
| Alinhamento com auditoria manual | Divergência < 5% nos casos revisados pela CCIH |
| Não conformidades reais identificadas | Apenas erros inequivocamente lógicos (timing, dose, antibiótico errado) |
| Falsos positivos (alertas desnecessários) | < 10% do total de alertas |

### Facilidade de uso
| Métrica | Meta para o piloto |
|---|---|
| Tempo do upload até download do resultado | < 2 minutos |
| Tempo para visualizar o dashboard após login | < 30 segundos |
| Necessidade de suporte técnico para uso rotineiro | Zero |
| Funciona sem instalação, direto no navegador | Sim |

---

## 7. Features e requisitos

### P0 — Essencial para o MVP (Mês 2)

**F01 — Autenticação e controle de acesso**
- Login com e-mail e senha
- Cada usuário é vinculado a uma ou mais unidades hospitalares
- Auditora e Coordenadora veem apenas os dados da(s) sua(s) unidade(s)
- Sessão com expiração por inatividade

**F02 — Upload e processamento da planilha**
- Upload de arquivo Excel (.xlsx, .xls)
- Anonimização automática de dados pessoais antes de qualquer persistência
  (nomes de pacientes, médicos e dados identificadores são removidos ou hasheados)
- Arquivo original nunca armazenado no servidor — processado em memória e descartado
- Processamento assíncrono com indicador de progresso na tela
- Associação automática ao período (mês/ano) detectado na planilha ou informado pelo usuário

**F03 — Download dos resultados**
- Arquivo Excel com as colunas originais + colunas de conformidade adicionadas
- Abas separadas: todos os casos, não conformes, alertas, estatísticas
- Arquivo de resumo em texto (.txt) com os principais indicadores
- Resultados disponíveis para re-download a qualquer momento

**F04 — Histórico de runs**
- Lista dos processamentos anteriores por unidade, ordenada por data
- Status de cada run (concluído, erro)
- Botão de re-download de qualquer run anterior

---

### P1 — Necessário para o piloto completo (Mês 3)

**F05 — Dashboard de indicadores**

*Visão do mês atual:*
- Taxa de conformidade total (%)
- Distribuição Conforme / Alerta / Não Conforme (gráfico de barras ou pizza)
- Volume de cirurgias auditadas
- Conformidade por critério: escolha do antibiótico, dose, timing, repique

*Evolução histórica (linha do tempo):*
- Taxa de conformidade total mês a mês
- Evolução dos não conformes por tipo

*Análise de não conformidades:*
- Ranking dos principais tipos de erro
- Distribuição por especialidade cirúrgica
- Casos que precisam de revisão manual (sem match no protocolo)

*Filtros:*
- Por unidade (para usuários com acesso a mais de uma)
- Por período (mês/ano)

---

### P2 — Pós-piloto / Contratação ampla

**F06 — Gestão de usuários** (interface admin para adicionar/remover usuários e vincular unidades)
**F07 — Comparativo entre unidades** (dashboard cross-unidade para a coordenação central)
**F08 — Notificações por e-mail** (resultado disponível, alertas críticos)
**F09 — Atualização do protocolo** (fluxo para re-extrair regras quando o PDF do protocolo mudar)
**F10 — Exportação de relatório para gerência** (PDF executivo com os indicadores do período)

---

## 8. Requisitos não funcionais

### Segurança e LGPD
- Dados pessoais de pacientes e profissionais são anonimizados no momento do upload (Art. 11 LGPD)
- Nenhum dado identificador é armazenado no banco ou em disco
- Comunicação via HTTPS em toda a aplicação
- Senhas armazenadas com hash (bcrypt)
- Tokens JWT com expiração
- Isolamento de dados por unidade — usuário de uma unidade não acessa dados de outra

### Disponibilidade e performance
- Disponível 24h/dia (hospedagem em nuvem com uptime ≥ 99%)
- Processamento de uma planilha mensal típica (< 1.000 linhas) em menos de 2 minutos
- Dashboard carrega em menos de 30 segundos

### Compatibilidade
- Funciona nos navegadores modernos (Chrome, Firefox, Edge) sem instalação
- Responsivo para uso em telas de desktop e notebook (mobile não é prioridade no piloto)

### Manutenibilidade
- Motor de regras (código Python atual) reutilizado como biblioteca interna — sem duplicação
- Mapeamento de procedimentos (`procedimentos.json`) atualizável sem redeploy
- Logs de cada processamento armazenados para diagnóstico

---

## 9. Visão de longo prazo — Modelo Cowork (pós-piloto)

Após a validação do piloto (meses 1-4), a evolução planejada é transformar o sistema em um
modelo conversacional onde a equipe CCIH interage com um agente especializado — em vez de
editar arquivos JSON e rodar scripts. O motor de regras determinístico permanece intacto;
o LLM encapsula a interação com uma camada conversacional.

### Princípio central

LLM = linguagem e fluxo de trabalho. Motor = classificação de conformidade. Separação rígida.

### Tools planejadas para o agente

| Tool | O que faz |
|---|---|
| `run_audit(excel, period)` | Dispara auditoria e retorna narrativa em linguagem clínica |
| `explain_case(id)` | Explica um caso individualmente em linguagem acessível |
| `propose_mapping / confirm_mapping` | Resolve procedimentos sem match via conversa (substitui edição de JSON) |
| `query_protocol_rule(procedure)` | Consulta o protocolo em linguagem natural |
| `compare_periods(run_a, run_b)` | Comparativo narrativo entre dois meses |

### Roadmap do cowork

| Fase | Quando | Entrega |
|---|---|---|
| 0 | Meses 1-4 | Piloto web — validar motor e estabilizar mapeamentos |
| 1 | Mês 5-6 | Motor como tools + chat integrado ao web app |
| 2 | Mês 7 | Revisão de mapeamentos conversacional (elimina edição manual de JSON) |
| 3 | Mês 8 | Explicabilidade e análise comparativa por período |
| 4 | Mês 9-10 | Atualização de protocolo via upload de PDF no chat |

**Critério de entrada na Fase 1:** `procedimentos.json` com cobertura suficiente para
< 20 procedimentos sem match por mês — volume ergonômico para revisão conversacional.

### Decisões de design

- Toda confirmação via chat gera log auditável (usuário + timestamp + texto da interação)
- `procedimentos.json` passa a ser versionado (git-tracked ou banco) para rastreabilidade
- Custo de API controlado: batch roda sem LLM; LLM ativado apenas para explicações e mapeamentos

---

## 10. Fora do escopo do piloto

Os itens abaixo são **explicitamente excluídos** do piloto para manter o escopo controlado:

- Integração com sistemas do hospital (HIS, prontuário eletrônico)
- Aplicativo mobile
- Notificações automáticas por e-mail ou WhatsApp
- Comparativo entre unidades hospitalares diferentes
- Gestão de usuários via interface (usuários criados manualmente no mês 1)
- Atualização automática do protocolo quando o PDF mudar
- Auditoria em tempo real (integrada ao centro cirúrgico)
- Múltiplos idiomas

---

## 10. Critérios de aceite do piloto

O piloto será considerado bem-sucedido se, ao final dos 4 meses:

1. **Qualidade:** a equipe da CCIH confirmar que os resultados automáticos estão alinhados com
   a auditoria manual em ≥ 95% dos casos
2. **Usabilidade:** a auditora conseguir completar o fluxo de upload até download sem suporte
   técnico e em menos de 2 minutos
3. **Dashboard:** a coordenadora conseguir visualizar a evolução dos indicadores dos meses do
   piloto sem precisar exportar dados para outra ferramenta
4. **Estudo de caso:** existir evidência documentada (horas economizadas, erros identificados)
   suficiente para uma apresentação à gerência

---

## 11. Premissas e dependências

| Item | Premissa |
|---|---|
| Formato da planilha | Mantém o formato Excel atual; mudanças de colunas requerem ajuste no mapeamento |
| Protocolo institucional | Sem mudanças no PDF do protocolo durante o piloto; se houver, re-extração é necessária |
| Feedback da CCIH | Mapeamento de procedimentos da Genoveva recebido até o fim do mês 1 para inclusão no piloto |
| Contrato | Assinado antes do início do desenvolvimento da web app |
| LGPD | Hospital Mater Dei atua como controlador de dados; Leonardo Furlan como operador (Art. 39) |

---

## 12. Aberto / A definir

- [ ] Quais colunas das planilhas do Santa Clara contêm dados pessoais (necessário para o módulo de anonimização)
- [ ] Genoveva entra no piloto ou fica para a contratação ampla (depende do retorno da CCIH)
- [ ] Credenciais iniciais de acesso: quem são os usuários do Santa Clara que precisam de login
