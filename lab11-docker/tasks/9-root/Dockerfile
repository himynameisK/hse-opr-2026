FROM python:3.12-slim
WORKDIR /app
COPY app.py .
RUN mkdir -p /app/data
VOLUME /app/data
EXPOSE 8000
CMD ["python3", "app.py"]
