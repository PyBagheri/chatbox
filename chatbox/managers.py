from django.db import models

# We don't import the models directly to avoid
# circular imports.
import chatbox.models


class ChatManager(models.Manager):
    def create_mutual_chat(self, *, creator, peer):
        chat = self.create(
            chat_type=chatbox.models.Chat.ChatTypeChoices.MUTUAL
        )
        chat.members.add(creator, peer)
        return chat
    
    def create_group_chat(self, *, creator, group_name):
        group_chat_info = chatbox.models.GroupChatInfo.objects.create(
            group_name=group_name
        )
        chat = self.create(
            chat_type=chatbox.models.Chat.ChatTypeChoices.GROUP,
            group_chat_info=group_chat_info
        )
        chat.members.add(creator)
        return chat
