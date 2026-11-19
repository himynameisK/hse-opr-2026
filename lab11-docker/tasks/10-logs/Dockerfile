FROM python:3.12-slim
WORKDIR /app
COPY app.py .
RUN mkdir -p /var/log/shop
ENV LOG_FILE=/var/log/shop/app.log
EXPOSE 8000
CMD ["python3", "app.py"]
