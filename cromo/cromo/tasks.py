import requests
from celery import shared_task
from cromo_core.models import Cromo_POI, MinioStorage, Status
from django.core.mail import send_mail
import os
from dotenv import load_dotenv
load_dotenv()

@shared_task(bind=True)
def call_api_and_save(self, lesson_id, training_type):
    storage = MinioStorage()
    response = None
    try:
        lesson = Cromo_POI.objects.get(pk=lesson_id)
        payload = {
            'lesson_title': lesson.title,
            'lesson_id': lesson.id,
            'video_url': lesson.video_file,
            'training_type': training_type
        }
        
        # url = f"http://full_gaussian_pipe:8000/"
        
        # response = requests.post(url, data=payload)
        response = requests.Response()
        response.status_code = 200
        
        if response.status_code == 200:
            status = Status.BUILDING
            lesson.status = status
            lesson.save()
            send_mail(
                'Build in corso',
                f"Lezione {lesson.title} in fase di build.",
                os.environ.get('EMAIL_HOST_USER'),
                [lesson.user.email],
                fail_silently=False,
            )
            return f"Lezione {lesson_id} in building"
        elif response.status_code == 500:
            status = Status.FAILED
            lesson.status = status
            lesson.save()
            send_mail(
                'Build Fallita',
                f"Lezione: {lesson.title} fallita.",
                os.environ.get('EMAIL_HOST_USER'),
                [lesson.user.email],
                fail_silently=False,
            )
            return f"Build failed for lesson {lesson_id}"
        elif response.status_code == 404:
            status = Status.FAILED
            lesson.status = status
            lesson.save()
            send_mail(
                'Build Fallita',
                f"Lezione: {lesson.title} fallita. Video non trovato.",
                os.environ.get('EMAIL_HOST_USER'),
                [lesson.user.email],
                fail_silently=False,
            )
            return f"Build failed for lesson {lesson_id}"
        else:
            return f"Build failed for lesson {lesson_id}"
    
    except Exception as e:
        if response is not None and response.status_code != 200:
            status = Status.FAILED
            lesson.Status = status
            lesson.save()
            send_mail(
                'Build Fallita',
                f"Lezione: {lesson.title} fallita.",
                "demaio.dario95@gmail.com",
                [lesson.user.email],
                fail_silently=False,
            )
        return str(e)