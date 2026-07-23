# Semantic Cache Monitoring Dashboard & Alerts

**Date:** July 24, 2026  
**Status:** Ready for Deployment  

---

## Prometheus Alert Rules

### File: `monitoring/prometheus_rules.yml`

```yaml
groups:
  - name: semantic_cache_alerts
    interval: 30s
    rules:
      
      # CRITICAL ALERTS - Immediate Page-on-Call
      
      - alert: CacheServiceDown
        expr: up{job="semantic-cache"} == 0
        for: 2m
        severity: critical
        annotations:
          summary: "Semantic Cache Service is DOWN"
          description: "Cache service at {{ $labels.instance }} has been down for >2 minutes"
          runbook: "https://wiki/runbooks/cache-service-down"
      
      - alert: CacheOperationErrors
        expr: rate(ledgerline_cache_operations_total{result="error"}[5m]) > 0.1
        for: 5m
        severity: critical
        annotations:
          summary: "High cache operation error rate (>0.1/sec)"
          description: "Cache errors at {{ $labels.instance }}: {{ $value }} errors/sec"
          runbook: "https://wiki/runbooks/cache-errors"
      
      - alert: GDPRComplianceViolation
        expr: increase(ledgerline_cache_consent_violations[1h]) > 0
        for: 1m
        severity: critical
        annotations:
          summary: "🔴 CRITICAL: GDPR Consent Violation Detected"
          description: "Cache returned hit despite withdrawn consent. Investigate immediately."
          action: "Page compliance officer immediately"
      
      # HIGH ALERTS - Require Investigation
      
      - alert: CachePolicyMismatch
        expr: increase(ledgerline_cache_policy_mismatches[1h]) > 0
        for: 5m
        severity: high
        annotations:
          summary: "Cache policy version mismatch detected"
          description: "Policy mismatch: {{ $value }} incidents in last hour"
          action: "Verify policy update propagation"
      
      - alert: HighCacheLatency
        expr: histogram_quantile(0.99, ledgerline_cache_latency_seconds) > 0.1
        for: 10m
        severity: high
        annotations:
          summary: "Cache query latency high (P99 > 100ms)"
          description: "P99 latency: {{ $value }}s"
          action: "Check Qdrant and PostgreSQL performance"
      
      - alert: RateLimitCheckFailures
        expr: increase(ledgerline_cache_rate_limit_blocks[1h]) > 1000
        for: 5m
        severity: high
        annotations:
          summary: "Excessive rate limit blocks in cache"
          description: "{{ $value }} rate limit blocks in last hour"
          action: "Review rate limit configuration"
      
      - alert: CacheLedgerLinkingFailed
        expr: |
          rate(ledgerline_cache_operations_total{result="hit"}[5m]) > 0 and
          rate(ledgerline_ledger_entries_created{request_type="cache_hit"}[5m]) == 0
        for: 5m
        severity: high
        annotations:
          summary: "Cache hits not being recorded in ledger"
          description: "Billing discrepancy: cache hits not linked to ledger"
          action: "Verify ledger recording logic"
      
      # MEDIUM ALERTS - Monitor & Trend
      
      - alert: LowCacheHitRate
        expr: (rate(ledgerline_cache_operations_total{result="hit"}[5m]) / rate(ledgerline_cache_operations_total[5m])) < 0.1
        for: 30m
        severity: warning
        annotations:
          summary: "Cache hit rate low (<10%)"
          description: "Hit rate: {{ $value }}. Check cache warmth."
          action: "Review cache warming strategy"
      
      - alert: ConsentViolationSpike
        expr: rate(ledgerline_cache_consent_violations[5m]) > 1
        for: 5m
        severity: warning
        annotations:
          summary: "Spike in consent violations detected"
          description: "{{ $value }} violations/sec. Investigate GDPR compliance."
          action: "Review candidate_consent table for anomalies"
      
      - alert: CacheMemoryHighUsage
        expr: container_memory_usage_bytes{name="ledgerline_cache"} > 1000000000
        for: 10m
        severity: warning
        annotations:
          summary: "Cache service memory usage high (>1GB)"
          description: "Memory: {{ $value | humanize }}"
          action: "Consider memory optimization or scaling"
      
      # INFORMATIONAL - Trend Tracking
      
      - alert: CacheInvalidationHigh
        expr: increase(ledgerline_cache_policy_mismatches[1h]) > 10
        for: 30m
        severity: info
        annotations:
          summary: "High cache invalidation rate"
          description: "{{ $value }} policy mismatches/hour"
          action: "Review policy update frequency"

# Alert notification channels
alertmanager:
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
      repeat_interval: 5m
    
    - match:
        severity: high
      receiver: 'slack-oncall'
      repeat_interval: 15m
    
    - match:
        severity: warning
      receiver: 'slack-engineering'
      repeat_interval: 1h
    
    - match:
        severity: info
      receiver: 'slack-monitoring'
      repeat_interval: 24h
```

