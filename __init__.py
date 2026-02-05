"""
Sistema de Auditoria de Profilaxia Antimicrobiana - Mater Dei

Este sistema audita procedimentos cirúrgicos comparando com protocolo
institucional de profilaxia antimicrobiana.

Módulos principais:
- models: Modelos de dados (regras do protocolo, registros de cirurgia)
- controllers: Lógica de negócio (extração, auditoria, relatórios)
- utils: Utilitários (normalização de texto, validação)
- config: Configurações do sistema
"""
from .config import SYSTEM_NAME, SYSTEM_VERSION

__version__ = SYSTEM_VERSION
__all__ = ['SYSTEM_NAME', 'SYSTEM_VERSION']