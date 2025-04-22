import json
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView
import base64
from unfold.admin import ModelAdmin
from unfold.views import UnfoldModelAdminViewMixin
from cromo_core.models import Cromo_POI

# Custom dasboard view
admin.site.index_title = 'Dashboard'

class DashboardView(UnfoldModelAdminViewMixin, TemplateView):
    title = "Dashboard"
    permission_required = ()
    template_name = "admin/index.html"

def dashboard_callback(request, context):
    if request.user.is_superuser:
        serving_cromo_poi = Cromo_POI.objects.filter(status="SERVING").count()
        failed_cromo_poi = Cromo_POI.objects.filter(status="FAILED").count()
        building_cromo_poi = Cromo_POI.objects.filter(status="BUILDING").count()
        cromo_pois = Cromo_POI.objects.all()
    else:
        serving_cromo_poi = Cromo_POI.objects.filter(user=request.user, status="SERVING").count()
        failed_cromo_poi = Cromo_POI.objects.filter(user=request.user, status="FAILED").count()
        building_cromo_poi = Cromo_POI.objects.filter(user=request.user, status="BUILDING").count()
        cromo_pois = Cromo_POI.objects.filter(user=request.user)
    
    # for lesson in cromo_pois:
        # if lesson.ref_ply:
        #     lesson.ref_ply = base64.b64encode(lesson.ref_ply.encode('utf-8')).decode('utf-8')
        # if lesson.ref_annotations:
        #     lesson.ref_annotations = base64.b64encode(lesson.ref_annotations.encode('utf-8')).decode('utf-8')

    kpis = [
        {"title": "Serving Cromo POI", "metric": serving_cromo_poi},
        {"title": "Failed Cromo POI", "metric": failed_cromo_poi},
        {"title": "Building Cromo POI", "metric": building_cromo_poi},
    ]

    context.update({
        "kpis": kpis,
        "cromo_pois": cromo_pois,
    })
    
    return context
