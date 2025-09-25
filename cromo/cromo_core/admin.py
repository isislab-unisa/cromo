from django.contrib import admin
from .models import Cromo_POI, Tag, Cromo_View, Cromo_Image
from unfold.admin import ModelAdmin, TabularInline
from django.utils.safestring import mark_safe
import nested_admin
from unfold.admin import TabularInline
from django import forms
from django.contrib import messages
from .cos2_client import COS2Client
from django import forms
from .models import Cromo_View
from django.forms.widgets import ClearableFileInput
from django.urls import path, reverse
from django.shortcuts import redirect

class TagAdmin(ModelAdmin):
    pass
admin.site.register(Tag, TagAdmin)


class Cromo_Image_Admin(admin.ModelAdmin):

    def has_change_permission(self, request, obj=None):
        has_permission = super().has_change_permission(request, obj)
        if not has_permission:
            return False
        if obj is None:
            return True
        if obj.cromo_view.cromo_poi.status in ['BUILT', 'BUILDING', 'SERVING', 'ENQUEUED']:
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
        if obj.cromo_view.cromo_poi.status in ['SERVING', 'BUILDING', 'ENQUEUED']:
            return False
        
        if obj.user != request.user:
            return False
        return True
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:pk>/delete-image/",
                self.admin_site.admin_view(self.delete_image),
                name="cromo_image_delete",
            ),
        ]
        return custom_urls + urls

    def delete_image(self, request, pk, *args, **kwargs):
        try:
            obj = Cromo_Image.objects.get(pk=pk)
            poi_pk = obj.cromo_view.cromo_poi.pk 
            if obj.cromo_view.cromo_poi.user != request.user:
                self.message_user(request, "Non hai i permessi per eliminare questa immagine.", level=messages.ERROR)
            else:
                obj.delete()
                self.message_user(request, "Immagine eliminata con successo.", level=messages.SUCCESS)
        except Cromo_Image.DoesNotExist:
            self.message_user(request, "Immagine non trovata.", level=messages.ERROR)
        change_url = reverse("admin:cromo_core_cromo_poi_change", args=[poi_pk])
        return redirect(change_url)

admin.site.register(Cromo_Image, Cromo_Image_Admin)

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
                {input_html}
            </label>
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

class ExistingImagesWidget(forms.Widget):
    """Widget per mostrare preview delle immagini già salvate con bottone elimina"""
    def render(self, name, value, attrs=None, renderer=None):
        if not value:
            return ""

        html = '''
        <div style="max-height:300px;overflow-y:auto;border:1px solid #ccc;padding:5px;display:flex;flex-direction:column;gap:10px;">
        '''

        for img in value:
            delete_url = reverse("admin:cromo_image_delete", args=[img.pk])
            html += f'''
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:5px; border-bottom:1px solid #eee;">
                <div style="flex:1;">
                    <img src="/stream-images/?path={img.image.name}" style="max-width:150px; max-height:150px; object-fit:contain; cursor:pointer;"
                        onclick="(function(s){{
                            let overlay = document.createElement('div');
                            overlay.style='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);display:flex;align-items:center;justify-content:center;z-index:9999;cursor:pointer;';
                            let img = document.createElement('img');
                            img.src=s;
                            img.style='max-width:90%;max-height:90%;box-shadow:0 0 20px #000';
                            overlay.appendChild(img);
                            overlay.onclick=()=>document.body.removeChild(overlay);
                            document.body.appendChild(overlay);
                        }})(this.src)">
                </div>
                <div style="flex-shrink:0;">
                    <a href="{delete_url}" class="button" 
                       style="display:inline-block;color:white;background:#d9534f;padding:6px 12px;border-radius:4px;text-decoration:none;"
                       onclick="return confirm('Sei sicuro di voler eliminare questa immagine?');">
                       Elimina
                    </a>
                </div>
            </div>
            '''

        html += '</div>'
        return mark_safe(html)
    
class CromoViewForm(forms.ModelForm):
    uploaded_images = forms.FileField(
        required=False,
        label='Views',
        widget=MultipleClearableFileInput()
    )

    existing_images = forms.CharField(
        required=False,
        label='Existing Images',
        widget=ExistingImagesWidget()
    )

    class Meta:
        model = Cromo_View
        fields = ['tag', 'uploaded_images', 'default_image', 'existing_images']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            images = self.instance.images.all()
            self.fields['existing_images'].initial = images

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

class ExternalPOIWidget(forms.Select):
    class Media:
        js = (
            'https://code.jquery.com/jquery-3.6.0.min.js',
            'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js',
            'js/external_poi.js',
        )
        css = {
            'all': (
                'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css',
                'unfold/css/unfold.css',
            )
        }

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
        fields = ['external_id', 'title', 'location', 'default_image', 'status']
        return fields

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
    
    def save_model(self, request, obj, form, change):
        client = COS2Client()

        if not change:
            api_url = "https://cos2.cityopensource.com/api/cromo/spaces/5b165325-183f-86fb-0210-9718f29af21e/locations"

            data = {"title": obj.title}
            if obj.location and "," in obj.location:
                lat, lon = obj.location.split(",", 1)
                data["lat"] = lat.strip()
                data["lon"] = lon.strip()

            files = {}
            if obj.default_image:
                files["image"] = obj.default_image.file

            try:
                r = client.request("POST", api_url, data=data, files=files)
                remote = r.json()

                obj.external_id = remote.get("id")
                obj.user = request.user
                super().save_model(request, obj, form, change)

            except Exception as e:
                messages.error(request, f"Errore creazione remoto: {e}")
                return

        else:
            super().save_model(request, obj, form, change)
    
    def delete_model(self, request, obj):
        client = COS2Client()

        if not obj.external_id:
            messages.error(request, "Nessun external_id associato, impossibile eliminare remoto.")
            return

        api_url = f"https://cos2.cityopensource.com/api/cromo/spaces/5b165325-183f-86fb-0210-9718f29af21e/locations/{obj.external_id}"

        try:
            r = client.request("DELETE", api_url)
            if r.status_code in (200, 204):
                super().delete_model(request, obj)
            else:
                messages.error(request, f"Errore eliminazione remota: {r.text}")
        except Exception as e:
            messages.error(request, f"Eccezione API remota: {e}")

    def delete_queryset(self, request, queryset):
        client = COS2Client()
        for obj in queryset:
            if not obj.external_id:
                messages.error(request, f"{obj} non ha external_id, skip eliminazione remota.")
                continue

            api_url = f"https://cos2.cityopensource.com/api/cromo/spaces/5b165325-183f-86fb-0210-9718f29af21e/locations/{obj.external_id}"

            try:
                r = client.request("DELETE", api_url)
                if r.status_code in (200, 204):
                    super().delete_model(request, obj)
                else:
                    messages.error(request, f"Errore eliminazione remota di {obj}: {r.text}")
            except Exception as e:
                messages.error(request, f"Eccezione API remota su {obj}: {e}")
    
admin.site.register(Cromo_POI, Cromo_POIAdmin)
