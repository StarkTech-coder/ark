"""MCP FileSystem Server module.

Handles secure directory scanning, subfolder categorization (relationship, university, code),
and multi-format file reading including images via local Ollama Vision model.
"""

from typing import Any
import base64
import csv
import glob
import json as json_lib
import os
import docx
import httpx
import pypdf

BASE_DIR = os.path.expanduser("~/Desktop/ark")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def get_vision_model_name() -> str:
    """Read vision model name from config.json dynamically, defaulting to llava if missing."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json_lib.load(f)
                return data.get("ai", {}).get("vision_model", "llava")
        except Exception as e:
            print(f"[CONFIG ERROR] Failed to read vision model from config: {e}")
    return "llava"


def scan_documents_directory(docs_dir: str) -> list[dict[str, str]]:
    """Scan subdirectories (relationship, university, code) inside documents directory.

    Returns a list of dictionaries containing file paths and assigned categories.
    """
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(os.path.join(docs_dir, "relationship"), exist_ok=True)
        os.makedirs(os.path.join(docs_dir, "university"), exist_ok=True)
        os.makedirs(os.path.join(docs_dir, "code"), exist_ok=True)
        return []

    categorized_files = []
    subfolders = {
        "relationship": "relationship",  # Maps to relationship knowledge base table
        "university": "university",
        "code": "code",
    }

    patterns = [
        "*.pdf",
        "*.txt",
        "*.py",
        "*.go",
        "*.md",
        "*.json",
        "*.csv",
        "*.docx",
        "*.jpg",
        "*.jpeg",
        "*.png",
    ]

    for subfolder, category in subfolders.items():
        folder_path = os.path.join(docs_dir, subfolder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path, exist_ok=True)
            continue

        for pattern in patterns:
            found = glob.glob(os.path.join(folder_path, pattern))
            for f_path in found:
                categorized_files.append({"path": f_path, "category": category})

    return categorized_files


def describe_image_locally(image_path: str) -> str:
    """Send image to local Ollama vision model (e.g., llava) to generate a detailed text description."""
    model_name = get_vision_model_name()
    try:
        with open(image_path, "rb") as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode("utf-8")

        response = httpx.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model_name,
                "prompt": (
                    "Describe this image in detail, noting any text, "
                    "playlists, people, or context visible."
                ),
                "images": [encoded_image],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=30.0,
        )
        if response.status_code == 200:
            description = response.json().get("response", "").strip()
            return f"[VISION ANALYSIS / CAPTION]\n{description}"
    except Exception as e:
        print(f"[MCP FS VISION ERROR] Failed to process image {image_path}: {e}")
    return "[Vision analysis unavailable]"


def read_document_content(file_path: str) -> str:
    """Read and extract text content from documents, code files, or describe images locally."""
    file_ext = os.path.splitext(file_path)[1].lower()
    file_content = ""

    try:
        if file_ext == ".pdf":
            reader = pypdf.PdfReader(file_path)
            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    file_content += f"\n[Page {page_idx + 1}]\n" + page_text + "\n\n"

        elif file_ext in [".txt", ".py", ".go", ".md"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                file_content = f.read()

        elif file_ext == ".json":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json_lib.load(f)
                file_content = json_lib.dumps(data, indent=2, ensure_ascii=False)

        elif file_ext == ".csv":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                rows = [", ".join(row) for row in reader]
                file_content = "\n".join(rows)

        elif file_ext == ".docx":
            doc = docx.Document(file_path)
            file_content = "\n".join(
                [para.text for para in doc.paragraphs if para.text.strip()]
            )

        elif file_ext in [".jpg", ".jpeg", ".png"]:
            file_content = describe_image_locally(file_path)

    except Exception as e:
        print(f"[MCP FS ERROR] Failed to read file {file_path}: {e}")

    return file_content
