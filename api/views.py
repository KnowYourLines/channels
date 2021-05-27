# chat/views.py
from django.shortcuts import render


def index(request):
    return render(request, "api/index.html")


def room(request, room_name):
    return render(request, "api/room.html", {"room_name": room_name})
