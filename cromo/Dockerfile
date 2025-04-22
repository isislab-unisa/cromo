FROM python:3.12

WORKDIR /workspace

COPY . .

RUN apt-get update && \
    apt-get install -y default-libmysqlclient-dev build-essential && \
    pip install -r requirements.txt

RUN apt-get update && \
apt-get install -y ca-certificates && \
update-ca-certificates

RUN apt-get update && \
    apt-get install -y gdal-bin libgdal-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

RUN pip install gunicorn

EXPOSE 8000

CMD sh -c "python manage.py makemigrations && python manage.py migrate && python manage.py init_groups && gunicorn --bind 0.0.0.0:8000 cromo.wsgi:application"