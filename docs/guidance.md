# Resolution Guidance

## Overview
Guidance provides actionable steps for resolving incidents. Each guidance entry is mapped to an `anomaly_type` and contains a title, description, and a list of resolution steps.

## How it Works
1. **Detection**: When an anomaly is detected (e.g., `cpu_temp_high`), it is tagged with an `anomaly_type`.
2. **Incident Creation**: The alert is mapped to an incident.
3. **Guidance Mapping**: The UI uses the incident's `anomaly_type` to look up guidance from the system template.
4. **Resolution**: Users can click the "Guidance" button on any incident to see a checklist of steps to resolve the issue.

## Configuration
Guidance is defined in `template.json` under the `template.guidance` object.

```json
"guidance": {
  "cpu_temp_high": {
    "title": "High CPU Temperature",
    "description": "The processor is operating above safe temperature thresholds.",
    "steps": [
      "Identify and terminate high-CPU processes.",
      "Check cooling vents.",
      ...
    ],
    "priority": "CRITICAL"
  }
}
```

## Adding New Guidance
To add guidance for a new anomaly type:
1. Identify the `anomaly_type` string used by the detector.
2. Add a corresponding entry to the `guidance` section of your template.
3. Push the template update via the UI or by editing the file.
