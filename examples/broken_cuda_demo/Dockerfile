FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

RUN apt-get update \
    && apt-get install -y python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py
CMD ["python3", "/app/app.py"]
