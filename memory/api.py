"""Management API facade for ARK persistent memory operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from memory.service import MemoryService


class MemoryManagementAPI:
    """Facade exposing memory management operations for application integrations."""

    def __init__(self, db_path: str | Path | None = None):
        self.service = MemoryService(db_path=db_path)

    def create(self, **payload: Any) -> str:
        return self.service.create_memory(**payload)

    def read(self, record_id: str, *, domain: str) -> dict[str, Any] | None:
        return self.service.get_memory(record_id, domain=domain)

    def update(self, record_id: str, *, domain: str, **payload: Any) -> bool:
        return self.service.update_memory(record_id, domain=domain, **payload)

    def delete(self, record_id: str, *, domain: str, permanent: bool = False) -> bool:
        return self.service.delete_memory(record_id, domain=domain, permanent=permanent)

    def search(self, **filters: Any) -> list[dict[str, Any]]:
        return self.service.search_memories(**filters)

    def list(self, *, domain: str, **filters: Any) -> dict[str, Any]:
        return self.service.list_memories(domain=domain, **filters)

    def export(self, *, domain: str, fmt: str = "json") -> str:
        return self.service.export_memories(domain=domain, fmt=fmt)

    def import_data(
        self, *, domain: str, payload: str, fmt: str = "json", allow_overwrite: bool = False
    ) -> dict[str, int]:
        return self.service.import_memories(
            domain=domain,
            payload=payload,
            fmt=fmt,
            allow_overwrite=allow_overwrite,
        )

    def stats(self, *, domain: str | None = None) -> dict[str, Any]:
        return self.service.get_memory_stats(domain=domain)

    def health(self) -> dict[str, Any]:
        return self.service.health()
