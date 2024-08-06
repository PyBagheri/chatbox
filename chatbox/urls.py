from django.urls import path, include, re_path
from rest_framework.routers import SimpleRouter
from chatbox.views import (
    ChatMessageViewSet,
    ChatViewSet,
    MessageViewSet
)

router = SimpleRouter(use_regex_path=False)

router.register('chat', ChatViewSet, basename='chat')
router.register('message', MessageViewSet, basename='user_message')


# Currently, all of the URL's in this app are API urls.
urlpatterns = [
    path('', include(router.urls))
]
