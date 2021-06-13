from django.core.validators import RegexValidator
from django.db import models

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    id = models.AutoField(primary_key=True)
    phone_regex = RegexValidator(
        regex=r"^\+?1?\d{9,15}$",
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.",
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.TextField()
    room = models.TextField()
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
