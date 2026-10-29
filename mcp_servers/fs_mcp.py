"""
MCP FileSystem Server: Handles secure directory scanning and file reading (PDF & TXT).
"""

import os
import glob


def scan_documents_directory(docs_dir: str) -> list:
    """Scans the documents directory for PDF and TXT files."""
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir, exist_ok=True)
        return []

    pdf_files = glob.glob(os.path.join(docs_dir, "*.pdf"))
    txt_files = glob.glob(os.path.join(docs_dir, "*.txt"))
    return pdf_files + txt_files


def read_document_content(file_path: str) -> str:
    """Reads and extracts text content from a given PDF or TXT file path."""
    file_ext = os.path.splitext(file_path)[1].lower()
    file_content = ""

    try:
        if file_ext == ".pdf":
            import pypdf

            reader = pypdf.PdfReader(file_path)
            for page_idx, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    file_content += f"\n[Page {page_idx + 1}]\n" + page_text + "\n\n"

        elif file_ext == ".txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                file_content = f.read()

    except Exception as e:
        print(f"[MCP FS ERROR] Failed to read file {file_path}: {e}")

    return file_content
