# Run with -p 8888:8888

FROM ultralytics/ultralytics:latest

RUN pip3 install jupyterlab jupyterlab-vim
RUN pip3 install -U datumaro[default] jupyter ipywidgets

ENV JUPYTER_PORT=8888
EXPOSE $JUPYTER_PORT

COPY jupyter_lab_config.py  jupyter_notebook_config.json  jupyter_notebook_config.py /etc/jupyter/
