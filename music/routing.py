from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/player/(?P<room_id>[a-zA-Z0-9_-]+)/$', consumers.PlayerConsumer.as_asgi()),
]
