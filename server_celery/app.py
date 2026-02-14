from celery import Celery
from celery.schedules import crontab

app = Celery(
    "myapp",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

app.conf.timezone = "Asia/Kolkata"

app.conf.beat_schedule = {
    "one_min_roll_up": {
        "task": "server_celery.tasks.one_min_rollup",
        "schedule": crontab(minute="*"),
    },
    "ten_min_roll_up": {
        "task": "server_celery.tasks.ten_min_rollup",
        "schedule": crontab(minute="*/10"),
    },
    "one_hour_roll_up": {
        "task": "server_celery.tasks.one_hour_rollup",
        "schedule": crontab(hour="*"),
    },
    "run_zscore_anomaly": {
        "task": "server_celery.tasks.run_anomaly_cycle",
        "schedule": crontab(minute="*/10"),
    },
}

app.autodiscover_tasks(["server_celery"])