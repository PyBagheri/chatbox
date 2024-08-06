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
    message_datetime_lookup = 'sent_at'
    message_uuid_lookup = 'message_id'
    
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
            ordering = (
                self.message_datetime_lookup,
                self.message_uuid_lookup
            )
        else:
            # Newer to older
            ordering = (
                f'-{self.message_datetime_lookup}',
                f'-{self.message_uuid_lookup}'
            )

        # Django imposes that annotations must happen before `.union()`.
        queryset = queryset.annotate(
            _pagination_message_datetime=models.F(self.message_datetime_lookup),
            _pagination_message_uuid=models.F(self.message_uuid_lookup)
        )
        
        # `offset_datetime` is INCLUSIVE.
        # `offset_message_id` is EXCLUSIVE.
        #
        # We imposed in the query params serializer that either both
        # of `offset_datetime` and `offset_message_id` should be given
        # or neither should be given. This is rather out of laziness
        # and that currently it works out well.
        if offset_datetime := qp.get('offset_datetime', None):
            offset_message_id = qp.get('offset_message_id')
            
            comparison = 'gt' if self.reverse else 'lt'
            
            q1 = queryset.filter(**{
                self.message_datetime_lookup: offset_datetime,
                
                # String comparison using the alphabetic order.
                f'{self.message_uuid_lookup}__{comparison}': offset_message_id
            })
            
            q2 = queryset.filter(**{
                f'{self.message_datetime_lookup}__{comparison}': offset_datetime,
            })
            
            # We use `UNION ALL` as there will be no duplicates and the
            # queries are mutually exclusive since they have different
            # datetimes.
            queryset = q1.union(q2, all=True)
                
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
            'offset_datetime',
            self.older_edge_item._pagination_message_datetime.timestamp()
        )
        url = replace_query_param(
            url,
            'offset_message_id',
            self.older_edge_item._pagination_message_uuid
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
            'offset_datetime',
            self.newer_edge_item._pagination_message_datetime.timestamp()
        )
        url = replace_query_param(
            url,
            'offset_message_id',
            self.newer_edge_item._pagination_message_uuid
        )
        return url
    
    def get_paginated_response(self, data):
        # Due to the dynamic nature of messages, chats, etc., both the
        # 'older' and 'newer' links are always present, and the end is
        # only detected once the clients retrieve an empty page. Plus,
        # the older/newer links are based on the datetime of the last
        # item in the page; this means that if two or more messages in
        # the end of the page share the same datetime (which is rather
        # unlikely for a single user), then the older/newer page will
        # contain repetitive results. Clients must take care of this
        # themselves.
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
    message_datetime_lookup = 'message__sent_at'
    message_uuid_lookup = 'message__message_id'
