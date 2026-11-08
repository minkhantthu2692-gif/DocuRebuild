from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.models import Project
from app.db.session import get_db
from app.services.projects import get_project

DbSession = Annotated[Session, Depends(get_db)]


def project_dependency(project_id: str, session: DbSession) -> Project:
    return get_project(session, project_id)


ProjectDep = Annotated[Project, Depends(project_dependency)]
