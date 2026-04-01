from datetime import datetime,timedelta
# Cooldown windows per severity (minutes)
_COOLDOWN_MINUTES: dict[str, int] = {
    "P1": 10,
    "P2": 15,
    "P3": 30,
}

# Automatic resolution windows per severity (hours)
_RESOLUTION_HOURS: dict[str, int] = {
    "P1": 2,
    "P2": 6,
    "P3": 12,
    "P4": 24,   # kept for completeness; P4 alerts are never created
}

def doIgnoreTicketBySeverity(severity : str):
    # Severities that should never create or update alerts
    _IGNORED_SEVERITIES = {"P4"}

    return severity in _IGNORED_SEVERITIES

def get_resolution_window(severity: str) -> timedelta:
    """
    Return the silence window after which an OPEN alert is auto-resolved.

    If no new ticket activity is seen for this duration since last_seen_at,
    ResolutionService will close the alert and its related tickets.
    """
    hours = _RESOLUTION_HOURS.get(severity, 24)
    return timedelta(hours=hours)

def compute_cooldown(severity: str) -> datetime:
    """
    Return the datetime until which notifications should be suppressed.

    P1 → 10 min, P2 → 15 min, P3+ → 30 min.
    """
    minutes = _COOLDOWN_MINUTES.get(severity, 30)
    return datetime.now() + timedelta(minutes=minutes)

