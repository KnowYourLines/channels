# chat/urls.py
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("find_my_rooms/", views.find_my_rooms, name="find"),
    path("<str:room_name>/", views.room, name="room"),
]
