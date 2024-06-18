FROM ultralytics/ultralytics:latest-jetson-jetpack4

# Install dependencies
RUN python3 -m pip install -U pip

RUN git clone --depth 1 https://github.com/Salmon-Computer-Vision/salmon-computer-vision.git /tools

RUN python3 -m pip install /tools/training/pysalmcount

RUN pip install watchdog

COPY config /app/config
COPY watcher.py /app/watcher.py

WORKDIR /app

# Start the watcher script
CMD ["python3", "watcher.py"]

