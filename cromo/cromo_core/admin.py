from django.contrib import admin
from .models import Cromo_POI, Tag, Cromo_View
from unfold.admin import ModelAdmin, TabularInline
import json
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage 
from .models import MinioStorage
# from leaflet.forms.widgets import LeafletWidget
# from django import forms
# from unfold.forms import FormLayout, FormFieldset

class TagAdmin(ModelAdmin):
    pass
admin.site.register(Tag, TagAdmin)


class Cromo_View_Inline(TabularInline):
    model = Cromo_View
    extra = 1

admin.site.register(Cromo_View)

def generate_data_json(instance):
    storage = MinioStorage()
    images = instance.images.all()
    data = [{
        "cromo_view_tag":img.tag,
        "url": img.image.url,
        "file_name": img.image.name,
    } for img in images]
    content = json.dumps(data, indent=2)
    file = ContentFile(content.encode('utf-8'))
    file_name = f"{instance.id}/data.json"
    storage.save(file_name, file)
        
class Cromo_POIAdmin(ModelAdmin):
    list_display = ('title', 'creation_time', 'status', 'user', 'location')
    list_filter = ('status', 'user')
    search_fields = ('title', 'description')
    date_hierarchy = 'creation_time'
    inlines = [Cromo_View_Inline]
    from location_field.widgets import LocationWidget
    from location_field.models.plain import PlainLocationField
    formfield_overrides = {
        PlainLocationField: {"widget": LocationWidget},
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def get_fields(self, request, obj=None):
        fields = ['title', 'location']

        if obj and request.user.is_superuser:
            fields.append('status')

        # if request.user.is_superuser:
        #     fields.append('user')

        return fields

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        if not request.user.is_superuser:
            return base + ('user',)
        return base

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and not obj.user:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if not request.user.is_superuser:
            initial['user'] = request.user.pk
        return initial
    
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        cromo_poi = form.instance
        generate_data_json(cromo_poi)
    
    
admin.site.register(Cromo_POI, Cromo_POIAdmin)
