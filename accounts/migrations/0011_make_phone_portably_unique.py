from django.db import migrations, models


def blank_phones_to_null(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(phone="").update(phone=None)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0010_passwordchangecode"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="user",
            name="unique_non_blank_user_phone",
        ),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                verbose_name="Телефон",
            ),
        ),
        migrations.RunPython(blank_phones_to_null, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                unique=True,
                verbose_name="Телефон",
            ),
        ),
    ]
