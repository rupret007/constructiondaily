from django.contrib import admin

from reports.models import (
    ApprovalAction,
    DailyReport,
    DelayEntry,
    EquipmentEntry,
    LaborEntry,
    MaterialEntry,
    ReportSnapshot,
    WorkLogEntry,
)

admin.site.register(DailyReport)
admin.site.register(LaborEntry)
admin.site.register(EquipmentEntry)
admin.site.register(MaterialEntry)
admin.site.register(WorkLogEntry)
admin.site.register(DelayEntry)
admin.site.register(ApprovalAction)
admin.site.register(ReportSnapshot)
