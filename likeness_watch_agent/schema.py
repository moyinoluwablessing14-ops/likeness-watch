"""
Structured output schema for Likeness Watch reports. Kept as plain Pydantic
models (not wired via ADK's output_schema) because output_schema + tools on
the same agent is still an unreliable combination in current ADK — see
https://github.com/google/adk-python/issues/3969. Instead, the final tool
call builds and validates this object directly in Python, guaranteeing
well-formed JSON every time regardless of what the LLM does.
"""

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


class Citation(BaseModel):
    url: str
    title: str
    excerpt: str


class Finding(BaseModel):
    claim: str = Field(description="The product/endorsement claim found for this person")
    source: Citation
    scam_pattern_matched: bool


class RiskReport(BaseModel):
    talent_name: str
    risk_flag: Literal["red", "yellow", "green"]
    reason: str
    recommended_action: str
    findings: list[Finding] = Field(default_factory=list)
    victim_reports: list[Citation] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
