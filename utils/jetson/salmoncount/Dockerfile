FROM ultralytics/ultralytics:latest-jetson-jetpack4

# Install dependencies
RUN pip install watchdog

WORKDIR /app

# Start the watcher script
CMD ["python3", "watcher.py"]

