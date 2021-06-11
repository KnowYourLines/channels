# chat/views.py
import uuid

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.models import Message


@api_view(["GET"])
def username(request):
    username = uuid.uuid4()
    if request.user.is_authenticated:
        username = (
            request.user.first_name or request.user.email or request.user.username
        )
    return Response({"username": username})


@login_required
def find_my_rooms(request):
    username = request.user.get_username()
    result = list(
        Message.objects.filter(username__exact=username)
        .values("room")
        .order_by("-timestamp")
    )
    return JsonResponse(result, safe=False)
