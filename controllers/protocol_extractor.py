"""
Controller para extraÃ§Ã£o de regras do protocolo a partir do PDF
"""
import sys
from pathlib import Path

# Garante que a raiz do projeto estÃ¡ no sys.path quando executado diretamente
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import re
import logging
from typing import List, Dict, Any, Optional
import json
import time
from itertools import zip_longest
import pandas as pd
try:
    import camelot
except ImportError:
    camelot = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
import textwrap
import dotenv
import os
from google import genai
from google.genai import types as genai_types
try:
    import langextract as lx
    from langextract.data import ExampleData, Extraction
except ImportError:
    lx = None
    ExampleData = None
    Extraction = None

dotenv.load_dotenv()

# Tenta mÃºltiplas variÃ¡veis de ambiente para a API key
api_key = (
    os.getenv("LANGEXTRACT_API_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or os.getenv("API_KEY_GOOGLE_AI_STUDIO")
)

logger = logging.getLogger(__name__)

if not api_key:
    logger.warning("Nenhuma API key encontrada! Defina GEMINI_API_KEY, GOOGLE_API_KEY, API_KEY_GOOGLE_AI_STUDIO ou LANGEXTRACT_API_KEY no .env")

from models import ProtocolRule, Recommendation, Drug, ProtocolRulesRepository, AntibioticRule, SurgeryType
from utils import normalize_text, extract_drug_names
from config import EXTRACTION_CONFIG, DRUG_DICTIONARY




class ProtocolExtractor:
    _PAGE_BREAK_MARKER = "<<PAGE_BREAK>>"
    
    def __init__(self, pdf_path: Path, config: Dict[str, Any] = None):
        """
        Inicializa o extrator.
        
        Args:
            pdf_path: Caminho para o PDF do protocolo
            config: ConfiguraÃ§Ãµes de extraÃ§Ã£o (usa EXTRACTION_CONFIG se None)
        """
        self.pdf_path = pdf_path
        self.config = config or EXTRACTION_CONFIG
        self.rules: List[ProtocolRule] = []
        self.llm_backend = str(self.config.get("llm_backend", "gemini")).strip().lower()
        self.gemini_model = self.config.get("gemini_model", "gemini-2.5-flash")
        self.langextract_model = self.config.get("langextract_model", self.gemini_model)
        self._gemini_client = genai.Client(api_key=api_key) if api_key else None
        
        if self.llm_backend not in {"gemini", "langextract"}:
            logger.warning(f"Backend LLM invalido '{self.llm_backend}'. Usando 'gemini'.")
            self.llm_backend = "gemini"
        
        if self.llm_backend == "langextract" and lx is None:
            logger.warning("Biblioteca 'langextract' nao instalada. Fallback para backend 'gemini'.")
            self.llm_backend = "gemini"
        
    def extract_all_rules(self) -> List[ProtocolRule]:
        """
        Pipeline completo: PDF -> LLM -> ProtocolRule.
        Extrai texto, chama o LLM, converte para objetos Python.
        
        Returns:
            Lista de regras extraÃ­das
        """
        logger.info(f"Iniciando extraÃ§Ã£o de regras de: {self.pdf_path}")
        
        # Passo 1: Extrai texto do PDF
        text = self._get_pdf_text()
        
        # Passo 2: Chama o LLM e obtÃ©m resultado bruto
        raw_extractions = self.extract_raw_from_text(text)
        
        # Passo 3: Converte para objetos ProtocolRule
        self.rules = self.convert_raw_to_rules(raw_extractions)
        
        logger.info(f"ExtraÃ§Ã£o concluÃ­da: {len(self.rules)} regras")
        return self.rules

    def extract_rules_from_text(self, text: str) -> List[ProtocolRule]:
        """
        Pipeline alternativo: texto cru -> LLM -> ProtocolRule.
        """
        raw_extractions = self.extract_raw_from_text(text)
        self.rules = self.convert_raw_to_rules(raw_extractions)
        return self.rules

    def extract_preview(self, output_dir: Path) -> Path:
        """
        Modo preview: extrai texto do PDF, chama o LLM,
        salva resultado bruto em raw_extractions.json e PARA.
        
        Args:
            output_dir: DiretÃ³rio onde salvar raw_extractions.json
            
        Returns:
            Caminho do arquivo raw_extractions.json gerado
        """
        logger.info(f"[PREVIEW] Extraindo texto de: {self.pdf_path}")
        text = self._get_pdf_text()
        
        logger.info("[PREVIEW] Chamando LLM para extraÃ§Ã£o...")
        raw_extractions = self.extract_raw_from_text(text)
        
        # Salva resultado bruto
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_path = output_dir / 'raw_extractions.json'
        self.save_raw_extractions(raw_extractions, raw_path)
        
        logger.info(f"[PREVIEW] {len(raw_extractions)} extraÃ§Ãµes salvas em: {raw_path}")
        logger.info("[PREVIEW] Revise o arquivo e depois execute com --from-raw para gerar rules.json")
        return raw_path

    def build_from_raw(self, raw_path: Path) -> List[ProtocolRule]:
        """
        Modo from-raw: carrega raw_extractions.json revisado
        e converte para objetos ProtocolRule.
        
        Args:
            raw_path: Caminho para raw_extractions.json
            
        Returns:
            Lista de regras extraÃ­das
        """
        logger.info(f"[FROM-RAW] Carregando extraÃ§Ãµes de: {raw_path}")
        raw_extractions = self.load_raw_extractions(raw_path)
        
        self.rules = self.convert_raw_to_rules(raw_extractions)
        logger.info(f"[FROM-RAW] {len(self.rules)} regras convertidas")
        return self.rules

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    #  MÃ©todos internos
    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_pdf_text(self) -> str:
        """Extrai texto cru do PDF."""
        if pdfplumber is None:
            logger.error("pdfplumber nao instalado. Nao foi possivel extrair texto do PDF.")
            return ""

        page_texts: List[str] = []
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                pages_config = self.config.get('pages_to_extract', None)
                if pages_config and '-' in pages_config:
                    start, end = map(int, pages_config.split('-'))
                    pages = pdf.pages[start - 1:end]
                else:
                    pages = pdf.pages

                for page in pages:
                    page_text = page.extract_text()
                    if page_text:
                        page_texts.append(page_text)
        except Exception as e:
            logger.error(f"Erro ao extrair texto do PDF: {e}")

        text = f"\n{self._PAGE_BREAK_MARKER}\n".join(page_texts)

        # Remove caracteres Unicode n?o-imprim?veis
        text = re.sub(r'[^\x20-\x7E\u00A0-\u00FF\u0100-\u024F\t\n\r]', ' ', text)
        text = re.sub(r'[^\S\n]+', ' ', text)

        return text

    def _split_text_into_chunks(self, text: str, pages_per_chunk: int = 3) -> List[str]:
        """
        Divide o texto em chunks menores para evitar respostas truncadas do LLM.
        """
        max_chunk_chars = int(self.config.get("llm_max_chunk_chars", 12000))

        if self._PAGE_BREAK_MARKER in text:
            pages = [p.strip() for p in text.split(self._PAGE_BREAK_MARKER) if p.strip()]
        else:
            pages = [p.strip() for p in text.split('\n\n') if p.strip()]

        chunks: List[str] = []
        step = max(int(pages_per_chunk), 1)
        for i in range(0, len(pages), step):
            chunk = '\n\n'.join(pages[i:i + step]).strip()
            if not chunk:
                continue

            if len(chunk) <= max_chunk_chars:
                chunks.append(chunk)
                continue

            start = 0
            while start < len(chunk):
                end = min(start + max_chunk_chars, len(chunk))
                if end < len(chunk):
                    newline_pos = chunk.rfind('\n', start, end)
                    if newline_pos > start + 200:
                        end = newline_pos
                piece = chunk[start:end].strip()
                if piece:
                    chunks.append(piece)
                start = end

        logger.info(f"Texto dividido em {len(chunks)} chunks ({len(pages)} blocos, {step} por chunk)")
        return chunks

    def _build_prompt_and_schema(self) -> Dict[str, Any]:
        """Retorna prompt base e schema JSON esperado pelo Gemini."""
        prompt = textwrap.dedent("""\
            Analise o texto do protocolo de profilaxia cirurgica.
            Extraia regras de antibiotico para cada cirurgia identificada.

            Regras:
            1. Ignore cabecalhos, rodapes, titulos institucionais e linhas sem recomendacao clinica.
            2. Para cada cirurgia, gere um item com:
               - extraction_class: sempre "regra_cirurgia"
               - extraction_text: nome da cirurgia como aparece no texto
               - attributes.surgery_name: lista de nomes equivalentes
               - attributes.surgery_type: categoria de contaminacao (ex: Limpa, Limpa-contaminada, Contaminada, Infectada)
               - attributes.antibiotics: lista de objetos com name, dose, route e time
               - attributes.notes: observacoes complementares (opcional)
            3. Se algum campo nao estiver claro, retorne string vazia nesse campo.
            4. Retorne somente JSON valido, sem markdown e sem texto adicional.
        """)

        response_schema: Dict[str, Any] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "extraction_class": {"type": "string"},
                    "extraction_text": {"type": "string"},
                    "attributes": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "surgery_name": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "surgery_type": {"type": "string"},
                            "antibiotics": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "dose": {"type": "string"},
                                        "route": {"type": "string"},
                                        "time": {"type": "string"},
                                    },
                                    "required": ["name", "dose", "route", "time"],
                                },
                            },
                            "notes": {"type": "string"},
                        },
                        "required": ["surgery_name", "surgery_type", "antibiotics", "notes"],
                    },
                },
                "required": ["extraction_class", "extraction_text", "attributes"],
            },
        }

        return {"prompt": prompt, "response_schema": response_schema}

    def _build_langextract_prompt_and_examples(self) -> Dict[str, Any]:
        """Retorna prompt e exemplos few-shot para o backend langextract."""
        prompt_description = textwrap.dedent("""\
            Extraia regras de profilaxia antimicrobiana cirurgica do texto.
            Crie uma extracao para cada cirurgia/procedimento com recomendacao.

            Campos obrigatorios em attributes:
            - surgery_name: lista de nomes equivalentes do procedimento
            - surgery_type: classificacao (Limpa, Limpa-contaminada, Contaminada, Infectada, Suja/Infectada)
            - antibiotic_names: lista de nomes de antibioticos na mesma ordem das doses/rotas/tempos
            - antibiotic_doses: lista de doses correspondentes (ex: 2g, 900mg)
            - antibiotic_routes: lista de vias correspondentes (ex: EV, IV)
            - antibiotic_times: lista de tempos correspondentes (ex: na inducao, 30 min antes)
            - notes: observacoes complementares

            Regras:
            - extraction_class deve ser sempre "regra_cirurgia".
            - extraction_text deve ser o nome exato do procedimento no texto.
            - Ignore cabecalhos, rodapes e metadados administrativos.
            - Quando nao houver antibiotico recomendado, retorne listas vazias.
            - Quando algum campo nao existir, use string vazia.
        """)

        if ExampleData is None or Extraction is None:
            return {"prompt_description": prompt_description, "examples": []}

        examples = [
            ExampleData(
                text=(
                    "Colecistectomia laparoscopica limpa-contaminada: Cefazolina 2g EV "
                    "na inducao. Em alergia, Clindamicina 900mg EV na inducao."
                ),
                extractions=[
                    Extraction(
                        extraction_class="regra_cirurgia",
                        extraction_text="Colecistectomia laparoscopica",
                        attributes={
                            "surgery_name": ["Colecistectomia laparoscopica"],
                            "surgery_type": "Limpa-contaminada",
                            "antibiotic_names": ["Cefazolina", "Clindamicina"],
                            "antibiotic_doses": ["2g", "900mg"],
                            "antibiotic_routes": ["EV", "EV"],
                            "antibiotic_times": ["na inducao", "na inducao"],
                            "notes": "",
                        },
                    )
                ],
            ),
            ExampleData(
                text=(
                    "Parotidectomia sem implantes (cirurgia limpa): nao recomendado "
                    "profilaxia antimicrobiana."
                ),
                extractions=[
                    Extraction(
                        extraction_class="regra_cirurgia",
                        extraction_text="Parotidectomia sem implantes",
                        attributes={
                            "surgery_name": ["Parotidectomia sem implantes"],
                            "surgery_type": "Limpa",
                            "antibiotic_names": [],
                            "antibiotic_doses": [],
                            "antibiotic_routes": [],
                            "antibiotic_times": [],
                            "notes": "Nao recomendado",
                        },
                    )
                ],
            ),
        ]

        return {"prompt_description": prompt_description, "examples": examples}

    def _coerce_attr_list(self, value: Any, split_delimited: bool = False) -> List[str]:
        """Normaliza atributo string/list para lista de strings limpas."""
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return []
            if split_delimited and (";" in cleaned or "|" in cleaned):
                return [part.strip() for part in re.split(r"[;|]", cleaned) if part.strip()]
            return [cleaned]
        return []

    def _build_antibiotics_from_flat_attributes(self, attrs: Dict[str, Any]) -> List[Dict[str, str]]:
        """Converte atributos flat do langextract em lista padrao de antibioticos."""
        names = self._coerce_attr_list(attrs.get("antibiotic_names"), split_delimited=True)
        doses = self._coerce_attr_list(attrs.get("antibiotic_doses"), split_delimited=True)
        routes = self._coerce_attr_list(attrs.get("antibiotic_routes"), split_delimited=True)
        times = self._coerce_attr_list(attrs.get("antibiotic_times"), split_delimited=True)

        # Compatibilidade com eventuais respostas em "antibiotics"
        raw_antibiotics = attrs.get("antibiotics")
        if not names:
            if isinstance(raw_antibiotics, list):
                for item in raw_antibiotics:
                    if isinstance(item, str) and item.strip():
                        names.append(item.strip())
            elif isinstance(raw_antibiotics, str):
                names = self._coerce_attr_list(raw_antibiotics, split_delimited=True)

        antibiotics: List[Dict[str, str]] = []
        for name, dose, route, time_text in zip_longest(names, doses, routes, times, fillvalue=""):
            entry = {
                "name": (name or "").strip(),
                "dose": (dose or "").strip(),
                "route": (route or "").strip(),
                "time": (time_text or "").strip(),
            }
            if any(entry.values()):
                antibiotics.append(entry)

        return antibiotics

    def _normalize_langextract_extractions(self, extractions: List[Any]) -> List[Dict[str, Any]]:
        """Converte saida do langextract para o formato bruto interno."""
        normalized: List[Dict[str, Any]] = []

        for item in extractions:
            if isinstance(item, dict):
                extraction_class = str(item.get("extraction_class") or "regra_cirurgia").strip()
                extraction_text = str(item.get("extraction_text") or "").strip()
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
            else:
                extraction_class = str(getattr(item, "extraction_class", "regra_cirurgia") or "regra_cirurgia").strip()
                extraction_text = str(getattr(item, "extraction_text", "") or "").strip()
                attrs = getattr(item, "attributes", {}) or {}
                if not isinstance(attrs, dict):
                    attrs = {}

            surgery_names = self._coerce_attr_list(attrs.get("surgery_name"))
            if not surgery_names and extraction_text:
                surgery_names = [extraction_text]

            normalized.append(
                {
                    "extraction_class": extraction_class or "regra_cirurgia",
                    "extraction_text": extraction_text or (surgery_names[0] if surgery_names else ""),
                    "attributes": {
                        "surgery_name": surgery_names,
                        "surgery_type": str(attrs.get("surgery_type") or "").strip(),
                        "antibiotics": self._build_antibiotics_from_flat_attributes(attrs),
                        "notes": str(attrs.get("notes") or "").strip(),
                    },
                }
            )

        return normalized

    def _extract_with_langextract(self, text: str) -> List[Dict[str, Any]]:
        """Executa extracao usando a biblioteca langextract."""
        if lx is None:
            logger.error("Biblioteca 'langextract' nao encontrada.")
            return []

        if not api_key:
            logger.error("API key nao encontrada para backend langextract.")
            return []

        payload = self._build_langextract_prompt_and_examples()
        prompt_description = payload["prompt_description"]
        examples = payload["examples"]

        if not examples:
            logger.error("Nao foi possivel montar exemplos few-shot para langextract.")
            return []

        try:
            pages_per_chunk = int(self.config.get("llm_pages_per_chunk", 3))
            chunks = self._split_text_into_chunks(text, pages_per_chunk=pages_per_chunk)
            max_retries = int(self.config.get("langextract_max_retries", 2))
            all_raw_extractions: List[Dict[str, Any]] = []

            logger.info(f"Extraindo regras com backend langextract... ({len(chunks)} chunks)")
            for idx, chunk in enumerate(chunks):
                chunk_extractions: List[Any] = []
                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(
                            f"[Langextract] Chunk {idx+1}/{len(chunks)} tentativa {attempt}/{max_retries}"
                        )
                        result = lx.extract(
                            text_or_documents=chunk,
                            prompt_description=prompt_description,
                            examples=examples,
                            model_id=self.langextract_model,
                            api_key=api_key,
                            max_char_buffer=int(self.config.get("llm_max_chunk_chars", 12000)),
                            temperature=0,
                            batch_length=int(self.config.get("langextract_batch_length", 4)),
                            max_workers=int(self.config.get("langextract_max_workers", 4)),
                            extraction_passes=int(self.config.get("langextract_extraction_passes", 1)),
                            use_schema_constraints=True,
                            fetch_urls=False,
                            show_progress=False,
                        )

                        documents = result if isinstance(result, list) else [result]
                        for document in documents:
                            doc_extractions = getattr(document, "extractions", None)
                            if isinstance(doc_extractions, list):
                                chunk_extractions.extend(doc_extractions)

                        if chunk_extractions:
                            break
                    except Exception as chunk_exc:
                        logger.warning(
                            f"[Langextract] Chunk {idx+1}/{len(chunks)} tentativa {attempt} falhou: {chunk_exc}"
                        )
                        if attempt < max_retries:
                            time.sleep(attempt)

                normalized_chunk = self._normalize_langextract_extractions(chunk_extractions)
                all_raw_extractions.extend(normalized_chunk)
                logger.info(
                    f"[Langextract] Chunk {idx+1}/{len(chunks)}: {len(normalized_chunk)} extracoes (total: {len(all_raw_extractions)})"
                )

            logger.info(f"Extracao langextract concluida: {len(all_raw_extractions)} extracoes")
            return all_raw_extractions
        except Exception as exc:
            logger.error(f"Falha no backend langextract: {exc}", exc_info=True)
            return []

    def _extract_with_gemini(self, text: str) -> List[Dict[str, Any]]:
        """Executa extracao usando cliente Gemini direto."""
        llm_payload = self._build_prompt_and_schema()
        prompt = llm_payload["prompt"]
        response_schema = llm_payload["response_schema"]
        pages_per_chunk = self.config.get("llm_pages_per_chunk", 3)
        chunks = self._split_text_into_chunks(text, pages_per_chunk=pages_per_chunk)
        
        all_raw_extractions = []
        
        logger.info(f"Extraindo regras com backend gemini... ({len(chunks)} chunks)")
        for i, chunk in enumerate(chunks):
            raw = self._extract_chunk(chunk, i, len(chunks), prompt, response_schema)
            all_raw_extractions.extend(raw)
            logger.info(f"[Gemini] Chunk {i+1}/{len(chunks)}: {len(raw)} extracoes (total: {len(all_raw_extractions)})")
        
        logger.info(f"Extracao total gemini: {len(all_raw_extractions)} extracoes de {len(chunks)} chunks")
        return all_raw_extractions

    def _build_chunk_prompt(self, prompt: str, chunk_text: str, chunk_idx: int, total_chunks: int) -> str:
        return textwrap.dedent(f"""\
            {prompt}

            CHUNK_ATUAL: {chunk_idx + 1}/{total_chunks}
            TEXTO_DO_CHUNK:
            <<<INICIO_CHUNK>>>
            {chunk_text}
            <<<FIM_CHUNK>>>
        """)

    def _load_json_payload(self, payload_text: str) -> Optional[Any]:
        try:
            return json.loads(payload_text)
        except json.JSONDecodeError:
            cleaned = payload_text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                logger.warning(f"Nao foi possivel parsear JSON do Gemini: {exc}")
                return None

    def _normalize_raw_extractions(self, response: Any) -> List[Dict[str, Any]]:
        payload = getattr(response, "parsed", None)
        if payload is None:
            response_text = (getattr(response, "text", "") or "").strip()
            if not response_text:
                return []
            payload = self._load_json_payload(response_text)
            if payload is None:
                return []

        if isinstance(payload, dict):
            payload = payload.get("extractions", [payload])

        if not isinstance(payload, list):
            logger.warning(f"Formato inesperado de resposta Gemini: {type(payload)}")
            return []

        normalized: List[Dict[str, Any]] = []

        for item in payload:
            if not isinstance(item, dict):
                continue

            attrs = item.get("attributes")
            if not isinstance(attrs, dict):
                attrs = {}

            surgery_names_raw = attrs.get("surgery_name", [])
            if isinstance(surgery_names_raw, str):
                surgery_names = [surgery_names_raw.strip()] if surgery_names_raw.strip() else []
            elif isinstance(surgery_names_raw, list):
                surgery_names = [str(name).strip() for name in surgery_names_raw if str(name).strip()]
            else:
                surgery_names = []

            antibiotics_raw = attrs.get("antibiotics", [])
            if isinstance(antibiotics_raw, (str, dict)):
                antibiotics_raw = [antibiotics_raw]
            elif not isinstance(antibiotics_raw, list):
                antibiotics_raw = []

            antibiotics: List[Dict[str, str]] = []
            for antibiotic in antibiotics_raw:
                if isinstance(antibiotic, str):
                    name = antibiotic.strip()
                    if name:
                        antibiotics.append({"name": name, "dose": "", "route": "", "time": ""})
                    continue

                if not isinstance(antibiotic, dict):
                    continue

                antibiotics.append(
                    {
                        "name": str(antibiotic.get("name") or "").strip(),
                        "dose": str(antibiotic.get("dose") or "").strip(),
                        "route": str(antibiotic.get("route") or "").strip(),
                        "time": str(antibiotic.get("time") or "").strip(),
                    }
                )

            extraction_text = str(item.get("extraction_text") or "").strip()
            if not extraction_text and surgery_names:
                extraction_text = surgery_names[0]

            normalized.append(
                {
                    "extraction_class": str(item.get("extraction_class") or "regra_cirurgia").strip() or "regra_cirurgia",
                    "extraction_text": extraction_text,
                    "attributes": {
                        "surgery_name": surgery_names,
                        "surgery_type": str(attrs.get("surgery_type") or "").strip(),
                        "antibiotics": antibiotics,
                        "notes": str(attrs.get("notes") or "").strip(),
                    },
                }
            )

        return normalized

    def _extract_chunk(
        self,
        chunk_text: str,
        chunk_idx: int,
        total_chunks: int,
        prompt: str,
        response_schema: Dict[str, Any],
        max_retries: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Extrai de um unico chunk usando Gemini direto com resposta JSON.
        """
        if not self._gemini_client:
            logger.error("Gemini client indisponivel. Defina GOOGLE_API_KEY, GEMINI_API_KEY ou API_KEY_GOOGLE_AI_STUDIO.")
            return []

        if not isinstance(response_schema, dict):
            logger.error("Schema de resposta JSON invalido para extracao do Gemini.")
            return []

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[Chunk {chunk_idx+1}/{total_chunks}] Tentativa {attempt}/{max_retries} ({len(chunk_text)} chars)")
                chunk_prompt = self._build_chunk_prompt(prompt, chunk_text, chunk_idx, total_chunks)
                response = self._gemini_client.models.generate_content(
                    model=self.gemini_model,
                    contents=chunk_prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_json_schema=response_schema,
                        max_output_tokens=self.config.get("gemini_max_output_tokens", 8192),
                    ),
                )

                raw = self._normalize_raw_extractions(response)
                if raw:
                    logger.info(f"[Chunk {chunk_idx+1}/{total_chunks}] OK {len(raw)} extracoes encontradas")
                    return raw

                logger.warning(f"[Chunk {chunk_idx+1}/{total_chunks}] Nenhuma extracao no resultado")

            except Exception as e:
                logger.warning(f"[Chunk {chunk_idx+1}/{total_chunks}] Tentativa {attempt} falhou: {e}")
                if attempt < max_retries:
                    time.sleep(2 * attempt)

        logger.error(f"[Chunk {chunk_idx+1}/{total_chunks}] Falhou apos {max_retries} tentativas")
        return []

    def extract_raw_from_text(self, text: str) -> List[Dict[str, Any]]:

        """
        Chama o LLM em chunks e retorna resultado bruto como lista de dicts.
        Divide o texto em pedaÃ§os menores para evitar respostas truncadas.
        """
        if self.llm_backend == "langextract":
            raw = self._extract_with_langextract(text)
            if raw:
                return raw
            logger.warning("Backend langextract retornou 0 extracoes. Tentando fallback com Gemini.")

        return self._extract_with_gemini(text)

    def save_raw_extractions(self, raw_extractions: List[Dict], output_path: Path) -> None:
        """Salva extraÃ§Ãµes brutas em JSON para revisÃ£o."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(raw_extractions, f, ensure_ascii=False, indent=2)

    def load_raw_extractions(self, input_path: Path) -> List[Dict]:
        """Carrega extraÃ§Ãµes brutas de JSON."""
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def convert_raw_to_rules(self, raw_extractions: List[Dict]) -> List[ProtocolRule]:
        """
        Converte lista de dicts brutos (do LLM) para objetos ProtocolRule.
        """
        rules = []
        
        for idx, entry in enumerate(raw_extractions):
            attrs = entry.get("attributes", {})
            
            antibiotics_raw = attrs.get("antibiotics", [])
            antibiotics_objs: List[AntibioticRule] = []
            for ab in antibiotics_raw:
                if isinstance(ab, dict):
                    antibiotics_objs.append(
                        AntibioticRule(
                            name=ab.get("name", ""),
                            dose=ab.get("dose", ""),
                            route=ab.get("route", ""),
                            time=ab.get("time", ""),
                        )
                    )
                elif isinstance(ab, str):
                    antibiotics_objs.append(
                        AntibioticRule(name=ab.strip(), dose="", route="", time="")
                    )
                else:
                    logger.warning(
                        f"Formato inesperado de antibiotico ignorado: {type(ab)} -> {ab}"
                    )
            
            s_type_str = attrs.get("surgery_type", "").upper().replace("-", "_")
            try:
                surgery_enum = SurgeryType[s_type_str]
            except KeyError:
                normalization_map = {
                    "LIMPA": SurgeryType.CLEAN,
                    "LIMPA_CONTAMINADA": SurgeryType.CLEAN_CONTAMINATED,
                    "CONTAMINADA": SurgeryType.CONTAMINATED,
                    "INFECTADA": SurgeryType.INFECTED,
                    "SUJA": SurgeryType.DIRTY,
                    "SUJA_INFECTADA": SurgeryType.DIRTY,
                }
                surgery_enum = normalization_map.get(
                    s_type_str, SurgeryType.CLEAN_CONTAMINATED
                )
            
            surgery_names_raw = attrs.get("surgery_name", [])
            if isinstance(surgery_names_raw, str):
                surgery_names = [surgery_names_raw.strip()] if surgery_names_raw.strip() else []
            elif isinstance(surgery_names_raw, list):
                surgery_names = [
                    str(name).strip() for name in surgery_names_raw if str(name).strip()
                ]
            else:
                surgery_names = []

            extraction_text = str(entry.get("extraction_text") or "").strip()
            procedure = surgery_names[0] if surgery_names else extraction_text
            notes = str(attrs.get("notes") or "").strip()

            notes_norm = normalize_text(notes)
            is_prophylaxis_required = bool(antibiotics_objs)
            if "nao recomendado" in notes_norm or "sem profilaxia" in notes_norm:
                is_prophylaxis_required = False

            primary_drugs = [
                Drug(
                    name=ab.name,
                    dose=ab.dose or None,
                    route=ab.route or None,
                    timing=ab.time or None,
                )
                for ab in antibiotics_objs
            ]

            if antibiotics_objs:
                audit_category = "OK"
            elif is_prophylaxis_required:
                audit_category = "REQUIRES_VALIDATION"
            else:
                audit_category = "NO_PROPHYLAXIS"
            
            rule = ProtocolRule(
                rule_id=f"llm_rule_{idx:04d}",
                section=s_type_str or "NAO_CLASSIFICADO",
                procedure=procedure,
                procedure_normalized=normalize_text(procedure),
                is_prophylaxis_required=is_prophylaxis_required,
                primary_recommendation=Recommendation(
                    drugs=primary_drugs,
                    raw_text=extraction_text,
                    notes=notes,
                ),
                audit_category=audit_category,
                metadata={"source": "llm", "backend": self.llm_backend},
                surgery_name=surgery_names,
                surgery_type=surgery_enum,
                antibiotics=antibiotics_objs,
                notes=notes,
            )
            rules.append(rule)

        return rules

    def _extract_tables(self) -> List[pd.DataFrame]:
        """
        Extrai tabelas do PDF usando mÃºltiplas estratÃ©gias.
        
        Returns:
            Lista de DataFrames
        """
        if camelot is None:
            logger.warning("Camelot nao instalado. Extracao tabular foi desabilitada.")
            return []

        pages = self.config.get('pages_to_extract', '8-35')
        
        tables = []
        
        # EstratÃ©gia 1: Camelot lattice (tabelas com bordas)
        lattice_tables = None
        try:
            logger.debug("Tentando extraÃ§Ã£o com Camelot (lattice)")
            lattice_tables = camelot.read_pdf(
                str(self.pdf_path),
                pages=pages,
                flavor='lattice',
                line_scale=self.config.get('camelot_lattice_line_scale', 40),
                line_tol=self.config.get('camelot_lattice_line_tol', 2),
                joint_tol=self.config.get('camelot_lattice_joint_tol', 2),
                process_background=self.config.get('camelot_lattice_process_background', False),
            )
            
            for table in lattice_tables:
                df = table.df
                if len(df) >= self.config.get('min_table_rows', 2):
                    tables.append(df)
            
            logger.debug(f"Camelot lattice (config): {len(tables)} tabelas")
        except Exception as e:
            logger.warning(f"Erro na extraÃ§Ã£o com Camelot lattice: {e}")
            lattice_tables = None

        # Fallback: lattice sem parÃ¢metros avanÃ§ados (compatibilidade)
        if lattice_tables is None or len(tables) == 0:
            try:
                logger.debug("Tentando extraÃ§Ã£o com Camelot (lattice) sem parÃ¢metros avanÃ§ados")
                lattice_tables = camelot.read_pdf(
                    str(self.pdf_path),
                    pages=pages,
                    flavor='lattice',
                    line_scale=self.config.get('camelot_lattice_line_scale', 40),
                    line_tol=self.config.get('camelot_lattice_line_tol', 2),
                    joint_tol=self.config.get('camelot_lattice_joint_tol', 2),
                    process_background=self.config.get('camelot_lattice_process_background', False),
                )
                
                for table in lattice_tables:
                    df = table.df
                    if len(df) >= self.config.get('min_table_rows', 2):
                        tables.append(df)
                
                logger.debug(f"Camelot lattice (fallback): {len(tables)} tabelas")
            except Exception as e:
                logger.warning(f"Erro na extraÃ§Ã£o com Camelot lattice (fallback): {e}")
        
        # EstratÃ©gia 2: Camelot stream (tabelas sem bordas completas)
        try:
            logger.debug("Tentando extraÃ§Ã£o com Camelot (stream)")
            camelot_tables = camelot.read_pdf(
                str(self.pdf_path),
                pages=pages,
                flavor='stream',
                edge_tol=self.config.get('camelot_stream_edge_tol', 50),
                row_tol=self.config.get('camelot_stream_row_tol', 10),
                column_tol=self.config.get('camelot_stream_column_tol', 10),
            )
            
            for table in camelot_tables:
                df = table.df
                if len(df) >= self.config.get('min_table_rows', 2):
                    # Verifica se jÃ¡ nÃ£o temos tabela similar
                    if not self._is_duplicate_table(df, tables):
                        tables.append(df)
                        
            logger.debug(f"Total apÃ³s Camelot stream: {len(tables)} tabelas")
        except Exception as e:
            logger.warning(f"Erro na extraÃ§Ã£o com Camelot stream: {e}")
        
        return tables
    
    def _is_duplicate_table(self, df: pd.DataFrame, existing_tables: List[pd.DataFrame]) -> bool:
        """
        Verifica se uma tabela jÃ¡ existe na lista.
        
        Args:
            df: DataFrame a verificar
            existing_tables: Lista de tabelas existentes
            
        Returns:
            True se Ã© duplicata
        """
        for existing_df in existing_tables:
            if df.shape == existing_df.shape:
                # Compara primeiras cÃ©lulas
                if df.iloc[0, 0] == existing_df.iloc[0, 0]:
                    return True
        return False

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove linhas repetidas de cabeÃ§alho no meio do DataFrame.
        
        Args:
            df: DataFrame original
            
        Returns:
            DataFrame limpo
        """
        if df is None or df.empty:
            return df
        
        header_keywords = {
            'procedimento',
            'procedimentos',
            'cirurgia',
            '1a opcao',
            'alergia',
            'pos operatorio',
        }

        doc_keywords = {
            'titulo do documento',
            'codigo',
            'pagina',
            'versao',
            'data da emissao',
            'protocolo',
            'profilaxia antimicrobiana',
            'hospital mater dei',
        }
        
        header_row = [normalize_text(str(c)) for c in df.iloc[0].tolist()]
        indices_to_drop = []
        first_index = df.index[0]
        
        for idx, row in df.iterrows():
            row_norm = [normalize_text(str(c)) for c in row.tolist()]
            
            if row_norm == header_row:
                indices_to_drop.append(idx)
                continue
            
            keyword_hits = sum(1 for cell in row_norm if cell in header_keywords)
            if keyword_hits >= 2:
                indices_to_drop.append(idx)
                continue

            row_text = ' '.join(row_norm)
            if any(keyword in row_text for keyword in doc_keywords):
                indices_to_drop.append(idx)
        
        if indices_to_drop:
            df = df.drop(index=indices_to_drop).reset_index(drop=True)
        
        return df
    
    def _process_table(self, df: pd.DataFrame, table_index: int) -> List[ProtocolRule]:
        """
        Processa uma tabela e extrai regras.
        
        Args:
            df: DataFrame da tabela
            table_index: Ãndice da tabela
            
        Returns:
            Lista de regras extraÃ­das
        """
        rules = []

        # Limpa cabeÃƒÂ§alhos repetidos no meio da tabela
        df = self._clean_dataframe(df)
        
        # Detecta seÃ§Ã£o da tabela
        section = self._detect_section(df)
        
        # Processa cada linha da tabela
        for idx, row in df.iterrows():
            try:
                rule = self._parse_row_to_rule(row, section, table_index, idx)
                if rule:
                    rules.append(rule)
            except Exception as e:
                logger.warning(f"Erro ao processar linha {idx} da tabela {table_index}: {e}")
        
        return rules
    
    def _detect_section(self, df: pd.DataFrame) -> str:
        """
        Detecta a seÃ§Ã£o/categoria da tabela.
        
        Args:
            df: DataFrame da tabela
            
        Returns:
            Nome da seÃ§Ã£o
        """
        # Procura por palavras-chave nas primeiras linhas
        keywords = {
            'CABEÃ‡A E PESCOÃ‡O': ['cabeca', 'pescoco'],
            'CIRURGIA CARDIOVASCULAR': ['cardiovascular', 'cardiaca'],
            'CIRURGIA GERAL': ['cirurgia geral', 'abdomen'],
            'GINECOLOGIA': ['ginecologia', 'ginecologica'],
            'NEUROCIRURGIA': ['neurocirurgia', 'neurocirug'],
            'OFTALMOLOGIA': ['oftalmologia', 'oftalmo'],
            'ORTOPEDIA': ['ortopedia', 'ortopedica'],
            'OTORRINOLARINGOLOGIA': ['otorrino', 'orl'],
            'UROLOGIA': ['urologia', 'urologica'],
        }
        
        # Examina primeiras 3 linhas
        text = ' '.join([str(cell) for row in df.head(3).values for cell in row])
        text_norm = normalize_text(text)
        
        for section_name, section_keywords in keywords.items():
            for keyword in section_keywords:
                if keyword in text_norm:
                    return section_name
        
        return "OUTROS"
    
    def _parse_row_to_rule(self, row: pd.Series, section: str, 
                          table_index: int, row_index: int) -> Optional[ProtocolRule]:
        """
        Parseia uma linha da tabela para uma regra do protocolo.
        
        Args:
            row: SÃ©rie pandas representando a linha
            section: SeÃ§Ã£o da tabela
            table_index: Ãndice da tabela
            row_index: Ãndice da linha
            
        Returns:
            ProtocolRule ou None se invÃ¡lida
        """
        # Extrai dados bÃ¡sicos (assume formato padrÃ£o do protocolo)
        # Colunas esperadas: Procedimento | 1Âª OpÃ§Ã£o | Alergia | PÃ³s-operatÃ³rio
        
        if len(row) < 3:
            return None
        
        procedure = str(row.iloc[0]).strip()
        # Remove bullets e normaliza espaÃƒÂ§os
        procedure = re.sub(r'[\u2022\u2023\u25E6\u2043\u2219\uF0A0]+', ' ', procedure)
        procedure = re.sub(r'\s+', ' ', procedure).strip()
        
        # Ignora linhas de cabeÃ§alho ou vazias
        if not procedure or len(procedure) < 3:
            return None
        procedure_norm = normalize_text(procedure)
        if procedure_norm in ['procedimento', 'cirurgia', '']:
            return None
        if ('procedimento' in procedure_norm or 'procedimentos' in procedure_norm) and (
            'opcao' in procedure_norm or 'alergia' in procedure_norm
        ):
            return None
        if any(
            phrase in procedure_norm
            for phrase in [
                'titulo do documento',
                'profilaxia antimicrobiana',
                'hospital mater dei',
                'codigo',
                'pagina',
            ]
        ):
            return None
        
        # RecomendaÃ§Ã£o primÃ¡ria
        primary_text = str(row.iloc[1]).strip() if len(row) > 1 else ""
        
        # RecomendaÃ§Ã£o para alergia
        allergy_text = str(row.iloc[2]).strip() if len(row) > 2 else ""
        
        # PÃ³s-operatÃ³rio
        postop = str(row.iloc[3]).strip() if len(row) > 3 else ""

        # Ignora linhas sem recomendaÃ§Ãµes
        if not primary_text and not allergy_text and not postop:
            return None
        
        # Verifica se requer profilaxia
        is_prophylaxis_required = self._requires_prophylaxis(primary_text)
        
        # Parseia recomendaÃ§Ãµes
        primary_rec = self._parse_recommendation(primary_text)
        allergy_rec = self._parse_recommendation(allergy_text)
        
        # Gera ID Ãºnico
        rule_id = f"rule_{section}_{table_index}_{row_index}"
        
        # Normaliza nome do procedimento
        procedure_norm = normalize_text(procedure)
        section_norm = normalize_text(section)
        if procedure_norm in [section_norm, f"cirurgia de {section_norm}", f"cirurgia {section_norm}"]:
            return None
        
        # Cria regra
        rule = ProtocolRule(
            rule_id=rule_id,
            section=section,
            procedure=procedure,
            procedure_normalized=procedure_norm,
            is_prophylaxis_required=is_prophylaxis_required,
            primary_recommendation=primary_rec,
            allergy_recommendation=allergy_rec,
            postoperative=postop,
            audit_category=self._categorize_rule(primary_rec, allergy_rec),
            original_row_index=int(row_index),
        )
        
        return rule
    
    def _requires_prophylaxis(self, text: str) -> bool:
        """
        Determina se o texto indica que profilaxia Ã© requerida.
        
        Args:
            text: Texto da recomendaÃ§Ã£o
            
        Returns:
            True se profilaxia Ã© requerida
        """
        text_norm = normalize_text(text)
        
        negative_patterns = [
            'nao recomendado',
            'sem profilaxia',
            'dispensavel',
            'desnecessario',
        ]
        
        for pattern in negative_patterns:
            if pattern in text_norm:
                return False
        
        # Se menciona medicamento, provavelmente requer
        if extract_drug_names(text, DRUG_DICTIONARY):
            return True
        
        return True  # Default: requer
    
    def _parse_recommendation(self, text: str) -> Recommendation:
        """
        Parseia texto de recomendaÃ§Ã£o em objeto Recommendation.
        
        Args:
            text: Texto da recomendaÃ§Ã£o
            
        Returns:
            Objeto Recommendation
        """
        if not text or len(text) < 3:
            return Recommendation(raw_text=text)
        
        # Extrai medicamentos
        drug_names = extract_drug_names(text, DRUG_DICTIONARY)
        
        # Cria objetos Drug
        drugs = []
        for drug_name in drug_names:
            # Tenta extrair dose do texto
            dose = self._extract_dose_from_context(text, drug_name)
            
            drug = Drug(
                name=drug_name,
                dose=dose,
                route='IV',  # Assume IV como padrÃ£o
            )
            drugs.append(drug)
        
        return Recommendation(
            drugs=drugs,
            raw_text=text,
        )
    
    def _extract_dose_from_context(self, text: str, drug_name: str) -> Optional[str]:
        """
        Extrai dose do contexto em torno do nome do medicamento.
        
        Args:
            text: Texto completo
            drug_name: Nome do medicamento
            
        Returns:
            Texto da dose ou None
        """
        # Procura primeiro por padrÃµes de dose ponderal (mg/kg)
        mgkg_pattern = r'(\d+(?:\.\d+)?\s*(?:mg|g)\s*/\s*kg)'
        mgkg_match = re.search(mgkg_pattern, text, re.IGNORECASE)
        if mgkg_match:
            return mgkg_match.group(1)

        # Procura por padrÃ£o de dose prÃ³ximo ao medicamento
        # Ex: "Cefazolina 2g" ou "2g de Cefazolina"
        pattern = r'(\d+(?:\.\d+)?\s*(?:g|mg|mcg))'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            return matches[0]
        
        return None
    
    def _categorize_rule(self, primary: Recommendation, allergy: Recommendation) -> str:
        """
        Categoriza a regra para auditoria.
        
        Args:
            primary: RecomendaÃ§Ã£o primÃ¡ria
            allergy: RecomendaÃ§Ã£o para alergia
            
        Returns:
            Categoria da regra
        """
        if not primary.drugs:
            return "REQUIRES_VALIDATION"
        
        if not allergy.drugs:
            return "REQUIRES_VALIDATION"
        
        return "OK"
    
    def _deduplicate_rules(self, rules: List[ProtocolRule]) -> List[ProtocolRule]:
        """
        Remove regras duplicadas.
        
        Args:
            rules: Lista de regras
            
        Returns:
            Lista sem duplicatas
        """
        seen = set()
        unique_rules = []
        
        for rule in rules:
            # Usa procedimento normalizado como chave
            key = rule.procedure_normalized
            
            if key and key not in seen:
                seen.add(key)
                unique_rules.append(rule)
        
        return unique_rules
    
    def save_rules(self, output_dir: Path) -> None:
        """
        Salva regras extraÃ­das em arquivos.
        
        Args:
            output_dir: DiretÃ³rio de saÃ­da
        """
        if not self.rules:
            logger.warning("Nenhuma regra para salvar")
            return
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cria repositÃ³rio e salva
        repo = ProtocolRulesRepository()
        repo.rules = self.rules
        repo._build_index()
        repo.save_to_json(output_dir / 'rules.json')
        
        logger.info(f"Regras salvas em: {output_dir}")
    
    def get_validation_report(self) -> Dict[str, Any]:
        """
        Gera relatÃ³rio de validaÃ§Ã£o das regras extraÃ­das.
        
        Returns:
            DicionÃ¡rio com estatÃ­sticas de validaÃ§Ã£o
        """
        total = len(self.rules)
        
        with_prophylaxis = sum(1 for r in self.rules if r.is_prophylaxis_required)
        without_prophylaxis = total - with_prophylaxis
        
        needs_validation = sum(1 for r in self.rules if r.audit_category == "REQUIRES_VALIDATION")
        
        with_primary_drugs = sum(1 for r in self.rules if r.primary_recommendation.drugs)
        with_allergy_drugs = sum(1 for r in self.rules if r.allergy_recommendation.drugs)
        
        sections = {}
        for rule in self.rules:
            sections[rule.section] = sections.get(rule.section, 0) + 1
        
        return {
            'total_rules': total,
            'with_prophylaxis': with_prophylaxis,
            'without_prophylaxis': without_prophylaxis,
            'needs_validation': needs_validation,
            'with_primary_drugs': with_primary_drugs,
            'with_allergy_drugs': with_allergy_drugs,
            'sections': sections,
        }

