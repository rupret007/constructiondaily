from django.contrib import admin

from audit.models import AuditEvent

admin.site.register(AuditEvent)
