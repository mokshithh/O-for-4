from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.project import ProjectStatus


class CreatorSetupRequest(BaseModel):
    channel_url: Optional[str] = None
    niche: str
    tone: str
    target_audience: str
    goal: str
    video_style: str
    intended_duration: str
    title: Optional[str] = None


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

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int
