import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import boto3
from urllib.parse import urlparse
import shutil
import requests
import threading
import subprocess
import base64


MINIO_EDNPOINT = "http://minio:9000"
MINIO_ROOT_USER = "minioadmin"
MINIO_ROOT_PASSWORD = "minioadmin123"
AWS_STORAGE_BUCKET_NAME = "points-of-interests"
CALLBACK_ENDPOINT = "http://web:8001/complete_build/"
TOKEN_REQUEST_ENDPOINT = "http://web:8001/api/token/"


class CustomHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, error_code: int):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class Response(BaseModel):
    model_url: str | None = None
    report_url: str | None = None
    view_name: str | None = None
    poi_id: str | None = None
    message: str | None = None


class Request(BaseModel):
    data_url: str | None = None
    model_url: str | None = None
    poi_name: str | None = None
    poi_id: str | None = None


app = FastAPI()

# origins = ["http://localhost", "http://localhost:8000", "*"]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )


s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_EDNPOINT,
    aws_access_key_id=MINIO_ROOT_USER,
    aws_secret_access_key=MINIO_ROOT_PASSWORD,
)

#prefix = "root_folder/"
def download_minio_folder(prefix: str, local_dir: str, s3_client):
    """
    Downloads all objects from `bucket_name` under `prefix` to `local_dir`,
    preserving the folder hierarchy.
    """
    paginator = s3_client.get_paginator(
        "list_objects_v2"
    )  # Handles pagination :contentReference[oaicite:3]{index=3}
    for page in paginator.paginate(Bucket=AWS_STORAGE_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                # Skip zero-byte “folder” markers
                continue

            # Derive the local path by stripping the prefix
            rel_path = os.path.relpath(key, prefix)
            local_path = os.path.join(local_dir, rel_path)

            # Ensure the target directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            # Download the object to the local path
            s3_client.download_file(AWS_STORAGE_BUCKET_NAME, key, local_path)
            print(f"Downloaded {key} → {local_path}")
    return local_dir

def read_s3_file(file_name):
    try:
        video_key = file_name
        response = s3.get_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=video_key)
        print("RESPONSE:" + str(response))
        data = response["Body"].read()
        return data, video_key
    except Exception as e:
        print(f"Error reading file from S3: {e}")
        return None


def write_s3_file(file_path, remote_path):
    try:
        s3.upload_file(
            file_path,
            AWS_STORAGE_BUCKET_NAME,
            remote_path,
        )
        print(f"File {remote_path} written to S3")
    except Exception as e:
        print(f"Error writing file {file_path} to S3: {e}")


def run_training_subproc(
    input_dir: str,
    output_dir: str,
    num_epochs: int,
    run_name: int,
):
    try:
        cmd = [
            "python",
            "train_script.py",
            "--input-dir",
            input_dir,
            "--output-dir",
            output_dir,
            "--run-name",
            run_name,
        ]
        if num_epochs != 25:
            cmd.append("--num-epochs")
            cmd.append(str(num_epochs))
        print("Running command:", " ".join(cmd))

        subprocess.run(cmd, check=True)
        return
    except Exception as e:
        print(f"Training failed: {e}")


def run_train(request: Request, view_dir: str, data_path: str):

    try:
        # RUN THE FULL PIPELINE
        run_training_subproc(
            input_dir=data_path,
            output_dir=view_dir,
            num_epochs=25,
            run_name=request.view_name,
        )

        model_path = os.path.join(view_dir, "model.pth")
        report_path = os.path.join(view_dir, "probability_table.csv")

        # LOAD ON MINIO
        write_s3_file(
            model_path, f"{request.poi_id}/model.pth"
        )
        
        write_s3_file(
            report_path, f"{request.poi_id}/report.csv"
        )
        
        
        # DELETE FOLDER
        shutil.rmtree(view_dir, ignore_errors=True)
        print("Folder deleted")

        # print("Running full pipeline...")
        # time.sleep(5)  # Simulate processing time
        # # Simulate successful completion of the pipeline

        # REQUEST TOKEN
        token_payload = {
            "username": "root",
            "password": "root",
        }

        token_response = requests.post(
            TOKEN_REQUEST_ENDPOINT,
            json=token_payload,
        )
        print(
            "Token response:",
            token_response.status_code,
            token_response.text,
            flush=True,
        )
        token_access = token_response.json().get("access")

        callback_payload = {
            "view_id": request.lesson_id,
            "view_name": request.lesson_name,
            "model_path": f"{request.lesson_name}_{request.lesson_id}/model.pth",
            "report_path": f"{request.lesson_name}_{request.lesson_id}/report.csv",	
            "status": "COMPLETED",
        }

        headers = {
            "Authorization": f"Bearer {token_access}",
        }

        try:
            response = requests.post(
                CALLBACK_ENDPOINT,
                json=callback_payload,
                headers=headers,
            )
            print("Callback response:", response.status_code, response.text, flush=True)
        except requests.RequestException as e:
            print(f"Error sending callback: {e}")

    except Exception as e:
        print(f"Error processing full pipeline: {e}", flush=True)
        callback_payload = {
            "view_id": request.lesson_id,
            "view_name": request.lesson_name,
            "model_path": None,
            "report_path": None,
            "status": "FAILED",
        }

        token_payload = {
            "username": "root",
            "password": "root",
        }

        try:
            token_response = requests.post(
                TOKEN_REQUEST_ENDPOINT,
                json=token_payload,
            )
            print("Token response:", token_response.status_code, token_response.text)
            token_access = token_response.json().get("access")
            headers = {
                "Authorization": f"Bearer {token_access}",
            }

            response = requests.post(
                CALLBACK_ENDPOINT,
                json=callback_payload,
                headers=headers,
            )
            print("Callback response:", response.status_code, response.text)
        except requests.RequestException as e:
            print(f"Error sending callback: {e}")

@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.post("/train_model")
async def train_model(request: Request) -> Response:
    try:
        print(f"REQUEST: {request}")
        # CREATE A DIRECTORY FOR THE LESSON
        view_dir = f"/data/{request.view_name}"
        os.makedirs(view_dir, exist_ok=True)
        
        # RETRIEVE THE DATA FROM MINIO        
        local_data_path = download_minio_folder(request.data_url, view_dir, s3)
        print("DATA DOWNLOADED")
            
        worker_thread = threading.Thread(
            target=run_train,
            args=(request, view_dir, local_data_path),
            daemon=True,
        )
        worker_thread.start()

        if worker_thread.is_alive():
            return Response(
                message="Processing started. You will be notified once it is completed."
            )
        else:
            raise CustomHTTPException(
                status_code=500, detail="Processing failed", error_code=1002
            )

    except Exception as e:
        raise CustomHTTPException(status_code=500, detail=str(e), error_code=1001)
    