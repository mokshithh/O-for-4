from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from core.database import Base


class ProjectStatus(str, enum.Enum):
    setup = "setup"
    ideas_generated = "ideas_generated"
    idea_selected = "idea_selected"
    questions_answered = "questions_answered"
    script_generated = "script_generated"
    video_submitted = "video_submitted"
    review_complete = "review_complete"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    status = Column(SAEnum(ProjectStatus), default=ProjectStatus.setup)

    # Creator setup
    channel_url = Column(String, nullable=True)
    niche = Column(String, nullable=True)
    tone = Column(String, nullable=True)
    target_audience = Column(String, nullable=True)
    goal = Column(String, nullable=True)
    video_style = Column(String, nullable=True)
    intended_duration = Column(String, nullable=True)

    # Selected idea
    selected_idea_id = Column(String, nullable=True)
    selected_idea_title = Column(String, nullable=True)
    selected_idea_explanation = Column(String, nullable=True)

    # Personalization answers (JSON map of question->answer)
    personalization_answers = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="projects")
    ideas = relationship("IdeaOption", back_populates="project", cascade="all, delete-orphan")
    scripts = relationship("Script", back_populates="project", cascade="all, delete-orphan")
    reviews = relationship("VideoReview", back_populates="project", cascade="all, delete-orphan")
