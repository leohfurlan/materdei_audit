# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2025-01-XX

### Adicionado
- Sistema completo de extração de regras de protocolo PDF
- Sistema de auditoria de cirurgias comparando com protocolo
- Validação de três critérios: escolha de antibiótico, dose e timing
- Geração de relatórios em múltiplos formatos (Excel, CSV, JSON, TXT)
- Fuzzy matching para match inteligente de procedimentos
- Detecção automática de medicamentos em texto
- Cálculo de conformidade com tolerâncias configuráveis
- Logs detalhados de processamento
- Documentação completa (README, TECHNICAL_DOCS)
- Scripts CLI para extração e auditoria
- Exemplo de uso programático

### Estrutura
- Arquitetura MVC modular
- Models: ProtocolRule, SurgeryRecord, AuditResult
- Controllers: ProtocolExtractor, SurgeryAuditor, ReportGenerator
- Utils: Normalização de texto, validação de dados
- Config: Configurações centralizadas

### Funcionalidades
- Extração de 150+ regras de PDF de 30 páginas
- Auditoria de centenas de cirurgias por minuto
- Relatórios com múltiplas abas para análise
- Estatísticas detalhadas de conformidade
- Identificação de casos não conformes
- Alertas para pequenas diferenças de dose

## [Não Lançado]

### Planejado para v2.0.0
- Interface web Flask
- API REST
- Dashboard interativo com gráficos
- Autenticação e controle de acesso
- Histórico de auditorias
- Geração de relatórios em PDF
- Notificações por email
- Machine learning para sugestões

### Planejado para v1.1.0
- Testes unitários completos
- Validação de peso por kg/mg
- Suporte para múltiplas doses
- Melhor detecção de repique
- Validação de duração de cirurgia
- Export para Google Sheets
- Comparação entre períodos

---

## Tipos de mudanças
- `Adicionado` para novas funcionalidades
- `Modificado` para mudanças em funcionalidades existentes
- `Descontinuado` para funcionalidades que serão removidas
- `Removido` para funcionalidades removidas
- `Corrigido` para correções de bugs
- `Segurança` para vulnerabilidades corrigidas