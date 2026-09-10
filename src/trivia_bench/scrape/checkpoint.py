"""Etat de reprise du scraping, sauvegarde apres chaque lot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class CategoryState(BaseModel):
    """Avancement d'une categorie."""

    expected: int = 0
    received: int = 0
    calls: int = 0
    done: bool = False


class Checkpoint(BaseModel):
    """Etat complet d'une session de scraping."""

    token: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    categories: dict[str, CategoryState] = Field(default_factory=dict)

    def state(self, category_id: int) -> CategoryState:
        return self.categories.setdefault(str(category_id), CategoryState())

    @classmethod
    def load(cls, path: Path) -> Checkpoint:
        """Charge un checkpoint existant, ou en cree un neuf."""
        if path.exists():
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        return cls()

    def save(self, path: Path) -> None:
        """Ecrit le checkpoint de facon atomique."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.model_dump(mode="json"), indent=2), encoding="utf-8")
        tmp.replace(path)

    @property
    def total_received(self) -> int:
        return sum(state.received for state in self.categories.values())
