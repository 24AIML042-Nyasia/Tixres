"""
Background Workers
==================
Two long-running workers that drive the alert correlation lifecycle:

Worker 1 — Ticket → Alert Processor  (every 30 s)
  Polls for recently created/updated tickets and feeds them into AlertService.
  P4 tickets are silently skipped inside AlertService.process_ticket.

Worker 2 — Resolution Worker  (every 60 s)
  Scans all OPEN alerts and closes any that have been silent beyond their
  severity-specific resolution window.

Running
-------
Both workers are designed to run concurrently, e.g.:

    import threading
    threading.Thread(target=run_ticket_processor, daemon=True).start()
    threading.Thread(target=run_resolution_worker, daemon=True).start()

Or via any task runner / process supervisor of your choice.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from server_db.connection import SessionLocal  # adjust import to your project
from ticket_service.models import Ticket
from alert_service.alert_service import process_ticket
from alert_service.resolution_service import ResolutionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker 1 — Ticket → Alert Processor
# ---------------------------------------------------------------------------

# How far back to look for "recent" tickets on each poll cycle.
# Should be at least 2× the worker sleep interval to avoid gaps during slow cycles.
_TICKET_POLL_LOOKBACK_SECONDS = 90
_TICKET_WORKER_SLEEP_SECONDS  = 30


def _fetch_recent_tickets(db, since: datetime) -> list[Ticket]:
    """
    Return all tickets whose last_occurred_at falls within the lookback window.

    Using last_occurred_at (rather than created_at) ensures that a merged ticket
    that just gained a new occurrence is re-evaluated by AlertService.
    """
    return (
        db.query(Ticket)
        .filter(Ticket.last_occurred_at >= since)
        .order_by(Ticket.last_occurred_at.asc())
        .all()
    )


def run_ticket_processor() -> None:
    """
    Continuously poll for recent tickets and forward them to AlertService.

    Cycle
    -----
    1. Open a DB session.
    2. Fetch tickets updated in the last `_TICKET_POLL_LOOKBACK_SECONDS` seconds.
    3. For each ticket, call process_ticket (P4 tickets are no-ops inside it).
    4. Close the session.
    5. Sleep for `_TICKET_WORKER_SLEEP_SECONDS` seconds.
    """
    logger.info("Ticket processor started.")

    while True:
        db = SessionLocal()
        try:
            since   = datetime.now() - timedelta(seconds=_TICKET_POLL_LOOKBACK_SECONDS)
            tickets = _fetch_recent_tickets(db, since)

            for ticket in tickets:
                try:
                    alert = process_ticket(db, ticket)
                    if alert is not None:
                        logger.debug(
                            "Ticket %d → Alert %d (%s / %s / %s)",
                            ticket.id, alert.id,
                            alert.type, alert.status, alert.severity,
                        )
                except Exception:
                    logger.exception("Error processing ticket %d", ticket.id)

        except Exception:
            logger.exception("Ticket processor cycle failed.")
        finally:
            db.close()

        time.sleep(_TICKET_WORKER_SLEEP_SECONDS)


# ---------------------------------------------------------------------------
# Worker 2 — Resolution Worker
# ---------------------------------------------------------------------------

_RESOLUTION_WORKER_SLEEP_SECONDS = 60


def run_resolution_worker() -> None:
    """
    Continuously scan OPEN alerts and resolve any that have gone silent.

    Cycle
    -----
    1. Open a DB session.
    2. Call ResolutionService.run_resolution_pass — it checks every OPEN alert
       against its resolution window and closes stale ones.
    3. Log which alert IDs were closed.
    4. Close the session.
    5. Sleep for `_RESOLUTION_WORKER_SLEEP_SECONDS` seconds.
    """
    logger.info("Resolution worker started.")

    while True:
        db = SessionLocal()
        try:
            resolved_ids = ResolutionService.run_resolution_pass(db)
            if resolved_ids:
                logger.info("Resolved alerts: %s", resolved_ids)
        except Exception:
            logger.exception("Resolution worker cycle failed.")
        finally:
            db.close()

        time.sleep(_RESOLUTION_WORKER_SLEEP_SECONDS)
