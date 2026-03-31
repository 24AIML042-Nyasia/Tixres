"""
slas/alert_services.py
----------------------
SLA policy: timing constants (cooldown, auto-resolution windows) and helpers.

What lives here
---------------
* Cooldown windows per severity — how long to suppress duplicate notifications.
* Auto-resolution windows per severity — how long a ticket/alert may be stale
  before ResolutionService closes it.
* Helper functions: compute actual datetimes from the above.

What does NOT live here
-----------------------
* Ticket / Alert status values   — those are WorkflowStatus DB rows (workflows app).
* Django model field choices      — no choices= constraints on status fields;
  WorkflowService.get_ticket_status_choices() / get_alert_status_choices()
  provide runtime choices when needed (e.g. serialisation, admin UI).
* Severity level lists            — severity is a free-form string; teams may use
  P1/P2/P3/P4, Critical/High/Medium/Low, or anything else.  The SLA dicts below
  define timing for known severity strings and fall back to a sensible default.
"""

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# SLA timing — cooldown windows per severity (minutes)
# ---------------------------------------------------------------------------
# How long to suppress re-notification after an alert fires.
# Add or override entries to adjust per-severity policy.
COOLDOWN_MINUTES: dict[str, int] = {
    "P1":       10,
    "P2":       15,
    "P3":       30,
    "P4":       30,
    "P0":       30,
    "Critical": 5,
    "High":     15,
    "Medium":   30,
    "Low":      60,
}

# ---------------------------------------------------------------------------
# SLA timing — auto-resolution windows per severity (hours)
# ---------------------------------------------------------------------------
# If no new ticket activity is seen for this duration since last_seen_at,
# ResolutionService will close the alert and its related tickets.
RESOLUTION_HOURS: dict[str, int] = {
    "P1":       2,
    "P2":       6,
    "P3":       12,
    "P4":       24,
    "P0":       24,
    "Critical": 1,
    "High":     6,
    "Medium":   12,
    "Low":      24,
}

# ---------------------------------------------------------------------------
# Severities that never create / update alerts
# ---------------------------------------------------------------------------
# Extend this set if your team uses different low-priority severity labels.
IGNORED_SEVERITIES: set[str] = {"P4", "P0", "Low"}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def do_ignore_ticket_by_severity(severity: str) -> bool:
    """Return True for severities that should never generate alerts."""
    return severity in IGNORED_SEVERITIES


def get_resolution_window(severity: str) -> timedelta:
    """
    Return the silence window after which a stale alert is auto-resolved.
    Falls back to 24 h for unknown severity strings.
    """
    hours = RESOLUTION_HOURS.get(severity, 24)
    return timedelta(hours=hours)


def compute_cooldown(severity: str) -> datetime:
    """
    Return the UTC datetime until which notifications should be suppressed.
    Falls back to 30 min for unknown severity strings.
    """
    minutes = COOLDOWN_MINUTES.get(severity, 30)
    return datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)



# ---------------------------------------------------------------------------
# Ticket statuses
# ---------------------------------------------------------------------------
# These drive the Ticket.status field choices and all status-check logic.
# Add new statuses here; the model picks them up via get_ticket_status_choices().

TICKET_STATUS_OPEN   = "OPEN"
TICKET_STATUS_ACK    = "ACK"
TICKET_STATUS_CLOSED = "CLOSED"

# Ordered lifecycle — used for validation and display
TICKET_STATUSES: list[str] = [
    TICKET_STATUS_OPEN,
    TICKET_STATUS_ACK,
    TICKET_STATUS_CLOSED,
]

# Statuses that auto-resolution is allowed to close
TICKET_AUTO_RESOLVABLE_STATUSES: set[str] = {TICKET_STATUS_OPEN, TICKET_STATUS_ACK}

# ---------------------------------------------------------------------------
# Alert statuses
# ---------------------------------------------------------------------------

ALERT_STATUS_OPEN   = "OPEN"
ALERT_STATUS_ACK    = "ACK"
ALERT_STATUS_CLOSED = "CLOSED"

ALERT_STATUSES: list[str] = [
    ALERT_STATUS_OPEN,
    ALERT_STATUS_ACK,
    ALERT_STATUS_CLOSED,
]

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

SEVERITY_P1 = "P1"
SEVERITY_P2 = "P2"
SEVERITY_P3 = "P3"
SEVERITY_P4 = "P4"
SEVERITY_P0 = "P0"

# Ordered from most to least severe – can be iterated for priority logic
SEVERITIES: list[str] = [SEVERITY_P1, SEVERITY_P2, SEVERITY_P3, SEVERITY_P4, SEVERITY_P0]

# Severities that never create/update alerts
IGNORED_SEVERITIES: set[str] = {SEVERITY_P4, SEVERITY_P0}

# ---------------------------------------------------------------------------
# Django model field helper: returns choices tuples from the canonical lists
# ---------------------------------------------------------------------------

def get_ticket_status_choices() -> list[tuple[str, str]]:
    """Django field choices for Ticket.status, derived from TICKET_STATUSES."""
    labels = {
        TICKET_STATUS_OPEN:   "Open",
        TICKET_STATUS_ACK:    "Acknowledged",
        TICKET_STATUS_CLOSED: "Closed",
    }
    return [(s, labels.get(s, s.title())) for s in TICKET_STATUSES]


def get_alert_status_choices() -> list[tuple[str, str]]:
    """Django field choices for Alert.status, derived from ALERT_STATUSES."""
    labels = {
        ALERT_STATUS_OPEN:   "Open",
        ALERT_STATUS_ACK:    "Acknowledged",
        ALERT_STATUS_CLOSED: "Closed",
    }
    return [(s, labels.get(s, s.title())) for s in ALERT_STATUSES]


def get_severity_choices() -> list[tuple[str, str]]:
    """Django field choices for severity fields, derived from SEVERITIES."""
    return [(s, s) for s in SEVERITIES]

# ---------------------------------------------------------------------------
# SLA: cooldown and resolution windows
# ---------------------------------------------------------------------------

# Cooldown windows per severity (minutes) — how long to suppress re-alerts
COOLDOWN_MINUTES: dict[str, int] = {
    SEVERITY_P1: 10,
    SEVERITY_P2: 15,
    SEVERITY_P3: 30,
}

# Automatic resolution windows per severity (hours) — stale after this
RESOLUTION_HOURS: dict[str, int] = {
    SEVERITY_P1: 2,
    SEVERITY_P2: 6,
    SEVERITY_P3: 12,
    SEVERITY_P4: 24,   # kept for completeness; P4/P0 alerts are never created
    SEVERITY_P0: 24,
}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def do_ignore_ticket_by_severity(severity: str) -> bool:
    """Return True for severities that should never create or update alerts (P4, P0)."""
    return severity in IGNORED_SEVERITIES


def get_resolution_window(severity: str) -> timedelta:
    """
    Return the silence window after which an OPEN alert is auto-resolved.

    If no new ticket activity is seen for this duration since last_seen_at,
    ResolutionService will close the alert and its related tickets.
    """
    hours = RESOLUTION_HOURS.get(severity, 24)
    return timedelta(hours=hours)


def compute_cooldown(severity: str) -> datetime:
    """
    Return the datetime until which notifications should be suppressed.

    P1 → 10 min, P2 → 15 min, P3+ → 30 min.
    """
    minutes = COOLDOWN_MINUTES.get(severity, 30)
    return datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
