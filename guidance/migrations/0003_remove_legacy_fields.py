from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('guidance', '0002_guidance_document_summary_source'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='guidance',
            name='resolution_steps',
        ),
        migrations.RemoveField(
            model_name='guidance',
            name='resolver_notes',
        ),
    ]
