package main

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	_ "github.com/lib/pq"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

var (
	redisClient *redis.Client
	db          *sql.DB
	tracer      trace.Tracer

	// Prometheus metrics
	streamingRequests = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ledgerline_streaming_requests_total",
			Help: "Total streaming requests processed",
		},
		[]string{"provider", "status"},
	)
	checkpointWrites = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "ledgerline_checkpoint_writes_total",
			Help: "Total checkpoint writes to Redis",
		},
	)
	streamingLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "ledgerline_streaming_latency_seconds",
			Help:    "Streaming request latency distribution",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"provider"},
	)
	orphanedStreamDetections = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "ledgerline_orphaned_stream_detections_total",
			Help: "Total orphaned streams detected",
		},
	)
)

func init() {
	prometheus.MustRegister(streamingRequests)
	prometheus.MustRegister(checkpointWrites)
	prometheus.MustRegister(streamingLatency)
	prometheus.MustRegister(orphanedStreamDetections)
}

type StreamRequest struct {
	CorrelationID      string            `json:"correlation_id"`
	AttemptID          string            `json:"attempt_id"`
	TenantID           string            `json:"tenant_id"`
	Provider           string            `json:"provider"`
	Model              string            `json:"model"`
	Messages           []interface{}     `json:"messages"`
	MaxTokens          int               `json:"max_tokens"`
	Temperature        float64           `json:"temperature"`
	CostAllocationTags map[string]string `json:"cost_allocation_tags"`
}

type StreamCheckpoint struct {
	CorrelationID string    `json:"correlation_id"`
	AttemptID     string    `json:"attempt_id"`
	TenantID      string    `json:"tenant_id"`
	Provider      string    `json:"provider"`
	Model         string    `json:"model"`
	TokenCount    int       `json:"token_count"`
	Status        string    `json:"status"`
	LastHeartbeat time.Time `json:"last_heartbeat"`
	CreatedAt     time.Time `json:"created_at"`
}

// writeCheckpoint writes an incremental checkpoint to Redis
func writeCheckpoint(ctx context.Context, checkpoint *StreamCheckpoint) error {
	ctx, span := tracer.Start(ctx, "writeCheckpoint")
	defer span.End()

	span.SetAttributes(
		attribute.String("correlation_id", checkpoint.CorrelationID),
		attribute.Int("token_count", checkpoint.TokenCount),
	)

	checkpoint.LastHeartbeat = time.Now()

	data, err := json.Marshal(checkpoint)
	if err != nil {
		return fmt.Errorf("failed to marshal checkpoint: %w", err)
	}

	// Write checkpoint with 5 minute TTL
	key := fmt.Sprintf("stream:checkpoint:%s", checkpoint.CorrelationID)
	if err := redisClient.SetEX(ctx, key, data, 5*time.Minute).Err(); err != nil {
		return fmt.Errorf("failed to write checkpoint to Redis: %w", err)
	}

	checkpointWrites.Inc()
	return nil
}

// sendHeartbeat updates the last_heartbeat timestamp without incrementing token count
func sendHeartbeat(ctx context.Context, correlationID string) error {
	key := fmt.Sprintf("stream:checkpoint:%s", correlationID)

	// Get existing checkpoint
	data, err := redisClient.Get(ctx, key).Result()
	if err != nil {
		return fmt.Errorf("failed to get checkpoint: %w", err)
	}

	var checkpoint StreamCheckpoint
	if err := json.Unmarshal([]byte(data), &checkpoint); err != nil {
		return fmt.Errorf("failed to unmarshal checkpoint: %w", err)
	}

	// Update heartbeat
	checkpoint.LastHeartbeat = time.Now()

	updatedData, err := json.Marshal(checkpoint)
	if err != nil {
		return fmt.Errorf("failed to marshal updated checkpoint: %w", err)
	}

	// Write back with fresh TTL
	if err := redisClient.SetEX(ctx, key, updatedData, 5*time.Minute).Err(); err != nil {
		return fmt.Errorf("failed to update heartbeat: %w", err)
	}

	return nil
}

