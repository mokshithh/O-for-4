from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ScriptSegment(BaseModel):
    title: str
    content: str
    duration_estimate: Optional[str] = None


class ScriptBrainPrediction(BaseModel):
    trend_match_score: float          # 0-100
    audience_fit_score: float         # 0-100
    hook_strength_score: float        # 0-100
    retention_risk_score: float       # 0-100 (higher = more risk)
    format_confidence_score: float    # 0-100
    novelty_score: float              # 0-100
    predicted_retention_drops: List[str]   # segment labels with drop risk
    summary: str


class ScriptResponse(BaseModel):
    id: str
    project_id: str
    version: float
    title: Optional[str]
    hook: Optional[str]
    full_script: str
    segment_outline: Optional[List[Dict[str, Any]]]
    cta: Optional[str]
    pacing_notes: Optional[str]
    trend_match_score: Optional[float]
    trend_match_explanation: Optional[str]
    brain_prediction: Optional[Dict[str, Any]]
    user_edited_content: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ScriptEditRequest(BaseModel):
    edited_content: str


class ScriptRevisionRequest(BaseModel):
    revision_instructions: str
