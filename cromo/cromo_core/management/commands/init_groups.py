from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Crea il gruppo "User" con i permessi per i modelli Cromo_POI, Cromo_Image, Cromo_View, CromoPOIQuerySet'

    def handle(self, *args, **kwargs):
        from cromo_core.models import Cromo_POI, Cromo_Image, Cromo_View, CromoPOIQuerySet

        user_group, created = Group.objects.get_or_create(name='User')

        poi_ct = ContentType.objects.get_for_model(Cromo_POI)
        image_ct = ContentType.objects.get_for_model(Cromo_Image)
        view_ct = ContentType.objects.get_for_model(Cromo_View)
        queryset_ct = ContentType.objects.get_for_model(CromoPOIQuerySet)

        perms = Permission.objects.filter(
            content_type__in=[poi_ct, image_ct, view_ct, queryset_ct]
        )

        user_group.permissions.set(perms)
        user_group.save()

        self.stdout.write(self.style.SUCCESS(
            'Gruppo "User" creato e permessi assegnati con successo ai modelli Cromo_POI, Cromo_Image, Cromo_View, CromoPOIQuerySet.'
        ))
