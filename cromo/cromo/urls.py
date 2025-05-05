from django.contrib import admin
from django.urls import path, include
# from .views import DashboardView
import nested_admin

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('cromo_core.urls')),
    path('nested_admin/', include('nested_admin.urls')),
]