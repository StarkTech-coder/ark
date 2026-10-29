"""
MCP Router Server: Uses local Ollama model (configured in config.json) to classify documents and route queries dynamically.
"""

import json
import os
import re
import httpx
from ollama import AsyncClient

BASE_DIR = os.path.expanduser("~/Desktop/ark")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def get_active_model() -> str:
    """Reads active model from config.json, defaults to qwen3:8b if missing."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("ai", {}).get("active_model", "qwen3:8b")
        except Exception:
            pass
    return "qwen3:8b"


async def classify_document(file_name: str, file_content_preview: str) -> dict:
    """Analyzes document name and text preview using the active model from config.json."""
    active_model = get_active_model()

    prompt = (
        f"You are a document classifier.\n"
        f"Filename: {file_name}\n"
        f"Preview: {file_content_preview[:400]}\n\n"
        f"Task: Classify this document.\n"
        f'Output ONLY valid raw JSON with format: {{"category": "academic", "is_academic": true}} or {{"category": "general", "is_academic": false}}'
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
                print(
                    f"[MCP ROUTER] Successfully classified '{file_name}' via '{active_model}': {parsed}"
                )
                return parsed
            else:
                print(
                    f"[MCP ROUTER WARN] Ollama returned HTTP status {response.status_code}"
                )

    except Exception as e:
        print(
            f"[MCP ROUTER ERROR] Classification failed via ({active_model}): {type(e).__name__} {str(e)}"
        )

    # Heuristic Fallback
    lower_name = file_name.lower()
    is_acad = not any(
        kw in lower_name for kw in ["whatsapp", "chat", "sohbet", "mesaj", "gunluk"]
    )
    return {
        "category": "academic" if is_acad else "general",
        "is_academic": is_acad,
    }


async def route_query_intent(query_text: str) -> str:
    """Determines semantically which database table the query belongs to using the Ollama model."""
    active_model = get_active_model()
    client = AsyncClient(host="[http://127.0.0.1:11434](http://127.0.0.1:11434)")

    prompt = f"""
You are an intelligent RAG database router (Query Router).
Based on the user's query, you must decide which database table should be searched.

Available Tables:
1. "ark_knowledge_base" -> Personal chats, WhatsApp logs, daily memories, relationships, personal correspondence, etc.
2. "academic_pdf_kb" -> Academic papers, PDF lecture notes, technical theories, books, manuals, etc.

User Query: "{query_text}"

Please respond ONLY in the following JSON format (write nothing else):
{{"target_table": "ark_knowledge_base"}} or {{"target_table": "academic_pdf_kb"}} or {{"target_table": "both"}}
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
            target = data.get("target_table", "both")
            print(
                f"[MCP ROUTER] Query intent target mapped via '{active_model}' -> '{target}'"
            )
            return target
    except Exception as e:
        print(f"[MCP ROUTER ERROR] Query routing failed via ({active_model}): {e}")

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
            "kavga",
            "günlük",
            "chat",
        ]
    ):
        return "ark_knowledge_base"
    if any(
        kw in query_lower
        for kw in ["fotoğraf", "pdf", "ders", "akademik", "teori", "makale", "not"]
    ):
        return "academic_pdf_kb"

    return "both"
