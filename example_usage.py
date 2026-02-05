#!/usr/bin/env python3
"""
Script de exemplo demonstrando uso programático do sistema

Este script mostra como usar o sistema de auditoria diretamente
no código Python, sem usar os scripts CLI.
"""
import sys
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from materdei_audit.controllers import ProtocolExtractor, SurgeryAuditor, ReportGenerator
from materdei_audit.models import ProtocolRulesRepository
from materdei_audit.config import OUTPUT_DIR, INPUT_DIR

print("=" * 70)
print("EXEMPLO DE USO PROGRAMÁTICO - SISTEMA DE AUDITORIA MATER DEI")
print("=" * 70)
print()

# ============================================================================
# EXEMPLO 1: Extração de Regras do Protocolo
# ============================================================================
print("EXEMPLO 1: Extraindo regras do protocolo")
print("-" * 70)

# Caminho para PDF (ajuste conforme necessário)
pdf_path = INPUT_DIR / "protocolo_profilaxia.pdf"

if pdf_path.exists():
    print(f"PDF encontrado: {pdf_path}")
    
    # Cria extrator
    extractor = ProtocolExtractor(pdf_path)
    
    # Extrai regras
    print("Extraindo regras...")
    rules = extractor.extract_all_rules()
    
    print(f"✓ {len(rules)} regras extraídas")
    
    # Mostra exemplo de regra
    if rules:
        print("\nExemplo de regra extraída:")
        rule = rules[0]
        print(f"  ID: {rule.rule_id}")
        print(f"  Seção: {rule.section}")
        print(f"  Procedimento: {rule.procedure}")
        print(f"  Requer profilaxia: {rule.is_prophylaxis_required}")
        if rule.primary_recommendation.drugs:
            print(f"  Medicamento: {rule.primary_recommendation.drugs[0].name}")
    
    # Salva regras
    print("\nSalvando regras...")
    extractor.save_rules(OUTPUT_DIR)
    print(f"✓ Regras salvas em: {OUTPUT_DIR}")
    
    # Gera relatório de validação
    validation = extractor.get_validation_report()
    print("\nRelatório de validação:")
    print(f"  Total: {validation['total_rules']}")
    print(f"  Com profilaxia: {validation['with_prophylaxis']}")
    print(f"  Sem profilaxia: {validation['without_prophylaxis']}")
    print(f"  Precisam validação: {validation['needs_validation']}")
else:
    print(f"⚠ PDF não encontrado: {pdf_path}")
    print("  Coloque o PDF do protocolo em: data/input/")

print()
print()

# ============================================================================
# EXEMPLO 2: Carregamento de Regras
# ============================================================================
print("EXEMPLO 2: Carregando regras existentes")
print("-" * 70)

rules_path = OUTPUT_DIR / "rules.json"

