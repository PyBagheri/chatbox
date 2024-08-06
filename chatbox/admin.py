from django.contrib import admin
from chatbox import models

for model in (
    models.Chat,
    models.GroupChatInfo,
    models.Membership,
    models.AdminRole,
    models.FileData,
    models.Message,
):
    admin.site.register(model)
