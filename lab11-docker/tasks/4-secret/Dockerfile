FROM python:3.12-slim
WORKDIR /app
# Токен приходит из конвейера: docker build --build-arg API_TOKEN=… .
ARG API_TOKEN
ENV API_TOKEN=${API_TOKEN}
COPY prepare.py app.py ./
RUN python3 prepare.py
EXPOSE 8000
CMD ["python3", "app.py"]
