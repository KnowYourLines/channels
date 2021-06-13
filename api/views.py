# chat/views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.models import Message
from api.serializers import MessageSerializer


@api_view(["GET"])
def find_my_rooms(request):
    data = (
        Message.objects.filter(username__exact=request.user.username)
        .values("room")
        .order_by("-timestamp")
    )
    result = MessageSerializer(data, many=True)
    return Response(result)
