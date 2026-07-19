module github.com/ledgerline/rate-limiter

go 1.22

require (
	github.com/go-redis/redis/v8 v8.11.5
	github.com/prometheus/client_golang v1.19.0
	go.opentelemetry.io/otel v1.24.0
	go.opentelemetry.io/otel/trace v1.24.0
	go.opentelemetry.io/otel/exporters/jaeger v1.24.0
)
