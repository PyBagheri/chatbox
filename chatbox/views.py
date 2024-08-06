from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated


from chatbox.models import (
    Chat,
    Message
)
from chatbox.serializers import (
    MessageSerializer,
    ChatMessageSerializer,
    ChatSerializer,
)
from chatbox.qparams import (
    ExpandUserChatPeerQueryParams,
    ChatMessageFilterQueryParams,
)
from chatbox.permissions import (
    ChatPrivileges,
    CoMemberMessagePerms
)
from chatbox.decorators import (
    list_viewset_action
)
from chatbox.pagination import (
    MessagePagination,
    ChatPagination
)


class ChatMessageViewSet(
    viewsets.mixins.ListModelMixin,
    viewsets.mixins.CreateModelMixin,
    viewsets.GenericViewSet
):
    """A viewset for creating or listing the messages belonging to the given chat.
    
    This viewset is meant to be invoked by `ChatViewSet`, which gives it the
    `chat` kwarg. The necessary permission checks related to the chat must
    be done by `ChatViewSet`, and the permissions on this viewset should only
    account for messages of the chat, not the chat itself.
    """
    
    serializer_class = ChatMessageSerializer
    pagination_class = MessagePagination
    
    # Since this viewset is meant to be used as a subset of the `ChatViewSet`,
    # the permissions here are only extensions to those used in `ChatViewSet`,
    # and are checked after them.
    #
    # Currently, there are no permissions on this viewset, becasue if someone
    # has access to the chat (checked by `ChatViewSet`), then they are allowed
    # to list messages or create them. In the future, we might implement it so
    # that the admins can specify the types of messages that can be sent. There
    # might also be rate limit (slow mode) for chats. In these cases, it would
    # make sense to implement them as permissions and place them here.
    permission_classes = []
    
    def get_queryset(self):
        serializer = ChatMessageFilterQueryParams(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        qp = serializer.validated_data
        
        queryset = Message.objects.filter(chat=self.kwargs['chat'])
        
        if qp['unread']:
            queryset = queryset.unread()
            
        return queryset

    def perform_create(self, serializer):
        serializer.save(chat=self.kwargs['chat'], user=self.request.user)


class ChatViewSet(viewsets.ModelViewSet):
    # `chat_id` is the UUID, not the sequential id.
    lookup_field = 'chat_id'
    lookup_url_kwarg = 'chat_id'
    
    permission_classes = [IsAuthenticated, ChatPrivileges]
    
    serializer_class = ChatSerializer
    pagination_class = ChatPagination
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        serializer = ExpandUserChatPeerQueryParams(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        context['query_params'] = serializer.validated_data
        return context

    def get_queryset(self):
        return Chat.objects.of_user(
            self.request.user
        ).annotate_last_message(
            include_user=True
        )
    
    @list_viewset_action(ChatMessageViewSet, actions=['list', 'create'], detail=True)
    def message(self, request, chat_id):
        return {
            'chat': self.get_object()
        }


class MessageViewSet(
    # Everything except `CreateModelMixin` and `ListModelMixin`,
    # because sending messages is done through the `ChatMessageViewSet`
    # on a sub-URL of the chat resource, and listing messages
    # is currently only supported on a per-chat basis. Currently
    # I don't know of a way to retrieve all the messages belonging
    # to a certain user in a non-resource-intensive manner.
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.GenericViewSet
):
    """A viewset for the messages from the chats that the authenticated user is a member of."""
    
    # `message_id` is the UUID, not the sequential id.
    lookup_field = 'message_id'
    lookup_url_kwarg = 'message_id'
    
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated, CoMemberMessagePerms]
    pagination_class = MessagePagination
    
    def get_queryset(self):
        return Message.objects.for_user(self.request.user)
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        serializer = ExpandUserChatPeerQueryParams(data=self.request.query_params)
        serializer.is_valid(raise_exception=True)
        context['query_params'] = serializer.validated_data
        return context
