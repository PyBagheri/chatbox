from django.db import models
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.utils import timezone
import uuid

from chatbox.managers import (
    ChatManager
)
from chatbox.querysets import (
    ChatQuerySet,
    MessageQuerySet
)
from chatbox.utils import chatbox_settings

from pathlib import Path


ALL_ZERO_UUID = uuid.UUID('00000000-0000-0000-0000-000000000000')


class Chat(models.Model):
    class ChatTypeChoices(models.TextChoices):
        MUTUAL = 'MU', 'Mutual Chat'
        GROUP = 'GR', 'Group Chat'
    
    # We leave the default sequential ID as the primary key.
    chat_id = models.UUIDField(unique=True, default=uuid.uuid4) ################# test pk and stuff ..??
    
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Membership')
    
    created_at = models.DateTimeField(auto_now_add=True)
    chat_type = models.CharField(choices=ChatTypeChoices, max_length=2)

    def get_peer(self, user):
        if self.chat_type != Chat.ChatTypeChoices.MUTUAL:
            raise RuntimeError("'get_peer()' can only be used on mutual chats")
        
        
        return self.members.exclude(pk=user.pk).first()

    objects = ChatManager.from_queryset(ChatQuerySet)()


class GroupChatInfo(models.Model):
    chat = models.OneToOneField(
        Chat, on_delete=models.CASCADE,
        related_name='group_chat_info'
    )
    
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,   ####################### test
        related_name='+'  # no reverse relation
    )
    
    group_name = models.CharField(
        max_length=chatbox_settings.GROUP_NAME_MAX_LENGTH
    )
    
    # We don't want a reverse relation on user objects for admin roles.
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='AdminRole', 
        related_name='+'  # no reverse relation
    )


class Membership(models.Model):
    # In case a user is deleted, we want to keep the membership as a "ghost" user.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True)
    
    # If the chat itself is deleted, all the memberships must also be deleted.
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    
    joined_at = models.DateTimeField(auto_now_add=True)

    # This is used to determine and filter for new messages.
    # We're storing these separately because the message itself
    # might be deleted. Also in case two messages have the same
    # datetime, we'll use their UUID to order them.
    last_seen_message_datetime = models.DateTimeField(default=timezone.now)
    last_seen_message_id = models.UUIDField(default=ALL_ZERO_UUID)


class AdminRole(models.Model):
    class AdminPrivileges(models.TextChoices):
        ADD_MEMBER = 'AM', 'Add Member'
        KICK_MEMBER = 'KM', 'Kick Member'
        DELETE_MESSAGE = 'DM', 'Delete Message'
        CHANGE_GROUP_INFO = 'GI', 'Change Group Info'
    
    # In case a user is deleted, we want to keep the admin role as a "ghost" user.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True)
    
    # If the group chat info itself is deleted (or its related chat, which would
    # cause a cascade deletion), all the admin roles must also be deleted.
    group_chat_info = models.ForeignKey(GroupChatInfo, on_delete=models.CASCADE)
    
    privileges = ArrayField(
        base_field=models.CharField(choices=AdminPrivileges, max_length=2)
    )


class FileData(models.Model):
    class FileTypeChoices(models.TextChoices):
        IMAGE = 'IM', 'Image'
        VIDEO = 'VD', 'Video'
        AUDIO = 'AD', 'Audio'
        GENERIC = 'GN', 'Generic'
    
    def get_file_path(self, filename):
        return Path(chatbox_settings.UPLOADED_FILES_RELATIVE_PATH) / self.file_id
        
    # We leave the default sequential ID as the primary key.
    file_id = models.UUIDField(unique=True, default=uuid.uuid4) ############## test pk and stuff
    
    # We store the file name separately from the `file` field,
    # as the name of the stored file on the server will be
    # different.
    file_name = models.CharField(
        max_length=chatbox_settings.UPLOADED_FILENAME_MAX_LENGTH
    )
    
    file_type = models.CharField(choices=FileTypeChoices, max_length=2)
    file = models.FileField(upload_to=get_file_path)


def string_not_empty(string):
    if string == "":
        raise ValidationError("'text' must be either None or not empty")


class Message(models.Model):
    class Meta:
        indexes = [
            # Use cases:
            # 1. Finding the last messages in a chat (this is why we have
            #    descending orders on the second and third columns).
            # 2. Pagination of messages in chats (the descending orders
            #    don't make a problem here, because we can look at the
            #    end of the index too).
            models.Index(fields=['chat_id', '-sent_at', '-message_id'], name='msg_chatid_sentat_msgid_idx'),
        ]
    
    # We leave the default sequential ID as the primary key.
    # Also note that if two messages have the same timestamp,
    # we sort them using their sequential ID.
    message_id = models.UUIDField(unique=True, default=uuid.uuid4)
    
    # In case a user is deleted, we want to keep their messages
    # as from a "ghost" user.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True)
    
    # If the chat itself is deleted, all the messages must also be deleted.
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    
    sent_at = models.DateTimeField(auto_now_add=True)
    
    file_data = models.ForeignKey(
        FileData, on_delete=models.PROTECT,
        blank=True, null=True
    )
    
    # When there is no text, we save it as null instead of an empty.
    # string. This makes the API clearer.
    text = models.TextField(
        max_length=chatbox_settings.MESSAGE_TEXT_MAX_LENGTH,
        blank=True, null=True, validators=[string_not_empty]  #################### test
    )

    objects = models.Manager.from_queryset(MessageQuerySet)()
