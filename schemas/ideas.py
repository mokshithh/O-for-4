from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime


class IdeaOptionResponse(BaseModel):
    id: str
    rank: float
    title: str
    hook: Optional[str]
    explanation: Optional[str]
    trend_alignment: Optional[str]
    dataset_signals: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class IdeasGeneratedResponse(BaseModel):
    project_id: str
    ideas: List[IdeaOptionResponse]


class SelectIdeaRequest(BaseModel):
    idea_id: str


class PersonalizationQuestionsResponse(BaseModel):
    project_id: str
    selected_idea: IdeaOptionResponse
    questions: List[Dict[str, str]]  # [{id, question, hint}]


class PersonalizationAnswersRequest(BaseModel):
    answers: Dict[str, str]  # {question_id: answer}
