import json
from channels.generic.websocket import AsyncWebsocketConsumer

class PlayerConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f"player_{self.room_id}"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('type')

        if action == 'song_changed':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'song_changed',
                    'data': data
                }
            )
        elif action == 'play':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'play',
                    'data': data
                }
            )
        elif action == 'pause':
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'pause',
                    'data': data
                }
            )
        else:
            # Handle sync_state, request_state, etc.
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'room_message',
                    'data': data
                }
            )

    # Receive song_changed event from group
    async def song_changed(self, event):
        await self.send(text_data=json.dumps(event['data']))

    # Receive play event from group
    async def play(self, event):
        await self.send(text_data=json.dumps(event['data']))

    # Receive pause event from group
    async def pause(self, event):
        await self.send(text_data=json.dumps(event['data']))

    # Receive general message event from group
    async def room_message(self, event):
        await self.send(text_data=json.dumps(event['data']))
