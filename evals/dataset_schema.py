"""Pydantic models for the golden evaluation dataset."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

Category = Literal["standard", "niche", "broad", "edge_case", "agency"]
Tool = Literal["freehire", "duckduckgo"]

DEFAULT_DATASET_PATH = Path(__file__).parent / "golden_dataset.json"


class GoldenQuery(BaseModel):
    id: str = Field(min_length=1)
    query: str
    category: Category
    description: str = Field(min_length=1)
    expected_tools: List[Tool] = Field(default_factory=list)
    min_jobs: int = Field(default=0, ge=0)
    relevance_keywords: List[str] = Field(default_factory=list)
    expect_agency_flag: bool = False
    expect_failure: bool = False
    cv_path: Optional[str] = None  # None means a query-only run (no --cv)


class GoldenDataset(BaseModel):
    version: str
    queries: List[GoldenQuery]

    @model_validator(mode="after")
    def _unique_ids(self) -> "GoldenDataset":
        dupes = [i for i, n in Counter(q.id for q in self.queries).items() if n > 1]
        if dupes:
            raise ValueError(f"Duplicate query ids: {dupes}")
        return self

    def by_category(self) -> Dict[str, List[GoldenQuery]]:
        grouped: Dict[str, List[GoldenQuery]] = {}
        for q in self.queries:
            grouped.setdefault(q.category, []).append(q)
        return grouped


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> GoldenDataset:
    return GoldenDataset.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
