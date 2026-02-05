# Sistema de Auditoria de Profilaxia Antimicrobiana - Mater Dei

## Visão Geral

Sistema para auditoria automatizada de procedimentos cirúrgicos, comparando a profilaxia antimicrobiana administrada com o protocolo institucional do Hospital Mater Dei.

**Versão:** 1.0.0  
**Python:** 3.10+

## Funcionalidades

### 1. Extração de Regras do Protocolo (PDF → JSON)
- Extrai automaticamente regras do protocolo institucional em PDF
- Identifica procedimentos cirúrgicos e suas recomendações
- Detecta medicamentos, doses e condições especiais
- Gera banco de dados estruturado em JSON

### 2. Auditoria de Cirurgias (Excel → Relatórios)
- Carrega planilha Excel com cirurgias realizadas
- Faz match inteligente entre procedimento e protocolo
- Valida 3 critérios de conformidade:
  - **Escolha do antibiótico**: medicamento está no protocolo?
  - **Dose administrada**: dose correta para o procedimento?
  - **Timing**: antibiótico dado na janela de 1 hora antes da incisão?
- Gera relatórios detalhados em Excel, CSV e JSON

### 3. Geração de Relatórios
- Excel com múltiplas abas (todos casos, não conformes, alertas, estatísticas)
- CSV para análise de dados
- JSON para integração com outros sistemas
- Relatório resumido em texto

## Arquitetura

```
materdei_audit/
├── models/              # Modelos de dados
│   ├── protocol_rules.py    # Regras do protocolo
│   └── audit_data.py         # Dados de auditoria
├── controllers/         # Lógica de negócio
│   ├── protocol_extractor.py   # Extração de PDF
│   ├── surgery_auditor.py      # Auditoria de cirurgias
│   └── report_generator.py     # Geração de relatórios
├── utils/               # Utilitários
│   ├── text_utils.py         # Normalização de texto
│   └── validation.py         # Validação de dados
├── config/              # Configurações
│   └── settings.py           # Configurações globais
└── data/                # Dados
    ├── input/           # Arquivos de entrada
    ├── output/          # Arquivos de saída
    └── temp/            # Arquivos temporários
```

## Instalação

### Requisitos
- Python 3.10 ou superior
- Ghostscript (para processamento de PDF)

### Passo a Passo

1. **Clone ou baixe o projeto:**
```bash
cd /path/to/project
```

2. **Crie ambiente virtual (recomendado):**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. **Instale dependências:**
```bash
pip install -r requirements.txt
```

4. **Instale Ghostscript (necessário para Camelot):**

**Linux/Ubuntu:**
```bash
sudo apt-get install ghostscript python3-tk
```

**MacOS:**
```bash
brew install ghostscript
```

**Windows:**
- Baixe de: https://www.ghostscript.com/download/gsdnld.html
- Instale e adicione ao PATH

## Uso

### 1. Extração de Regras do Protocolo

Primeiro, extraia as regras do PDF do protocolo institucional:

```bash
python extract_rules.py /caminho/para/protocolo.pdf --output ./data/output
```

**Parâmetros:**
- `pdf_path`: Caminho para o PDF do protocolo (obrigatório)
- `--output, -o`: Diretório de saída (padrão: `./data/output`)
- `--pages, -p`: Páginas a extrair (padrão: "8-35")

**Saída:**
- `rules.json`: Banco de dados com todas as regras
- `rules_index.json`: Índice para busca rápida
- `rules.meta.json`: Metadados e hash SHA256

**Exemplo:**
```bash
python extract_rules.py ./protocolo_materdei.pdf \
  --output ./data/output \
  --pages "8-35"
```

### 2. Auditoria de Cirurgias

Com as regras extraídas, audite a planilha de cirurgias:

```bash
python audit_surgeries.py /caminho/para/cirurgias.xlsx ./data/output/rules.json --output ./data/output
```

