from __future__ import annotations

from datetime import timedelta
import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from agents.models import Agent, Purpose
from alerts.models import Alert
from guidance.models import Guidance
from guidance.services import GuidanceService
from tickets.services import TicketService


class Command(BaseCommand):
    help = "Seed demo data (agents, guidance, tickets, alerts) for the feature client UI."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing demo data (agent_demo_*) before seeding.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        sample_agents = [
            ("agent_demo_web", "Web Tier", "ubuntu-web-1", "linux", "general"),
            ("agent_demo_db", "DB Primary", "postgres-01", "linux", "database"),
            ("agent_demo_cache", "Cache Node", "redis-03", "linux", "cache"),
            ("agent_demo_search", "Search Tier", "es-02", "linux", "search"),
            ("agent_demo_queue", "Queue Worker", "rq-01", "linux", "general"),
        ]
        sample_metrics = {
            "cpu_v1.0.0.usage_overall": "CPU usage sustained above 90% for 5 minutes",
            "disk_v1.0.0.usage": "Disk usage above 85% for 30 minutes",
            "memory_v1.0.0.ram": "Memory pressure detected with swap activity",
            "network_v1.0.0.errors": "Network errors spiking beyond SLO",
        }

        if force:
            self.stdout.write("Clearing existing demo data (agent_demo_*, sample guidance)...")
            Alert.objects.filter(agent_ids__icontains="agent_demo_").delete()
            from tickets.models import Ticket

            Ticket.objects.filter(agent_id__startswith="agent_demo_").delete()
            Agent.objects.filter(agent_id__startswith="agent_demo_").delete()
            Guidance.objects.filter(metric_name__in=sample_metrics.keys()).delete()

        # Purposes
        purpose_map = {}
        for purpose_name in {"general", "database", "cache", "search"}:
            purpose_obj, _ = Purpose.objects.get_or_create(purpose=purpose_name)
            purpose_map[purpose_name] = purpose_obj

        # Agents
        for agent_id, label, hostname, os_name, purpose_name in sample_agents:
            Agent.objects.get_or_create(
                agent_id=agent_id,
                defaults={
                    "agent_version": "1.0.0",
                    "hostname": hostname,
                    "os": os_name,
                    "purpose": purpose_map.get(purpose_name),
                    "heartbeat": timezone.now() - timedelta(minutes=3),
                    "fingerprint": f"fp-{agent_id}",
                },
            )

        # Guidance records
        guidance_payloads = [
            {
                "metric_name": "cpu_v1.0.0.usage_overall",
                "priority": "P1",
                "purpose": "general",
                "resolution_steps": [
                    {"step": 1, "action": "Check top/htop for runaway processes."},
                    {"step": 2, "action": "Restart offending service if safe; otherwise scale out."},
                ],
                "resolver_notes": "Escalate to infra if >95% for 10m.",
            },
            {
                "metric_name": "disk_v1.0.0.usage",
                "priority": "P2",
                "purpose": "database",
                "resolution_steps": [
                    {"step": 1, "action": "Inspect largest directories with du -sh /*."},
                    {"step": 2, "action": "Purge old WAL/backups; consider adding space."},
                ],
            },
            {
                "metric_name": "memory_v1.0.0.ram",
                "priority": "P2",
                "purpose": "general",
                "resolution_steps": [
                    {"step": 1, "action": "Capture ps aux --sort=-%mem head -n 5."},
                    {"step": 2, "action": "Restart leaky service; add swap as stopgap."},
                ],
            },
            {
                "metric_name": "network_v1.0.0.errors",
                "priority": "P1",
                "purpose": "search",
                "resolution_steps": [
                    {"step": 1, "action": "Check interface error counters (ethtool -S)."},
                    {"step": 2, "action": "Flip traffic to healthy node; investigate NIC/cable."},
                ],
            },
        ]
        for payload in guidance_payloads:
            GuidanceService.upsert(payload)

        # Tickets (auto-creates Alerts)
        now = timezone.now()
        ticket_events = [
            # agent_id, metric, severity, detector, minutes_ago, message, occurrences
            ("agent_demo_web", "cpu_v1.0.0.usage_overall", "P1", "anomaly_z_score", 12, sample_metrics["cpu_v1.0.0.usage_overall"], 3),
            ("agent_demo_db", "disk_v1.0.0.usage", "P2", "disk_usage", 35, sample_metrics["disk_v1.0.0.usage"], 2),
            ("agent_demo_cache", "memory_v1.0.0.ram", "P2", "memory_leak", 8, sample_metrics["memory_v1.0.0.ram"], 5),
            ("agent_demo_search", "network_v1.0.0.errors", "P1", "nic_errors", 55, sample_metrics["network_v1.0.0.errors"], 4),
            ("agent_demo_queue", "cpu_v1.0.0.usage_overall", "P3", "threshold_cpu", 5, "Worker CPU bursts during requeue", 2),
        ]

        created_count = 0
        for agent_id, metric, severity, detector, minutes_ago, message, occurrences in ticket_events:
            # skip if a ticket with same keys already exists
            existing = TicketService.get_tickets(agent_id, limit=1, include_p4=True, status=None, severity=None)
            if existing:
                continue

            res = TicketService.create_ticket(
                agent_id=agent_id,
                metric_name=metric,
                severity=severity,
                detector=detector,
                meta=json.dumps({"seeded": True}),
                message=message,
                dedup=False,
                purpose=None,
            )
            ticket = res["ticket"]
            created_count += 1
            # adjust timestamps and occurrence count
            ticket.first_occurred_at = now - timedelta(minutes=minutes_ago + 10)
            ticket.last_occurred_at = now - timedelta(minutes=minutes_ago)
            ticket.occurrence_count = occurrences
            ticket.save(update_fields=["first_occurred_at", "last_occurred_at", "occurrence_count"])

        # Ack one alert for variety
        alert = Alert.objects.filter(status="OPEN").order_by("-last_seen_at").first()
        if alert:
            alert.status = "ACK"
            alert.acknowledged_by = "resolver_demo"
            alert.acknowledged_at = now - timedelta(minutes=2)
            alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])

        self.stdout.write(self.style.SUCCESS(f"Seed complete: {len(sample_agents)} agents, {len(guidance_payloads)} guidance, {created_count} tickets (+alerts)."))
