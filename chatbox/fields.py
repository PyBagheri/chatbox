from rest_framework import serializers

from datetime import datetime, UTC


class UnixTimestampField(serializers.DateTimeField):
    def to_internal_value(self, value):
        try:
            # We need the datetime objects to be timezone-aware
            # to work properly with Django and storing in the DB.
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, TypeError):
            return None
    
    def to_representation(self, value):
        return value.timestamp()
