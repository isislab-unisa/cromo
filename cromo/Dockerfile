FROM python:3.12

WORKDIR /workspace

COPY . .

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    build-essential \
    gdal-bin \
    libgdal-dev \
    ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

RUN pip install gunicorn

EXPOSE 8001