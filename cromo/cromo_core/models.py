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
    BUILT = "BUILT", "Built"
    SERVING = "SERVING", "Serving"

class CromoPOIQuerySet(models.QuerySet):
    def delete(self, *args, **kwargs):
        for obj in self:
            obj.delete()
        super().delete(*args, **kwargs)

class Cromo_POI(models.Model):
    title = models.CharField(max_length=64)
    creation_time = models.DateTimeField(auto_now_add=True)
    # tag = models.ManyToManyField('Tag')
    user = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.READY
    )
    location = PlainLocationField(zoom=7, null=True, blank=True)
    build_started_at = models.DateTimeField(null=True, blank=True)
    objects = CromoPOIQuerySet.as_manager()

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
    
    def delete(self, *args, **kwargs):
        folder_name = self.get_folder_name() + "/"
        storage = MinioStorage()
        elements = storage.bucket.objects.filter(Prefix=folder_name)
        try:
            for k in elements:
                k.delete()
        except:
            objects = list(storage.bucket.objects.all())
            object_keys = [obj.key for obj in objects]
            raise Exception(f"La cartella {folder_name} non esiste. Oggetti presenti: {object_keys}")
        super().delete(*args, **kwargs)

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
    poi_id = instance.cromo_view.cromo_poi.id
    tag = instance.cromo_view.tag.replace(" ", "_")
    storage = MinioStorage()
    elements = storage.bucket.objects.filter(Prefix=f"{poi_id}/data/{tag}/test")
    c = 0
    for k in elements:
        c += 1
    
    if c == 0:
        return f"{poi_id}/data/{tag}/test/{file_name}"
    else:
        return f"{poi_id}/data/{tag}/train/{file_name}"

def default_image(instance, file_name):
    return f"{instance.cromo_poi.id}/default_image/{file_name}"

class Cromo_View(models.Model):
    # ITEMS_SCHEMA = {
    #     'type': 'array', # a list which will contain the items
    #     'items': {
    #         'type': 'string' # items in the array are strings
    #     }
    # }
    tag = models.CharField(max_length=200)
    cromo_poi = models.ForeignKey(Cromo_POI, on_delete=models.CASCADE, related_name="images")
    timestamp = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    crowsourced = models.BooleanField(default=False)
    metadata = models.JSONField(null=True, blank=True)
    model_path = models.CharField(max_length=200, null=True, blank=True)
    build_started_at = models.DateTimeField(null=True, blank=True)
    default_image = models.ImageField(upload_to=default_image, storage=MinioStorage(), null=True, blank=True)
    
    class Meta:
        verbose_name = "Cromo View"
        verbose_name_plural = "Cromo Views"
    
    def __str__(self):
        return self.tag

class Cromo_Image(models.Model):
    cromo_view = models.ForeignKey(Cromo_View, related_name='images', on_delete=models.CASCADE, null=True, blank=True)
    image = models.ImageField(upload_to=upload_to_poi, storage=MinioStorage(), null=True, blank=True)
    
    def __str__(self):
        return f"Image for {self.cromo_view.tag}"