---

## Grafana Dashboard JSON

### Dashboard: "Semantic Cache - 24h Monitoring"

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": "-- Prometheus --",
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "gstatus": "ok",
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "",
            "axisPlacement": "auto",
            "barAlignment": 0,
            "drawStyle": "line",
            "fillOpacity": 10,
            "gradientMode": "none",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            },
            "lineInterpolation": "linear",
            "lineWidth": 1,
            "pointSize": 5,
            "scaleDistribution": {
              "type": "linear"
            },
            "showPoints": "never",
            "spanNulls": false,
            "stacking": {
              "group": "A",
              "mode": "none"
            },
            "thresholdsStyle": {
              "mode": "off"
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 80
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 0
      },
      "id": 1,
      "options": {
        "legend": {
          "calcs": ["mean", "max"],
          "displayMode": "table",
          "placement": "right"
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "rate(ledgerline_cache_operations_total{result=\"hit\"}[5m])",
          "format": "time_series",
          "intervalFactor": 2,
          "legendFormat": "Cache Hits/sec",
          "refId": "A"
        },
        {
          "expr": "rate(ledgerline_cache_operations_total{result=\"miss\"}[5m])",
          "format": "time_series",
          "intervalFactor": 2,
          "legendFormat": "Cache Misses/sec",
          "refId": "B"
        },
        {
          "expr": "rate(ledgerline_cache_operations_total{result=\"error\"}[5m])",
          "format": "time_series",
          "intervalFactor": 2,
          "legendFormat": "Errors/sec",
          "refId": "C"
        }
      ],
      "title": "Cache Operations Rate",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "red",
                "value": null
              },
              {
                "color": "yellow",
                "value": 10
              },
              {
                "color": "green",
                "value": 20
              }
            ]
          },
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 0
      },
      "id": 2,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "values": false,
          "limit": 0,
          "calcs": ["lastNotNull"]
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true,
        "text": {}
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "100 * rate(ledgerline_cache_operations_total{result=\"hit\"}[5m]) / rate(ledgerline_cache_operations_total[5m])",
          "format": "time_series",
          "intervalFactor": 2,
          "legendFormat": "Hit Rate %",
          "refId": "A"
        }
      ],
      "title": "Cache Hit Rate (%)",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "Latency (seconds)",
            "axisPlacement": "auto",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "yellow",
                "value": 0.05
              },
              {
                "color": "red",
                "value": 0.1
              }
            ]
          },
          "unit": "s"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 0,
        "y": 8
      },
      "id": 3,
      "options": {
        "legend": {
          "calcs": ["mean", "max"],
          "displayMode": "table",
          "placement": "right"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "histogram_quantile(0.5, ledgerline_cache_latency_seconds)",
          "legendFormat": "P50",
          "refId": "A"
        },
        {
          "expr": "histogram_quantile(0.95, ledgerline_cache_latency_seconds)",
          "legendFormat": "P95",
          "refId": "B"
        },
        {
          "expr": "histogram_quantile(0.99, ledgerline_cache_latency_seconds)",
          "legendFormat": "P99",
          "refId": "C"
        }
      ],
      "title": "Cache Latency Distribution",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "axisLabel": "Count",
            "axisPlacement": "auto",
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 8,
        "w": 12,
        "x": 12,
        "y": 8
      },
      "id": 4,
      "targets": [
        {
          "expr": "increase(ledgerline_cache_policy_mismatches[1h])",
          "legendFormat": "Policy Mismatches",
          "refId": "A"
        },
        {
          "expr": "increase(ledgerline_cache_consent_violations[1h])",
          "legendFormat": "Consent Violations",
          "refId": "B"
        },
        {
          "expr": "increase(ledgerline_cache_rate_limit_blocks[1h])",
          "legendFormat": "Rate Limit Blocks",
          "refId": "C"
        }
      ],
      "title": "Compliance Events (Last Hour)",
      "type": "timeseries"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "red",
                "value": 1
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 0,
        "y": 16
      },
      "id": 5,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "values": false,
          "limit": 0,
          "calcs": ["lastNotNull"]
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "increase(ledgerline_cache_policy_mismatches[24h])",
          "legendFormat": "Policy Mismatches (24h)",
          "refId": "A"
        }
      ],
      "title": "Policy Mismatches (24h)",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              },
              {
                "color": "yellow",
                "value": 5
              },
              {
                "color": "red",
                "value": 10
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 6,
        "y": 16
      },
      "id": 6,
      "targets": [
        {
          "expr": "increase(ledgerline_cache_consent_violations[24h])",
          "legendFormat": "Consent Violations (24h)",
          "refId": "A"
        }
      ],
      "title": "GDPR Consent Violations (24h)",
      "type": "gauge"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "palette-classic"
          },
          "custom": {
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            }
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          }
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 12,
        "y": 16
      },
      "id": 7,
      "options": {
        "legend": {
          "displayMode": "list",
          "placement": "bottom"
        },
        "pieType": "donut",
        "reduceOptions": {
          "values": false,
          "limit": 0,
          "calcs": ["lastNotNull"]
        },
        "tooltip": {
          "mode": "single"
        }
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "sum(increase(ledgerline_cache_operations_total[24h])) by (result)",
          "format": "time_series",
          "intervalFactor": 2,
          "legendFormat": "{{ result }}",
          "refId": "A"
        }
      ],
      "title": "Operations Distribution (24h)",
      "type": "piechart"
    },
    {
      "datasource": "Prometheus",
      "fieldConfig": {
        "defaults": {
          "color": {
            "mode": "thresholds"
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {
                "color": "green",
                "value": null
              }
            ]
          },
          "unit": "short"
        },
        "overrides": []
      },
      "gridPos": {
        "h": 4,
        "w": 6,
        "x": 18,
        "y": 16
      },
      "id": 8,
      "options": {
        "orientation": "auto",
        "reduceOptions": {
          "values": false,
          "limit": 0,
          "calcs": ["lastNotNull"]
        },
        "showThresholdLabels": false,
        "showThresholdMarkers": true
      },
      "pluginVersion": "8.0.0",
      "targets": [
        {
          "expr": "increase(ledgerline_cache_rate_limit_blocks[24h])",
          "legendFormat": "Rate Limit Blocks (24h)",
          "refId": "A"
        }
      ],
      "title": "Rate Limit Blocks (24h)",
      "type": "stat"
    }
  ],
  "refresh": "10s",
  "schemaVersion": 30,
  "style": "dark",
  "tags": [
    "semantic-cache",
    "deployment",
    "monitoring"
  ],
  "templating": {
    "list": []
  },
  "time": {
    "from": "now-24h",
    "to": "now"
  },
  "timepicker": {},
  "timezone": "",
  "title": "Semantic Cache - 24h Deployment Monitoring",
  "uid": "semantic-cache-deployment",
  "version": 1
}
```

---

## 24-Hour Monitoring Checklist

### Hour-by-Hour Schedule

| Hour | Time UTC | Check | Action |
|------|----------|-------|--------|
| 0-1 | 00:00-01:00 | Service startup | Verify no startup errors |
| 1-2 | 01:00-02:00 | Stability | Check metrics flowing |
| 2-3 | 02:00-03:00 | Health | Verify health check endpoint |
| 3-4 | 03:00-04:00 | Database | Verify DB connection stable |
| 4-5 | 04:00-05:00 | First traffic | Monitor first requests |
| 5-6 | 05:00-06:00 | Ledger recording | Verify cache entries in ledger |
| 6-7 | 06:00-07:00 | Policy checks | Verify policy validation working |
| 7-8 | 07:00-08:00 | Consent checks | Verify consent validation working |
| 8-12 | 08:00-12:00 | Peak load | Monitor under load |
| 12-16 | 12:00-16:00 | Performance | Verify latency acceptable |
| 16-20 | 16:00-20:00 | Compliance | Verify no violations |
| 20-24 | 20:00-00:00 | Stability | Final stability confirmation |

### Hourly Check Template

```bash
#!/bin/bash
# check_hour.sh - Run at the start of each hour

