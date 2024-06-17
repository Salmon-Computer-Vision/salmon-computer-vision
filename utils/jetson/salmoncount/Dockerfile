FROM ultralytics/ultralytics:latest-jetson-jetpack4

# Install dependencies
RUN python3 -m pip install -U pip

ADD *.whl /whls/

RUN cd /whls && python3 -m pip install pytz-2024.1-py2.py3-none-any.whl python_dateutil-2.9.0.post0-py2.py3-none-any.whl
RUN cd /whls && python3 -m pip install pandas-1.1.5-cp36-cp36m-manylinux2014_aarch64.whl

RUN git clone --depth 1 https://github.com/Salmon-Computer-Vision/salmon-computer-vision.git /tools

RUN python3 -m pip install -e /tools/training/pysalmcount

RUN pip install watchdog

COPY 2023_combined_salmon.yaml /app/config/2023_combined_salmon.yaml
COPY watcher.py /app/watcher.py

WORKDIR /app

# Start the watcher script
CMD ["python3", "watcher.py"]

