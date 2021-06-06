# chat/views.py
import uuid

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from api.models import Message


def username(request):
    username = uuid.uuid4()
    if request.user.is_authenticated:
        username = request.user.get_username()
    return JsonResponse({"username": username})


@login_required
def find_my_rooms(request):
    username = request.user.get_username()
    result = list(
        Message.objects.filter(username__exact=username)
        .values("room")
        .order_by("-timestamp")
    )
    return JsonResponse(result, safe=False)