HOUR=$(date +%H)
TIMESTAMP=$(date)

echo "=== Semantic Cache Monitoring - Hour $HOUR: $TIMESTAMP ===" | tee hour_$HOUR.log

# 1. Service health
echo "
1. SERVICE HEALTH:"
curl -s http://localhost:8088/health | jq . >> hour_$HOUR.log

# 2. Metrics summary
echo "
2. METRICS SUMMARY:"
curl -s http://localhost:9090/api/v1/query?query='sum(rate(ledgerline_cache_operations_total[5m]))' | jq . >> hour_$HOUR.log

# 3. Error rate
echo "
3. ERROR RATE (errors/sec):"
curl -s http://localhost:9090/api/v1/query?query='rate(ledgerline_cache_operations_total{result="error"}[5m])' | jq . >> hour_$HOUR.log

# 4. Hit rate
echo "
4. HIT RATE (%):"
curl -s http://localhost:9090/api/v1/query?query='100*rate(ledgerline_cache_operations_total{result="hit"}[5m])/rate(ledgerline_cache_operations_total[5m])' | jq . >> hour_$HOUR.log

# 5. Compliance events
echo "
5. COMPLIANCE EVENTS (last hour):"
psql -U ledgerline -d ledgerline -c "
  SELECT hit_reason, COUNT(*) as count FROM cache_hit_log 
  WHERE created_at > NOW() - INTERVAL '1 hour'
  GROUP BY hit_reason
  ORDER BY count DESC;
