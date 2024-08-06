from django.db import models
from django.db.models.constants import LOOKUP_SEP

import chatbox.models


class AdvancedQuerySet(models.QuerySet):
    def annotate_backward_related(self, *related_list, only=None, **labels):
        """Set the field values of the backward-related models as annotations."""
        # dict[compound relation, list of fields]
        related_and_fields_map = {}
        
        # Make it possible to do this many times.
        if hasattr(self.query, '_backward_relation_labels_map'):
            labels.extend(self.query._backward_relation_labels_map)
            related_and_fields_map.extend(self.query._backward_relation_fields_map)
        
        annotation_map = {}
        
        for label in labels:
            if LOOKUP_SEP in label:
                raise ValueError('labels can only be applied to top-level relations')   
        
        if only:
            for related_compound_field in only:
                related_compound, _, field_name = related_compound_field.rpartition(LOOKUP_SEP)
                
                if related_compound in related_and_fields_map:
                    related_and_fields_map[related_compound].append(
                        field_name
                    )
                else:
                    related_and_fields_map[related_compound] = [field_name]
                    
                annotation_map[related_compound_field] = models.F(related_compound_field)
            
            # We enforce that the primary key field must be included.
            # This is especially important when we want to check if
            # a related object is empty or not (as some fields may
            # or may not be set, but if we always have the primary
            # key, we can always do this check in a consistent way).
            for related_compound in related_and_fields_map:
                related_and_fields_map[related_compound].append('pk')
                pk_lookup = LOOKUP_SEP.join([related_compound, 'pk'])
                annotation_map[pk_lookup] = models.F(pk_lookup)
        else:
            # The order of kwarg items for annotation here is the reverse
            # of what we have in the normal `.annotate()`. This is so that
            # we only have one label per backward relation (as otherwise
            # it makes no sense since the values are all the same) and also
            # to make it more clear as to what the method does.
            #
            # We call it compound because each relation that is specified
            # can be a chain of relations with nested models. For example,
            # 'message__user__profile' that is backward-related to 'chat'.
            # Note that when the given relation is compound, all of the
            # related models in the chain will be processed and added to
            # the model instance.
            for related_compound in related_list:
                related_compound_parts = []
                last_model = self.model
                
                for part in related_compound.split(LOOKUP_SEP):
                    related_compound_parts.append(part)
                    related_lookup = LOOKUP_SEP.join(related_compound_parts)
                    
                    # Get the next related model in the compound chain.
                    last_model = last_model._meta.get_field(part).related_model
                    
                    # If related model 'A' is given along with another related
                    # model that is nested in 'A', such as 'A__B', then 'A' will
                    # be processed twice. Therefore we skip it if it already
                    # exists.
                    if related_lookup in related_and_fields_map:
                        continue
                                    
                    fields_list = []
                    
                    # We only include concrete fields (i.e., we don't include
                    # nested backward relations BECAUSE they must be specified
                    # explicitly in the args for this method). For example, we
                    # should specify 'A__B' along with 'A' to also include the
                    # model 'B'.
                    for field in last_model._meta.concrete_fields:
                        # Using `attname` instead of `name`. These will be the
                        # names of the actual attributes that hold the concrete
                        # values. I'm not sure if this makes any difference, even
                        # for foreign keys (as specifying the normal name in the
                        # annotation still selects the primary key).
                        full_lookup = LOOKUP_SEP.join(
                            [*related_compound_parts, field.attname]
                        )
                        annotation_map[full_lookup] = models.F(full_lookup)
                        fields_list.append(field.attname)
                    
                    related_and_fields_map[related_lookup] = fields_list
    
        # We set the attributes on query as the `self.query` persists
        # upon chain or clone.
        self.query._backward_relation_labels_map = labels
        self.query._backward_relation_fields_map = related_and_fields_map
        
        return self.annotate(**annotation_map)

    # TODO: search if there is any better way to do this without
    # accessing the private API.
    def _fetch_all(self):
        super()._fetch_all()
        
        # Keep with the default if no backward annotation is specified.
        if not hasattr(self.query, '_backward_relation_labels_map'):
            return

        # By sorting the name of the relations, nested relations come
        # after the upper-level ones. For example, 'message__user' comes
        # after 'message'. This way, when we set the attributes for the
        # nested relations, the upper-level relations have already been
        # set, and thus we can set the attributes on them; For example,
        # the `.message` attribute must have been set before we set the
        # `.message.user`, like `setattr(obj.message, 'user', user)`.
        sorted_compounds_list = list(sorted(self.query._backward_relation_fields_map.keys()))
        
        for item in self._result_cache:
            for related_compound in sorted_compounds_list:
                # `current`: current related model's name.
                attr_path, sep, current = related_compound.rpartition(LOOKUP_SEP)
                
                # A top-level related attribute, where we must set the attribute
                # with the name given in the labels for backward annotation. As
                # an example, the backward-related `message` of a `Chat`, might
                # be its `last_message`.
                if not sep:
                    related_model = self.model._meta.get_field(current).related_model
                    obj = related_model()
                    
                    # If no label is set, use the related query name.
                    label = self.query._backward_relation_labels_map.get(current, current)
                    
                    setattr_target = item
                    setattr_attr_name = label
                else:
                    # Get the innermost instance.
                    instance = item
                    parts = attr_path.split(LOOKUP_SEP)
                    
                    first_part = parts[0]
                    
                    # The first part is the top-level one in the related compound,
                    # which might have an label/alias set for it. If there was no
                    # label, simply use the related query name.
                    first_attr_name = self.query._backward_relation_labels_map.get(first_part, first_part)
                    
                    instance = getattr(instance, first_attr_name, None)
                    
                    for part in parts[1:]:
                        # The upper-level related model instance might be null;
                        # in this case, simply ignore its nested/inner related
                        # models (the ignoring part is completed with another
                        # check for `None` after this loop, below).
                        if instance is None:
                            break
                        
                        instance = getattr(instance, part, None)
                    
                    if instance is None:
                        continue
                
                    related_model = instance._meta.get_field(current).related_model
                    obj = related_model()
                    
                    setattr_target = instance
                    setattr_attr_name = current

                # Set the actual field values for the model instances that we set.
                for field_name in self.query._backward_relation_fields_map[related_compound]:
                    setattr(
                        obj,
                        field_name,
                        getattr(item, LOOKUP_SEP.join([related_compound, field_name]))
                    )
                
                # If the related object doesn't exist (i.e., the part of the
                # result row from the outer join that belongs to the related
                # model is null), then set it as `None` instead.
                if obj.pk is None:
                    setattr(setattr_target, setattr_attr_name, None)
                else:
                    setattr(setattr_target, setattr_attr_name, obj)


