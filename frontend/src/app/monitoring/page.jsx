"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function MonitoringPage() {
  const [metrics, setMetrics] = useState({
    requestRate: 847,
    errorRate: 0.12,
    avgLatency: 127,
    p99Latency: 342,
    activeStreams: 42,
    queueDepth: 156,
    redisLatency: 3.2,
    cacheHitRate: 78.5,
  });

  const [systemHealth, setSystemHealth] = useState({
    services: [
      { name: "Kong Gateway", status: "healthy", latency: 12, uptime: "99.98%" },
      { name: "Rate Limiter", status: "healthy", latency: 3, uptime: "99.99%" },
      { name: "Dispatcher", status: "healthy", latency: 127, uptime: "99.97%" },
      { name: "DLQ Handler", status: "healthy", latency: 8, uptime: "100.00%" },
      { name: "Streaming Dispatcher", status: "healthy", latency: 145, uptime: "99.95%" },
    ],
    databases: [
      { name: "PostgreSQL", status: "healthy", connections: 23, maxConnections: 100 },
      { name: "Redis", status: "healthy", memory: "342MB", maxMemory: "512MB" },
      { name: "RabbitMQ", status: "healthy", messages: 156, consumers: 5 },
      { name: "Qdrant", status: "healthy", collections: 3, vectors: 12847 },
    ],
  });

  const [alerts, setAlerts] = useState([
    {
      id: 1,
      severity: "warning",
      message: "Rate limit rejections above 5% for tenant_002",
      timestamp: "2 minutes ago",
    },
    {
      id: 2,
      severity: "info",
      message: "Semantic cache hit rate increased to 82%",
      timestamp: "15 minutes ago",
    },
  ]);

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setMetrics((prev) => ({
        ...prev,
        requestRate: Math.floor(800 + Math.random() * 100),
        avgLatency: Math.floor(120 + Math.random() * 20),
        activeStreams: Math.floor(40 + Math.random() * 10),
      }));
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case "healthy":
        return "text-green-600 bg-green-50 dark:bg-green-950/30";
      case "degraded":
        return "text-amber-600 bg-amber-50 dark:bg-amber-950/30";
      case "unhealthy":
        return "text-red-600 bg-red-50 dark:bg-red-950/30";
      default:
        return "text-zinc-600 bg-zinc-50 dark:bg-zinc-950/30";
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case "critical":
        return "border-red-500 bg-red-50 dark:bg-red-950/20";
      case "warning":
        return "border-amber-500 bg-amber-50 dark:bg-amber-950/20";
      case "info":
        return "border-blue-500 bg-blue-50 dark:bg-blue-950/20";
      default:
        return "border-zinc-300 bg-zinc-50 dark:bg-zinc-950/20";
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-zinc-50 dark:bg-zinc-900">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b border-zinc-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60 dark:border-zinc-800 dark:bg-zinc-950/95">
        <div className="container flex h-16 items-center px-8">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500">
              <span className="text-lg font-bold text-white">L</span>
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent">
              Ledgerline
            </span>
          </div>
          <nav className="ml-auto flex items-center gap-6">
            <Link href="/" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Dashboard
            </Link>
            <Link href="/ledger" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Ledger
            </Link>
            <Link href="/monitoring" className="text-sm font-medium transition-colors hover:text-blue-600">
              Monitoring
            </Link>
            <Link href="/manual-review" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Manual Review
            </Link>
            <Link href="/config" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Configuration
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 container px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            Real-time Monitoring
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            System metrics, health checks, and performance monitoring
          </p>
        </div>

        {/* Key Metrics */}
        <div className="grid gap-4 md:grid-cols-4 mb-8">
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Request Rate</p>
            <p className="text-3xl font-bold text-zinc-900 dark:text-zinc-50 mt-2">{metrics.requestRate}</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">requests/min</p>
            <div className="mt-4 h-16 bg-gradient-to-r from-blue-500/20 to-cyan-500/20 rounded"></div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Error Rate</p>
            <p className="text-3xl font-bold text-green-600 dark:text-green-500 mt-2">{metrics.errorRate}%</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">last 5 minutes</p>
            <div className="mt-4 h-16 bg-gradient-to-r from-green-500/20 to-emerald-500/20 rounded"></div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Avg Latency</p>
            <p className="text-3xl font-bold text-zinc-900 dark:text-zinc-50 mt-2">{metrics.avgLatency}ms</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">P99: {metrics.p99Latency}ms</p>
            <div className="mt-4 h-16 bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded"></div>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Cache Hit Rate</p>
            <p className="text-3xl font-bold text-blue-600 dark:text-blue-500 mt-2">{metrics.cacheHitRate}%</p>
            <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">semantic cache</p>
            <div className="mt-4 h-16 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 rounded"></div>
          </div>
        </div>

        {/* Alerts */}
        {alerts.length > 0 && (
          <div className="mb-8 space-y-3">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Active Alerts</h2>
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`rounded-lg border-l-4 p-4 ${getSeverityColor(alert.severity)}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{alert.message}</p>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">{alert.timestamp}</p>
                  </div>
                  <button className="text-sm font-medium text-blue-600 hover:text-blue-700">
                    Investigate →
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Service Health */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Service Health</h2>
            <div className="space-y-3">
              {systemHealth.services.map((service) => (
                <div key={service.name} className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800 last:border-0">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{service.name}</p>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400">Uptime: {service.uptime}</p>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="text-xs text-zinc-600 dark:text-zinc-400">Latency</p>
                      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{service.latency}ms</p>
                    </div>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(service.status)}`}>
                      {service.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Database Status */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Database Status</h2>
            <div className="space-y-3">
              {systemHealth.databases.map((db) => (
                <div key={db.name} className="flex items-center justify-between pb-3 border-b border-zinc-200 dark:border-zinc-800 last:border-0">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{db.name}</p>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400">
                      {db.connections && `${db.connections}/${db.maxConnections} connections`}
                      {db.memory && `${db.memory} / ${db.maxMemory}`}
                      {db.messages && `${db.messages} messages, ${db.consumers} consumers`}
                      {db.vectors && `${db.collections} collections, ${db.vectors.toLocaleString()} vectors`}
                    </p>
                  </div>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(db.status)}`}>
                    {db.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Performance Metrics */}
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h3 className="text-sm font-medium text-zinc-600 dark:text-zinc-400 mb-4">Active Streams</h3>
            <p className="text-4xl font-bold text-zinc-900 dark:text-zinc-50">{metrics.activeStreams}</p>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-2">Currently processing</p>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h3 className="text-sm font-medium text-zinc-600 dark:text-zinc-400 mb-4">Queue Depth</h3>
            <p className="text-4xl font-bold text-zinc-900 dark:text-zinc-50">{metrics.queueDepth}</p>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-2">Messages pending</p>
          </div>

          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h3 className="text-sm font-medium text-zinc-600 dark:text-zinc-400 mb-4">Redis Latency</h3>
            <p className="text-4xl font-bold text-zinc-900 dark:text-zinc-50">{metrics.redisLatency}ms</p>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-2">P99 latency</p>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="mt-8 rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Quick Actions</h2>
          <div className="grid gap-3 md:grid-cols-3">
            <button className="flex items-center gap-2 rounded-md border border-zinc-200 px-4 py-2 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh Metrics
            </button>
            <button className="flex items-center gap-2 rounded-md border border-zinc-200 px-4 py-2 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Export Report
            </button>
            <a 
              href="http://localhost:9090" 
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-md border border-zinc-200 px-4 py-2 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              Open Prometheus
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}
