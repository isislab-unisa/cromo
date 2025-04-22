from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from cromo_core.models import Cromo_POI, Tag

class Command(BaseCommand):
    help = 'Crea i gruppi Author e Student con i permessi associati'

    def handle(self, *args, **kwargs):
        author_group, _ = Group.objects.get_or_create(name='Author')
        student_group, _ = Group.objects.get_or_create(name='Student')

        cromo_poi_ct = ContentType.objects.get_for_model(Cromo_POI)
        tag_ct = ContentType.objects.get_for_model(Tag)

        cromo_poi_perms = [
            Permission.objects.get(codename='add_cromo_poi', content_type=cromo_poi_ct),
            Permission.objects.get(codename='view_cromo_poi', content_type=cromo_poi_ct),
            Permission.objects.get(codename='change_cromo_poi', content_type=cromo_poi_ct),
            Permission.objects.get(codename='delete_cromo_poi', content_type=cromo_poi_ct),
        ]

        tag_perms = [
            Permission.objects.get(codename='add_tag', content_type=tag_ct),
            Permission.objects.get(codename='view_tag', content_type=tag_ct),
            Permission.objects.get(codename='change_tag', content_type=tag_ct),
            Permission.objects.get(codename='delete_tag', content_type=tag_ct),
        ]

        author_group.permissions.set(cromo_poi_perms + tag_perms)
        student_group.permissions.set([Permission.objects.get(codename='view_cromo_poi', content_type=cromo_poi_perms)])

        self.stdout.write(self.style.SUCCESS('Gruppi e permessi creati con successo.'))
