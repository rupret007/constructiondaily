from django.contrib import admin

from files.models import Attachment, UploadIntent

admin.site.register(Attachment)
admin.site.register(UploadIntent)
