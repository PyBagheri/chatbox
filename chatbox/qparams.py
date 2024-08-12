from rest_framework import serializers

from chatbox.utils import (
    chatbox_settings
)


class ExpandUserChatPeerQueryParams(serializers.Serializer):
    expand_user = serializers.BooleanField(default=False)
    expand_chat = serializers.BooleanField(default=False)
    expand_peer = serializers.BooleanField(default=False)


class ChatMessageFilterQueryParams(serializers.Serializer):
    unread = serializers.BooleanField(default=False)


class MessageRelatedPaginationQueryParams(serializers.Serializer):
    reverse = serializers.BooleanField(default=False)
    offset_message_id = serializers.CharField(required=False, max_length=20)


class MessagePaginationQueryParams(MessageRelatedPaginationQueryParams):
    limit = serializers.IntegerField(
        default=chatbox_settings.MESSAGE_DEFAULT_PAGE_SIZE,
        max_value=chatbox_settings.MESSAGE_MAX_PAGE_SIZE,
        min_value=1
    )


class ChatPaginationQueryParams(MessageRelatedPaginationQueryParams):
    limit = serializers.IntegerField(
        default=chatbox_settings.CHAT_DEFAULT_PAGE_SIZE,
        max_value=chatbox_settings.CHAT_MAX_PAGE_SIZE,
        min_value=1
    )
