from server_db.connection import SessionLocal
from ticket_service.models import Ticket
from datetime import datetime

class TicketService:
    @staticmethod
    def create_ticket(
        agent_id: str,
        metric_name: str,
        severity: str,
        detector: str,
        meta: str,
        message: str
    ):
        db = SessionLocal()
        try:
            ticket = Ticket(
                agent_id=agent_id,
                metric_name=metric_name,
                severity=severity,
                detector=detector,
                meta=meta,
                message=message,
                created_at=datetime.now()
            )
            db.add(ticket)
            db.commit()
        finally:
            db.close()

    @staticmethod
    def get_Tickets(limit=100) -> list:
        db = SessionLocal()
        try:
            tickets = db.query(Ticket).limit(limit).all()
            return [
                {
                    'id': t.id,
                    'agent_id': t.agent_id,
                    'metric_name': t.metric_name,
                    'severity': t.severity,
                    'status': t.status,
                    'detector': t.detector,
                    'meta': t.meta,
                    'message': t.message,
                    'created_at': t.created_at
                }
                for t in tickets
            ]
        finally:
            db.close()