from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from chatbox.fields import (
    UnixTimestampField
)
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
    offset_datetime = UnixTimestampField(required=False)
    
    # We're not using `SlugRelatedField` on the UUID here; this
    # is because the message might have been deleted, but we still
    # need its UUID to be able to avoid duplicate results in the
    # next/prev pages in case there are more than one messages with
    # the same datetime at the end/start of the page.
    offset_message_id = serializers.UUIDField(required=False)
    
    def validate(self, attrs):
        # This restriction is to simplify the pagination process a bit.
        # If later we need these filters to work separately, we must
        # correct the implementation of the pagination.
        if any([
            'offset_datetime' in attrs and 'offset_message_id' not in attrs,
            'offset_datetime' not in attrs and 'offset_message_id' in attrs
        ]):
            raise ValidationError(
                "'offset_datetime' and 'offset_message_id' must either both "
                "be given or not given"
            )
        
        return super().validate(attrs)


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

