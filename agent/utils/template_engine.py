import json
from dataclasses import dataclass, field
from typing import Callable, Literal

FrequencyUnit = Literal["ms", "s"]


@dataclass(frozen=True)
class ParsedTemplate:
    modules: list[str]
    metrics: dict[str, int]  # frequency in ms


@dataclass(frozen=True)
class TemplateVerificationResult:
    ok: bool
    missing_modules: list[str] = field(default_factory=list)
    missing_functions: list[str] = field(default_factory=list)
    invalid_metrics: list[str] = field(default_factory=list)
    parse_error: str | None = None


def _to_ms(freq: int | float, unit: FrequencyUnit) -> int:
    if unit == "ms":
        return int(freq)
    return int(float(freq) * 1000)


def parse_template(
    raw: str | dict,
    *,
    flat_frequency_unit: FrequencyUnit = "ms",
    nested_frequency_unit: FrequencyUnit = "s",
) -> ParsedTemplate:
    root = json.loads(raw) if isinstance(raw, str) else raw

    if isinstance(root, dict) and "template" in root and isinstance(root["template"], dict):
        template = root["template"]
        modules = list(template.get("modules", []))
        metrics_raw = template.get("metrics", {})
        unit = nested_frequency_unit
    else:
        modules = []
        metrics_raw = root
        unit = flat_frequency_unit

    if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
        raise ValueError('Template "modules" must be a list[str]')

    if not isinstance(metrics_raw, dict) or not all(isinstance(k, str) for k in metrics_raw):
        raise ValueError('Template "metrics" must be a dict[str, number]')

    metrics: dict[str, int] = {}
    for name, freq in metrics_raw.items():
        if not isinstance(freq, (int, float)) or freq <= 0:
            raise ValueError(f'Frequency for "{name}" must be a positive number')
        metrics[name] = _to_ms(freq, unit)

    return ParsedTemplate(modules=modules, metrics=metrics)


def verify_template(raw: str | dict, registry) -> TemplateVerificationResult:
    try:
        parsed = parse_template(raw)
    except Exception as exc:  # pragma: no cover
        return TemplateVerificationResult(ok=False, parse_error=str(exc))

    available_module_ids = {
        entry.module.module_id
        for _, entry in registry.entries()
        if getattr(entry, "module", None) is not None
    }

    template_module_ids = set(parsed.modules)
    metric_module_ids = {name.rsplit(".", 1)[0] for name in parsed.metrics if "." in name}
    invalid_metrics = sorted([name for name in parsed.metrics if "." not in name])

    required_module_ids = template_module_ids | metric_module_ids
    missing_modules = sorted(required_module_ids - available_module_ids)
    missing_functions = sorted([name for name in parsed.metrics if not registry.has(name)])

    ok = not missing_modules and not missing_functions and not invalid_metrics
    return TemplateVerificationResult(
        ok=ok,
        missing_modules=missing_modules,
        missing_functions=missing_functions,
        invalid_metrics=invalid_metrics,
    )

@dataclass
class TemplateDiff:
    added:   list[tuple[str, int]] = field(default_factory=list)
    removed: list[str]             = field(default_factory=list)
    updated: list[tuple[str, int]] = field(default_factory=list)

class TemplateEngine:
    def __init__(self):
        self._current: dict[str, int] = {}
        # Simple observer list — no need for full EventTarget in Python
        self._listeners: list[Callable[[TemplateDiff], None]] = []

    def on_change(self, fn: Callable[[TemplateDiff], None]):
        """Register a listener called whenever the template changes."""
        self._listeners.append(fn)

    def apply(self, raw: str | dict, registry) -> TemplateDiff:
        parsed = parse_template(raw)
        next_tmpl = parsed.metrics

        for name, freq in next_tmpl.items():
            entry = registry.get(name)
            if not entry:
                raise ValueError(f'Unknown function: "{name}"')
            if entry.type != "loop":
                raise ValueError(f'Function "{name}" is not a loop function')
            if not isinstance(freq, int) or freq <= 0:
                raise ValueError(f'Frequency for "{name}" must be a positive number')

        diff = self._diff(self._current, next_tmpl)
        self._current = next_tmpl

        for listener in self._listeners:
            listener(diff)

        return diff

    @property
    def snapshot(self) -> dict[str, int]:
        return dict(self._current)

    def _diff(self, prev: dict, next_tmpl: dict) -> TemplateDiff:
        prev_keys = set(prev)
        next_keys = set(next_tmpl)
        return TemplateDiff(
            added   = [(k, next_tmpl[k]) for k in next_keys - prev_keys],
            removed = list(prev_keys - next_keys),
            updated = [(k, next_tmpl[k]) for k in next_keys & prev_keys
                       if prev[k] != next_tmpl[k]],
        )
