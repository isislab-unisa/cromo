import mimetypes
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
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
import base64
import uuid
from django.core.files.base import ContentFile
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import requests
from django.views.decorators.csrf import csrf_exempt
import redis
from redis.lock import Lock

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
            'report_url': openapi.Schema(type=openapi.TYPE_STRING, description="URL of the report (required if status is COMPLETED)"),
            'status': openapi.Schema(type=openapi.TYPE_STRING, description="Build status: 'COMPLETED' or 'FAILED'"),
        }
    ),
    responses={200: "Build status updated", 404: "POI not found", 500: "Error saving POI"},
)
@permission_classes([IsAuthenticated])
@api_view(['POST'])
def complete_build(request):
    print(f"Request data: {request.POST.get("poi_id")}")
    redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))
    cromo_title = request.data.get('poi_name')
    cromo_poi_id =request.data.get('poi_id')
    model_url = request.data.get('model_url')
    status = request.data.get('status')
    
    if status == "COMPLETED":
        try:
            cromo_poi = Cromo_POI.objects.get(pk=int(cromo_poi_id))
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
        try:
            redis_client.delete("build_lock")
        except Exception as e:
            print(f"Errore nell'eliminazione del lock: {e}")
        return JsonResponse({"message": "Build completata"}, status=200)
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
        try:
            redis_client.delete("build_lock")
        except Exception as e:
            print(f"Errore nell'eliminazione del lock: {e}")
        return JsonResponse({"error": "Cromo POI not found"}, status=404)

@swagger_auto_schema(
    method='get',
    operation_summary="Export POIs as GeoJSON",
    operation_description=(
        "This endpoint returns a **downloadable GeoJSON file** containing all "
        "Points of Interest (POIs), regardless of their status.\n\n"
        "### How it works\n"
        "- Fetches **all POIs**\n"
        "- Each POI is converted into a GeoJSON **Feature** with:\n"
        "  - `id`: the POI ID\n"
        "  - `cityopensource_id`: the external ID\n"
        "  - `POI`: the POI title\n"
        "  - `status`: the POI status\n"
        "  - `has_model`: `true` if the POI is `BUILT`, otherwise `false`\n"
        "  - `geometry`: a `Point` object with geographic coordinates `[longitude, latitude]`\n\n"
        "### Response format\n"
        "Returns a `FeatureCollection` in GeoJSON format with the following structure:\n\n"
        "```json\n"
        "{\n"
        "  \"type\": \"FeatureCollection\",\n"
        "  \"name\": \"POI CROMO\",\n"
        "  \"features\": [\n"
        "    {\n"
        "      \"type\": \"Feature\",\n"
        "      \"properties\": {\n"
        "        \"id\": 1,\n"
        "        \"cityopensource_id\": \"abc123\",\n"
        "        \"POI\": \"Some Title\",\n"
        "        \"status\": \"xxxx\", \"// if status == BUILT the model to do recognition is available\"\n"
        "      },\n"
        "      \"geometry\": {\n"
        "        \"type\": \"Point\",\n"
        "        \"coordinates\": [12.34, 56.78]\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n\n"
        "The response is returned as a **downloadable file** (`list.json`)."
    ),
    responses={
        200: 'Downloadable GeoJSON file containing POIs as a FeatureCollection',
        401: 'Unauthorized – user must be authenticated',
    }
)
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def list(request):
    cromo_pois = Cromo_POI.objects.all()
    features = []

    for poi in cromo_pois:
        poi_id = poi.id
        title = poi.title
        location = poi.location
        # cromo_views = poi.images.all()
        external_id = poi.external_id
        l = location.split(",")
        lat, lng = float(l[0]), float(l[1])
        feature = {
            "type": "Feature",
            "properties": {
                "id": poi_id,
                "cityopensource_id": external_id,
                "POI": title,
                "status": poi.status
            },
            "geometry": {
                "type": "Point",
                "coordinates": [lng, lat]
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "name": "POI CROMO",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }

    buffer = io.BytesIO()
    buffer.write(json.dumps(geojson).encode('utf-8'))
    buffer.seek(0)

    response = FileResponse(buffer, as_attachment=True, filename="list.json")
    response['Content-Type'] = 'application/json'
    return response

@swagger_auto_schema(
    method='post',
    operation_summary="Get POI views with images",
    operation_description=(
        "Given a `poi_id`, this endpoint returns all **views** associated with the specified POI.\n\n"
        "### Request\n"
        "Send a JSON body with:\n"
        "```json\n"
        "{ \"poi_id\": 123 }\n"
        "```\n\n"
        "### Response format\n"
        "Returns a JSON object with the list of views. Each view contains:\n"
        "- `poi_id`: the ID of the POI\n"
        "- `view_id`: the ID of the view\n"
        "- `title`: the view tag/title\n"
        "- `images`: a list of images, each with:\n"
        "  - `id_image`: the image ID\n"
        "  - `image`: the image file encoded as base64 string\n\n"
        "Example:\n"
        "```json\n"
        "{\n"
        "  \"views\": [\n"
        "    {\n"
        "      \"poi_id\": 123,\n"
        "      \"view_id\": 45,\n"
        "      \"title\": \"Front view\",\n"
        "      \"images\": [\n"
        "        {\n"
        "          \"id_image\": 1,\n"
        "          \"image\": \"/9j/4AAQSkZJRgABAQAAAQ...\"\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='ID of the POI'),
        },
        required=['poi_id']
    ),
    responses={
        200: 'JSON object containing all views with their images encoded in base64',
        401: 'Unauthorized – user must be authenticated',
        404: 'POI not found'
    }
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def get_view(request):
    minio_storage = MinioStorage()
    poi_id = request.data.get('poi_id')
    try:
        poi = Cromo_POI.objects.get(pk=poi_id)
    except Cromo_POI.DoesNotExist:
        return JsonResponse({"error": "POI not found"}, status=404)
    views = poi.images.all()
    views_data = []
    for view in views:
        images = view.images.all()
        print(len(images), flush=True)
        images_data = []
        for image in images:
            with image.image.open("rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            images_data.append({
                "id_image": image.id,
                "image": image_data,
            })
        views_data.append({
            "poi_id": poi.id,
            "cityopensource_id": poi.external_id,
            "view_id": view.id,
            "title": view.tag,
            "images": images_data,
        })
    return JsonResponse({"views": views_data})     

