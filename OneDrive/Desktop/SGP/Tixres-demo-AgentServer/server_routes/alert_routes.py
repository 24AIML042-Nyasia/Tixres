from fastapi import APIRouter, Query, Path, HTTPException, Depends
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from server_db.connection import get_db
from alert_service.models import Alert, ALERT_STATUS_ACK, ALERT_STATUS_OPEN
from alert_service.resolution_service import ResolutionService

router = APIRouter(
    prefix="/api/alerts",
    tags=["Alerts"],
)

# Response Schemas
class AlertResponse(BaseModel):
    id: int
    metric_name: str
    severity: str
    purpose: str
    type: str
    status: str
    agent_ids: str
    total_occurrence: int
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    cooldown_until: Optional[datetime]
    created_at: Optional[datetime]
    closed_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class AckAlertRequest(BaseModel):
    acked_by: str = "resolver"

class AlertListResponse(BaseModel):
    total: int
    items: List[AlertResponse]

class ResolveAlertResponse(BaseModel):
    message: str
    resolved_id: int

@router.get("", response_model=AlertListResponse)
def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, CLOSED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (e.g., P1, P2)"),
    purpose: Optional[str] = Query(None, description="Filter by purpose"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List alerts, optionally filtering by status and severity.
    """
    query = db.query(Alert)
    
    if status is not None:
        query = query.filter(Alert.status == status.upper())
    if severity is not None:
        query = query.filter(Alert.severity == severity.upper())
    if purpose is not None:
        query = query.filter(Alert.purpose == purpose)

    total = query.count()
    items = query.order_by(Alert.last_seen_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": items
    }

@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert_by_id(
    alert_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Get a specific alert by its ID.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert

@router.post("/{alert_id}/resolve", response_model=ResolveAlertResponse)
def resolve_alert_manually(
    alert_id: int = Path(...),
    db: Session = Depends(get_db)
):
    """
    Manually resolve an open alert and close all associated open tickets.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if alert.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Alert is already closed")

    # Manually resolve the alert along with related open tickets
    ResolutionService.resolve_alert(db, alert)
    
    return {
        "message": "Alert resolved successfully",
        "resolved_id": alert.id
    }


@router.patch("/{alert_id}/ack", response_model=ResolveAlertResponse)
def acknowledge_alert_endpoint(
    alert_id: int = Path(...),
    payload: AckAlertRequest = AckAlertRequest(),
    db: Session = Depends(get_db)
):
    """
    Acknowledge an open alert, protecting it from auto-resolution
    and visually marking it as 'investigating'.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    if alert.status == "CLOSED":
        raise HTTPException(status_code=400, detail="Alert is already closed")
        
    if alert.status == ALERT_STATUS_OPEN:
        alert.status = ALERT_STATUS_ACK
        alert.acknowledged_at = datetime.now()
        alert.acknowledged_by = payload.acked_by
        db.commit()
        return {"message": "Alert acknowledged", "resolved_id": alert.id}
    else:
        return {"message": "Alert is already acknowledged", "resolved_id": alert.id}
