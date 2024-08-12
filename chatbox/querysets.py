from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.contrib.postgres.expressions import ArraySubquery

import chatbox.models


class Any(models.Lookup):
    lookup_name = 'any'
    
    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = list(lhs_params) + list(rhs_params)
        return "%s = ANY(%s)" % (lhs, rhs), params

models.Field.register_lookup(Any)


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
        # This generates something like:
        # `... WHERE chatbox_chat.id = ANY( ARRAY( ... ) ) ...`
        #
        # This is an unusual optimization. It basically forces PostgreSQL to first
        # find the ID's of all the chats that the user is a member of, and then get
        # each chat using the index for its ID. It can also affect joins on further
        # tables later (such as preventing a hash join to messages when retrieving
        # the last message for each chat. I don't know why this happens). There are
        # other techniques to force PostgreSQL to first retrieve the list of all
        # the chat ID's for the user, such as the `OFFSET 0` hack or materialized
        # CTE's, but the `array` version also affects further joins (as noted above)
        # in a way that makes them faster (I don't know why it affects them this way).
        #
        # For just returning the chats that the user is a member of, PostgreSQL seems
        # to choose the efficient plan, but the materialized query (using array(...) or
        # materialized CTE's or `OFFSET 0`) makes it faster. However, when it comes to
        # joining to further tables (such as for when we want to get the last message
        # for each chat) the `array` version makes a lot of difference (even the other
        # materialized versions fail to make it faster. It seems that the array trick
        # is the only way).
        # 
        # For ONLY returning the chats that the user is a member of (without further joins),
        # if the data is big enough, PostgreSQL usually chooses one of these plans:
        #
        # 1. retrieve all the memberships and then find each chat by an index scan
        #    using the chat's ID. This seems to be better most of the time and is
        #    what we intend for.
        # 2. a merge join with a index scan for *all* the chats and the memberships
        #    of the specified user. Usually when PostgreSQL chooses this, it actually
        #    performs well, but is slower than (1).
        # 3. a hash join with a FULL sequence scan on the chats table. This makes the
        #    execution even slower.
        #
        # This needs further investigation to understand why PostgreSQL does these.
        # The above information are tested in PostgreSQL 14 and 17-beta3.
        #
        # Finally, it should be noted that the plans are heavily data-dependent. Also
        # our assumption is that each user is member of only a couple of thousand chats
        # on average. Also checking if an item is in an array or not must be one with
        # the `= ANY(...)` operator, so we had to implement it manually above.
        return self.filter(id__any=ArraySubquery(
            chatbox.models.Membership.objects.filter(user=user).values('chat_id')
        ))
        
    def annotate_last_message(self, include_user=False):
        backward_annotation_relations = ['message']
        if include_user:
            backward_annotation_relations.append('message__user')
        
        # Every chat has at least one message: the service message
        # for creating the chat. With the use of this fact, the query
        # for retrieving the chats along with their last messages
        # (and possibly ordering them) is greatly simplified and also
        # optimized (with the help of a proper index on messages).
        #
        # By specifying a filter on the backward relation `message`,
        # Django will perform a JOIN from the chat to the messages in
        # that chat, which will cause the chat rows to be duplicated
        # to cover all the messages, but only one row will be returned
        # per chat (the one attached to its last message) by the use of
        # the specified condition.
        return self.filter(
            message=models.Subquery(
                chatbox.models.Message.objects.filter(
                    chat=models.OuterRef('pk')
                ).order_by('-message_id').values('pk')[:1]
            )
        ).annotate_backward_related(
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
        # Unlike the case of `ChatQuerySet.of_user()`, we don't need manual
        # optimizations for this, because it's only intended as a permission
        # check for retrieveing a SINGLE message (as explained in the docstring).
        return self.filter(
            chat__members=user
        )
    
    def unread(self, *, chat, user):
        """Return the messages in `chat` which are unread for `user`."""

        return self.filter(
            chat=chat,
            
            # `message_id` has the timestamp as part of it, so we can sort the
            # messages based on it. See `chatbox.utils.generate_message_id` for
            # more details.
            message_id__gt=models.Subquery(
                chatbox.models.Membership.objects.filter(
                    user=user, chat=chat
                ).values('last_seen_message_id')
            )
        )
