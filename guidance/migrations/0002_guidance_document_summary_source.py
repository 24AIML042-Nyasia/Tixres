from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guidance', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='guidance',
            name='document',
            field=models.TextField(default=''),
        ),
        migrations.AddField(
            model_name='guidance',
            name='summary',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='guidance',
            name='source',
            field=models.CharField(default='resolver', max_length=50),
        ),
    ]
