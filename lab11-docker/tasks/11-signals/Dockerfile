FROM python:3.12-slim
WORKDIR /app
COPY app.py entrypoint.sh ./
RUN chmod +x entrypoint.sh
ENV QUEUE_DIR=/tmp/queue
CMD ./entrypoint.sh
