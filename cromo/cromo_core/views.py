from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
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
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
import base64
import uuid
from django.core.files.base import ContentFile
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

def get_base64_extension(base64_string):
    if ';base64,' in base64_string:
        header = base64_string.split(';base64,')[0]
        mime_type = header.split(':')[-1]
        extension = mime_type.split('/')[-1]
        return extension
    return None

def save_base64_image_to_model(base64_data, instance, field_name='image'):
    format, imgstr = base64_data.split(';base64,')
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
    if cromo_poi.status == "READY":
        cromo_poi.status = "ENQUEUED"
        cromo_poi.save()
        call_api_and_save.apply_async(args=[cromo_poi.id], queue='api_tasks')

    return redirect('/admin/')

@swagger_auto_schema(
    method='post',
    operation_summary="Complete Build",
    operation_description="Marks the build process for a POI as COMPLETED or FAILED, updates its status, and sends a notification email.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_id', 'poi_name', 'status'],
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the POI"),
            'poi_name': openapi.Schema(type=openapi.TYPE_STRING, description="Name of the POI"),
            'model_url': openapi.Schema(type=openapi.TYPE_STRING, description="URL of the trained model (required if status is COMPLETED)"),
            'status': openapi.Schema(type=openapi.TYPE_STRING, description="Build status: 'COMPLETED' or 'FAILED'"),
        }
    ),
    responses={200: "Build status updated", 404: "POI not found", 500: "Error saving POI"},
)
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def complete_build(request):
    cromo_title = request.POST.get('poi_name')
    cromo_poi_id =int(request.POST.get('poi_id'))
    model_url = request.POST.get('model_url')
    status = request.POST.get('status')
    
    if status == "COMPLETED":
        try:
            cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
            cromo_poi.model_path = model_url
            cromo_poi.status = "BUILT"
            cromo_poi.save()
        except Cromo_POI.DoesNotExist:
            return JsonResponse({"error": "Cromo POI not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": f"Error saving Cromo POI: {str(e)}"}, status=500)
        send_mail(
            'Build completata',
            f"Lezione {cromo_poi.title} buildata.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )
    else:
        cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
        cromo_poi.status = "FAILED"
        cromo_poi.save()
        
        send_mail(
            'Build fallita',
            f"Build Fallita {cromo_poi.title}.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )   

@swagger_auto_schema(
    method='post',
    operation_summary="Export POIs as GeoJSON",
    operation_description=(
        "Returns a downloadable GeoJSON file containing all Points of Interest (POIs) "
        "with status 'READY'. Each POI is represented as a GeoJSON Feature with properties "
        "such as ID, title, and number of associated images, and geographic coordinates "
        "in 'Point' format."
    ),
    responses={200: 'Downloadable JSON file containing a FeatureCollection in GeoJSON format'}
)
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

@swagger_auto_schema(
    method='post',
    operation_summary="Serve POI View",
    operation_description="Returns the first image view and associated tag for a given POI as a downloadable JSON file.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_id', 'poi_view_image'],
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the POI"),
            'poi_view_image': openapi.Schema(type=openapi.TYPE_STRING, format='byte', description="Base64-encoded input image for tag recognition"),
        }
    ),
    responses={200: "File response with tag and view", 404: "POI not found"},
)
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

@swagger_auto_schema(
    method='post',
    operation_summary="Add a new view to a POI",
    operation_description=(
        "Adds a new image view to the specified Point of Interest (POI), along with a tag and "
        "optional metadata. The view is marked as crowdsourced. The image is stored after being "
        "encoded in Base64 format."
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_id', 'tag', 'poi_view_image'],
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the POI"),
            'tag': openapi.Schema(type=openapi.TYPE_STRING, description="Tag for the view image"),
            'poi_view_image': openapi.Schema(type=openapi.TYPE_STRING, format='byte', description="Base64-encoded image of the POI view"),
            'poi_metadata': openapi.Schema(type=openapi.TYPE_STRING, description="Metadata related to the POI view", nullable=True),
        }
    ),
    responses={200: "View added successfully", 404: "POI not found"},
)
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
    