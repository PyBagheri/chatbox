from django.conf import settings
from chatbox import defaults


class _ChatboxSettingsRetriever:
    def __getattr__(self, name):
        if hasattr(settings, 'CHATBOX') and name in settings.CHATBOX:
            value = settings.CHATBOX.get(name)
        else:
            value = defaults.CHATBOX.get(name, None)
            if not value:
                raise KeyError("No such setting '%s'")

        # By caching the attribute on the __dict__ of the instance,
        # `__getattribute__` will return this attribute directly.
        self.__dict__[name] = value
        return value

chatbox_settings = _ChatboxSettingsRetriever()


def without(i1, i2):
    """Subtract the elements in `i2 from `i1`.
    
    The elements of `i1 and `i2` must be unique. Also `i2` 
    be a subset of `i1`.
    
    Parameters
    ----------
    i1, i2 : Iterable
        Iterables with unique items. `i2` must be a subset
        if `i1`.
    
    Notes
    -----
    If the elements of `i1` or `i2` are not unique,
    some elements will get lost. We impose that `i2` must
    be a subset of `i1` to prevent silent bugs.
    """
    s1 = set(i1)
    s2 = set(i2)
    if not s2.issubset(s1):
        raise ValueError("`i2` must be a subset of `i1`")
    return list(s1 - s2)
