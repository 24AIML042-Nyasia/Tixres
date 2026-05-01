# Anomaly Detector Configuration

The system uses a template-driven configuration for all anomaly detectors.

## Thresholds
Configuration is managed in `template.json` under the `detectors` key:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `stat_z_high` | Z-score for HIGH statistical anomaly | 5.0 |
| `cpu_temp_high_c` | Temperature threshold for HIGH alert | 85.0 |
| `ram_high_pct` | RAM usage percentage for alert | 90.0 |
| `net_spike_factor` | Multiplier for network usage spike | 2.0 |

## Retention Policies
Retention is defined per table type in days:
- `metric_numeric`: 7 days
- `metric_json`: 3 days
- `metric_log`: 1 day

## System Configuration (config.json)

Core system settings are managed in `config.json` at the project root.

### Database Engine
Switch between SQLite and PostgreSQL:
```json
{
  "database": {
    "engine": "postgresql",
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "yourpassword",
    "name": "tixres"
  }
}
```
> [!IMPORTANT]
> If your password contains special characters like `@`, you should URL-encode them in `config.json` (e.g., `@` becomes `%40`). The system will decode them automatically.

### Celery Infrastructure
Configure the message broker and backend:
```json
{
  "celery": {
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1"
  }
}
```