" >> hour_$HOUR.log

# 6. Latency (P99)
echo "
6. LATENCY P99:"
curl -s http://localhost:9090/api/v1/query?query='histogram_quantile(0.99,ledgerline_cache_latency_seconds)' | jq . >> hour_$HOUR.log

# 7. Decision
echo "
7. DECISION:"
if grep -q "error" hour_$HOUR.log; then
  echo "⚠️ ERRORS DETECTED - Investigate" >> hour_$HOUR.log
else
  echo "✅ HOUR $HOUR PASSED - Continue monitoring" >> hour_$HOUR.log
fi
```

---

## Critical Thresholds

| Metric | Threshold | Severity | Action |
|--------|-----------|----------|--------|
| Error rate | > 0.1/sec | CRITICAL | Page on-call |
| GDPR violation | > 0 | CRITICAL | Immediate investigation |
| Policy mismatch | > 0 | HIGH | Review policy updates |
| Hit rate | < 5% (after warmup) | MEDIUM | Check cache warming |
| P99 latency | > 100ms | MEDIUM | Check infrastructure |
| Rate limit blocks | > 100/hour | LOW | Review limits |

---

## Success Criteria for 24h Monitoring

✅ **All of these must be true:**

1. **Availability:** Service uptime = 100%
2. **Errors:** Error rate < 0.01/sec (except during intentional tests)
3. **GDPR:** Zero consent violations
4. **Policies:** Zero policy mismatches (after initial warmup)
5. **Billing:** All cache hits recorded in ledger
6. **Latency:** P99 latency < 100ms
7. **Reliability:** No false positive alerts
8. **Completeness:** All audit logs properly populated

---

**Monitoring Configuration Status:** ✅ Ready for Deployment  
**Last Updated:** July 23, 2026 22:43 UTC+5:30