// processStreamingRequest handles streaming AI requests with incremental checkpointing
func processStreamingRequest(ctx context.Context, req *StreamRequest) error {
	ctx, span := tracer.Start(ctx, "processStreamingRequest")
	defer span.End()

	startTime := time.Now()

	span.SetAttributes(
		attribute.String("correlation_id", req.CorrelationID),
		attribute.String("provider", req.Provider),
	)

	// Initialize checkpoint
	checkpoint := &StreamCheckpoint{
		CorrelationID: req.CorrelationID,
		AttemptID:     req.AttemptID,
		TenantID:      req.TenantID,
		Provider:      req.Provider,
		Model:         req.Model,
		TokenCount:    0,
		Status:        "STREAMING",
		CreatedAt:     time.Now(),
	}

	// Write initial checkpoint
	if err := writeCheckpoint(ctx, checkpoint); err != nil {
		log.Printf("Failed to write initial checkpoint: %v", err)
		streamingRequests.WithLabelValues(req.Provider, "checkpoint_failed").Inc()
		return err
	}

	// Start heartbeat goroutine (every 5 seconds)
	heartbeatCtx, cancelHeartbeat := context.WithCancel(ctx)
	defer cancelHeartbeat()

	heartbeatDone := make(chan struct{})
	go func() {
		ticker := time.NewTicker(5 * time.Second)
		defer ticker.Stop()
		defer close(heartbeatDone)

		for {
			select {
			case <-heartbeatCtx.Done():
				return
			case <-ticker.C:
				if err := sendHeartbeat(context.Background(), req.CorrelationID); err != nil {
					log.Printf("Heartbeat failed for %s: %v", req.CorrelationID, err)
				}
			}
		}
	}()

	// Simulate streaming response (in production, this would call OpenAI/Anthropic streaming API)
	tokenCount := 0
	lastCheckpointTokens := 0
	checkpointInterval := 50 // Write checkpoint every 50 tokens

	// Mock streaming - in production, replace with actual provider API call
	response := simulateStreamingResponse(req)
	scanner := bufio.NewScanner(strings.NewReader(response))
	scanner.Split(bufio.ScanWords)

	for scanner.Scan() {
		// Simulate receiving one token
		tokenCount++

		// Write checkpoint every N tokens
		if tokenCount-lastCheckpointTokens >= checkpointInterval {
			checkpoint.TokenCount = tokenCount
			if err := writeCheckpoint(ctx, checkpoint); err != nil {
				log.Printf("Failed to write checkpoint at %d tokens: %v", tokenCount, err)
			}
			lastCheckpointTokens = tokenCount
		}

		// Simulate streaming delay
		time.Sleep(10 * time.Millisecond)
	}

	// Stop heartbeat goroutine
	cancelHeartbeat()
	<-heartbeatDone

	// Write final checkpoint
	checkpoint.TokenCount = tokenCount
	checkpoint.Status = "COMPLETED"
	if err := writeCheckpoint(ctx, checkpoint); err != nil {
		log.Printf("Failed to write final checkpoint: %v", err)
		// Mark as PARTIAL for manual review
		checkpoint.Status = "PARTIAL"
		writeCheckpoint(ctx, checkpoint)
		streamingRequests.WithLabelValues(req.Provider, "partial").Inc()
		return err
	}

	// Write to ledger
	if err := writeLedgerEntry(ctx, checkpoint); err != nil {
		log.Printf("Failed to write ledger entry: %v", err)
		// Keep checkpoint for DLQ handler to pick up
		return err
	}

	// Clean up checkpoint after successful ledger write
	redisClient.Del(ctx, fmt.Sprintf("stream:checkpoint:%s", req.CorrelationID))

	streamingRequests.WithLabelValues(req.Provider, "success").Inc()
	streamingLatency.WithLabelValues(req.Provider).Observe(time.Since(startTime).Seconds())

	log.Printf("Streaming request %s completed with %d tokens", req.CorrelationID, tokenCount)
	return nil
}

