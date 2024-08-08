from rest_framework import permissions

from chatbox.models import (
    Chat,
    AdminRole
)

from http import HTTPMethod


class ChatPrivileges(permissions.BasePermission):
    def has_object_permission(self, request, view, chat):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # For a mutual chat, both peers have full permission on the chat,
        # but deletion, etc. works differently; e.g., when a peer deletes
        # the chat, they only get removed from the members rather than the
        # chat object getting deleted entirely (in order to delete the chat
        # entirely, both peers must "delete" the chat).
        if chat.chat_type == Chat.ChatTypeChoices.MUTUAL:
            return True
        
        # ----- GROUP CHATS -----
        
        # The creator of a group chat has all the permissions.
        if chat.group_chat_info.creator == request.user:
            return True
        
        # Admins may only have update permissions, and cannot delete the chat.
        if request.method in (HTTPMethod.PUT, HTTPMethod.PATCH):
            if AdminRole.objects.filter(
                group_chat_info__chat=chat,
                user=request.user,
                privileges__contains=[AdminRole.AdminPrivileges.CHANGE_GROUP_INFO]
            ).exists():
                return True

        return False


class CoMemberMessagePerms(permissions.BasePermission):
    def has_object_permission(self, request, view, message):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # ----- NON-SAFE METHODS -----
        
        # Currently, service messages cannot be deleted or edited.
        # This might change later.
        if message.service_action is not None:
            return False
        
        # ----- NON-SERVICE MESSAGE -----
        
        # The author of the message has all the permissions.
        if message.user == request.user:
            return True
        
        # ----- NON-AUTHOR USER -----
        
        # In a mutual chat, the peer does NOT have permissions
        # for non-safe methods.
        if message.chat.chat_type == Chat.ChatTypeChoices.MUTUAL:
            return False
        
        # ----- GROUP CHAT -----
        
        # Here, the only possible permission is for the admins
        # of a group chat to delete the messages of a user (the
        # admin must have the privilege to delete messages).
        # Admins cannot edit the messages of other users. The
        # creator can delete the messages of other admins, but
        # in order for an admin (with the message deletion privilege)
        # to be able to delete the messages of another admin,
        # the target admin MUST NOT have the message deletion
        # privilege.
        
        if request.method != HTTPMethod.DELETE:
            return False
        
        # ----- DELETE METHOD -----
        
        if message.chat.creator == request.user:
            return True
        
        # ----- NON-CREATOR USER -----
        
        # Nobody can delete the messages of the creator
        # of the group chat.
        if message.user == message.chat.creator:
            return False
        
        # ----- MESSAGE AUTHOR IS NOT THE CREATOR -----
        
        # Check if the requesting user is an admin with the message
        # deletion privilege or not.
        if not AdminRole.objects.filter(
            group_chat_info=message.chat.group_chat_info,
            user=request.user,
            privileges__contains=[AdminRole.AdminPrivileges.DELETE_MESSAGE]
        ).exists():
            return False
        
        # ----- USER IS AN ADMIN WITH THE MESSAGE DELETION PRIVILEGE -----
        
        # Check if the author of the message is an admin with the message
        # deletion privilege or not.
        if not AdminRole.objects.filter(
            group_chat_info=message.chat.group_chat_info,
            user=message.user,
            privileges__contains=[AdminRole.AdminPrivileges.DELETE_MESSAGE]
        ).exists():
            return True
        
        # ----- MESSAGE AUTHOR IS AN ADMIN WITH THE MESSAGE DELETION PRIVILEGE -----
        
        return False
