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
import dotenv
dotenv.load_dotenv()    


MINIO_ENDPOINT = "http://minio:9001"
CALLBACK_ENDPOINT = "http://web:8001/complete_build"
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
    inference_image: str | None = None
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
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
    aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
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
    for page in paginator.paginate(
        Bucket=os.getenv("AWS_STORAGE_BUCKET_NAME"), Prefix=prefix
    ):
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
            s3_client.download_file(
                os.getenv("AWS_STORAGE_BUCKET_NAME"), key, local_path
            )
            print(f"Downloaded {key} → {local_path}")
    return local_dir

def read_s3_file(file_name):
    try:
        video_key = file_name
        response = s3.get_object(
            Bucket=os.getenv("AWS_STORAGE_BUCKET_NAME"), Key=video_key
        )
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
            os.getenv("AWS_STORAGE_BUCKET_NAME"),
            remote_path,
        )
        print(f"File {remote_path} written to S3")
    except Exception as e:
        print(f"Error writing file {file_path} to S3: {e}")


def run_inference_subproc(
    input_dir: str,
    model_path: str,
):
    try:
        cmd = [
            "python",
            "inference_script.py",
            "--image-path",
            input_dir,
            "--checkpoint",
            model_path,
        ]
        print("Running command:", " ".join(cmd))

        result = subprocess.run(cmd, check=True, capture_output=True)
        return result
    except Exception as e:
        print(f"Inference failed: {e}")

@app.get("/")
async def read_root():
    return {"Hello": "World"}    
    
@app.post("/inference")
async def inference(request: Request) -> Response:
    try:
        print(f"REQUEST: {request}")
        #DOWNLOAD REQUESTED MODEL FROM MINIO
        model, key = read_s3_file(request.model_url)
        if model is None:
            raise CustomHTTPException(
                status_code=404,
                detail="Model not found",
                error_code=1003,
            )
        #SAVE MODEL LOCALLY
        model_path = os.path.join("/models", request.poi_name)
        os.makedirs(model_path, exist_ok=True)
        with open(os.path.join(model_path, "model.pth"), "wb") as f:
            f.write(model)
        print("MODEL DOWNLOADED")
        
        #CONVERT REQUEST IMAGE FROM BASE64 TO JPG
        input_image = request.inference_image
        if input_image is None:
            raise CustomHTTPException(
                status_code=404,
                detail="Image not found",
                error_code=1004,
            )
        input_image = base64.b64decode(input_image)
        #SAVE IMAGE LOCALLY
        data_path = os.path.join("/data", request.poi_name)
        os.makedirs(data_path, exist_ok=True)
        with open(os.path.join(data_path, "input_image.jpg"), "wb") as f:
            f.write(input_image)
        print("DATA DOWNLOADED")
        
        #RUN INFERENCE
        result = run_inference_subproc(
            input_dir=os.path.join(data_path, "input_image.jpg"),
            model_path=os.path.join(model_path, "model.pth"),
        )
        
        print("INFERENCE DONE")
        
        #REMOVE FOLDER
        shutil.rmtree("/data", ignore_errors=True)
        
        return Response(
            model_url="",
            report_url="",
            view_name=request.view_name,
            poi_id=request.poi_id,
            message=f"{result}",
        )
        

    except Exception as e:
        raise CustomHTTPException(status_code=500, detail=str(e), error_code=1001)
