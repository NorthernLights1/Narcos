from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_numbersequence_doc_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="companysettings",
            name="print_layout",
            field=models.CharField(
                choices=[("COMPACT", "Compact"), ("DETAILED", "Detailed")],
                default="COMPACT",
                max_length=8,
                verbose_name="Print layout",
            ),
        ),
    ]
