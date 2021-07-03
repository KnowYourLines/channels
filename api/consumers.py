import json
import logging

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from firebase_admin import auth

from api.models import Message, Room, User
from firebase_auth.exceptions import FirebaseError, InvalidAuthToken

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    def messages_to_json(self, messages):
        result = []
        for message in messages:
            result.append(self.message_to_json(message))
        return result[::-1]

    def message_to_json(self, message):
        return {
            "display_name": message.user.display_name
            or message.user.get_full_name()
            or message.user.email
            or message.user.phone_number
            or message.user.username,
            "content": message.content,
            "timestamp": str(message.timestamp),
        }

    async def connect(self):
        self.room_group_name = self.scope["url_route"]["kwargs"]["room_name"]
        self.room = await database_sync_to_async(self.get_room)(self.room_group_name)

        # Join room group
        await self.channel_layer.group_add(str(self.room.id), self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    def fetch_messages(self):
        try:
            messages = self.room.message_set.order_by("-timestamp")[:10]
            logger.debug(f"messages: {messages}")
            logger.debug(f"{self.messages_to_json(messages)}")
            for message in self.messages_to_json(messages):
                async_to_sync(self.channel_layer.send)(
                    self.channel_name,
                    {
                        "type": "chat_message",
                        "message": f"{message['display_name']}: {message['content']}",
                    },
                )
        except Message.DoesNotExist:
            pass

    def update_display_name(self, new_name):
        self.user.display_name = new_name
        self.user.save()

    def update_room_name(self, new_name):
        self.room.display_name = new_name
        self.room.save()

    def update_privacy(self, private):
        self.room.private = private
        self.room.save()

    async def fetch_display_name(self):
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "display_name",
                "new_display_name": f"{self.user.display_name or self.user.get_full_name() or self.user.email or self.user.phone_number or self.user.username}",
            },
        )

    async def fetch_room_name(self):
        self.room = await database_sync_to_async(self.get_room)(self.room_group_name)
        logger.debug(f"{self.room.id}: {self.room.display_name}")
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "room_name",
                "new_room_name": f"{self.room.display_name or self.room.id}",
            },
        )

    async def fetch_privacy(self):
        self.room = await database_sync_to_async(self.get_room)(self.room_group_name)
        logger.debug(f"{self.room.id}: {self.room.private}")
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "privacy",
                "privacy": f"{self.room.private}",
            },
        )

    def update_room_members(self, room, user):
        if user not in room.members.all():
            room.members.add(user)

    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        return room

    def create_new_message(self, message):
        return Message.objects.create(user=self.user, room=self.room, content=message)

    def get_user(self, token):
        try:
            decoded_token = auth.verify_id_token(token)
        except Exception:
            raise InvalidAuthToken("Invalid auth token")
            pass
        try:
            uid = decoded_token.get("uid")
            logger.debug(f"decoded_token: {decoded_token}")
        except Exception:
            raise FirebaseError()

        name = decoded_token.get("name")
        last_name = ""
        first_name = ""
        if name:
            split_name = name.split(" ")
            first_name = split_name[0]
            if len(split_name) > 1:
                last_name = split_name[1]
        user, created = User.objects.update_or_create(
            username=uid,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": decoded_token.get("email") or "",
                "phone_number": decoded_token.get("phone_number") or "",
            },
        )
        return user

    def user_not_allowed(self):
        return self.user not in self.room.members.all() and self.room.private

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        if text_data_json.get("command") == "fetch_messages":
            self.user = await database_sync_to_async(self.get_user)(
                text_data_json["token"]
            )
            user_not_allowed = await database_sync_to_async(self.user_not_allowed)()
            if user_not_allowed:
                await self.close()
            else:
                await database_sync_to_async(self.fetch_messages)()
        elif text_data_json.get("command") == "fetch_display_name":
            await self.fetch_display_name()
        elif text_data_json.get("command") == "update_display_name":
            await database_sync_to_async(self.update_display_name)(
                text_data_json["name"]
            )
        elif text_data_json.get("command") == "fetch_room_name":
            await self.fetch_room_name()
        elif text_data_json.get("command") == "update_room_name":
            await database_sync_to_async(self.update_room_name)(text_data_json["name"])
        elif text_data_json.get("command") == "refresh_room_name":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_room_name"},
            )
        elif text_data_json.get("command") == "fetch_privacy":
            await self.fetch_privacy()
        elif text_data_json.get("command") == "update_privacy":
            await database_sync_to_async(self.update_privacy)(text_data_json["privacy"])
        elif text_data_json.get("command") == "refresh_privacy":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_privacy"},
            )
        elif text_data_json.get("command") == "join_room":
            self.user = await database_sync_to_async(self.get_user)(
                text_data_json["token"]
            )
            await database_sync_to_async(self.update_room_members)(self.room, self.user)
        elif text_data_json.get("command") == "refresh_chat":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_chat"},
            )
        else:
            message = text_data_json["message"]
            display_name = text_data_json["user"]
            await database_sync_to_async(self.create_new_message)(message)
            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "chat_message", "message": f"{display_name}: {message}"},
            )

    # Receive message from room group
    async def chat_message(self, event):
        message = event["message"]

        # Send message to WebSocket
        await self.send(text_data=json.dumps({"message": message}))

    async def display_name(self, event):
        name = event["new_display_name"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"new_display_name": name}))

    async def room_name(self, event):
        name = event["new_room_name"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"new_room_name": name}))

    async def privacy(self, event):
        privacy = event["privacy"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"privacy": privacy}))

    async def refresh_privacy(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_privacy": True}))

    async def refresh_chat(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_chat": True}))

    async def refresh_room_name(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_room_name": True}))
