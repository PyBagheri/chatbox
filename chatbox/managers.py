from django.db import models
from django.db import transaction

# We don't import the models directly to avoid
# circular imports.
import chatbox.models


class ChatManager(models.Manager):
    @transaction.atomic(durable=True)
    def create_mutual_chat(self, *, creator, peer):
        chat = self.create(
            chat_type=chatbox.models.Chat.ChatTypeChoices.MUTUAL
        )
        chat.members.add(creator, peer)
        
        # Create the service message indicating that the chat has been created.
        chatbox.models.Message.objects.create(
            chat=chat,
            service_action=chatbox.models.Message.ServiceMessageActionChoices.CREATE_CHAT
        )
        
        return chat
    
    @transaction.atomic(durable=True)
    def create_group_chat(self, *, creator, group_name):
        group_chat_info = chatbox.models.GroupChatInfo.objects.create(
            group_name=group_name
        )
        chat = self.create(
            chat_type=chatbox.models.Chat.ChatTypeChoices.GROUP,
            group_chat_info=group_chat_info
        )
        chat.members.add(creator)
        
        # Create the service message indicating that the chat has been created.
        chatbox.models.Message.objects.create(
            chat=chat,
            service_action=chatbox.models.Message.ServiceMessageActionChoices.CREATE_CHAT
        )
        
        return chat
