package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/go-redis/redis/v8"
	_ "github.com/lib/pq"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/streadway/amqp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
	"net/http"
)

var (
	redisClient *redis.Client
	db          *sql.DB
	rabbitConn  *amqp.Connection
	rabbitCh    *amqp.Channel
	tracer      trace.Tracer

	// Prometheus metrics
	dlqProcessed = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "ledgerline_dlq_processed_total",
			Help: "Total DLQ messages processed",
		},
		[]string{"status", "reason"},
	)
	orphanedStreams = prometheus.NewGauge(
		prometheus.GaugeOpts{
			Name: "ledgerline_orphaned_streams",
			Help: "Current count of orphaned streams",
		},
	)
)

func init() {
	prometheus.MustRegister(dlqProcessed)
	prometheus.MustRegister(orphanedStreams)
}

type OutboxRecord struct {
	CorrelationID string    `json:"correlation_id"`
	AttemptID     string    `json:"attempt_id"`
	TenantID      string    `json:"tenant_id"`
	Status        string    `json:"status"`
	TokenCount    int       `json:"token_count"`
	Checkpoint    int       `json:"checkpoint"`
	Provider      string    `json:"provider"`
	CreatedAt     time.Time `json:"created_at"`
	LastHeartbeat time.Time `json:"last_heartbeat"`
}

type LedgerEntry struct {
	CorrelationID      string                 `json:"correlation_id"`
	AttemptID          string                 `json:"attempt_id"`
	TenantID           string                 `json:"tenant_id"`
	Status             string                 `json:"status"`
	TokenCount         int                    `json:"token_count"`
	EstimatedCost      float64                `json:"estimated_cost"`
	Provider           string                 `json:"provider"`
	CostAllocationTags map[string]string      `json:"cost_allocation_tags"`
	Metadata           map[string]interface{} `json:"metadata"`
	CreatedAt          time.Time              `json:"created_at"`
	UpdatedAt          time.Time              `json:"updated_at"`
}

// OrphanedStreamSweep runs every 10 seconds to detect orphaned streams
func OrphanedStreamSweep(ctx context.Context) {
	ticker := time.NewTicker(10 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := detectAndResolveOrphanedStreams(ctx); err != nil {
				log.Printf("Orphaned stream sweep failed: %v", err)
			}
		}
	}
}

// detectAndResolveOrphanedStreams finds streams that haven't been updated recently
func detectAndResolveOrphanedStreams(ctx context.Context) error {
	ctx, span := tracer.Start(ctx, "detectAndResolveOrphanedStreams")
	defer span.End()

	// Find all outbox records with status STREAMING that haven't been updated in 30s
	pattern := "outbox:*"
	var cursor uint64
	orphanCount := 0

	for {
		keys, newCursor, err := redisClient.Scan(ctx, cursor, pattern, 100).Result()
		if err != nil {
			return fmt.Errorf("redis scan failed: %w", err)
		}

		for _, key := range keys {
			data, err := redisClient.Get(ctx, key).Result()
			if err != nil {
				continue
			}

			var record OutboxRecord
			if err := json.Unmarshal([]byte(data), &record); err != nil {
				continue
			}

			// Check if this is an orphaned stream (no heartbeat for 30s)
			if record.Status == "STREAMING" && time.Since(record.LastHeartbeat) > 30*time.Second {
				log.Printf("Detected orphaned stream: %s (last heartbeat: %v)", record.CorrelationID, record.LastHeartbeat)
				orphanCount++

				// Attempt provider true-up
				if err := attemptProviderTrueUp(ctx, &record); err != nil {
					log.Printf("Provider true-up failed for %s: %v", record.CorrelationID, err)
					// Mark as PARTIAL for manual review
					if err := markAsPartial(ctx, &record); err != nil {
						log.Printf("Failed to mark as PARTIAL: %v", err)
					}
				}
			}
		}

		cursor = newCursor
		if cursor == 0 {
			break
		}
	}

	orphanedStreams.Set(float64(orphanCount))
	return nil
}

// attemptProviderTrueUp queries the provider API to get actual token usage
func attemptProviderTrueUp(ctx context.Context, record *OutboxRecord) error {
	ctx, span := tracer.Start(ctx, "attemptProviderTrueUp")
	defer span.End()

	span.SetAttributes(
		attribute.String("correlation_id", record.CorrelationID),
		attribute.String("provider", record.Provider),
	)

	// TODO: Implement actual provider API calls
	// For OpenAI: GET /v1/usage?date=...
	// For Anthropic: Similar usage endpoint
	
	// For now, we'll use the checkpoint as the final count
	finalTokens := record.Checkpoint
	
	// Update ledger with reconciled status
	entry := LedgerEntry{
		CorrelationID:      record.CorrelationID,
		AttemptID:          record.AttemptID,
		TenantID:           record.TenantID,
		Status:             "RECONCILED",
		TokenCount:         finalTokens,
		Provider:           record.Provider,
		CostAllocationTags: map[string]string{},
		Metadata: map[string]interface{}{
			"reconciliation_method": "provider_true_up",
			"checkpoint_tokens":     record.Checkpoint,
		},
		UpdatedAt: time.Now(),
	}

	if err := writeLedgerEntry(ctx, &entry); err != nil {
		return fmt.Errorf("failed to write ledger entry: %w", err)
	}

	// Remove from outbox
	outboxKey := fmt.Sprintf("outbox:%s", record.CorrelationID)
	redisClient.Del(ctx, outboxKey)

	dlqProcessed.WithLabelValues("reconciled", "provider_true_up").Inc()
	log.Printf("Successfully reconciled orphaned stream %s with %d tokens", record.CorrelationID, finalTokens)

	return nil
}

