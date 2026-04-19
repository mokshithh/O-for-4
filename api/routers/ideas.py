from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.project import Project, ProjectStatus
from models.script import IdeaOption
from schemas.ideas import (
    IdeasGeneratedResponse, IdeaOptionResponse, SelectIdeaRequest,
    PersonalizationQuestionsResponse, PersonalizationAnswersRequest,
)
from services.idea_service import generate_ideas, PERSONALIZATION_QUESTIONS

router = APIRouter(prefix="/projects/{project_id}/ideas", tags=["ideas"])


def _get_project(project_id: str, user_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/generate", response_model=IdeasGeneratedResponse)
def generate_project_ideas(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)
    try:
        ideas = generate_ideas(project, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Idea generation failed: {exc}")
    return IdeasGeneratedResponse(
        project_id=project_id,
        ideas=[IdeaOptionResponse.model_validate(i) for i in ideas],
    )


@router.get("", response_model=IdeasGeneratedResponse)
def list_project_ideas(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    ideas = db.query(IdeaOption).filter(IdeaOption.project_id == project_id).order_by(IdeaOption.rank).all()
    return IdeasGeneratedResponse(
        project_id=project_id,
        ideas=[IdeaOptionResponse.model_validate(i) for i in ideas],
    )


@router.post("/select", response_model=PersonalizationQuestionsResponse)
def select_idea(
    project_id: str,
    body: SelectIdeaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)
    idea = db.query(IdeaOption).filter(IdeaOption.id == body.idea_id, IdeaOption.project_id == project_id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    project.selected_idea_id = idea.id
    project.selected_idea_title = idea.title
    project.selected_idea_explanation = idea.explanation
    project.status = ProjectStatus.idea_selected
    db.commit()
    db.refresh(project)

    return PersonalizationQuestionsResponse(
        project_id=project_id,
        selected_idea=IdeaOptionResponse.model_validate(idea),
        questions=PERSONALIZATION_QUESTIONS,
    )


@router.post("/personalize")
def submit_personalization(
    project_id: str,
    body: PersonalizationAnswersRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)
    if not project.selected_idea_id:
        raise HTTPException(status_code=400, detail="No idea selected yet — call /select first")

    project.personalization_answers = body.answers
    project.status = ProjectStatus.questions_answered
    db.commit()
    return {"project_id": project_id, "status": "questions_answered", "message": "Ready to generate script"}
