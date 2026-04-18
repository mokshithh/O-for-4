from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.review import VideoSource, PerformanceLabel, ReviewStatus


class VideoSubmitRequest(BaseModel):
    youtube_url: Optional[str] = None
    script_id: Optional[str] = None  # Link to script if review follows scripting


class ReviewSegmentResponse(BaseModel):
    id: str
    segment_index: float
    label: str
    start_seconds: Optional[float]
    end_seconds: Optional[float]
    transcript_excerpt: Optional[str]
    engagement_score: Optional[float]
    retention_risk: Optional[float]
    is_weak: bool
    weakness_reason: Optional[str]
    coaching_note: Optional[str]
    attention_continuity: Optional[float]

    class Config:
        from_attributes = True


class ScoreDetail(BaseModel):
    score: float
    reasoning: str
    dataset_signal: Optional[str] = None


class ReviewResponse(BaseModel):
    id: str
    project_id: str
    source: VideoSource
    youtube_url: Optional[str]
    duration_seconds: Optional[float]
    status: ReviewStatus
    transcript: Optional[str]

    # Scores
    overall_score: Optional[float]
    niche_fit_score: Optional[float]
    retention_potential_score: Optional[float]
    brain_engagement_score: Optional[float]
    virality_potential_score: Optional[float]
    performance_label: Optional[PerformanceLabel]

    # Feedback
    coaching_feedback: Optional[str]
    score_explanations: Optional[Dict[str, Any]]
    improvement_suggestions: Optional[List[str]]

    # Script divergence
    script_divergence_flagged: bool
    script_divergence_notes: Optional[str]

    # Segments
    segments: List[ReviewSegmentResponse] = []

    tribe_used: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReviewStatusResponse(BaseModel):
    id: str
    status: ReviewStatus
    progress_message: Optional[str] = None
