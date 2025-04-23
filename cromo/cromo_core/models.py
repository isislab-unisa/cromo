from django.db import models
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
import logging
import dotenv
from storages.backends.s3boto3 import S3Boto3Storage
import os
from django.core.files.base import ContentFile
from django.contrib.gis.db import models as mdl
# from django_jsonform.models.fields import JSONField
from location_field.models.plain import PlainLocationField

dotenv.load_dotenv()

class MinioStorage(S3Boto3Storage):
    bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME")
    custom_domain = False

logger = logging.getLogger(__name__)

class Tag(models.Model):
    name = models.CharField(max_length=64, null=False, blank=False, primary_key=True)
    
    class Meta:
        db_table = "Tag"
        verbose_name = "Tag"
        verbose_name_plural = "Tag"
        
    def __str__(self):
        return self.name

class Status(models.TextChoices):
    READY = "READY", "Ready"
    FAILED = "FAILED", "Failed"
    BUILDING = "BUILDING", "Building"
    BUILDED = "BUILDED", "Builded"
    SERVING = "SERVING", "Serving"

class Cromo_POI(models.Model):
    title = models.CharField(max_length=64)
    creation_time = models.DateTimeField(auto_now_add=True)
    tag = models.ManyToManyField('Tag')
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY
    )
    location = PlainLocationField(zoom=7, null=True, blank=True)

    class Meta:
        db_table = "Cromo_POI"
        verbose_name = "Cromo POI"
        verbose_name_plural = "Cromo POIs"
        permissions = [
            ("can_create_cromo_poi", "Can create cromo_poi"),
            ("can_view_cromo_poi", "Can view cromo_poi"),
        ]

    def __str__(self):
        return self.title

    def get_folder_name(self):
        return f"{self.pk}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if is_new:
            super().save(*args, **kwargs)

        folder_name = self.get_folder_name()

        storage = MinioStorage()
        keep_path = f"{folder_name}/.keep"
        if not storage.exists(keep_path):
            storage.save(keep_path, ContentFile(b""))

        if is_new:
            self.status = Status.READY
        
        super().save(*args, **kwargs)

def upload_to_poi(instance, file_name):
    poi_id = instance.cromo_poi.id
    return f"{poi_id}/{file_name}"
    
class Cromo_View(models.Model):
    # ITEMS_SCHEMA = {
    #     'type': 'array', # a list which will contain the items
    #     'items': {
    #         'type': 'string' # items in the array are strings
    #     }
    # }
    tag = models.CharField(max_length=200)
    image = models.ImageField(upload_to=upload_to_poi, storage=MinioStorage(), null=True, blank=True)
    cromo_poi = models.ForeignKey(Cromo_POI, on_delete=models.CASCADE, related_name="images")
    timestamp = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    crowsourced = models.BooleanField(default=False)
    metadata = models.JSONField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Cromo View"
        verbose_name_plural = "Cromo Views"
    
    def __str__(self):
        return self.tag