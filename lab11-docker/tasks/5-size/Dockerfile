FROM golang:1.23-alpine
WORKDIR /src
COPY . .
RUN go build -o /usr/local/bin/pinger .
EXPOSE 8080
CMD ["pinger"]
