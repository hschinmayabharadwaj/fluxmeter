FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod ./
COPY go.sum* ./
# Skip go.sum validation - will be regenerated on build
RUN go mod download || go get -u ./... || true

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o dlq-handler .

FROM alpine:latest

RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/dlq-handler .

EXPOSE 8082

CMD ["./dlq-handler"]
