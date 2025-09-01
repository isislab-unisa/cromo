from django.contrib import admin
from .models import Cromo_POI, Tag, Cromo_View, Cromo_Image
from unfold.admin import ModelAdmin, TabularInline
import json
from .models import MinioStorage
from location_field.widgets import LocationWidget
from location_field.models.plain import PlainLocationField
from django.utils.safestring import mark_safe
import nested_admin
from unfold.admin import TabularInline

class TagAdmin(ModelAdmin):
    pass
admin.site.register(Tag, TagAdmin)

class Cromo_Image_Admin(ModelAdmin):
    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.cromo_view.cromo_poi.user != request.user:
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.cromo_view.cromo_poi.user != request.user:
            return False
        return True

admin.site.register(Cromo_Image, Cromo_Image_Admin)

def get_image_preview_html(img_url):
    return mark_safe(f'''
    <img src="{img_url}" style="max-width:200px;cursor:pointer"
         onclick="(function(s){{let m=document.createElement('div');m.style='position:fixed;top:0;left:0;width:100%;height:100%;background:#000c;z-index:9999;display:flex;align-items:center;justify-content:center;';let i=document.createElement('img');i.src=s;i.style='max-width:90%;max-height:90%;box-shadow:0 0 20px #000';m.onclick=()=>document.body.removeChild(m);m.appendChild(i);document.body.appendChild(m)}})(this.src)">
    ''')

from django import forms
from .models import Cromo_View
from django.forms.widgets import ClearableFileInput

class MultipleClearableFileInput(ClearableFileInput):
    def __init__(self, attrs=None):
        super().__init__(attrs)
        if self.attrs is None:
            self.attrs = {}
        self.attrs['multiple'] = True
        
    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        return mark_safe(f"""
        <div class="flex w-full max-w-2xl items-center justify-between gap-2 rounded-default border border-base-200 px-3 py-2 shadow-xs dark:border-base-700">
            <label class="text-sm font-medium text-base-700 dark:text-base-200">
                Upload Images
                {input_html}
            </label>
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-base-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1M12 12v6m0 0L8 16m4 2l4-2m-6-6h6m-3-4v4" />
            </svg>
        </div>
        """)

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleClearableFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(d, initial) for d in data]
        return [single_file_clean(data, initial)]
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        print("[DEBUG] Saving form for Cromo_View", instance)

        uploaded_files = self.cleaned_data.get('uploaded_images')
        print("[DEBUG] Uploaded files:", uploaded_files)

        if instance.pk and uploaded_files:
            for uploaded_file in uploaded_files:
                Cromo_Image.objects.create(cromo_view=instance, image=uploaded_file)

        return instance

class CromoViewForm(forms.ModelForm):
    uploaded_images = forms.FileField(
        required=False,
        label='Views',
        widget=MultipleClearableFileInput()
    )

    def clean_uploaded_images(self):
        if not self.files:
            return []
        return self.files.getlist(self.add_prefix('uploaded_images')) or []
    
    def save(self, commit=True):
        instance = super().save(commit=commit)

        if commit and hasattr(self, 'cleaned_data') and 'uploaded_images' in self.cleaned_data:
            uploaded_files = self.cleaned_data['uploaded_images']
            for uploaded_file in uploaded_files:
                Cromo_Image.objects.create(cromo_view=instance, image=uploaded_file)

        return instance

    class Meta:
        model = Cromo_View
        fields = ['tag', 'uploaded_images', 'default_image']

class Cromo_View_Inline(TabularInline, nested_admin.NestedInlineModelAdmin):
    model = Cromo_View
    extra = 1
    form = CromoViewForm
    readonly_fields = ['crowsourced', 'timestamp']
    
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        for formset in formsets:
            for inline_form in formset.forms:
                if not hasattr(inline_form, 'cleaned_data'):
                    continue
                uploaded_files = inline_form.cleaned_data.get('uploaded_images', [])
                print("uploaded_files per form:", uploaded_files)
                if uploaded_files:
                    cromo_view = inline_form.instance
                    print("Salvo per Cromo_View:", cromo_view)
                    for uploaded_file in uploaded_files:
                        Cromo_Image.objects.create(cromo_view=cromo_view, image=uploaded_file)
    
    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        # if obj.cromo_poi.user != request.user:
        #     return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        # if obj.cromo_poi.user != request.user:
        #     return False
        return True
    
admin.site.register(Cromo_View)

from django import forms
from django.utils.safestring import mark_safe
import json

class ExternalPOIWidget(forms.Select):
    class Media:
        js = ('js/external_poi.js',)

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        html += mark_safe('<div id="external-poi-preview"></div>')
        return html

class CromoPOIForm(forms.ModelForm):
    class Meta:
        model = Cromo_POI
        fields = '__all__'
        widgets = {
            'external_id': ExternalPOIWidget
        }

class Cromo_POIAdmin(ModelAdmin, nested_admin.NestedModelAdmin):
    form = CromoPOIForm
    list_display = ('title', 'creation_time', 'status', 'user', 'location')
    readonly_fields = ['status', 'user', 'creation_time']
    list_filter = ('status', 'user')
    search_fields = ('title', 'description')
    date_hierarchy = 'creation_time'
    inlines = [Cromo_View_Inline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def get_fields(self, request, obj=None):
        fields = ['title', 'location', 'default_image', 'status', 'external_id']
        return fields

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
    
    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.status in ['BUILT', 'BUILDING', 'SERVING', 'ENQUEUED']:
            return False
        if obj.user != request.user:
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        has_permission = super().has_delete_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.status in ['SERVING', 'BUILDING', 'ENQUEUED']:
            return False
        
        if obj.user != request.user:
            return False
        return True
    
    
admin.site.register(Cromo_POI, Cromo_POIAdmin)
