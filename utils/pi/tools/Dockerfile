ARG IMAGE_REPO_HOST
ARG TAG
FROM ${IMAGE_REPO_HOST}/salmoncounter:${TAG}

RUN apt-get update && apt-get install -y ffmpeg
RUN python3 -m pip install ffmpeg-python

COPY reencode_h264.py /app/reencode_h264.py
