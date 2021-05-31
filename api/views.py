# chat/views.py
import uuid

from django.shortcuts import render


def index(request):
    return render(request, "api/index.html")


def room(request, room_name):
    username = uuid.uuid4()
    if request.user.is_authenticated:
        username = request.user.get_username()
    return render(
        request, "api/room.html", {"room_name": room_name, "username": username}
    )
