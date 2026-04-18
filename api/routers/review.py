import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional

from core.database import get_db
from core.security import get_current_user
from core.config import settings
from models.user import User
from models.project import Project, ProjectStatus
from models.review import VideoReview, VideoSource, ReviewStatus
from schemas.review import ReviewResponse, ReviewStatusResponse, VideoSubmitRequest
from services import video_service, review_service

router = APIRouter(prefix="/projects/{project_id}/review", tags=["review"])


def _get_project(project_id: str, user_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/upload", response_model=ReviewStatusResponse, status_code=202)
async def upload_video(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    script_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)

    # Size guard
    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Max {settings.max_upload_size_mb}MB.")

    temp_path = video_service.save_upload(content, file.filename or "upload.mp4")

    review = VideoReview(
        project_id=project_id,
        source=VideoSource.upload,
        original_filename=file.filename,
        script_id=script_id,
        status=ReviewStatus.pending,
    )
    db.add(review)
    project.status = ProjectStatus.video_submitted
    db.commit()
    db.refresh(review)

    background_tasks.add_task(review_service.process_review, review, temp_path, db)

    return ReviewStatusResponse(
        id=review.id,
        status=review.status,
        progress_message="Video received. Processing in background.",
    )


@router.post("/youtube", response_model=ReviewStatusResponse, status_code=202)
async def submit_youtube(
    project_id: str,
    background_tasks: BackgroundTasks,
    body: VideoSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)

    if not body.youtube_url:
        raise HTTPException(status_code=400, detail="youtube_url is required")

    review = VideoReview(
        project_id=project_id,
        source=VideoSource.youtube,
        youtube_url=body.youtube_url,
        script_id=body.script_id,
        status=ReviewStatus.pending,
    )
    db.add(review)
    project.status = ProjectStatus.video_submitted
    db.commit()
    db.refresh(review)

    async def _download_and_process():
        try:
            temp_path = video_service.fetch_youtube(body.youtube_url)
            await review_service.process_review(review, temp_path, db)
        except Exception as exc:
            review.status = ReviewStatus.failed
            review.error_message = str(exc)
            db.commit()

    background_tasks.add_task(_download_and_process)

    return ReviewStatusResponse(
        id=review.id,
        status=review.status,
        progress_message="YouTube link received. Downloading and processing in background.",
    )


@router.get("/{review_id}/status", response_model=ReviewStatusResponse)
def get_review_status(
    project_id: str,
    review_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    review = db.query(VideoReview).filter(VideoReview.id == review_id, VideoReview.project_id == project_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return ReviewStatusResponse(id=review.id, status=review.status)


@router.get("/{review_id}/progress")
def get_review_progress(
    project_id: str,
    review_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns real-time processing log for the brain simulation side panel."""
    _get_project(project_id, current_user.id, db)
    review = db.query(VideoReview).filter(VideoReview.id == review_id, VideoReview.project_id == project_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "id": review.id,
        "status": review.status,
        "processing_log": review.processing_log or [],
        "overall_score": review.overall_score,
        "tribe_used": review.tribe_used,
        "tribe_raw": review.tribe_raw_output,
    }


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(
    project_id: str,
    review_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    review = db.query(VideoReview).filter(VideoReview.id == review_id, VideoReview.project_id == project_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.status != ReviewStatus.complete:
        raise HTTPException(status_code=202, detail=f"Review status: {review.status}")
    return ReviewResponse.model_validate(review)


@router.get("", response_model=list[ReviewResponse])
def list_reviews(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    reviews = db.query(VideoReview).filter(VideoReview.project_id == project_id).order_by(VideoReview.created_at.desc()).all()
    return [ReviewResponse.model_validate(r) for r in reviews]
