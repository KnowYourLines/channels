# chat/views.py
import uuid

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from api.models import Message


def index(request):
    room_name = uuid.uuid4()
    return render(request, "api/index.html", {"room_name": room_name})


def room(request, room_name):
    username = uuid.uuid4()
    if request.user.is_authenticated:
        username = request.user.get_username()
    return render(
        request, "api/room.html", {"room_name": room_name, "username": username}
    )


@login_required
def find_my_rooms(request):
    username = request.user.get_username()
    result = list(
        Message.objects.filter(username__exact=username)
        .values("room")
        .order_by("-timestamp")
    )
    return JsonResponse(result, safe=False)