// simulateStreamingResponse generates mock streaming response
func simulateStreamingResponse(req *StreamRequest) string {
	// In production, this would call the actual provider streaming API
	return `The quick brown fox jumps over the lazy dog. This is a simulated streaming response 
	that demonstrates incremental token tracking with checkpoints written to Redis every 50 tokens.
	The streaming dispatcher maintains a heartbeat every 5 seconds to prove the stream is still active.
	If the heartbeat stops for more than 30 seconds, the DLQ handler will detect it as an orphaned stream.
	This ensures zero-silent-loss even during network failures or service crashes during long-running streams.`
}

// writeLedgerEntry persists final token count to PostgreSQL
func writeLedgerEntry(ctx context.Context, checkpoint *StreamCheckpoint) error {
	ctx, span := tracer.Start(ctx, "writeLedgerEntry")
	defer span.End()

	query := `
		INSERT INTO ledger (
			correlation_id, attempt_id, tenant_id, provider, model, 
			token_count, status, created_at, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (correlation_id, attempt_id) 
		DO UPDATE SET 
			token_count = EXCLUDED.token_count,
			status = EXCLUDED.status,
			updated_at = EXCLUDED.updated_at
	`

	now := time.Now()
	_, err := db.ExecContext(ctx, query,
		checkpoint.CorrelationID,
		checkpoint.AttemptID,
		checkpoint.TenantID,
		checkpoint.Provider,
		checkpoint.Model,
		checkpoint.TokenCount,
		"RECONCILED",
		checkpoint.CreatedAt,
		now,
	)

	return err
}

// handleStreamRequest HTTP handler for streaming requests
func handleStreamRequest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req StreamRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate required fields
	if req.CorrelationID == "" || req.TenantID == "" || req.Provider == "" {
		http.Error(w, "Missing required fields", http.StatusBadRequest)
		return
	}

	// Process streaming request asynchronously
	go func() {
		if err := processStreamingRequest(context.Background(), &req); err != nil {
			log.Printf("Streaming request failed: %v", err)
		}
	}()

	// Return immediately with accepted status
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{
		"correlation_id": req.CorrelationID,
		"status":         "STREAMING",
		"message":        "Request accepted for streaming processing",
	})
}

// getStreamStatus returns current checkpoint for a streaming request
func getStreamStatus(w http.ResponseWriter, r *http.Request) {
	correlationID := r.URL.Query().Get("correlation_id")
	if correlationID == "" {
		http.Error(w, "Missing correlation_id parameter", http.StatusBadRequest)
		return
	}

	key := fmt.Sprintf("stream:checkpoint:%s", correlationID)
	data, err := redisClient.Get(r.Context(), key).Result()
	if err == redis.Nil {
		http.Error(w, "Stream not found", http.StatusNotFound)
		return
	} else if err != nil {
		log.Printf("Failed to get stream status: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	var checkpoint StreamCheckpoint
	if err := json.Unmarshal([]byte(data), &checkpoint); err != nil {
		log.Printf("Failed to unmarshal checkpoint: %v", err)
		http.Error(w, "Internal server error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(checkpoint)
}

func healthCheck(w http.ResponseWriter, r *http.Request) {
	if err := db.Ping(); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprintf(w, "Database unavailable: %v", err)
		return
	}

	if err := redisClient.Ping(r.Context()).Err(); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprintf(w, "Redis unavailable: %v", err)
		return
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, "OK")
}

func main() {
	tracer = otel.Tracer("streaming-dispatcher")

	// Initialize PostgreSQL
	dbConnStr := os.Getenv("DATABASE_URL")
	if dbConnStr == "" {
		dbConnStr = "postgres://ledgerline:ledgerline@localhost:5432/ledgerline?sslmode=disable"
	}

	var err error
	db, err = sql.Open("postgres", dbConnStr)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	// Initialize Redis
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
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := redisClient.Ping(ctx).Err(); err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}

	log.Println("Connected to Redis and PostgreSQL successfully")

	// HTTP routes
	http.HandleFunc("/stream", handleStreamRequest)
	http.HandleFunc("/stream/status", getStreamStatus)
	http.HandleFunc("/health", healthCheck)
	http.Handle("/metrics", promhttp.Handler())

	port := os.Getenv("PORT")
	if port == "" {
		port = "8083"
	}

	log.Printf("Streaming Dispatcher service starting on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
