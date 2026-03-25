# Anomaly Detectors

Detection flow for metric anomalies and how they raise tickets.

## Components
- `BaseAnomaly` (`anomaly/baseAnomaly.py`): abstract class; implement `detect_anomaly()` in new detectors.
- `ZScoreAnomaly` (`anomaly/zScore.py`): current detector.
- `AnomalyState` (`anomaly/models.py`): stores last processed bucket per `(table_name, detector, agent_id, metric_name)` to avoid duplicate alerts.
- Constants (`anomaly/const.py`): allowed measurements `metric_numeric_1m`, `metric_numeric_10m`, `metric_numeric_1h`; allowed fields `avg|sum|min|max|count`.

## ZScoreAnomaly Workflow
1) Instantiate with `agent_id`, `metrics` list, optional `window` (default 30 points), `measurement` (default `metric_numeric_1m`), and `on` field (default `sum`).
2) Fetch last 7d of data from Influx for the agent/metrics/measurement/field.
3) Group by metric; require at least `max(window, 10)` points. Use the most recent point as the "current" sample and the rest as history.
4) Skip processing if `AnomalyState` already recorded the same `latest_bucket` (prevents duplicate tickets on re-runs).
5) Compute z-score of current vs history:
   - |z| >= 4 -> severity P2
   - |z| >= 3 -> severity P3
   - |z| >= 2 -> severity P3 (as implemented)
   - |z| >= 1.5 -> severity P4
   - otherwise ignored.
6) On detection:
   - Update `anomaly_state.last_bucket` for this metric/detector.
   - Create a ticket via `TicketService.create_ticket(...)` with `detector="zscore"` and meta containing `current_value`, `baseline_value`, `deviation`, and `table`.
7) Return a list of detections `{"metric","z","severity"}` or `None` when nothing fires.

## Extending
- Subclass `BaseAnomaly` and implement `detect_anomaly()`; use `AnomalyService.insertOrReplace` / `selectOne` to manage per-metric cursors.
- Ensure new detectors write meaningful `meta` for auditability and call `TicketService.create_ticket` so downstream alerting continues to work.
