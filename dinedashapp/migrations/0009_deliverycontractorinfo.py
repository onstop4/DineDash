# Generated by Django 5.1.6 on 2025-03-03 20:06

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dinedashapp", "0008_alter_restaurant_user"),
    ]

    operations = [
        migrations.CreateModel(
            name="DeliveryContractorInfo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "first_name",
                    models.CharField(max_length=150, verbose_name="first name"),
                ),
                (
                    "last_name",
                    models.CharField(max_length=150, verbose_name="last name"),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_contractor_info",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
