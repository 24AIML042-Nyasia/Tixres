# System Documentation

This document provides an overview of the Tixres monitoring system, its architecture, and its components.

## Architecture Overview

Tixres is a distributed monitoring system consisting of:
- **Agents**: Installed on target systems to collect and submit metrics.
- **Metric Server**: Central hub for receiving data, performing anomaly detection, and managing storage.
- **Incident Engine**: Maps raw alerts to higher-level incidents for easier management.
- **UI Dashboard**: Real-time visualization and management interface.

## Core Components

### 1. Metric Storage
Tixres supports a hybrid storage model:
- **SQLite**: Default for development and small-scale deployments.
- **PostgreSQL**: Production-grade storage via SQLAlchemy for high concurrency and scalability.

Data is stored across several optimized tables:
- `metric_numeric`: Raw numeric time-series data.
- `metric_json`: Structured log and metadata.
- `metric_numeric_1m/10m/1h`: Continuous rollups for performant long-term visualization.
- `alerts`: Historical record of detected anomalies.
- `incidents`: Aggregated incidents with state and severity tracking.

### 2. Anomaly Detection
Detectors run in real-time as metrics arrive. They use two main strategies:
- **Statistical**: Z-score and MAD (Median Absolute Deviation) based on historical data.
- **Rule-based**: Fixed thresholds and stateful rules (e.g., sustained high CPU).

### 3. Incident Management
Alerts are grouped into incidents using a deterministic hash:
`incident_key = hash(host_id, service, plugin, time_bucket)`
This ensures related alerts are deduplicated and tracked as a single event.

### 4. Resolution Guidance
Provides actionable, step-by-step instructions for resolving incidents. Guidance is context-aware and retrieved based on the incident's anomaly type.

### 5. Background Processing (Celery)
Automated tasks handle system maintenance:
- **Expiry**: Stale alerts and resolved incidents are automatically closed.
- **Rollups**: Continuous aggregation of raw metrics.
- **Retention**: Periodic cleanup of old data based on template policies.

## Configuration (template.json)
The system is fully template-driven. Changes to `template.json` are hot-reloaded and propagated to all connected agents and detectors.
