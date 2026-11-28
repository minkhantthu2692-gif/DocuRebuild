from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.api.deps import ProjectDep
from app.schemas.regions import ProjectRegionProposalsOut, RegionProposalsOut
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


@router.get(
    "/projects/{project_id}/region-proposals",
    response_model=ProjectRegionProposalsOut,
)
def read_project_region_proposals(
    project: ProjectDep,
    limit: int = Query(
        region_service.DEFAULT_PROJECT_REVIEW_PAGES,
        ge=1,
        le=region_service.MAX_PROJECT_REVIEW_PAGES,
    ),
    after_page_number: int | None = Query(None, ge=1),
) -> dict[str, Any]:
    """List derived region proposals across pages for read-only review."""
    directory = project_service.ensure_project_storage(project)
    return region_service.propose_project_regions(
        directory,
        limit=limit,
        after_page_number=after_page_number,
    )
