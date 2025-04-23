from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse, Http404
from django.shortcuts import render
from .models import MinioStorage
from django.http import JsonResponse
import base64
from django.http import FileResponse
from .models import Cromo_POI, MinioStorage, Cromo_View
from django.shortcuts import redirect
from cromo.tasks import call_api_and_save
from django.core.mail import send_mail
import os
import json
import io
import time
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
import base64
import uuid
from django.core.files.base import ContentFile

def get_base64_extension(base64_string):
    if ';base64,' in base64_string:
        header = base64_string.split(';base64,')[0]
        mime_type = header.split(':')[-1]  # e.g., 'image/png'
        extension = mime_type.split('/')[-1]  # e.g., 'png'
        return extension
    return None

def save_base64_image_to_model(base64_data, instance, field_name='image'):
    # Format: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
    format, imgstr = base64_data.split(';base64,')  # split the header
    ext = format.split('/')[-1]

    file_name = f"{uuid.uuid4()}.{ext}"
    image_data = ContentFile(base64.b64decode(imgstr), name=file_name)

    setattr(instance, field_name, image_data)
    instance.save()

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

# @csrf_exempt
# @require_http_methods(['POST'])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def list(request):
    
    cromo_pois = Cromo_POI.objects.filter(status="READY")
    features = []
    
    for poi in cromo_pois:
        poi_id = poi.id
        title = poi.title
        location = poi.location
        cromo_views = poi.images.all()
        l = location.split(",")
        lat, lng = l[0], l[1]
        feature = {
            "type": "Feature",
            "properties": {
                "id": poi_id,
                "title": title,
                "cromo_views": len(cromo_views)
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lng, lat]
            }
        }
        features.append(feature)
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    buffer = io.BytesIO()
    buffer.write(json.dumps(geojson).encode('utf-8'))
    buffer.seek(0)

    response = FileResponse(buffer, as_attachment=True, filename="list.json")
    response['Content-Type'] = 'application/json'
    return response
    
    # return JsonResponse(geojson)
    
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def serve(request):
    poi_id = request.POST.get('poi_id')
    poi_view_image = request.POST.get('poi_view_image')
    poi_view_image = base64.b64decode(poi_view_image)
    
    # Invoco servizio per riconoscere il tag
    poi = Cromo_POI.objects.get(pk=poi_id)
    images = poi.images.all().first()
    
    tag = images.tag
    with images.image.open('rb') as img_file:
        view = base64.b64encode(img_file.read()).decode('utf-8')
    res = {
        "tag": tag,
        "view": view
    }
    
    buffer = io.BytesIO()
    buffer.write(json.dumps(res).encode('utf-8'))
    buffer.seek(0)

    response = FileResponse(buffer, as_attachment=True, filename=f"view_{poi_id}.json")
    response['Content-Type'] = 'application/json'
    return response

@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def add_view(request):
    poi_id = request.POST.get('poi_id')
    tag = request.POST.get("tag")
    image64 = request.POST.get('poi_view_image')
    # poi_view_image = base64.b64decode(image64)
    poi_metadata = request.POST.get('poi_metadata')
    
    poi = Cromo_POI.objects.get(pk=poi_id)
    if poi is None:
        return JsonResponse({"error": "Cromo POI not found"}, status=404)
    
    c = Cromo_View.objects.create(
        cromo_poi=poi,
        tag=tag,
        # image=poi_view_image,
        metadata=poi_metadata,
        crowsourced=True
    )
    save_base64_image_to_model(image64, c)
    # c.image.save(f"{time.time()}.{get_base64_extension(image64)}", ContentFile(poi_view_image), save=True)
    return JsonResponse({"message": "View added successfully"}, status=200)
    