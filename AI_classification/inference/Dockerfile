FROM pytorch/pytorch:2.7.0-cuda11.8-cudnn9-runtime

WORKDIR /workspace

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8050

CMD ["fastapi", "run", "main.py", "--port", "8050", "--host", "0.0.0.0"]

