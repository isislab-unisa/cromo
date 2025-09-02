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
    serving_cromo_poi = Cromo_POI.objects.filter(status="SERVING").count()
    failed_cromo_poi = Cromo_POI.objects.filter(status="FAILED").count()
    building_cromo_poi = Cromo_POI.objects.filter(status="BUILDING").count()
    cromo_pois = Cromo_POI.objects.all()
    
    kpis = [
        {"title": "Serving Cromo POI", "metric": serving_cromo_poi},
        {"title": "Failed Cromo POI", "metric": failed_cromo_poi},
        {"title": "Building Cromo POI", "metric": building_cromo_poi},
    ]

    table_data = {
        "headers": ["Title", "Creation Date", "User", "Status", "Actions"],
        "rows": [
            [
                poi.title,
                getattr(poi, "created_at", ""),
                getattr(poi.user, "username", "") if hasattr(poi, "user") else "",
                poi.status,
                f"/admin/cromo_core/cromo_poi/{poi.id}/change/",
            ]
            for poi in cromo_pois
        ]
    }

    context.update({
        "kpis": kpis,
        "cromo_pois": cromo_pois,
        "table_data": table_data,
    })
    
    return context

