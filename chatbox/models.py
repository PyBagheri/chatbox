from typing import Iterable
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
from chatbox.utils import (
    chatbox_settings,
    generate_message_id
)

from pathlib import Path


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
    class Meta:
        constraints = [
            # Used for finding the chats that a user is a member of.
            models.UniqueConstraint('user_id', 'chat_id', name='membership_userid_chatid_idx')
        ]
    
    # In case a user is deleted, we want to keep the membership as a "ghost" user.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True)
    
    # If the chat itself is deleted, all the memberships must also be deleted.
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    
    joined_at = models.DateTimeField(auto_now_add=True)

    # This is used to determine and filter for new messages. We use '0'
    # as default as all `message_id` strings will compare to be greater
    # than '0' since their first hex digit is always greater than 0.
    last_seen_message_id = models.CharField(default='0', max_length=20)


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
    class ServiceMessageActionChoices(models.TextChoices):
        CREATE_CHAT = 'CC', 'Create Chat'
        
    class Meta:
        constraints = [
            # Notice that having a unique b-tree index rather than a normal
            # b-tree index doesn't have an overhead, as the database has to
            # scan the index to find the page to write it to anyways.
            
            models.UniqueConstraint('message_id', name='msg_msgid_unique_idx'),

            # Use cases:
            # 1. Finding the last messages in a chat.
            # 2. Pagination of messages in chats.
            #
            # Note that `message_id` has the timestamp as part of it, so we
            # can do the sortings based entirely on `message_id`. See the
            # function `chatbox.utils.generate_message_id`.
            models.UniqueConstraint(fields=['chat_id', 'message_id'], name='msg_chatid_msgid_unique_idx'),
        ]
    
    # We leave the default sequential ID as the primary key.
    # We generate the `message_id` using the util function
    # described `chatbox.utils`. See its docstring and comments
    # for further information.
    message_id = models.CharField(unique=True, max_length=20)
    
    # The cases where `user` might be blank:
    # 1. If the user is deleted, we want to keep their messages
    #    as from a "ghost" user.
    # 2. A service message *might* not have a user.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             blank=True, null=True)
    
    # If the chat itself is deleted, all the messages must also be deleted.
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE)
    
    # We don't specify `auto_now_add=True` here, and instead implement
    # the logic in model's `save()` method. This is because otherwise
    # we could not access its value which is necessary for generating
    # the `message_id` field.
    sent_at = models.DateTimeField()
    
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
    
    # Similar to Telegram's service message actions.
    service_action = models.CharField(choices=ServiceMessageActionChoices, max_length=2,
                                      blank=True, null=True)

    objects = models.Manager.from_queryset(MessageQuerySet)()

    def save(self, *args, **kwargs):
        if not self.pk:  # upon creation
            sent_at = timezone.now()
            self.sent_at = sent_at
            self.message_id = generate_message_id(sent_at)
            
        return super().save(*args, **kwargs)
