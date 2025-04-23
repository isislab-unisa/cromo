from django.urls import path
from .views import pick_data_from_minio, render_xrts_viewer, build, pick_annotation_from_minio, complete_build, list, serve, add_view
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    path('pick_data_from_minio/<str:resource>', pick_data_from_minio, name='pick_data_from_minio'),
    path('pick_annotation_from_minio/<str:annotation>', pick_annotation_from_minio, name='pick_annotation_from_minio'),
    path('render_xrts_viewer/', render_xrts_viewer, name='render_xrts_viewer'),
    path('build', build, name='build'),
    path('complete_build', complete_build, name='complete_build'),
    path('list', list, name='list'),
    path('api/token-auth/', obtain_auth_token),
    path('serve', serve, name='serve'),
    path('add_view', add_view, name='add_view'),
]