**Parâmetros:**
- `excel_path`: Caminho para planilha Excel com cirurgias (obrigatório)
- `rules_path`: Caminho para rules.json (obrigatório)
- `--output, -o`: Diretório de saída para relatórios (padrão: `./data/output`)
- `--sheet, -s`: Nome da aba do Excel (padrão: primeira aba)

**Saída:**
- `auditoria_resultado.xlsx`: Relatório completo com múltiplas abas
- `auditoria_resultado.csv`: Dados em CSV
- `auditoria_resultado.json`: Dados em JSON
- `auditoria_resumo.txt`: Relatório resumido em texto

**Exemplo:**
```bash
python audit_surgeries.py ./cirurgias_dezembro.xlsx \
  ./data/output/rules.json \
  --output ./data/output \
  --sheet "DEZEMBRO 2025"
```

## Formato da Planilha Excel

A planilha de cirurgias deve conter as seguintes colunas:

| Coluna                          | Descrição                              | Tipo        |
|---------------------------------|----------------------------------------|-------------|
| `Dt Cirurgia`                   | Data da cirurgia                       | Data        |
| `Cirurgia`                      | Nome do procedimento                   | Texto       |
| `Especialidade`                 | Especialidade cirúrgica                | Texto       |
| `Hr Incisão`                    | Horário da incisão (HH:MM)            | Hora        |
| `Administração de Antibiotico`  | SIM ou NÃO                            | Texto       |
| `Antibiótico`                   | Nome e dose do antibiótico            | Texto       |
| `Hr Antibiótico`                | Horário de administração (HH:MM)      | Hora        |
| `Repique`                       | SIM ou NÃO                            | Texto       |
| `Hora Repique`                  | Horário do repique (HH:MM)            | Hora        |
| `Peso (kg)`                     | Peso do paciente (opcional)           | Número      |

**Exemplo de linha:**
```
Data: 01/12/2025
Cirurgia: Colecistectomia videolaparoscópica
Especialidade: Cirurgia Geral
Hr Incisão: 10:00
Administração de Antibiotico: SIM
Antibiótico: KEFAZOL 2G
Hr Antibiótico: 09:15
Repique: NÃO
Peso (kg): 75
```

## Critérios de Conformidade

### 1. Escolha do Antibiótico
- **CONFORME**: Antibiótico está nas recomendações do protocolo
- **NÃO CONFORME**: Antibiótico não recomendado ou não administrado quando requerido
- **INDETERMINADO**: Procedimento não encontrado no protocolo ou dados insuficientes

### 2. Dose
- **CONFORME**: Dose dentro da tolerância (±10%)
- **ALERTA**: Pequena diferença (10-15%)
- **NÃO CONFORME**: Diferença >15% ou dose muito baixa/alta
- **INDETERMINADO**: Dose não informada ou sem referência no protocolo

### 3. Timing
- **CONFORME**: Antibiótico administrado 0-60 minutos antes da incisão
- **NÃO CONFORME**: Fora da janela ou após incisão
- **INDETERMINADO**: Horários não informados

### Conformidade Final
A conformidade final é determinada pela combinação dos três critérios:
- **CONFORME**: Todos os critérios conformes
- **ALERTA**: Pelo menos um critério em alerta, nenhum não conforme
- **NÃO CONFORME**: Pelo menos um critério não conforme
- **INDETERMINADO**: Dados insuficientes para avaliar

## Configuração

As configurações do sistema estão em `materdei_audit/config/settings.py`:

### Tolerâncias de Auditoria
```python
AUDIT_CONFIG = {
    "match_threshold": 0.70,              # Score mínimo para match
    "dose_tolerance_percent": 15,         # Tolerância de dose
    "timing_window_minutes": 60,          # Janela de timing
    "alert_dose_tolerance_percent": 10,   # Tolerância para alertas
}
```

