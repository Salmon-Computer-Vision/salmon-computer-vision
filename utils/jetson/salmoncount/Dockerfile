FROM ultralytics/ultralytics:latest-jetson-jetpack4

# Install dependencies
RUN pip install watchdog

# Copy the necessary files
COPY videos /app/videos
COPY detections /app/detections
COPY config /app/config
COPY watcher.py /app/watcher.py
COPY salmon_counter.py /app/salmon_counter.py

WORKDIR /app

# Start the watcher script
CMD ["python3", "watcher.py"]

