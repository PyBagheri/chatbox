from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

from chatbox.models import (
    Chat,
    GroupChatInfo,
    FileData,
    Message
)
from chatbox.fields import (
    UnixTimestampField
)
from chatbox.utils import (
    chatbox_settings,
    without,
)

from urllib.parse import urlparse


# Used for determining file URL's.
is_media_url_absolute = hasattr(settings, 'MEDIA_URL') and  \
                        urlparse(settings.MEDIA_URL).netloc



class ChatBoxModelSerializer(serializers.ModelSerializer):
    serializer_field_mapping = serializers.ModelSerializer.serializer_field_mapping.copy()
    serializer_field_mapping[models.DateTimeField] = UnixTimestampField


class MinimalUserSerializer(ChatBoxModelSerializer):
    """A minimal serializer for the user model with read-only fields.
    
    Notes
    -----
    This serializer is suitable for chats as we only want a minimal
    amount of data about the user to whom the message belongs.
    """
    
    class Meta:
        model = get_user_model()
        
        fields = ['username', chatbox_settings.USER_ID_FIELD]
        read_only_fields = fields


def get_peer_representation(*, chat, user, expand=False):
    """Get the representation of the peer for mutual chats.
    
    Notes
    -----
    The peer is the member of the mutual chat that is not
    the given user.
    """
    if expand:
        field = MinimalUserSerializer
    else:
        field = serializers.PrimaryKeyRelatedField
    
    # We must include `read_only=True` because `PrimaryKeyRelationField`
    # must either be given a queryset or be set to read-only. Also we
    # cannot give the data upon instantiation to `PrimaryKeyRelationField`
    # and access its `.data` as we do with serializers; so we need to
    # use `to_representation()` directly.
    return field(read_only=True).to_representation(
        chat.get_peer(user)
    )


class MinimalChatSerializer(ChatBoxModelSerializer):
    """A minimal serializer for the `Chat` model with read-only fields.
    
    Notes
    -----
    This serializer can be used when we list the messages of a user
    or search in the messages of the chats that the user is a member
    of, as the messages might be from any chat in these cases.
    """
    
    class Meta:
        model = Chat
        fields = ['chat_id', 'chat_type']
        read_only_fields = fields
    
    def to_representation(self, instance):
        result = super().to_representation(instance)
        qp = self.context['query_params']
        
        if instance.chat_type == Chat.ChatTypeChoices.MUTUAL:
            result['peer'] = get_peer_representation(
                chat=instance,
                user=self.context['request'].user,
                expand=qp['expand_user']
            )
        else:  # group chat
            result['group_chat_info'] = GroupChatInfoSerializer(
                instance.group_chat_info
            ).data
        
        return result


class FileDataSerializer(ChatBoxModelSerializer):
    """A serializer for file data objects.
    
    Notes
    -----
    Currently, there are no changable fields for a `FileData`, so all
    the fields on the serializer are read-only. The file data can be
    created or deleted as a whole, but the fields themselves cannot
    change.
    """
    
    file = serializers.SerializerMethodField('get_file_url')
    
    def get_file_url(self, instance):
        # MEDIA_URL is prepended to the file url by Django;
        # we don't have to do it.
        
        if is_media_url_absolute:
            return instance.file.url
        
        return self.context['request'].build_absolute_uri(instance.file.url)
    
    class Meta:
        model = FileData
        fields = ['file_id', 'file_type', 'file']
        read_only_fields = fields


class MessageSerializer(ChatBoxModelSerializer):
    """An updatable serializer for message objects."""
    
    user = serializers.ReadOnlyField(source=f"user.{chatbox_settings.USER_ID_FIELD}")
    chat = serializers.ReadOnlyField(source='chat.chat_id')
    
    class Meta:
        model = Message
        fields = ['message_id', 'user', 'chat', 'sent_at', 'file_data', 'text']
        
        # 'sent_at' is read-only by default, because it has "auto_now_add=True",
        # but still we explicitly specify it here.
        read_only_fields = ['message_id', 'sent_at', 'user', 'chat']

    def to_representation(self, instance):
        result = super().to_representation(instance)
        qp = self.context['query_params']

        if instance.file_data is None:
            del result['file_data']
        else:
            result['file_data'] = FileDataSerializer(
                instance.file_data,
                context=self.context
            ).data
        
        # Subclasses might remove certain fields, therefore we only
        # do the expansion if the field is present.
        if qp['expand_user'] and 'user' in self.fields:
            result['user'] = MinimalUserSerializer(instance.user).data
        
        if qp['expand_chat'] and 'chat' in self.fields:
            result['chat'] = MinimalChatSerializer(
                instance.chat, expand_peer=self.expand_peer
            ).data
        
        return result


class ChatMessageSerializer(MessageSerializer):
    """A serializer for messages belonging to a specific chat.
    
    Notes
    -----
    We don't include `chat`, as the message(s) should belong to 
    the same chat, and the chat itself should be identified by some
    other means, typically through URL kwargs.
    """
    
    chat = None
    
    class Meta(MessageSerializer.Meta):
        fields = without(MessageSerializer.Meta.fields, ['chat'])
        read_only_fields = without(MessageSerializer.Meta.read_only_fields, ['chat'])


class GroupChatInfoSerializer(ChatBoxModelSerializer):
    class Meta:
        model = GroupChatInfo
        fields = ['group_name']


