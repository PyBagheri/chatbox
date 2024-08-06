from rest_framework.decorators import action
import functools


LIST_CREATE_ACTION_METHOD_MAPPING = {'list': 'get', 'create': 'post'}


def list_viewset_action(viewset_class, *, actions, detail):
    """Decorate the kwargs function for a list/create nested viewset action.
    
    The kwarg function (i.e., the decorated function) must return a dict that
    will be passed to the nested view, and will be thus available on its `kwargs`
    dictionary, which is set by its `dispatch`.
    
    Notes
    -----
    This decorator only supports the `list` and/or `create` actions, and is
    like a nested router that can be used on viewsets like dynamic actions
    to make another viewset handle the sub-URI entirely on its own. The is
    a minimal version of what libraries such as `drf-nested-routers` provide.
    Since we don't want nested resource URI's to get too complex, we only
    allow list or create actions which require no key, and delegate the
    key-requiring actions such as update or delete to a dedicated resource
    URI instead of a nested one. Using this decorator, the final URI will
    look like `resource1/item/resource2/`.
    
    The advantage of using this decorator over using routers with manually
    defined URL's is that the nested viewset complies with the permissions
    on the main viewset (i.e., the nested viewset is only used if the
    permissions on the main viewset allows), and also we can pass information
    from the main viewset to the nested viewset (by using the kwarg function),
    especially the main object or queryset (retrieved by `get_object()` and
    `get_queryset()` on the main viewset) which are themselves subject to the
    filters on the main viewset. Basically, it makes it so that the nested
    queryset has much less concern about how upper-level resource is handled,
    and simply just uses its value.
    
    If there are conflicts between the main viewset and the nested viewset
    on how the *upper-level* resource should be handled (e.g., the `resource1`
    in the above example), then this decorator is probably not useful. Instead
    register a custom URL in your router (which has kwargs for both resources)
    and handle the upper-level resource manually.
    """
    
    methods = []
    as_view_mapping = {}
    for act in actions:
        if act not in LIST_CREATE_ACTION_METHOD_MAPPING.keys():
            raise ValueError("this decorator only supports 'list' and 'create' actions")
        
        method = LIST_CREATE_ACTION_METHOD_MAPPING[act]
        methods.append(method)
        as_view_mapping[method] = act
    
    class OverriddenViewSet(viewset_class):
        # Since we'll pass the DRF's `Request` object instead,
        # we just eliminate the part where it creates a DRF
        # `Request` from a `HttpRequest`, and return the request
        # object itself. Passing the actual `HttpRequest` causes
        # certain issues, such as reading the request body twice,
        # which raises errors.
        def initialize_request(self, request, *args, **kwargs):
            return request
    
    view = OverriddenViewSet.as_view(as_view_mapping)

    def decorator(func):
        @functools.wraps(func)
        def final(self, request, *args, **kwargs):
            viewset_kwargs = func(self, request, *args, **kwargs)
            
            # The kwargs will be set as the `kwargs` attribute of
            # the view instance. Plus, if we return a `HttpResponse`
            # instead of DRF's `Response` (as we do here), it will
            # directly use it.
            return view(request, **viewset_kwargs)
            
        return action(methods=methods, detail=detail)(final)
    
    return decorator
