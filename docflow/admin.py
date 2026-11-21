from django.contrib import admin

from . import models as m

for model in (m.Journal, m.CaseFile, m.Template, m.Seal, m.DocTask, m.ArchiveRecord, m.SealUsage):
    admin.site.register(model)


class FileInline(admin.TabularInline):
    model = m.DocumentFile
    extra = 0


class ApprovalInline(admin.TabularInline):
    model = m.Approval
    extra = 0


@admin.register(m.Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "kind", "status", "doc_date", "counterparty")
    list_filter = ("kind", "status")
    search_fields = ("number", "title", "counterparty", "summary")
    inlines = [FileInline, ApprovalInline]


@admin.register(m.DocEvent)
class DocEventAdmin(admin.ModelAdmin):
    list_display = ("at", "document", "kind", "who", "text")

    def has_change_permission(self, request, obj=None):
        return False  # аудит не редактируется

    def has_delete_permission(self, request, obj=None):
        return False