class ChatQuerySet(AdvancedQuerySet):
    def of_user(self, user):
        return self.filter(members=user)
        
    def annotate_last_message(self, include_user=False):
        backward_annotation_relations = ['message']
        if include_user:
            backward_annotation_relations.append('message__user')
        
        
        # TODO: This must be optimized (which will most likely need
        # a serious change).
        return self.annotate(
            r=models.Window(
                # By specifying the `message` in the `order_by` part, Django does
                # a LEFT OUTER JOIN from the chat to the messages in that chat,
                # which will cause the chat rows to be duplicated to cover all
                # the messages. Then we order the messages from the newest to the
                # oldest, and then use the first row in each 'window' (=similar
                # to group; note that here each window represents a chat), which
                # will be the chat that has its last message attached (=JOIN'ed)
                # to it.
                expression=models.functions.RowNumber(),
                
                # Similar to group by chat.
                partition_by='id',
                
                # The order is from the newest to the oldest.
                # In case the messages have the same timestamp,
                # we use their UUID to order them.
                order_by=('-message__sent_at', '-message__message_id')
            )
        ).filter(r=1).annotate_backward_related(
            *backward_annotation_relations,
            
            # Use the label `last_message` for the backward-related `message`.
            message='last_message',
        )


class MessageQuerySet(models.QuerySet):
    def for_user(self, user):
        """Return the messages that belong to a chat that `user` is a member of.
        
        This method should only be used to get a filtered set of messages from
        which a single message with known `message_id` can be chosen, which is
        a means of checking whether or not a user has access to a certain message.
        
        The use of this method for listing messages should be avoided altogether,
        because it's quite resource-intensive for the database as it requires
        certain operations that are basically full table scans (at least for
        PostgreSQL).
        """
        return self.filter(
            chat__members=user
        )
    
    def unread(self, *, chat, user):
        """Return the messages in `chat` which are unread for `user`."""
        
        # ROW() is bascially the same as a tuple in this case.
        # In fact in PostgreSQL, (t1, t2, ..., tn) is equivalent
        # to ROW(t1, t2, ..., tn) when n > 1. For n = 1, we have
        # to explicitly use the ROW().
        sent_at_and_message_id_row_construct = models.Func(
            models.F('sent_at'),
            models.F('message_id'),
            function='ROW',
            
            # This is dummy; just to keep Django from complaining.
            output_field=models.TextField()
        )
        
        return self.alias(
            sent_at_and_message_id_tuple=sent_at_and_message_id_row_construct
        ).filter(
            chat=chat,
            
            # This can be thought of as a union of two queries:
            # 1. The messages of the given chat where the timestamp equals
            #    `last_seen_message_datetime` but the message uuid is greater
            #    than `last_seen_message_id`.
            # 2. The messages of the given chat where the timestamp is greater
            #    than `last_seen_message_datetime`.
            #
            # We achieve this by this tuple comparison.
            sent_at_and_message_id_tuple__gte=models.Subquery(
                chatbox.models.Membership.objects.filter(
                    user=user, chat=chat
                ).values('last_seen_message_datetime', 'last_seen_message_id')
            )
        )
