from django.conf import settings
from chatbox import defaults

from random import randint


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


GREATEST_28_BIT_INTEGER = 2**28-1
def generate_message_id(sent_at):
    """Generate a 80-bit chatbox-specific message ID similar to Twitter's Snowflake.

    Notes
    -----
    We use 80-bit message ID's for chatbox. Every message ID consists of two parts:
    the timestamp part (52 bits = 13 hex digits) and a random part (28 bits = 7 hex
    digits). The timestamp part is the number of microseconds since the UNIX epoch,
    which can be represented with 52 bits for most practical datetimes. For the second
    part we use a random number rather than sequential numbers to hide the number of
    messages in a microsecond, which can hint at the scale of the system. The second
    part is zero-filled to become a 7-digit hex string.
    
    Since we save the message datetimes with microsecond resolution, we do the same
    here for the message ID's so that their sort order is the same. Plus, it would be
    easier to manage since PostgreSQL's datetime types have a microsecond accuracy,
    and so is Python's `datetime.now()` on most modern machines.
    """
    
    # The number of hex digits for this will be 13 from about year 1979 to about
    # year 2112. If you need higher datetimes, you need to increase the length of
    # message ID's. If you need lower datetimes, use a `zfill(13)` (note that you
    # cannot go below the UNIX epoch).
    timestamp_part = hex(int(sent_at.timestamp()*1000000)).lstrip('0x')
    
    # This is inclusive.
    random_part = hex(randint(0, GREATEST_28_BIT_INTEGER)).lstrip('0x').zfill(7)
    
    return timestamp_part + random_part
