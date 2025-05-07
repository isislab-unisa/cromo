from django.urls import path, re_path
from .views import pick_data_from_minio, render_xrts_viewer, build, pick_annotation_from_minio, complete_build, list, serve, add_view
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
   openapi.Info(
      title="Cromo API",
      default_version='v1',
      description="These are the API endpoints for Cromo.",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@dummy.local"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)
urlpatterns = [
    path('pick_data_from_minio/<str:resource>', pick_data_from_minio, name='pick_data_from_minio'),
    path('pick_annotation_from_minio/<str:annotation>', pick_annotation_from_minio, name='pick_annotation_from_minio'),
    path('render_xrts_viewer/', render_xrts_viewer, name='render_xrts_viewer'),
    path('build', build, name='build'),
    path('complete_build', complete_build, name='complete_build'),
    path('list', list, name='list'),
    path('serve', serve, name='serve'),
    path('add_view', add_view, name='add_view'),
    re_path(r'^docs/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