class WriteOnlyGroupChatSerializer(ChatBoxModelSerializer):
    group_chat_info = GroupChatInfoSerializer()

    class Meta:
        model = Chat
        fields = ['group_chat_info']
    
    def create(self, validated_data): 
        # We take care of the creation entirely by ourselves.
        group_chat_info = validated_data.pop('group_chat_info')
        chat = Chat.objects.create_group_chat(
            creator=self.context['request'].user,
            group_name=group_chat_info['group_name']
        )
        return chat
    
    def update(self, instance, validated_data):
        # Currently, the only part of a group chat that can
        # be updated is the `chat.group_chat_info`. Since the
        # values are already validated, we directly pass them
        # to the `.update()` of the serializer rather than on
        # initialization.
        group_chat_info = validated_data.pop('group_chat_info')
        GroupChatInfoSerializer().update(
            instance.group_chat_info,
            group_chat_info
        )
        
        # If, later, there was any other non-nested fields,
        # this would take care of them.
        return super().update(instance, validated_data)
        

class WriteOnlyMutualChatSerializer(ChatBoxModelSerializer):
    # If the user id field was fixed, we could have used a 
    # normal `PrimaryKeyRelatedField` instead.
    peer = serializers.SlugRelatedField(
        slug_field=chatbox_settings.USER_ID_FIELD,
        queryset=get_user_model().objects.all(),
        
        # `peer` is only required for creation; it's not
        # needed for updates.
        required=False
    )
    
    class Meta:
        model = Chat
        fields = ['peer']
    
    def validate(self, attrs):
        """Validate the only field `peer` based on the action.
        
        Here we mandate that `peer` must be present for creation.

        Notes
        -----
        We take this as an assumption for overriding some other
        methods in this serializer.
        """
        if not self.instance and 'peer' not in attrs:
            raise ValidationError(
                "'peer' must be present for creating mutual chats"
            )
        
        return attrs
    
    def to_internal_value(self, data):
        # Ignore `peer` for update operations.
        if self.instance:
            data.pop('peer', None)
        
        return super().to_internal_value(data)
    
    def create(self, validated_data):
        # We take care of the creation entirely by ourselves.
        peer = validated_data.pop('peer')
        return Chat.objects.create_mutual_chat(
            creator=self.context['request'].user,
            peer=peer
        )
    
    # Currently we have no field other than `peer`, which is
    # ignored for updates. If we later had other fields such
    # as nested ones which needed special handling, use this.
    #
    # def update(...):
    #    ...
        

class ChatSerializer(ChatBoxModelSerializer):
    """A serializer for chat objects.
    
    Notes
    -----
    We delegate write operations to other write-only serializers
    based on the `chat_type` given. The main reason for this is
    so that we can simplify validations and the management of
    fields. Each chat type requires different validations and
    different sets of fields (e.g., `group_chat_info` and `peer`
    are mutually exclusive); rather than lumping all of this logic
    into a single serializer in a cumbersome way, we just use
    separate serializers upon write for each chat type.
    """
    
    last_message = ChatMessageSerializer()
    
    class Meta:
        model = Chat
        fields = ['chat_id', 'created_at', 'chat_type', 'last_message']
        read_only_fields = ['chat_id', 'created_at', 'last_message']
        extra_kwargs = {
            # `chat_type` is required for creation, but
            # it is not needed for updates.
            'chat_type': {'required': False}
        }
    
    def to_representation(self, instance):
        result = super().to_representation(instance)
        qp = self.context['query_params']
        
        if instance.chat_type == Chat.ChatTypeChoices.MUTUAL:
            result['peer'] = get_peer_representation(
                chat=instance,
                user=self.context['request'].user,
                expand=qp['expand_peer']
            )
        else:
            result['group_chat_info'] = GroupChatInfoSerializer(
                instance.group_chat_info
            ).data
        
        return result
    
    def validate(self, attrs):
        """Validate the only field `chat_type` based on the action.

        Notes
        -----
        Here we mandate that `chat_type` must be present for creation.
        We take this as an assumption for overriding some other methods
        in this serializer.
        """
        if not self.instance and 'chat_type' not in attrs:
            raise ValidationError(
                "'chat_type' must be present for chat creation"
            )
        
        return attrs
    
    def delegate_write(self, chat_type, instance=None):
        # Don't include `chat_type` in the data given
        # to the chosen serializer for writing.
        initial_data = self.initial_data.copy()
        initial_data.pop('chat_type', None)
        
        if chat_type == Chat.ChatTypeChoices.MUTUAL:
            chosen_serializer_class = WriteOnlyMutualChatSerializer
        else:  # group chat
            chosen_serializer_class = WriteOnlyGroupChatSerializer
        
        serializer_kwargs = {
            'data': initial_data,
            'context': self.context,
        }
        
        if instance:  # update
            serializer_kwargs['instance'] = instance

        serializer = chosen_serializer_class(**serializer_kwargs)
        serializer.is_valid(raise_exception=True)
        return serializer.save()
    
    def create(self, validated_data):
        return self.delegate_write(
            chat_type=validated_data['chat_type']
        )
    
    def update(self, instance, validated_data):
        return self.delegate_write(
            chat_type=validated_data['chat_type'],
            instance=instance
        )

