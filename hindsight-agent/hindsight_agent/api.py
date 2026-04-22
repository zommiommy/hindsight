"""Thin Hindsight API client for hindsight-agent."""

from __future__ import annotations

import httpx


class HindsightAPI:
    def __init__(self, api_url: str, timeout: float = 30.0):
        self.base = api_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base, timeout=timeout)

    def _bank_url(self, bank_id: str) -> str:
        return f"/v1/default/banks/{bank_id}"

    # ── Bank ──────────────────────────────────────────────

    def ensure_bank(self, bank_id: str) -> None:
        """Ensure bank exists by checking the banks list, creating via empty retain if needed."""
        r = self.client.get("/v1/default/banks")
        if r.status_code == 200:
            for bank in r.json().get("banks", []):
                if bank.get("bank_id") == bank_id:
                    return
        # Bank doesn't exist — create it with a no-op retain (empty items list triggers bank creation)
        r = self.client.post(
            f"{self._bank_url(bank_id)}/memories",
            json={"items": []},
        )
        # If empty items isn't allowed, the bank should already exist from the GET check
        if r.status_code not in (200, 201, 422):
            r.raise_for_status()

    # ── Retain ────────────────────────────────────────────

    def retain(
        self, bank_id: str, content: str, *, document_id: str | None = None
    ) -> dict:
        """Retain content into a bank (always async)."""
        item: dict = {"content": content}
        if document_id:
            item["document_id"] = document_id
        payload: dict = {"items": [item], "async": True}
        r = self.client.post(
            f"{self._bank_url(bank_id)}/memories",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    # ── Mental Models (pages) ─────────────────────────────

    def list_pages(self, bank_id: str) -> list[dict]:
        r = self.client.get(
            f"{self._bank_url(bank_id)}/mental-models",
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def get_page(self, bank_id: str, page_id: str) -> dict:
        r = self.client.get(
            f"{self._bank_url(bank_id)}/mental-models/{page_id}",
        )
        r.raise_for_status()
        return r.json()

    def create_page(
        self,
        bank_id: str,
        *,
        name: str,
        source_query: str,
        page_id: str | None = None,
    ) -> dict:
        payload: dict = {
            "name": name,
            "source_query": source_query,
            "trigger": {
                "mode": "delta",
                "refresh_after_consolidation": True,
                "exclude_mental_models": True,
            },
        }
        if page_id:
            payload["id"] = page_id
        r = self.client.post(
            f"{self._bank_url(bank_id)}/mental-models",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def update_page(
        self,
        bank_id: str,
        page_id: str,
        *,
        name: str | None = None,
        source_query: str | None = None,
    ) -> dict:
        payload: dict = {}
        if name is not None:
            payload["name"] = name
        if source_query is not None:
            payload["source_query"] = source_query
        r = self.client.patch(
            f"{self._bank_url(bank_id)}/mental-models/{page_id}",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def delete_page(self, bank_id: str, page_id: str) -> None:
        r = self.client.delete(
            f"{self._bank_url(bank_id)}/mental-models/{page_id}",
        )
        r.raise_for_status()

    # ── Recall ────────────────────────────────────────────

    def recall(
        self,
        bank_id: str,
        query: str,
        *,
        max_results: int = 10,
        types: list[str] | None = None,
    ) -> dict:
        """Recall memories from a bank."""
        payload: dict = {"query": query, "max_results": max_results}
        if types:
            payload["types"] = types
        r = self.client.post(
            f"{self._bank_url(bank_id)}/memories/recall",
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    # ── Documents ─────────────────────────────────────────

    def list_documents(self, bank_id: str) -> list[dict]:
        """List documents in a bank."""
        r = self.client.get(f"{self._bank_url(bank_id)}/documents")
        r.raise_for_status()
        return r.json().get("documents", r.json().get("items", []))

    # ── Bank Template ─────────────────────────────────────

    def import_template(self, bank_id: str, template: dict) -> dict:
        """Import a bank template (disposition, mission, directives, etc.)."""
        r = self.client.post(
            f"{self._bank_url(bank_id)}/import",
            json=template,
        )
        r.raise_for_status()
        return r.json()
