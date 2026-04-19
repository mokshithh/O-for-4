from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.project import Project, ProjectStatus
from models.review import VideoReview, ReviewStatus
from schemas.project import CreatorSetupRequest, ProjectResponse, ProjectListResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: CreatorSetupRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = Project(
        user_id=current_user.id,
        title=body.title or f"{body.niche} video project",
        channel_url=body.channel_url,
        niche=body.niche,
        tone=body.tone,
        target_audience=body.target_audience,
        goal=body.goal,
        video_style=body.video_style,
        intended_duration=body.intended_duration,
        status=ProjectStatus.setup,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=ProjectListResponse)
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    projects = db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.created_at.desc()).all()

    # Attach latest completed review per project (single query, no N+1)
    project_ids = [p.id for p in projects]
    latest_reviews: dict[str, VideoReview] = {}
    if project_ids:
        reviews = (
            db.query(VideoReview)
            .filter(VideoReview.project_id.in_(project_ids), VideoReview.status == ReviewStatus.complete)
            .order_by(VideoReview.created_at.desc())
            .all()
        )
        for r in reviews:
            if r.project_id not in latest_reviews:
                latest_reviews[r.project_id] = r

    project_responses = []
    for p in projects:
        r = latest_reviews.get(p.id)
        pr = ProjectResponse.model_validate(p)
        pr.latest_review_id = r.id if r else None
        pr.latest_review_score = r.overall_score if r else None
        project_responses.append(pr)

    return ProjectListResponse(projects=project_responses, total=len(project_responses))


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
