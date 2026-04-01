from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional, List
from sqlalchemy.orm import Session

from server_db.connection import get_db
from guidance.GuidanceService import GuidanceService, GuidanceNotFoundError
from guidance.schemas import (
    GuidanceUpsert,
    GuidanceUpdate,
    GuidanceResponse,
    GuidanceListResponse,
)
from guidance.models import Priority

router = APIRouter(prefix="/api/guidance", tags=["Guidance"])

def get_guidance_service(db: Session = Depends(get_db)) -> GuidanceService:
    return GuidanceService(db)

@router.put("", response_model=GuidanceResponse, status_code=200)
def upsert_guidance(
    payload: GuidanceUpsert,
    service: GuidanceService = Depends(get_guidance_service)
):
    """Create or update a Guidance record by natural key (metric_name, priority, purpose)."""
    record, created = service.upsert(payload)
    return record

@router.get("", response_model=GuidanceListResponse)
def list_guidance(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    priority: Optional[Priority] = None,
    metric_name: Optional[str] = None,
    purpose: Optional[str] = Query(None),
    service: GuidanceService = Depends(get_guidance_service)
):
    """List and filter Guidance records."""
    return service.list(
        skip=skip, limit=limit, priority=priority,
        metric_name=metric_name, purpose=purpose
    )

@router.get("/summary/stats")
def get_guidance_summary(service: GuidanceService = Depends(get_guidance_service)):
    """Get count of guidance records per priority level."""
    return service.summarize_by_priority()

def _pick_priority(priority: Optional[Priority], severity: Optional[Priority]) -> Priority:
    """
    Backwards-compatible helper: accept either `priority` (preferred) or
    `severity` (legacy test/query param) and return the chosen value.
    """
    chosen = priority or severity
    if not chosen:
        raise HTTPException(
            status_code=422,
            detail="Query parameter 'priority' (or legacy 'severity') is required",
        )
    return chosen


@router.get("/by-key", response_model=GuidanceResponse)
def get_guidance_by_natural_key(
    metric_name: str = Query(...),
    priority: Optional[Priority] = Query(None),
    severity: Optional[Priority] = Query(
        None, description="Alias for priority (legacy clients)"
    ),
    purpose: str = Query("general"),
    service: GuidanceService = Depends(get_guidance_service),
):
    """Get a Guidance record by its natural key (metric_name, priority, purpose)."""
    effective_priority = _pick_priority(priority, severity)
    try:
        return service.get_by_natural_key(metric_name, effective_priority, purpose)
    except GuidanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/{guidance_id}", response_model=GuidanceResponse)
def get_guidance_by_id(
    guidance_id: int = Path(...),
    service: GuidanceService = Depends(get_guidance_service)
):
    """Get a Guidance record by its ID."""
    try:
        return service.get_by_id(guidance_id)
    except GuidanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.patch("/{guidance_id}", response_model=GuidanceResponse)
def update_guidance(
    payload: GuidanceUpdate,
    guidance_id: int = Path(...),
    service: GuidanceService = Depends(get_guidance_service)
):
    """Partially update a Guidance record by its ID."""
    try:
        return service.update_by_id(guidance_id, payload)
    except GuidanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/{guidance_id}")
def delete_guidance(
    guidance_id: int = Path(...),
    service: GuidanceService = Depends(get_guidance_service)
):
    """Delete a Guidance record by its ID."""
    try:
        return service.delete_by_id(guidance_id)
    except GuidanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/by-key/steps")
def get_guidance_steps(
    metric_name: str = Query(...),
    priority: Optional[Priority] = Query(None),
    severity: Optional[Priority] = Query(
        None, description="Alias for priority (legacy clients)"
    ),
    purpose: str = Query("general"),
    service: GuidanceService = Depends(get_guidance_service),
):
    """Get only the resolution steps for a given natural key (metric_name, priority, purpose)."""
    effective_priority = _pick_priority(priority, severity)
    try:
        return {"steps": service.get_resolution_steps(metric_name, effective_priority, purpose)}
    except GuidanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
