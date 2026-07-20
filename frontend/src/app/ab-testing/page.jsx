"use client";

import { useState } from "react";
import Link from "next/link";

export default function ABTestingPage() {
  const [tests, setTests] = useState([
    {
      test_id: "test_001",
      test_name: "GPT-4 vs Claude-3 Cost Optimization",
      description: "Compare cost and quality between GPT-4 and Claude-3 Opus",
      status: "active",
      start_date: "2024-07-15T10:00:00Z",
      end_date: "2024-07-29T10:00:00Z",
      variants: [
        { id: "variant_a", name: "GPT-4", provider: "openai", model: "gpt-4", traffic: 50 },
        { id: "variant_b", name: "Claude-3 Opus", provider: "anthropic", model: "claude-3-opus", traffic: 50 },
      ],
      metrics: {
        total_requests: 4847,
        variant_a_requests: 2423,
        variant_b_requests: 2424,
        variant_a_cost: 72.45,
        variant_b_cost: 68.12,
        variant_a_avg_latency: 1247,
        variant_b_avg_latency: 1189,
      },
    },
    {
      test_id: "test_002",
      test_name: "Prompt Engineering Comparison",
      description: "Test different prompt templates for better response quality",
      status: "active",
      start_date: "2024-07-18T14:00:00Z",
      end_date: "2024-08-01T14:00:00Z",
      variants: [
        { id: "variant_a", name: "Standard Prompt", provider: "openai", model: "gpt-4", traffic: 33 },
        { id: "variant_b", name: "CRISPE Template", provider: "openai", model: "gpt-4", traffic: 33 },
        { id: "variant_c", name: "Zero-Shot CoT", provider: "openai", model: "gpt-4", traffic: 34 },
      ],
      metrics: {
        total_requests: 1523,
        variant_a_requests: 507,
        variant_b_requests: 503,
        variant_c_requests: 513,
        variant_a_cost: 23.14,
        variant_b_cost: 24.89,
        variant_c_cost: 25.12,
      },
    },
    {
      test_id: "test_003",
      test_name: "Streaming vs Batch Processing",
      description: "Compare user experience and costs for streaming responses",
      status: "completed",
      start_date: "2024-07-01T00:00:00Z",
      end_date: "2024-07-14T23:59:59Z",
      variants: [
        { id: "variant_a", name: "Streaming", provider: "openai", model: "gpt-4-turbo", traffic: 50 },
        { id: "variant_b", name: "Batch", provider: "openai", model: "gpt-4-turbo", traffic: 50 },
      ],
      metrics: {
        total_requests: 8942,
        variant_a_requests: 4471,
        variant_b_requests: 4471,
        variant_a_cost: 134.13,
        variant_b_cost: 134.13,
        variant_a_avg_latency: 892,
        variant_b_avg_latency: 2456,
      },
      winner: "variant_a",
      conclusion: "Streaming provides 63% better perceived latency with identical cost",
    },
  ]);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTest, setNewTest] = useState({
    test_name: "",
    description: "",
    variants: [
      { name: "", provider: "openai", model: "gpt-4", traffic: 50 },
      { name: "", provider: "anthropic", model: "claude-3-opus", traffic: 50 },
    ],
  });

  const getStatusColor = (status) => {
    switch (status) {
      case "active":
        return "text-green-600 bg-green-50 dark:bg-green-950/30";
      case "paused":
        return "text-amber-600 bg-amber-50 dark:bg-amber-950/30";
      case "completed":
        return "text-blue-600 bg-blue-50 dark:bg-blue-950/30";
      case "draft":
        return "text-zinc-600 bg-zinc-50 dark:bg-zinc-950/30";
      default:
        return "text-zinc-600 bg-zinc-50 dark:bg-zinc-950/30";
    }
  };

  const getVariantColor = (index) => {
    const colors = [
      "border-blue-500 bg-blue-50 dark:bg-blue-950/20",
      "border-purple-500 bg-purple-50 dark:bg-purple-950/20",
      "border-green-500 bg-green-50 dark:bg-green-950/20",
    ];
    return colors[index % colors.length];
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
            <Link href="/monitoring" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Monitoring
            </Link>
            <Link href="/manual-review" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Manual Review
            </Link>
            <Link href="/ab-testing" className="text-sm font-medium transition-colors hover:text-blue-600">
              A/B Testing
            </Link>
            <Link href="/config" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
              Configuration
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 container px-8 py-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              A/B Testing
            </h1>
            <p className="text-zinc-600 dark:text-zinc-400 mt-2">
              Compare models, prompts, and configurations to optimize cost and quality
            </p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-6 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Create Test
          </button>
        </div>

        {/* Active Tests Summary */}
        <div className="grid gap-4 md:grid-cols-3 mb-8">
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Active Tests</p>
            <p className="text-3xl font-bold text-green-600 dark:text-green-500 mt-2">
              {tests.filter((t) => t.status === "active").length}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Total Requests</p>
            <p className="text-3xl font-bold text-zinc-900 dark:text-zinc-50 mt-2">
              {tests.reduce((sum, t) => sum + t.metrics.total_requests, 0).toLocaleString()}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Completed Tests</p>
            <p className="text-3xl font-bold text-blue-600 dark:text-blue-500 mt-2">
              {tests.filter((t) => t.status === "completed").length}
            </p>
          </div>
        </div>

        {/* Test List */}
        <div className="space-y-6">
          {tests.map((test) => (
            <div key={test.test_id} className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              {/* Test Header */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                      {test.test_name}
                    </h3>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(test.status)}`}>
                      {test.status}
                    </span>
                    {test.winner && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium text-green-600 bg-green-50 dark:bg-green-950/30">
                        Winner: {test.variants.find((v) => v.id === test.winner)?.name}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">{test.description}</p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-500 mt-1">
                    {new Date(test.start_date).toLocaleDateString()} - {new Date(test.end_date).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  {test.status === "active" && (
                    <button className="px-3 py-1 rounded-md text-sm font-medium text-amber-600 border border-amber-300 hover:bg-amber-50 dark:border-amber-800 dark:hover:bg-amber-950/20">
                      Pause
                    </button>
                  )}
                  <button className="px-3 py-1 rounded-md text-sm font-medium text-blue-600 border border-blue-300 hover:bg-blue-50 dark:border-blue-800 dark:hover:bg-blue-950/20">
                    View Details
                  </button>
                </div>
              </div>

              {/* Variants */}
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-4">
                {test.variants.map((variant, index) => (
                  <div key={variant.id} className={`rounded-lg border-l-4 p-4 ${getVariantColor(index)}`}>
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">{variant.name}</p>
                      <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">{variant.traffic}%</span>
                    </div>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400 mb-2">
                      {variant.provider} / {variant.model}
                    </p>
                    <div className="space-y-1 text-xs">
                      <div className="flex justify-between">
                        <span className="text-zinc-600 dark:text-zinc-400">Requests:</span>
                        <span className="font-medium text-zinc-900 dark:text-zinc-50">
                          {test.metrics[`${variant.id.replace("variant", "variant")}_requests`]?.toLocaleString() || "N/A"}
                        </span>
                      </div>
                      {test.metrics[`${variant.id.replace("variant", "variant")}_cost`] && (
                        <div className="flex justify-between">
                          <span className="text-zinc-600 dark:text-zinc-400">Cost:</span>
                          <span className="font-medium text-zinc-900 dark:text-zinc-50">
                            ${test.metrics[`${variant.id.replace("variant", "variant")}_cost`].toFixed(2)}
                          </span>
                        </div>
                      )}
                      {test.metrics[`${variant.id.replace("variant", "variant")}_avg_latency`] && (
                        <div className="flex justify-between">
                          <span className="text-zinc-600 dark:text-zinc-400">Avg Latency:</span>
                          <span className="font-medium text-zinc-900 dark:text-zinc-50">
                            {test.metrics[`${variant.id.replace("variant", "variant")}_avg_latency`]}ms
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Metrics Summary */}
              <div className="rounded-lg bg-zinc-50 dark:bg-zinc-900 p-4">
                <h4 className="text-sm font-medium text-zinc-900 dark:text-zinc-50 mb-2">Overall Metrics</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <p className="text-zinc-600 dark:text-zinc-400">Total Requests</p>
                    <p className="font-semibold text-zinc-900 dark:text-zinc-50">{test.metrics.total_requests.toLocaleString()}</p>
                  </div>
                  {test.conclusion && (
                    <div className="col-span-2 md:col-span-3">
                      <p className="text-zinc-600 dark:text-zinc-400">Conclusion</p>
                      <p className="font-medium text-zinc-900 dark:text-zinc-50">{test.conclusion}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {tests.length === 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-950">
            <svg className="mx-auto h-12 w-12 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-zinc-900 dark:text-zinc-50">No A/B Tests</h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              Create your first A/B test to compare models and optimize performance
            </p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
            >
              Create Test
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