### Extração de PDF
```python
EXTRACTION_CONFIG = {
    "pages_to_extract": "8-35",
    "camelot_flavor": "lattice",
    "similarity_threshold": 0.7,
}
```

### Dicionário de Medicamentos
Edite `DRUG_DICTIONARY` em `settings.py` para adicionar novos medicamentos:
```python
DRUG_DICTIONARY = {
    "CEFAZOLINA": ["KEFAZOL", "CEFAZOLINA", "ANCEF"],
    # ... adicione mais aqui
}
```

## Estrutura dos Relatórios Excel

### Aba: "Todos os Casos"
Todos os casos auditados com todas as colunas de dados e conformidade.

### Aba: "Não Conformes"
Apenas casos com conformidade final = NAO_CONFORME.
Use para identificar casos que requerem ação corretiva.

### Aba: "Alertas"
Casos com pequenas diferenças de dose que merecem revisão.

### Aba: "Problemas de Dose"
Casos onde o antibiótico estava correto mas a dose estava incorreta.
Estes casos são particularmente importantes para feedback à equipe.

### Aba: "Sem Match Protocolo"
Procedimentos que não foram encontrados no protocolo.
Pode indicar necessidade de atualização do protocolo ou erros na nomenclatura.

### Aba: "Estatísticas"
Resumo quantitativo da auditoria:
- Total de cirurgias
- Conformidade por status
- Conformidade por critério
- Qualidade do match com protocolo
- Taxas de conformidade

## Logs

O sistema gera logs detalhados em `logs/audit.log`:
- DEBUG: Informações detalhadas de processamento
- INFO: Progresso geral da auditoria
- WARNING: Alertas e problemas não críticos
- ERROR: Erros que impedem o processamento

Logs também são exibidos no console durante a execução.

## Solução de Problemas

### Erro: "Arquivo PDF não encontrado"
- Verifique se o caminho está correto
- Use caminhos absolutos se necessário

### Erro: "Nenhuma regra extraída"
- Verifique o parâmetro `--pages`
- Confirme que o PDF não está corrompido
- Teste com uma única página primeiro

### Erro: "Colunas faltantes na planilha"
- Verifique os nomes das colunas no Excel
- Os nomes devem corresponder exatamente aos configurados
- Veja seção "Formato da Planilha Excel"

### Baixa taxa de conformidade
- Revise casos não conformes no relatório
- Verifique se o protocolo está atualizado
- Confirme se os nomes dos procedimentos correspondem

### Muitos casos "Sem Match"
- Procedimentos podem ter nomenclaturas diferentes
- Considere adicionar sinônimos no código
- Revise a normalização de texto

## Desenvolvimento Futuro

### Planejado para versão 2.0:
- [ ] Interface web Flask para upload e visualização
- [ ] API REST para integração com outros sistemas
- [ ] Dashboard interativo com gráficos
- [ ] Autenticação e controle de acesso
- [ ] Histórico de auditorias
- [ ] Geração de relatórios em PDF
- [ ] Notificações por email de não conformidades
- [ ] Machine learning para sugestões de melhoria

### Para Contribuir
O código está modularizado e documentado para facilitar extensões:
1. Novos medicamentos: edite `DRUG_DICTIONARY` em `config/settings.py`
2. Novos critérios: adicione em `controllers/surgery_auditor.py`
3. Novos relatórios: estenda `controllers/report_generator.py`
4. Novas validações: adicione em `utils/validation.py`

## Licença

© 2025 Hospital Mater Dei - Sistema Interno de Auditoria

## Suporte

Para dúvidas ou problemas:
1. Verifique a documentação acima
2. Consulte os logs em `logs/audit.log`
3. Entre em contato com a equipe de TI ou SECIH

---

**Sistema desenvolvido para automatizar e padronizar a auditoria de profilaxia antimicrobiana, contribuindo para a segurança do paciente e conformidade com protocolos institucionais.**