# Generated manually for attachments app (image-first, extensible)
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_id", models.PositiveIntegerField(db_index=True)),
                ("kind", models.CharField(choices=[("image", "Image"), ("file", "File"), ("link", "Link")], db_index=True, default="image", max_length=20)),
                ("url", models.TextField(help_text="Absolute or data URL pointing to the asset")),
                ("file_name", models.CharField(blank=True, max_length=255, null=True)),
                ("mime_type", models.CharField(default="image/png", max_length=100)),
                ("size_bytes", models.PositiveIntegerField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("content_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="contenttypes.contenttype")),
            ],
            options={
                "db_table": "attachments",
                "indexes": [
                    models.Index(fields=["content_type", "object_id"], name="attachments_content_obj_idx"),
                    models.Index(fields=["kind"], name="attachments_kind_idx"),
                ],
            },
        ),
    ]
