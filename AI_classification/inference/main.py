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
from fastapi.responses import JSONResponse
import dotenv
dotenv.load_dotenv()    


MINIO_ENDPOINT = "http://minio:9000"
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
    print(f"Downloading {prefix} to {local_dir}")
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
        # print("RESPONSE:" + str(response))
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


def run_inference_subproc(input_dir: str, model_path: str):
    try:
        cmd = [
            "python", "inference_script.py",
            "--image-path", input_dir,
            "--checkpoint", model_path,
        ]
        print(f"Running command: {' '.join(cmd)}", flush=True)
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        if result.returncode != 0:
            print("Inference failed:", result.stderr, flush=True)
            raise RuntimeError(f"Inference script failed: {result.stderr}")

        return result.stdout.strip()
    except Exception as e:
        raise RuntimeError(f"Subprocess error: {e}")

@app.get("/")
async def read_root():
    return {"Hello": "World"}    
    
app = FastAPI()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os, shutil, base64, subprocess

@app.post("/inference")
async def inference(request: Request):
    try:
        # --- Leggi body JSON ---
        body = await request.json()
        model_url = body.get("model_url")
        poi_name = body.get("poi_name")
        poi_id = body.get("poi_id")
        input_image_b64 = body.get("inference_image")

        print(f"Requested model: {model_url}", flush=True)

        # --- Scarica modello da MinIO ---
        model, key = read_s3_file(model_url)
        if model is None:
            raise CustomHTTPException(
                status_code=404, detail="Model not found", error_code=1003
            )

        # --- Salva modello ---
        model_dir = os.path.join("/models", poi_name)
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "model.pt")
        with open(model_path, "wb") as f:
            f.write(model)
        print("MODEL DOWNLOADED", flush=True)

        # --- Decodifica immagine base64 ---
        if not input_image_b64:
            raise CustomHTTPException(
                status_code=404, detail="Image not found", error_code=1004
            )

        def decode_base64_image(data: str) -> bytes:
            if data.startswith("data:"):
                data = data.split(",")[1]
            missing_padding = len(data) % 4
            if missing_padding:
                data += "=" * (4 - missing_padding)
            return base64.b64decode(data)

        try:
            input_image_bytes = decode_base64_image(input_image_b64)
        except Exception as e:
            print("Error decoding base64 image:", e, flush=True)
            raise CustomHTTPException(
                status_code=400, detail="Invalid base64 image", error_code=1005
            )

        # --- Salva immagine ---
        data_dir = os.path.join("/data", poi_name)
        os.makedirs(data_dir, exist_ok=True)
        image_path = os.path.join(data_dir, "input_image.jpg")
        with open(image_path, "wb") as f:
            f.write(input_image_bytes)
        print("DATA DOWNLOADED", flush=True)

        # --- Esegui inference ---
        cmd = [
            "python",
            "inference_script.py",
            "--image-path", image_path,
            "--checkpoint", model_path
        ]
        print(f"Running command: {' '.join(cmd)}", flush=True)
        result_proc = subprocess.run(cmd, capture_output=True, text=True)

        if result_proc.returncode != 0:
            print("Inference failed:", result_proc.stderr, flush=True)
            raise CustomHTTPException(
                status_code=500,
                detail=f"Inference failed: {result_proc.stderr}",
                error_code=1006
            )

        print("INFERENCE DONE", flush=True)
        result = result_proc.stdout.strip()

        # --- Pulisci cartella temporanea ---
        shutil.rmtree(data_dir, ignore_errors=True)

        return JSONResponse(
            status_code=200,
            content={
                "model_url": model_url,
                "report_url": f"/reports/{poi_name}",
                "view_name": poi_name,
                "poi_id": poi_id,
                "message": result,
            },
        )

    except CustomHTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}", flush=True)
        raise CustomHTTPException(status_code=500, detail=str(e), error_code=1001)
