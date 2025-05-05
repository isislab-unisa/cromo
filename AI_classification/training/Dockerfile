FROM PYTHON:3.10-slim

WORKDIR /workspace

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8090

CMD ["fastapi", "run", "main.py", "--port", "8090", "--host", "0.0.0.0"]