if rules_path.exists():
    print(f"Carregando regras de: {rules_path}")
    
    # Cria repositório e carrega regras
    rules_repo = ProtocolRulesRepository()
    rules_repo.load_from_json(rules_path)
    
    print(f"✓ {len(rules_repo.rules)} regras carregadas")
    
    # Mostra estatísticas
    stats = rules_repo.get_statistics()
    print("\nEstatísticas:")
    print(f"  Total de regras: {stats['total_rules']}")
    print(f"  Profilaxia requerida: {stats['prophylaxis_required']}")
    print(f"  Profilaxia não requerida: {stats['prophylaxis_not_required']}")
    
    print("\nRegras por seção:")
    for section, count in sorted(stats['sections'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {section}: {count}")
    
    # Exemplo de busca
    print("\nExemplo de busca de procedimento:")
    procedure = "colecistectomia"
    found = rules_repo.find_by_procedure(procedure)
    if found:
        print(f"  ✓ Encontrado: {found[0].procedure}")
    else:
        print(f"  ✗ Não encontrado")
else:
    print(f"⚠ Arquivo rules.json não encontrado: {rules_path}")
    print("  Execute primeiro a extração de regras")

print()
print()

# ============================================================================
# EXEMPLO 3: Auditoria de Cirurgias
# ============================================================================
print("EXEMPLO 3: Auditando cirurgias")
print("-" * 70)

excel_path = INPUT_DIR / "cirurgias_exemplo.xlsx"
rules_path = OUTPUT_DIR / "rules.json"

if excel_path.exists() and rules_path.exists():
    print(f"Planilha: {excel_path}")
    print(f"Regras: {rules_path}")
    
    # Carrega regras
    rules_repo = ProtocolRulesRepository()
    rules_repo.load_from_json(rules_path)
    print(f"✓ {len(rules_repo.rules)} regras carregadas")
    
    # Cria auditor
    auditor = SurgeryAuditor(rules_repo)
    
    # Carrega cirurgias
    print("\nCarregando cirurgias...")
    count = auditor.load_surgeries_from_excel(excel_path)
    print(f"✓ {count} cirurgias carregadas")
    
    # Executa auditoria
    print("\nExecutando auditoria...")
    results = auditor.audit_all_surgeries()
    print(f"✓ {len(results)} cirurgias auditadas")
    
    # Mostra exemplo de resultado
    if results:
        print("\nExemplo de resultado:")
        result = results[0]
        print(f"  Procedimento: {result.surgery_record.procedure}")
        print(f"  Match score: {result.match_score:.2f}")
        print(f"  Conformidade escolha: {result.conf_escolha}")
        print(f"  Conformidade dose: {result.conf_dose}")
        print(f"  Conformidade timing: {result.conf_timing}")
        print(f"  Conformidade final: {result.conf_final}")
    
    # Gera estatísticas
    stats = auditor.get_statistics()
    print("\nEstatísticas da auditoria:")
    print(f"  Total de cirurgias: {stats['total_cirurgias']}")
    print(f"  Conformes: {stats['conformidade_final']['conforme']}")
    print(f"  Alertas: {stats['conformidade_final']['alerta']}")
    print(f"  Não conformes: {stats['conformidade_final']['nao_conforme']}")
    print(f"  Indeterminados: {stats['conformidade_final']['indeterminado']}")
    print(f"\n  Taxa de conformidade: {stats['taxas']['conformidade_total_pct']:.1f}%")
    
    # Gera relatórios
    print("\nGerando relatórios...")
    report_gen = ReportGenerator(results)
    
    report_gen.export_excel(OUTPUT_DIR / "exemplo_auditoria.xlsx")
    print(f"  ✓ Excel: exemplo_auditoria.xlsx")
    
    report_gen.export_csv(OUTPUT_DIR / "exemplo_auditoria.csv")
    print(f"  ✓ CSV: exemplo_auditoria.csv")
    
    summary = report_gen.export_summary_report(OUTPUT_DIR / "exemplo_resumo.txt")
    print(f"  ✓ Resumo: exemplo_resumo.txt")
    
    print(f"\nRelatórios salvos em: {OUTPUT_DIR}")
    
else:
    print("⚠ Arquivos necessários não encontrados:")
    if not excel_path.exists():
        print(f"  - Excel: {excel_path}")
    if not rules_path.exists():
        print(f"  - Rules: {rules_path}")
    print("\n  Certifique-se de ter extraído as regras e ter uma planilha de exemplo")

print()
print()

# ============================================================================
# EXEMPLO 4: Auditoria de Cirurgia Individual
# ============================================================================
print("EXEMPLO 4: Auditando cirurgia individual")
print("-" * 70)

from materdei_audit.models import SurgeryRecord

if rules_path.exists():
    # Carrega regras
    rules_repo = ProtocolRulesRepository()
    rules_repo.load_from_json(rules_path)
    
    # Cria auditor
    auditor = SurgeryAuditor(rules_repo)
    
    # Cria registro de cirurgia de exemplo
    surgery = SurgeryRecord(
        procedure="Colecistectomia videolaparoscópica",
        specialty="Cirurgia Geral",
        incision_time="10:00",
        atb_given="SIM",
        atb_name="KEFAZOL 2G",
        atb_time="09:15",
        dose_administered_mg=2000.0,
        patient_weight=75.0
    )
    
    print("Dados da cirurgia:")
    print(f"  Procedimento: {surgery.procedure}")
    print(f"  Antibiótico: {surgery.atb_name}")
    print(f"  Hora ATB: {surgery.atb_time}")
    print(f"  Hora incisão: {surgery.incision_time}")
    
    # Audita
    print("\nAuditando...")
    result = auditor.audit_surgery(surgery)
    
    print("\nResultado:")
    print(f"  Match com protocolo: {result.match_score:.2f}")
    print(f"  Regra matched: {result.matched_rule_id}")
    print(f"  ATB recomendado: {', '.join(result.protocolo_atb_recomendados)}")
    print(f"  Conformidade escolha: {result.conf_escolha}")
    print(f"  Conformidade dose: {result.conf_dose}")
    print(f"  Conformidade timing: {result.conf_timing}")
    print(f"  >>> Conformidade final: {result.conf_final} <<<")
    
    if result.conf_final == 'NAO_CONFORME':
        print(f"\n  ⚠ Razão: {result.conf_final_razao}")
    elif result.conf_final == 'ALERTA':
        print(f"\n  ⚡ Razão: {result.conf_final_razao}")
    else:
        print(f"\n  ✓ Cirurgia conforme!")
else:
    print(f"⚠ Arquivo rules.json não encontrado: {rules_path}")

print()
print("=" * 70)
print("FIM DOS EXEMPLOS")
print("=" * 70)
print()
print("Para usar na prática:")
print("  1. Coloque o PDF do protocolo em: data/input/")
print("  2. Execute: python extract_rules.py data/input/protocolo.pdf")
print("  3. Coloque a planilha de cirurgias em: data/input/")
print("  4. Execute: python audit_surgeries.py data/input/cirurgias.xlsx data/output/rules.json")
print()