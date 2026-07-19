package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-redis/redis/v8"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

var (
	redisClient *redis.Client
	tracer      trace.Tracer

	// Prometheus metrics
	rateLimitChecks = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ledgerline_rate_limit_checks_total",
			Help: "Total number of rate limit checks",
		},
		[]string{"tenant_id", "result"},
	)
	rateLimitLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "ledgerline_rate_limit_latency_seconds",
			Help:    "Rate limit check latency distribution",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"operation"},
	)
)

func init() {
	prometheus.MustRegister(rateLimitChecks)
	prometheus.MustRegister(rateLimitLatency)
}

type RateLimitRequest struct {
	TenantID     string `json:"tenant_id"`
	RequestType  string `json:"request_type"` // TPM or RPM
	TokensNeeded int    `json:"tokens_needed"`
}

type RateLimitResponse struct {
	Allowed        bool  `json:"allowed"`
	Remaining      int64 `json:"remaining"`
	RetryAfter     int64 `json:"retry_after,omitempty"`
	ResetTimestamp int64 `json:"reset_timestamp"`
}

// CheckRateLimit uses Redis-Cell (CL.THROTTLE) for token bucket rate limiting
func CheckRateLimit(ctx context.Context, req RateLimitRequest) (*RateLimitResponse, error) {
	ctx, span := tracer.Start(ctx, "CheckRateLimit")
	defer span.End()

	start := time.Now()
	defer func() {
		rateLimitLatency.WithLabelValues("check").Observe(time.Since(start).Seconds())
	}()

	span.SetAttributes(
		attribute.String("tenant_id", req.TenantID),
		attribute.String("request_type", req.RequestType),
		attribute.Int("tokens_needed", req.TokensNeeded),
	)

	// Redis-Cell key format: rate_limit:{tenant_id}:{type}
	key := fmt.Sprintf("rate_limit:%s:%s", req.TenantID, req.RequestType)

	// Get tenant-specific limits from configuration or use defaults
	// CL.THROTTLE key max_burst count_per_period period [tokens_needed]
	// Example: For 10k TPM = 10000 tokens per 60 seconds
	var maxBurst, countPerPeriod, period int64
	if req.RequestType == "TPM" {
		maxBurst = 10000       // Allow burst up to 10k tokens
		countPerPeriod = 10000 // 10k tokens
		period = 60            // per 60 seconds
	} else if req.RequestType == "RPM" {
		maxBurst = 100       // Allow burst up to 100 requests
		countPerPeriod = 100 // 100 requests
		period = 60          // per 60 seconds
	}

	// Execute CL.THROTTLE command
	// Returns: [allowed, limit, remaining, retry_after, reset_after]
	result, err := redisClient.Do(ctx, "CL.THROTTLE", key, maxBurst, countPerPeriod, period, req.TokensNeeded).Result()
	if err != nil {
		rateLimitChecks.WithLabelValues(req.TenantID, "error").Inc()
		return nil, fmt.Errorf("redis CL.THROTTLE failed: %w", err)
	}

	values := result.([]interface{})
	allowed := values[0].(int64) == 0
	remaining := values[2].(int64)
	retryAfter := values[3].(int64)
	resetAfter := values[4].(int64)

	response := &RateLimitResponse{
		Allowed:        allowed,
		Remaining:      remaining,
		RetryAfter:     retryAfter,
		ResetTimestamp: time.Now().Unix() + resetAfter,
	}

	if allowed {
		rateLimitChecks.WithLabelValues(req.TenantID, "allowed").Inc()
	} else {
		rateLimitChecks.WithLabelValues(req.TenantID, "rejected").Inc()
	}

	return response, nil
}

func handleRateLimit(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req RateLimitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	resp, err := CheckRateLimit(r.Context(), req)
	if err != nil {
		log.Printf("Rate limit check failed: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if !resp.Allowed {
		w.Header().Set("Retry-After", strconv.FormatInt(resp.RetryAfter, 10))
		w.WriteHeader(http.StatusTooManyRequests)
	}
	json.NewEncoder(w).Encode(resp)
}

func healthCheck(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	if err := redisClient.Ping(ctx).Err(); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprintf(w, "Redis unavailable: %v", err)
		return
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, "OK")
}

func main() {
	// Initialize OpenTelemetry
	tracer = otel.Tracer("rate-limiter")

	// Initialize Redis client
	redisAddr := os.Getenv("REDIS_ADDR")
	if redisAddr == "" {
		redisAddr = "localhost:6379"
	}

	redisClient = redis.NewClient(&redis.Options{
		Addr:         redisAddr,
		Password:     os.Getenv("REDIS_PASSWORD"),
		DB:           0,
		PoolSize:     100,
		MinIdleConns: 20,
		MaxRetries:   3,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
	})

	// Test Redis connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := redisClient.Ping(ctx).Err(); err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}

	log.Println("Connected to Redis successfully")

	// HTTP routes
	http.HandleFunc("/rate-limit", handleRateLimit)
	http.HandleFunc("/health", healthCheck)
	http.Handle("/metrics", promhttp.Handler())

	port := os.Getenv("PORT")
	if port == "" {
		port = "8081"
	}

	log.Printf("Rate Limiter service starting on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
