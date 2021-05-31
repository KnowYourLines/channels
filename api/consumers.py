import json
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from api.models import Message


class ChatConsumer(WebsocketConsumer):
    def messages_to_json(self, messages):
        result = []
        for message in messages:
            result.append(self.message_to_json(message))
        return result

    def message_to_json(self, message):
        return {"content": message.content, "timestamp": str(message.timestamp)}

    def connect(self):
        self.room_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room_group_name = "chat_%s" % self.room_name

        # Join room group
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code):
        # Leave room group
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name, self.channel_name
        )

    # Receive message from WebSocket
    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        if text_data_json.get("command"):
            try:
                messages = Message.objects.filter(
                    room__exact=self.room_group_name
                ).order_by("timestamp")[:10]
                for message in self.messages_to_json(messages):
                    async_to_sync(self.channel_layer.send)(
                        self.channel_name,
                        {"type": "chat_message", "message": message["content"]},
                    )
            except Message.DoesNotExist:
                pass

        else:
            message = text_data_json["message"]
            Message.objects.create(room=self.room_group_name, content=message)

            # Send message to room group
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name, {"type": "chat_message", "message": message}
            )

    # Receive message from room group
    def chat_message(self, event):
        message = event["message"]

        # Send message to WebSocket
        self.send(text_data=json.dumps({"message": message}))
