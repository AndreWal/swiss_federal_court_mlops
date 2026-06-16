from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from constants import SCD_COLUMNS


class LlmClassification(BaseModel):
    area_detailed: str | None = None
    area_intermediate: str | None = None
    area_general: str | None = None
    app_class: str | None = None
    resp_class: str | None = None
    outcome: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None


class AnnotationRecord(BaseModel):
    docref: str | None = None
    url: str | None = None
    date: str | None = None
    year: int | None = None
    proc_type: str | None = None
    merged_cases: bool | None = None
    division: str | None = None
    division_type: str | None = None
    n_judges: int | None = None
    language: str | None = None
    length: int | None = None
    area_general: str | None = None
    area_intermediate: str | None = None
    area_detailed: str | None = None
    topic: str | None = None
    issue: str | None = None
    source_date: str | None = None
    source_canton: str | None = None
    proc_duration: int | None = None
    app_class: str | None = None
    app_represented: bool | None = None
    resp_class: str | None = None
    resp_represented: bool | None = None
    outcome: str | None = None
    outcome_binary: bool | None = None
    cited_bger: str | None = None
    n_cited_bger: int | None = None
    cited_bge: str | None = None
    n_cited_bge: int | None = None
    leading_case: str | None = None
    doi_version: str

    html_id: str
    raw_html_path: str
    annotation_version: str
    model_name: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    judge_names: list[str] = Field(default_factory=list)

    def scd_row(self) -> dict[str, Any]:
        return {column: getattr(self, column) for column in SCD_COLUMNS}
