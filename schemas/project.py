from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.project import ProjectStatus


class CreatorSetupRequest(BaseModel):
    channel_url: Optional[str] = Field(None, max_length=500)
    niche: str = Field(..., min_length=2, max_length=200)
    tone: str = Field(..., min_length=2, max_length=100)
    target_audience: str = Field(..., min_length=2, max_length=300)
    goal: str = Field(..., min_length=2, max_length=300)
    video_style: str = Field(..., min_length=2, max_length=100)
    intended_duration: str = Field(..., min_length=1, max_length=50)
    title: Optional[str] = Field(None, max_length=200)

    @field_validator("niche", "tone", "target_audience", "goal", "video_style", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class ProjectResponse(BaseModel):
    id: str
    title: Optional[str]
    status: ProjectStatus
    channel_url: Optional[str]
    niche: Optional[str]
    tone: Optional[str]
    target_audience: Optional[str]
    goal: Optional[str]
    video_style: Optional[str]
    intended_duration: Optional[str]
    selected_idea_id: Optional[str]
    selected_idea_title: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    latest_review_id: Optional[str] = None
    latest_review_score: Optional[float] = None

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int
