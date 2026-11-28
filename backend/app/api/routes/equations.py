from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ProjectDep
from app.schemas.equations import PageEquationProposalsOut
from app.services import projects as project_service
from app.services import regions as region_service

router = APIRouter(tags=["equations"])


@router.get(
    "/projects/{project_id}/pages/{page_id}/equation-proposals",
    response_model=PageEquationProposalsOut,
)
def read_page_equation_proposals(
    project: ProjectDep, page_id: str
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return region_service.propose_page_equations(directory, page_id)
