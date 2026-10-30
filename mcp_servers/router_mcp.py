"""MCP Router Server module.

Uses local Ollama model (configured in config.json) to classify documents and route queries dynamically across 3 distinct knowledge bases.
"""

from typing import Any
import json
import os
import re
import httpx
from ollama import AsyncClient

BASE_DIR = os.path.expanduser("~/Desktop/ark")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def get_active_model() -> str:
    """Read active model from config.json, defaulting to qwen3:8b if missing."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ai", {}).get("active_model", "qwen3:8b")
        except Exception:
            pass
    return "qwen3:8b"


async def classify_document(
    file_name: str, file_content_preview: str
) -> dict[str, Any]:
    """Analyze document name and text preview to classify into 3 main categories."""
    active_model = get_active_model()

    prompt = (
        f"You are a document classifier for a modular RAG system.\n"
        f"Filename: {file_name}\n"
        f"Preview: {file_content_preview[:400]}\n\n"
        f"Task: Classify this document into one of these categories:\n"
        f"1. 'university' (for lectures, academic papers, notes, study materials)\n"
        f"2. 'code' (for programming scripts, code documentation, technical repositories)\n"
        f"3. 'relationship' (for chat logs, Sima conversations, personal messages, relationship notes)\n"
        f'Output ONLY valid raw JSON with format: {{"category": "university"}} or {{"category": "code"}} or {{"category": "relationship"}}'
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model": active_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
                timeout=15.0,
            )
            if response.status_code == 200:
                raw_response = response.json().get("response", "").strip()
                clean_text = re.sub(
                    r"<think>.*?</think>", "", raw_response, flags=re.DOTALL
                ).strip()
                if "```" in clean_text:
                    clean_text = re.sub(
                        r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", clean_text
                    ).strip()

                parsed = json.loads(clean_text)
                print(f"[MCP ROUTER] Successfully classified '{file_name}': {parsed}")
                return parsed
    except Exception as e:
        print(f"[MCP ROUTER ERROR] Classification failed: {e}")

    # Heuristic Fallback
    lower_name = file_name.lower()
    if any(
        kw in lower_name
        for kw in ["whatsapp", "chat", "sohbet", "mesaj", "relationship"]
    ):
        cat = "relationship"
    elif any(
        kw in lower_name for kw in ["py", "go", "js", "code", "script", "sdk", "api"]
    ):
        cat = "code"
    else:
        cat = "university"
    return {"category": cat}


async def route_query_intent(query_text: str) -> str:
    """Determine semantically which of the 3 database tables the query belongs to."""
    active_model = get_active_model()
    client = AsyncClient(host="[http://127.0.0.1:11434](http://127.0.0.1:11434)")

    prompt = f"""
You are an intelligent RAG database router. Based on the user query, decide which database table to search.

Available Tables:
1. "relationship_knowledge_base" -> Chat logs with Sima, personal memories, dialogues, relationship notes.
2. "university_knowledge_base" -> University lectures, PDF notes, academic theories, books, assignments.
3. "code_knowledge_base" -> Source code, Go/Python projects, technical architecture, code documentation.
4. "all" -> General queries or questions spanning multiple domains.

User Query: "{query_text}"

Please respond ONLY in the following JSON format:
{{"target_table": "relationship_knowledge_base"}} or {{"target_table": "university_knowledge_base"}} or {{"target_table": "code_knowledge_base"}} or {{"target_table": "all"}}
"""

    try:
        response = await client.chat(
            model=active_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1, "num_predict": 50},
        )
        content = response.get("message", {}).get("content", "").strip()
        clean_content = re.sub(
            r"<think>.*?</think>", "", content, flags=re.DOTALL
        ).strip()
        if "```" in clean_content:
            clean_content = re.sub(
                r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", clean_content
            ).strip()

        if "{" in clean_content and "}" in clean_content:
            json_str = clean_content[
                clean_content.find("{") : clean_content.rfind("}") + 1
            ]
            data = json.loads(json_str)
            target = data.get("target_table", "all")
            print(f"[MCP ROUTER] Query intent target mapped -> '{target}'")
            return target
    except Exception as e:
        print(f"[MCP ROUTER ERROR] Query routing failed: {e}")

    # Heuristic Fallback
    query_lower = query_text.lower()
    if any(
        kw in query_lower
        for kw in [
            "sima",
            "whatsapp",
            "sohbet",
            "mesaj",
            "konuşma",
            "relationship",
            "ilişki",
        ]
    ):
        return "relationship_knowledge_base"
    if any(
        kw in query_lower
        for kw in ["kod", "python", "go", "fonksiyon", "script", "hata", "sdk"]
    ):
        return "code_knowledge_base"
    if any(
        kw in query_lower
        for kw in ["ders", "üniversite", "pdf", "not", "akademik", "teori"]
    ):
        return "university_knowledge_base"

    return "all"
