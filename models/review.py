from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Float, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from core.database import Base


class VideoSource(str, enum.Enum):
    upload = "upload"
    youtube = "youtube"


class PerformanceLabel(str, enum.Enum):
    weak = "Weak"
    promising = "Promising"
    strong = "Strong"
    high_potential = "High Potential"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class VideoReview(Base):
    __tablename__ = "video_reviews"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    script_id = Column(String, nullable=True)  # If review follows scripting

    # Video input
    source = Column(SAEnum(VideoSource), nullable=False)
    youtube_url = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)  # Temp only, not stored permanently
    duration_seconds = Column(Float, nullable=True)

    # Processing state
    status = Column(SAEnum(ReviewStatus), default=ReviewStatus.pending)
    transcript = Column(Text, nullable=True)
    error_message = Column(String, nullable=True)

    # Top-level scores (0-100)
    overall_score = Column(Float, nullable=True)
    niche_fit_score = Column(Float, nullable=True)
    retention_potential_score = Column(Float, nullable=True)
    brain_engagement_score = Column(Float, nullable=True)
    virality_potential_score = Column(Float, nullable=True)

    # Performance label
    performance_label = Column(SAEnum(PerformanceLabel), nullable=True)

    # Coaching and explanations
    coaching_feedback = Column(Text, nullable=True)
    score_explanations = Column(JSON, nullable=True)  # {dimension: {score, reasoning, dataset_signal}}
    improvement_suggestions = Column(JSON, nullable=True)  # [str]

    # Script divergence flag
    script_divergence_flagged = Column(Boolean, default=False)
    script_divergence_notes = Column(Text, nullable=True)

    # TRIBE v2 raw output (internal, not exposed directly)
    tribe_raw_output = Column(JSON, nullable=True)
    tribe_used = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="reviews")
    segments = relationship("ReviewSegment", back_populates="review", cascade="all, delete-orphan")


class ReviewSegment(Base):
    __tablename__ = "review_segments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id = Column(String, ForeignKey("video_reviews.id"), nullable=False)

    segment_index = Column(Float, nullable=False)
    label = Column(String, nullable=False)  # e.g. "Hook", "Act 1", "CTA"
    start_seconds = Column(Float, nullable=True)
    end_seconds = Column(Float, nullable=True)
    transcript_excerpt = Column(Text, nullable=True)

    # Segment-level scores
    engagement_score = Column(Float, nullable=True)
    retention_risk = Column(Float, nullable=True)  # 0=low risk, 1=high risk

    # Flags
    is_weak = Column(Boolean, default=False)
    weakness_reason = Column(Text, nullable=True)
    coaching_note = Column(Text, nullable=True)

    # TRIBE attention signal for this segment
    attention_continuity = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship("VideoReview", back_populates="segments")
