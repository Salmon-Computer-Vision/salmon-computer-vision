FROM ultralytics/ultralytics:latest-jetson-jetpack4
ARG USER=Salmon-Computer-Vision REPO=salmon-computer-vision BRANCH=master

# Install dependencies
RUN python3 -m pip install -U pip && \
    python3 -m pip install watchdog lapx && \
    apt-get update && DEBIAN_FRONTEND="noninteractive" apt-get install -y ffmpeg cifs-utils

ADD https://api.github.com/repos/${USER}/${REPO}/git/refs/heads/${BRANCH} version.json
RUN git clone --branch ${BRANCH} --depth 1 https://github.com/${USER}/${REPO}.git /tools

RUN python3 -m pip install /tools/training/pysalmcount

COPY watcher.py /app/watcher.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

WORKDIR /app

ENTRYPOINT ["/app/entrypoint.sh"]
