from django.db import models

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    pass


class Message(models.Model):
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
