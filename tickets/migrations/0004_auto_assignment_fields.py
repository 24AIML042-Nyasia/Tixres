from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("auth_core", "0001_initial"),
        ("tickets", "0003_alter_ticket_severity_alter_ticket_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticket",
            name="assigned_to",
            field=models.ForeignKey(
                related_name="assigned_tickets",
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="auth_core.ssouser",
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="ticket",
            name="assigned_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="ticket",
            name="assignment_strategy",
            field=models.CharField(max_length=50, blank=True, default=""),
        ),
        migrations.AddField(
            model_name="ticket",
            name="assignment_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="ticket",
            name="auto_assigned",
            field=models.BooleanField(default=False),
        ),
    ]
