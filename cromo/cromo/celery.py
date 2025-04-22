from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cromo.settings')

app = Celery('cromo')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks(lambda: ['cromo'])

app.conf.task_queues = {
    'api_tasks': {
        'exchange': 'api_tasks',
        'routing_key': 'api_tasks',
    }
}

# docker-compose exec web celery -A cromo.celery worker -Q api_tasks --concurrency=1 --loglevel=info
