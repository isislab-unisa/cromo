from django.contrib import admin
from .models import Cromo_POI, Tag, Cromo_View, Cromo_Image
from unfold.admin import ModelAdmin, TabularInline
import json
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage 
from .models import MinioStorage
from location_field.widgets import LocationWidget
from location_field.models.plain import PlainLocationField
from django.utils.safestring import mark_safe
import nested_admin

class TagAdmin(ModelAdmin):
    pass
admin.site.register(Tag, TagAdmin)


def get_image_preview_html(img_url):
    return mark_safe(f'''
    <img src="{img_url}" style="max-width:200px;cursor:pointer"
         onclick="(function(s){{let m=document.createElement('div');m.style='position:fixed;top:0;left:0;width:100%;height:100%;background:#000c;z-index:9999;display:flex;align-items:center;justify-content:center;';let i=document.createElement('img');i.src=s;i.style='max-width:90%;max-height:90%;box-shadow:0 0 20px #000';m.onclick=()=>document.body.removeChild(m);m.appendChild(i);document.body.appendChild(m)}})(this.src)">
    ''')

class Cromo_Image_Inline(nested_admin.NestedStackedInline):
    model = Cromo_Image
    extra = 1
    fields = ['image']

admin.site.register(Cromo_Image)

class Cromo_View_Inline(nested_admin.NestedStackedInline):
    model = Cromo_View
    extra = 1
    readonly_fields = [ 'crowsourced', 'timestamp', 'metadata']
    list_display = ( 'tag')
    fields = ['crowsourced', 'timestamp', 'tag', 'metadata', 'default_image']
    inlines = [Cromo_Image_Inline]
    
    # def image_preview(self, obj):
    #     if obj.image:
    #         from django.utils.html import format_html
    #         link = obj.image.url.replace("minio", "localhost")
    #         return get_image_preview_html(link)
    #     return obj.image.url
    # image_preview.short_description = 'Preview'
    
admin.site.register(Cromo_View)

# def generate_data_json(instance):
#     storage = MinioStorage()
#     images = instance.images.all()
#     data = [{
#         "cromo_view_tag":img.tag,
#         "url": img.image.url,
#         "file_name": img.image.name,
#     } for img in images]
#     content = json.dumps(data, indent=2)
#     file = ContentFile(content.encode('utf-8'))
#     file_name = f"{instance.id}/data.json"
#     storage.save(file_name, file)
        
class Cromo_POIAdmin(nested_admin.NestedModelAdmin, ModelAdmin):
    list_display = ('title', 'creation_time', 'status', 'user', 'location')
    readonly_fields = ['status', 'user', 'creation_time']
    list_filter = ('status', 'user')
    search_fields = ('title', 'description')
    date_hierarchy = 'creation_time'
    inlines = [Cromo_View_Inline]
    
    formfield_overrides = {
        PlainLocationField: {"widget": LocationWidget},
    }

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def get_fields(self, request, obj=None):
        fields = ['title', 'location', 'status']

        return fields

    # def get_readonly_fields(self, request, obj=None):
    #     base = super().get_readonly_fields(request, obj)
    #     if not request.user.is_superuser:
    #         return base + ('user',)
    #     return base

    def save_model(self, request, obj, form, change):
        if not change:
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        # if not request.user.is_superuser:
        initial['user'] = request.user.pk
        return initial
    
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        cromo_poi = form.instance
        # generate_data_json(cromo_poi)
    
    
admin.site.register(Cromo_POI, Cromo_POIAdmin)
