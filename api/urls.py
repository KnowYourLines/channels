# chat/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("find_my_rooms/", views.find_my_rooms, name="find"),
    path("username/", views.username, name="room"),
]