@swagger_auto_schema(
    method='post',
    operation_summary="Serve POI View",
    operation_description=(
        "Performs inference on a given POI view image and returns the recognized tag as a **downloadable JSON file**.\n\n"
        "### Request\n"
        "Provide:\n"
        "- `poi_id`: ID of the POI\n"
        "- `poi_view_image`: Base64-encoded input image used for inference\n"
        "- `poi_view_name`: (optional) Name of the POI view to match\n\n"
        "### Response\n"
        "A JSON file with the recognized tag. Two examples:\n\n"
        "**Positive case:**\n```json\n"
        "{\n"
        "  \"message\": \"Recognized waypoint: xxxx\",\n"
        "  \"view_id\": xxxx,\n"
        "  \"tag\": \"xxxx\",\n"
        "  \"poi_id_platform\": xxxx,\n"
        "  \"poi_id_cromo\": \"xxxx\"\n"
        "}\n```\n\n"
        "**Negative case (no matching view):**\n```json\n"
        "{\n"
        "  \"message\": \"No corresponding view found\",\n"
        "  \"view_id\": \"\",\n"
        "  \"tag\": \"\",\n"
        "  \"poi_id_platform\": \"\",\n"
        "  \"poi_id_cromo\": \"\"\n"
        "}\n```"
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_id', 'poi_view_image'],
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the POI"),
            'poi_view_image': openapi.Schema(type=openapi.TYPE_STRING, format='byte', description="Base64-encoded input image for tag recognition"),
            'poi_view_name': openapi.Schema(type=openapi.TYPE_STRING, description="Optional POI view name for filtering", nullable=True),
        }
    ),
    responses={
        200: openapi.Response(
            description='FileResponse with recognized tag as JSON',
            examples={
                'application/json': {
                    "positive": {
                        "message": "Recognized waypoint: xxxx",
                        "view_id": "xxxx",
                        "tag": "xxxx",
                        "poi_id_platform": "xxxID of the POI in the platform",
                        "poi_id_cromo": "Alphanumeric ID of the POI in Cromo"
                    },
                    "negative": {
                        "message": "No corresponding view found",
                        "view_id": "",
                        "tag": "",
                        "poi_id_platform": "",
                        "poi_id_cromo": ""
                    }
                }
            }
        ),
        404: 'POI or image not found',
        500: 'Error during inference or response serving',
    }
)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def serve(request):
    poi_id = request.data.get('poi_id')
    poi_view_image = request.data.get('poi_view_image')
    poi_view_name = request.data.get('poi_view_name')
    view = Cromo_View.objects.get(tag=poi_view_name, cromo_poi_id=poi_id)

    poi = Cromo_POI.objects.get(pk=poi_id)
    payload = {
        "poi_id": str(poi_id),
        "inference_image": poi_view_image,
        "model_url": poi.model_path,
        "poi_name": poi.title,
    }
    url = "http://ai_inference:8050/inference"
    headers = {"Content-type": "application/json"}
    response = requests.post(url, headers=headers, json=payload)

    print(response.json(), flush=True)

    if "RIFIUTATO" in response.json()['message']:
        res = {
            "message": "No corrisponding view found",
            "view_id": "",
            "tag": "",
            "poi_id_platform": "",
            "poi_id_cromo": "",
        }
        return JsonResponse(res)
    if response.status_code == 200:
        res = {
            "message": response.json()['message'].split('\n')[-1],
            "view_id": Cromo_View.objects.get(tag=response.json()['message'].split('\n')[-1].split(" ")[-1], cromo_poi_id=poi_id).id,
            "tag": view.tag,
            "poi_id_platform": view.cromo_poi_id,
            "poi_id_cromo": poi.external_id,
        }
    elif response.status_code == 404:
        return JsonResponse({"error": "Image not found"}, status=404)
    else:
        return JsonResponse({"error": "Error serving image"}, status=500)
    
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
        "Adds a new image view to the specified Point of Interest (POI).\n\n"
        "The view is associated with a **tag** and optional **metadata**, "
        "and the image is uploaded in Base64 format. The new view is marked as crowdsourced.\n\n"
        "### Request\n"
        "Send the following fields:\n"
        "- `poi_id`: ID of the POI\n"
        "- `tag`: descriptive tag for the image view\n"
        "- `poi_view_image`: Base64-encoded image of the view\n"
        "- `poi_metadata` (optional): metadata related to the POI view\n\n"
        "### Response\n"
        "```json\n"
        "{\n"
        "  \"message\": \"View added successfully\"\n"
        "}\n"
        "```"
    ),
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['poi_id', 'tag', 'poi_view_image'],
        properties={
            'poi_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the POI"),
            'tag': openapi.Schema(type=openapi.TYPE_STRING, description="Tag for the view image"),
            'poi_view_image': openapi.Schema(type=openapi.TYPE_STRING, format='byte', description="Base64-encoded image of the POI view"),
            'poi_metadata': openapi.Schema(type=openapi.TYPE_STRING, description="Optional metadata related to the POI view", nullable=True),
        }
    ),
    responses={
        200: 'View added successfully',
        401: 'Unauthorized – user must be authenticated',
        404: 'POI not found',
    }
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

@csrf_exempt
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def proxy_id_cromopoi(request):
    url = "https://cos2.cityopensource.com/api/cromo/spaces/5b165325-183f-86fb-0210-9718f29af21e/locations?format=json"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    if r.status_code != 200:
        return JsonResponse({
            "error": f"Server remoto ha risposto {r.status_code}",
            "text": r.text[:200]
        }, status=r.status_code)

    try:
        data = r.json()
    except ValueError:
        return JsonResponse({"error": "Server remoto non ha restituito JSON valido", "text": r.text[:200]}, status=500)

    return JsonResponse(data, safe=False)

@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def stream_images(request):
    minio_storage = MinioStorage()
    path = request.GET.get('path')
    try:
        file = minio_storage.open(path, mode='rb')
        content_type, _ = mimetypes.guess_type(path)
        if content_type is None:
                    content_type = 'application/octet-stream'
        response = FileResponse(file, as_attachment=False, filename=path)
        response['Content-Type'] = content_type
        return response
    except FileNotFoundError:
        return JsonResponse({"error": "File not found"}, status=404)