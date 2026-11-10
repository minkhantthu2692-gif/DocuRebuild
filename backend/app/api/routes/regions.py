from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import ProjectDep
from app.schemas.regions import RegionProposalsOut
from app.services import projects as project_service
from app.services import regions as region_service

router = APIRouter(tags=["elements"])


@router.get(
    "/projects/{project_id}/pages/{page_id}/region-proposals",
    response_model=RegionProposalsOut,
)
def read_region_proposals(project: ProjectDep, page_id: str) -> dict[str, Any]:
    directory = project_service.ensure_project_storage(project)
    return region_service.propose_regions(directory, page_id)
