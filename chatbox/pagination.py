from rest_framework.pagination import BasePagination
from rest_framework.response import Response
from rest_framework.utils.urls import (
    replace_query_param,
    remove_query_param
)

from django.db import models

from chatbox.qparams import (
    MessagePaginationQueryParams,
    ChatPaginationQueryParams
)


class MessageRelatedPagination(BasePagination):
    query_params_serializer = MessagePaginationQueryParams
    message_id_lookup = 'message_id'
    
    def paginate_queryset(self, queryset, request, view=None):
        # Used for older/newer links.
        self.request = request
        
        serializer = self.query_params_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        qp = serializer.validated_data
        
        # the name of `reverse` is rather counter-intuitive, as normally
        # the messages are ordered from the newest to the oldest, but 
        # with this query parameter, the order becomes from the oldest
        # to the newest.
        self.reverse = qp['reverse']
        
        if self.reverse:
            # Older to newer
            ordering = [self.message_id_lookup]
        else:
            # Newer to older
            ordering = [f'-{self.message_id_lookup}']

        queryset = queryset.annotate(
            _pagination_message_id=models.F(self.message_id_lookup)
        )
        
        comparison = 'gt' if self.reverse else 'lt'
        
        # `offset_message_id` is EXCLUSIVE.
        if offset_message_id := qp.get('offset_message_id', None):
            queryset = queryset.filter(**{
                f'{self.message_id_lookup}__{comparison}': offset_message_id
            })

        # The default/max/min values are set and validated
        # in the serializer.
        limit = qp['limit']

        queryset = queryset.order_by(*ordering)[:limit]
        
        qs_length = len(queryset)
        
        if not qs_length:
            return queryset

        # Note that these items are not necessarily `Message` objects.
        # They might be, for example, `Chat` objects too.
        last_in_page_item = queryset[qs_length-1]
        first_in_page_item = queryset[0]
        
        if self.reverse:
            self.older_edge_item = first_in_page_item
            self.newer_edge_item = last_in_page_item
        else:
            self.older_edge_item = last_in_page_item
            self.newer_edge_item = first_in_page_item
        
        return queryset
    
    def get_older_link(self):
        if not hasattr(self, 'older_edge_item'):
            return None

        url = self.request.build_absolute_uri()
        if self.reverse:
            url = remove_query_param(url, 'reverse')
        url = replace_query_param(
            url,
            'offset_message_id',
            self.older_edge_item._pagination_message_id
        )
        return url

    def get_newer_link(self):
        if not hasattr(self, 'newer_edge_item'):
            return None
        
        url = self.request.build_absolute_uri()
        if not self.reverse:
            url = replace_query_param(url, 'reverse', 'true')
        url = replace_query_param(
            url,
            'offset_message_id',
            self.newer_edge_item._pagination_message_id
        )
        return url
    
    def get_paginated_response(self, data):
        # Due to the dynamic nature of messages, chats, etc., both the
        # 'older' and 'newer' links are always present, and the end is
        # only detected once the clients retrieve an empty page.
        return Response({
            'older': self.get_older_link(),
            'newer': self.get_newer_link(),
            
            'results': data
        })


class MessagePagination(MessageRelatedPagination):
    pass


class ChatPagination(MessageRelatedPagination):
    query_params_serializer = ChatPaginationQueryParams
    
    # `message` will be backward-related to the `Chat` object.
    message_id_lookup = 'message__message_id'
