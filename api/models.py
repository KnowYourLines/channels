from django.db import models

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    id = models.AutoField(primary_key=True)


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.TextField()
    room = models.TextField()
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
