# Incident Management Guide

## Overview
Incidents are high-level events that represent system anomalies. Unlike raw alerts, incidents provide context and deduplication.

## Lifecycle
1. **Trigger**: An anomaly is detected, and an alert is created.
2. **Mapping**: The alert is mapped to an incident key based on the host, service, and a 10-minute time window.
3. **Open**: If no open incident exists for that key, a new one is created.
4. **Update**: Subsequent alerts for the same key update the existing incident's `last_seen` and `alert_count`.
5. **Resolution**: Incidents can be resolved manually via the UI or automatically via expiry tasks.

## Severity Levels
- **HIGH**: Critical issues requiring immediate attention (e.g., high CPU temperature).
- **MEDIUM**: Significant deviations (e.g., network spikes).
- **LOW**: Minor anomalies or early warnings.

## Automatic Expiry
Incidents are automatically resolved if no new alerts are received within their severity-based window:
- HIGH: 4 hours
- MEDIUM: 2 hours
- LOW: 1 hour
