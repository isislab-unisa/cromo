from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, Http404
from django.shortcuts import render
from .models import MinioStorage
from django.http import JsonResponse
import base64
from django.http import FileResponse
from .models import Cromo_POI
from django.shortcuts import redirect
from cromo.tasks import call_api_and_save
from django.core.mail import send_mail
import os

@login_required
@require_http_methods(['GET'])
def pick_data_from_minio(request, resource):
    try:
        file_name = base64.b64decode(resource).decode('utf-8')
        print(f"[DEBUG] Decoded file_name from base64: {file_name}")
    except Exception as e:
        return JsonResponse({"error": f"Invalid base64 encoding: {str(e)}"}, status=400)

    if not file_name:
        return JsonResponse({"error": "File name not provided"}, status=400)

    minio_storage = MinioStorage()

    try:
        file = minio_storage.open(file_name, mode='rb')
        response = FileResponse(file, as_attachment=True, filename=file_name)
        response['Content-Type'] = 'application/octet-stream'
        return response
    except FileNotFoundError:
        return JsonResponse({"error": "File not found"}, status=404)

@login_required
@require_http_methods(['GET'])
def pick_annotation_from_minio(request, annotation):
    try:
        file_name = base64.b64decode(annotation).decode('utf-8')
        print(f"[DEBUG] Decoded file_name from base64: {file_name}")
    except Exception as e:
        return JsonResponse({"error": f"Invalid base64 encoding: {str(e)}"}, status=400)

    if not file_name:
        return JsonResponse({"error": "File name not provided"}, status=400)

    minio_storage = MinioStorage()

    try:
        file = minio_storage.open(file_name, mode='rb')
        response = FileResponse(file, as_attachment=True, filename=file_name)
        response['Content-Type'] = 'application/json'
        return response
    except FileNotFoundError:
        return JsonResponse({"error": "File not found"}, status=404)

@login_required
@require_http_methods(['POST'])
def render_xrts_viewer(request):
    return render(request, 'viewer/xrts-viewer.html', context={'resource': request.POST.get('resource'),
                                                               'title': request.POST.get('title'),
                                                               'annotation': request.POST.get('annotation')})

@login_required
@require_http_methods(['POST'])
def build(request):
    cromo_poi_id = request.POST.get('poi_id')
    cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
    value = request.POST.get('training_type')
    call_api_and_save.apply_async(args=[cromo_poi.id, value], queue='api_tasks')
    
    return redirect('/admin/')

@require_http_methods(['POST'])
def complete_build(request):
    status = request.POST.get('status')
    cromo_poi_id = request.POST.get('poi_id')
    ply_path = request.POST.get('ply_path')
    
    if status == "COMPLETED":
        cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
        cromo_poi.ref_ply = ply_path
        cromo_poi.status = "BUILDED"
        cromo_poi.save()
        
        send_mail(
            'Build in corso',
            f"Lezione {cromo_poi.title} in fase di build.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )
    else:
        cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
        cromo_poi.status = "FAILED"
        cromo_poi.save()
        
        send_mail(
            'Build in corso',
            f"Lezione {cromo_poi.title} in fase di build.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )    