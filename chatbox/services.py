"""App-specific utilities for use in views.

Notes
-----
As opposed to what the name of this file may suggest, this
file is NOT for a separate service "layer"; The only purpose
of service modules in this app is to provide app-specific
utilities that serve one or more of the following purposes:

1) Accessing or manipulating more than one model (*).
2) Performing non-data-related actions, including
   3rd-party API calls.

(*) in some cases it would make sense to have a model method
or manager/queryset method to manipulate more than one model
(e.g., when we have a one-to-one relation); so you might consider
using them rather than creating a "service" for it.
"""
