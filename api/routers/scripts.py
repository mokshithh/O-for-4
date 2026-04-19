from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.project import Project, ProjectStatus
from models.script import Script, IdeaOption
from schemas.script import ScriptResponse, ScriptEditRequest, ScriptRevisionRequest
from services.script_service import generate_script, revise_script

router = APIRouter(prefix="/projects/{project_id}/scripts", tags=["scripts"])


def _get_project(project_id: str, user_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/generate", response_model=ScriptResponse, status_code=201)
def generate_project_script(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(project_id, current_user.id, db)

    if not project.selected_idea_id:
        raise HTTPException(status_code=400, detail="No idea selected. Complete /ideas/select and /ideas/personalize first.")
    if project.status not in (ProjectStatus.questions_answered, ProjectStatus.script_generated):
        raise HTTPException(status_code=400, detail="Complete personalization questions before generating script.")

    idea = db.query(IdeaOption).filter(IdeaOption.id == project.selected_idea_id).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Selected idea not found")

    try:
        script = generate_script(project, idea, db)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Script generation failed: {exc}")
    return ScriptResponse.model_validate(script)


@router.get("", response_model=List[ScriptResponse])
def list_scripts(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    scripts = db.query(Script).filter(Script.project_id == project_id).order_by(Script.version.desc()).all()
    return [ScriptResponse.model_validate(s) for s in scripts]


@router.get("/active", response_model=ScriptResponse)
def get_active_script(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    script = db.query(Script).filter(Script.project_id == project_id, Script.is_active == True).first()
    if not script:
        raise HTTPException(status_code=404, detail="No active script found")
    return ScriptResponse.model_validate(script)


@router.patch("/{script_id}/edit", response_model=ScriptResponse)
def edit_script(
    project_id: str,
    script_id: str,
    body: ScriptEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    script = db.query(Script).filter(Script.id == script_id, Script.project_id == project_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    script.user_edited_content = body.edited_content
    db.commit()
    db.refresh(script)
    return ScriptResponse.model_validate(script)


@router.post("/{script_id}/revise", response_model=ScriptResponse, status_code=201)
def request_revision(
    project_id: str,
    script_id: str,
    body: ScriptRevisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_project(project_id, current_user.id, db)
    script = db.query(Script).filter(Script.id == script_id, Script.project_id == project_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")

    new_script = revise_script(script, body.revision_instructions, db)
    return ScriptResponse.model_validate(new_script)