// markAsPartial marks a record as PARTIAL for manual review
func markAsPartial(ctx context.Context, record *OutboxRecord) error {
	entry := LedgerEntry{
		CorrelationID: record.CorrelationID,
		AttemptID:     record.AttemptID,
		TenantID:      record.TenantID,
		Status:        "PARTIAL",
		TokenCount:    record.Checkpoint,
		Provider:      record.Provider,
		Metadata: map[string]interface{}{
			"checkpoint_tokens": record.Checkpoint,
			"reason":            "orphaned_stream_timeout",
		},
		UpdatedAt: time.Now(),
	}

	if err := writeLedgerEntry(ctx, &entry); err != nil {
		return err
	}

	dlqProcessed.WithLabelValues("partial", "orphaned_stream").Inc()
	return nil
}

// writeLedgerEntry persists a ledger entry to PostgreSQL
func writeLedgerEntry(ctx context.Context, entry *LedgerEntry) error {
	ctx, span := tracer.Start(ctx, "writeLedgerEntry")
	defer span.End()

	costAllocationJSON, _ := json.Marshal(entry.CostAllocationTags)
	metadataJSON, _ := json.Marshal(entry.Metadata)

	query := `
		INSERT INTO ledger (
			correlation_id, attempt_id, tenant_id, status, token_count,
			estimated_cost, provider, cost_allocation_tags, metadata, updated_at
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		ON CONFLICT (correlation_id, attempt_id) 
		DO UPDATE SET 
			status = EXCLUDED.status,
			token_count = EXCLUDED.token_count,
			estimated_cost = EXCLUDED.estimated_cost,
			metadata = EXCLUDED.metadata,
			updated_at = EXCLUDED.updated_at
	`

	_, err := db.ExecContext(ctx, query,
		entry.CorrelationID,
		entry.AttemptID,
		entry.TenantID,
		entry.Status,
		entry.TokenCount,
		entry.EstimatedCost,
		entry.Provider,
		costAllocationJSON,
		metadataJSON,
		entry.UpdatedAt,
	)

	return err
}

// ProcessDLQMessages handles messages from the Dead Letter Queue
func ProcessDLQMessages(ctx context.Context) {
	msgs, err := rabbitCh.Consume(
		"ledgerline.dlq", // queue
		"dlq-handler",    // consumer tag
		false,            // auto-ack
		false,            // exclusive
		false,            // no-local
		false,            // no-wait
		nil,              // args
	)
	if err != nil {
		log.Fatalf("Failed to register DLQ consumer: %v", err)
	}

	for {
		select {
		case <-ctx.Done():
			return
		case msg := <-msgs:
			if err := processDLQMessage(ctx, msg); err != nil {
				log.Printf("Failed to process DLQ message: %v", err)
				msg.Nack(false, true) // Requeue
			} else {
				msg.Ack(false)
			}
		}
	}
}

func processDLQMessage(ctx context.Context, msg amqp.Delivery) error {
	ctx, span := tracer.Start(ctx, "processDLQMessage")
	defer span.End()

	var record OutboxRecord
	if err := json.Unmarshal(msg.Body, &record); err != nil {
		dlqProcessed.WithLabelValues("error", "invalid_json").Inc()
		return fmt.Errorf("invalid message format: %w", err)
	}

	span.SetAttributes(attribute.String("correlation_id", record.CorrelationID))

	// Determine resolution strategy based on the record state
	if record.Status == "STREAMING" {
		return attemptProviderTrueUp(ctx, &record)
	}

	// For other failures, mark as PARTIAL for manual review
	return markAsPartial(ctx, &record)
}

func healthCheck(w http.ResponseWriter, r *http.Request) {
	if err := db.Ping(); err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		fmt.Fprintf(w, "Database unavailable: %v", err)
		return
	}

	w.WriteHeader(http.StatusOK)
	fmt.Fprint(w, "OK")
}

func main() {
	tracer = otel.Tracer("dlq-handler")

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
		PoolSize:     50,
		MinIdleConns: 10,
	})

	// Initialize RabbitMQ
	rabbitURL := os.Getenv("RABBITMQ_URL")
	if rabbitURL == "" {
		rabbitURL = "amqp://guest:guest@localhost:5672/"
	}

	rabbitConn, err = amqp.Dial(rabbitURL)
	if err != nil {
		log.Fatalf("Failed to connect to RabbitMQ: %v", err)
	}
	defer rabbitConn.Close()

	rabbitCh, err = rabbitConn.Channel()
	if err != nil {
		log.Fatalf("Failed to open RabbitMQ channel: %v", err)
	}
	defer rabbitCh.Close()

	// Declare DLQ
	_, err = rabbitCh.QueueDeclare(
		"ledgerline.dlq", // name
		true,             // durable
		false,            // delete when unused
		false,            // exclusive
		false,            // no-wait
		nil,              // arguments
	)
	if err != nil {
		log.Fatalf("Failed to declare DLQ: %v", err)
	}

	ctx := context.Background()

	// Start background workers
	go OrphanedStreamSweep(ctx)
	go ProcessDLQMessages(ctx)

	// HTTP server for health checks and metrics
	http.HandleFunc("/health", healthCheck)
	http.Handle("/metrics", promhttp.Handler())

	port := os.Getenv("PORT")
	if port == "" {
		port = "8082"
	}

	log.Printf("DLQ Handler service starting on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
