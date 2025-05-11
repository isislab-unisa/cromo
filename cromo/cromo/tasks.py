import requests
from celery import shared_task
from cromo_core.models import Cromo_POI, MinioStorage, Status
from django.core.mail import send_mail
import os
import json
import time
import redis
from redis.exceptions import LockError
from redis.lock import Lock
from dotenv import load_dotenv
from django.utils import timezone
from datetime import timedelta

load_dotenv()

redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

@shared_task(bind=True, max_retries=20, default_retry_delay=10)
def call_api_and_save(self, cromo_poi_id):
    storage = MinioStorage()
    response = None
    lock = Lock(redis_client, "build_lock", timeout=24 * 60 * 60)

    try:
        cromo_poi = Cromo_POI.objects.get(pk=cromo_poi_id)
        print("Cromo POI:", cromo_poi.pk, cromo_poi.title)

        print("Tentativo di acquisizione lock...")
        try:
            acquired = lock.acquire(blocking=True, blocking_timeout=24 * 60 * 60)
            print(f"Acquired: {acquired}")
            if not acquired:
                print(f"Could not acquire lock for cromo poi {cromo_poi_id}, retrying...")
                raise self.retry(exc=Exception("Could not acquire build lock"), countdown=10)
        except Exception as lock_error:
            print(f"Errore nell'acquisizione del lock: {lock_error}")
            raise self.retry(exc=lock_error, countdown=10)
        
        print("Lock acquisito, procedo con la build...")
        try:
            payload = {
                "poi_name": cromo_poi.title,
                "poi_id": str(cromo_poi_id),
                "data_url": f"{cromo_poi_id}/data/",
            }

            url = f"http://ai_training:8090/train_model"
            headers = {"Content-type": "application/json"}
            response = requests.post(url, headers=headers, json=payload)
            
            print("Response status code:", response.status_code)
            print(response)
            
            # Simulazione della build
            # print("Simulazione build in corso...")
            
            # response = requests.Response()
            # response.status_code = 200

            if response.status_code == 200:
                cromo_poi.status = Status.BUILDING
                cromo_poi.build_started_at = timezone.now()
                cromo_poi.save()
                send_mail(
                    'Build in corso',
                    f"Cromo POI {cromo_poi.title} in fase di build.",
                    os.environ.get('EMAIL_HOST_USER'),
                    [cromo_poi.user.email],
                    fail_silently=False,
                )
                return f"Cromo POI {cromo_poi} in building"
            else:
                status = Status.FAILED
                cromo_poi.status = status
                cromo_poi.save()
                send_mail(
                    'Build Fallita',
                    f"Cromo POI: {cromo_poi.title} fallita. Errore interno del server",
                    os.environ.get('EMAIL_HOST_USER'),
                    [cromo_poi.user.email],
                    fail_silently=False,
                )
                if lock.locked():
                    print("Rilascio il lock...")
                    lock.release()
                return f"Build failed for cromo POI {cromo_poi}"  

        finally:
            pass
            # if lock.locked():
            #     print("Rilascio il lock...")
            #     lock.release()

    except Cromo_POI.DoesNotExist:
        return f"Cromo POI {cromo_poi} does not exist."

    except Exception as e:
        print(f"Errore generale: {e}")
        if response is not None and response.status_code != 200:
            status = Status.FAILED
            cromo_poi.status = status
            cromo_poi.save()
            send_mail(
                'Build Fallita',
                f"Cromo POI: {cromo_poi.title} fallita. Errore interno del server",
                os.environ.get('EMAIL_HOST_USER'),
                [cromo_poi.user.email],
                fail_silently=False,
            )
        return str(e)

@shared_task(queue='api_tasks')
def fail_stuck_builds():
    try:
        redis_client = redis.StrictRedis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        build_lock = Lock(redis_client, "build_lock")
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")
            
    cromo_poi = None
    try:
        timeout_minutes = 18 * 60 # 24 hours
        threshold = timezone.now() - timedelta(minutes=timeout_minutes)

        cromo_poi = Cromo_POI.objects.filter(status=Status.BUILDING, build_started_at__lt=threshold).first()
    except Cromo_POI.DoesNotExist:
        print("Cromo POI does not exist")
    except Exception as e:
        print(f"Errore: {e}")
        
    if cromo_poi is None:
        return
    try:
        cromo_poi.status = Status.FAILED
        cromo_poi.save()
        send_mail(
            'Build Fallita',
            f"Cromo POI: {cromo_poi.title} è fallita automaticamente per superamento del tempo massimo di build.",
            os.environ.get('EMAIL_HOST_USER'),
            [cromo_poi.user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")
    
    try:
        if build_lock.locked():
            build_lock.release()
    except Exception as e:
        print(f"Errore nell'acquisizione del lock: {e}")