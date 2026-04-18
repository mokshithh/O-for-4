from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Float, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from core.database import Base


class IdeaOption(Base):
    __tablename__ = "idea_options"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    rank = Column(Float, nullable=False)  # 1-5
    title = Column(String, nullable=False)
    hook = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    trend_alignment = Column(Text, nullable=True)
    dataset_signals = Column(JSON, nullable=True)  # stub for dataset backing
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="ideas")


class Script(Base):
    __tablename__ = "scripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    idea_id = Column(String, ForeignKey("idea_options.id"), nullable=True)
    version = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)

    # Script content
    title = Column(String, nullable=True)
    hook = Column(Text, nullable=True)
    full_script = Column(Text, nullable=False)
    segment_outline = Column(JSON, nullable=True)  # [{title, content, duration_estimate}]
    cta = Column(Text, nullable=True)
    pacing_notes = Column(Text, nullable=True)

    # Trend match info
    trend_match_score = Column(Float, nullable=True)
    trend_match_explanation = Column(Text, nullable=True)

    # Script-stage brain prediction
    brain_prediction = Column(JSON, nullable=True)  # ScriptBrainPrediction schema

    # User edits
    user_edited_content = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="scripts")
