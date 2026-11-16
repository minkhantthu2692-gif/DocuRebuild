from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ProjectDep
from app.schemas.tables import TableProposalOut
from app.services import projects as project_service
from app.services import table_structure as table_service

router = APIRouter(tags=["tables"])


@router.get(
    "/projects/{project_id}/pages/{page_id}/ocr/blocks/{block_id}/table-proposal",
    response_model=TableProposalOut,
)
def read_table_proposal(
    project: ProjectDep, page_id: str, block_id: str
) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return table_service.propose_table(directory, page_id, block_id)
