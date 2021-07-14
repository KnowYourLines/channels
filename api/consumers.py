import json
import logging
import os

import firebase_admin
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from firebase_admin import auth, credentials

from api.models import Message, Room, User, JoinRequest, Notification
from firebase_auth.exceptions import FirebaseError, InvalidAuthToken

logger = logging.getLogger(__name__)
cred = credentials.Certificate(
    {
        "type": "service_account",
        "project_id": os.environ.get("FIREBASE_PROJECT_ID"),
        "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID"),
        "private_key": os.environ.get("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
        "client_email": os.environ.get("FIREBASE_CLIENT_EMAIL"),
        "client_id": os.environ.get("FIREBASE_CLIENT_ID"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://accounts.google.com/o/oauth2/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": os.environ.get("FIREBASE_CLIENT_CERT_URL"),
    }
)

default_app = firebase_admin.initialize_app(cred)


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

    def get_room_join_requests(self):
        self.room = self.get_room(self.room_group_name)
        requests = list(
            self.room.joinrequest_set.order_by("-timestamp").values(
                "user", "user__username", "user__display_name"
            )
        )
        return requests

    async def fetch_join_requests(self):
        try:
            requests = await database_sync_to_async(self.get_room_join_requests)()
            logger.debug(f"{requests}")
            await self.channel_layer.send(
                self.channel_name,
                {
                    "type": "requests",
                    "requests": json.dumps(requests),
                },
            )
        except JoinRequest.DoesNotExist:
            pass

    def get_user_notifications(self):
        self.user.notification_set.filter(room=self.room).update(read=True)
        notifications = list(
            self.user.notification_set.all()
            .values(
                "room",
                "room__display_name",
                "message__content",
                "message__user__display_name",
                "timestamp",
                "read",
                "user_joined__display_name",
                "user_left__display_name",
            )
            .order_by("read", "-timestamp")
        )
        most_recent_room_notifications = []
        rooms_covered_already = set()
        for notification in notifications:
            notification["room"] = str(notification["room"])
            notification["timestamp"] = str(notification["timestamp"])
            if notification["room"] not in rooms_covered_already:
                most_recent_room_notifications.append(notification)
                rooms_covered_already.add(notification["room"])

        return most_recent_room_notifications

    async def fetch_user_notifications(self):
        try:
            notifications = await database_sync_to_async(self.get_user_notifications)()
            logger.debug(f"{notifications}")
            await self.channel_layer.send(
                self.channel_name,
                {
                    "type": "notifications",
                    "notifications": json.dumps(notifications),
                },
            )
        except Notification.DoesNotExist:
            pass

    async def fetch_room_name(self):
        self.room = await database_sync_to_async(self.get_room)(self.room_group_name)
        if not self.room.display_name:
            await database_sync_to_async(self.update_room_name)(str(self.room.id))
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "room_name",
                "new_room_name": f"{self.room.display_name}",
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

    async def fetch_room_members(self):
        members = await database_sync_to_async(self.get_room_members)()
        await self.channel_layer.send(
            self.channel_name,
            {
                "type": "members",
                "members": json.dumps(members),
            },
        )

    def get_room_members(self):
        return list(self.room.members.all().values("display_name"))

    def update_room_members(self, room, user):
        if user not in room.members.all():
            room.members.add(user)
            self.create_user_joined_notification_for_all_room_members(user_joining=user)

    def leave_room(self, room_id):
        room_to_leave = Room.objects.get(id=room_id)
        room_to_leave.members.remove(self.user)
        for user in room_to_leave.members.all():
            Notification.objects.create(
                user=user, room=room_to_leave, user_left=self.user
            )
        self.user.notification_set.filter(room=room_to_leave).delete()

    def get_room(self, room_id):
        room, created = Room.objects.get_or_create(id=room_id)
        return room

    def create_new_message_notification_for_all_room_members(self, new_message):
        for user in self.room.members.all():
            Notification.objects.create(user=user, room=self.room, message=new_message)

    def create_user_joined_notification_for_all_room_members(self, user_joining):
        if user_joining is self.user:
            if not self.user.display_name:
                self.update_display_name(
                    self.user.get_full_name()
                    or self.user.email
                    or self.user.phone_number
                    or self.user.username
                )
        for user in self.room.members.all():
            Notification.objects.create(
                user=user, room=self.room, user_joined=user_joining
            )

    def get_rooms_of_all_members(self):
        rooms = set()
        for user in self.room.members.all():
            for room in user.room_set.all():
                rooms.add(str(room.id))
        return rooms

    def create_new_message(self, message):
        new_message = Message.objects.create(
            user=self.user, room=self.room, content=message
        )
        self.create_new_message_notification_for_all_room_members(new_message)
        return new_message

    def get_or_create_new_join_request(self):
        return JoinRequest.objects.get_or_create(user=self.user, room=self.room)

    def approve_room_member(self, username):
        user = User.objects.get(username=username)
        self.room.members.add(user)
        self.room.joinrequest_set.filter(user=user).delete()
        self.create_user_joined_notification_for_all_room_members(user_joining=user)

    def approve_all_room_members(self):
        for request in self.room.joinrequest_set.all():
            self.room.members.add(request.user)
            self.create_user_joined_notification_for_all_room_members(
                user_joining=request.user
            )
        self.room.joinrequest_set.all().delete()

    def reject_room_member(self, username):
        user = User.objects.get(username=username)
        self.room.joinrequest_set.filter(user=user).delete()

    def get_user(self, token):
        try:
            decoded_token = auth.verify_id_token(token)
        except Exception:
            logger.debug(f"invalid token: {token}")
            raise InvalidAuthToken("Invalid auth token")
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
                await database_sync_to_async(self.get_or_create_new_join_request)()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "refresh_join_requests"},
                )
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "not_allowed",
                        "not_allowed": True,
                    },
                )
            else:
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "allowed",
                        "allowed": True,
                    },
                )
                await database_sync_to_async(self.fetch_messages)()
        elif text_data_json.get("command") == "fetch_allowed_status":
            self.user = await database_sync_to_async(self.get_user)(
                text_data_json["token"]
            )
            user_not_allowed = await database_sync_to_async(self.user_not_allowed)()
            if user_not_allowed:
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "not_allowed",
                        "not_allowed": True,
                    },
                )
            else:
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "allowed",
                        "allowed": True,
                    },
                )
        elif text_data_json.get("command") == "fetch_display_name":
            await self.fetch_display_name()
        elif text_data_json.get("command") == "update_display_name":
            await database_sync_to_async(self.update_display_name)(
                text_data_json["name"]
            )
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {"type": "refresh_notifications"},
                )
                await self.channel_layer.group_send(
                    room,
                    {"type": "refresh_members"},
                )
                await self.channel_layer.group_send(
                    room,
                    {"type": "refresh_chat"},
                )
        elif text_data_json.get("command") == "fetch_room_name":
            await self.fetch_room_name()
        elif text_data_json.get("command") == "fetch_members":
            await self.fetch_room_members()
        elif text_data_json.get("command") == "update_room_name":
            await database_sync_to_async(self.update_room_name)(text_data_json["name"])
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {"type": "refresh_notifications"},
                )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_room_name"},
            )
        elif text_data_json.get("command") == "exit_room":
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            await database_sync_to_async(self.leave_room)(text_data_json["room_id"])

            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {
                        "type": "refresh_notifications",
                    },
                )
            await self.channel_layer.group_send(
                text_data_json["room_id"],
                {"type": "refresh_members"},
            )
        elif text_data_json.get("command") == "approve_user":
            await database_sync_to_async(self.approve_room_member)(
                text_data_json["username"]
            )
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {"type": "refresh_notifications"},
                )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_join_requests"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_members"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_allowed_status"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_chat"},
            )
        elif text_data_json.get("command") == "approve_all_users":
            await database_sync_to_async(self.approve_all_room_members)()
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {
                        "type": "refresh_notifications",
                    },
                )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_join_requests"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_members"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_allowed_status"},
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_chat"},
            )
        elif text_data_json.get("command") == "reject_user":
            await database_sync_to_async(self.reject_room_member)(
                text_data_json["username"]
            )
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_join_requests"},
            )
        elif text_data_json.get("command") == "fetch_join_requests":
            await self.fetch_join_requests()
        elif text_data_json.get("command") == "fetch_user_notifications":
            await self.fetch_user_notifications()
        elif text_data_json.get("command") == "fetch_privacy":
            await self.fetch_privacy()
        elif text_data_json.get("command") == "update_privacy":
            await database_sync_to_async(self.update_privacy)(text_data_json["privacy"])
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "refresh_privacy"},
            )
        elif text_data_json.get("command") == "join_room":
            self.user = await database_sync_to_async(self.get_user)(
                text_data_json["token"]
            )
            user_not_allowed = await database_sync_to_async(self.user_not_allowed)()
            if user_not_allowed:
                await database_sync_to_async(self.get_or_create_new_join_request)()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "refresh_join_requests"},
                )
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "not_allowed",
                        "not_allowed": True,
                    },
                )
            else:
                await self.channel_layer.send(
                    self.channel_name,
                    {
                        "type": "allowed",
                        "allowed": True,
                    },
                )
                await database_sync_to_async(self.update_room_members)(
                    self.room, self.user
                )
                rooms_to_notify = await database_sync_to_async(
                    self.get_rooms_of_all_members
                )()
                for room in rooms_to_notify:
                    await self.channel_layer.group_send(
                        room,
                        {
                            "type": "refresh_notifications",
                        },
                    )
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {"type": "refresh_members"},
                )
        else:
            message = text_data_json["message"]
            display_name = text_data_json["user"]
            await database_sync_to_async(self.create_new_message)(message)
            rooms_to_notify = await database_sync_to_async(
                self.get_rooms_of_all_members
            )()
            for room in rooms_to_notify:
                await self.channel_layer.group_send(
                    room,
                    {
                        "type": "refresh_notifications",
                    },
                )
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

    async def not_allowed(self, event):
        not_allowed = event["not_allowed"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"not_allowed": not_allowed}))

    async def allowed(self, event):
        allowed = event["allowed"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"allowed": allowed}))

    async def members(self, event):
        members = event["members"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"members": members}))

    async def requests(self, event):
        requests = event["requests"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"requests": requests}))

    async def notifications(self, event):
        notifications = event["notifications"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"notifications": notifications}))

    async def privacy(self, event):
        privacy = event["privacy"]
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"privacy": privacy}))

    async def refresh_privacy(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_privacy": True}))

    async def refresh_members(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_members": True}))

    async def refresh_notifications(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_notifications": True}))

    async def refresh_join_requests(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_join_requests": True}))

    async def refresh_chat(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_chat": True}))

    async def refresh_room_name(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_room_name": True}))

    async def refresh_allowed_status(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({"refresh_allowed_status": True}))
