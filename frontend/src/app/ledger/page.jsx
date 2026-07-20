"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

export default function LedgerPage() {
  const [entries, setEntries] = useState([
    {
      id: 1,
      correlation_id: "corr_7x9m2k4p",
      tenant_id: "tenant_001",
      provider: "openai",
      model: "gpt-4",
      status: "RECONCILED",
      token_count: 2847,
      estimated_cost: 0.0854,
      created_at: "2024-07-18T10:32:15Z",
    },
    {
      id: 2,
      correlation_id: "corr_8n4k1j2q",
      tenant_id: "tenant_001",
      provider: "anthropic",
      model: "claude-3-opus",
      status: "RECONCILED",
      token_count: 3124,
      estimated_cost: 0.0937,
      created_at: "2024-07-18T10:28:42Z",
    },
    {
      id: 3,
      correlation_id: "corr_5m7p9r1s",
      tenant_id: "tenant_001",
      provider: "openai",
      model: "gpt-4-turbo",
      status: "PARTIAL",
      token_count: 1456,
      estimated_cost: 0.0437,
      created_at: "2024-07-18T10:15:28Z",
    },
  ]);

  const [filter, setFilter] = useState("all");

  const filteredEntries = entries.filter((entry) => {
    if (filter === "all") return true;
    return entry.status === filter.toUpperCase();
  });

  const getStatusColor = (status) => {
    switch (status) {
      case "RECONCILED":
        return "text-green-600 bg-green-50 dark:bg-green-950/30";
      case "PARTIAL":
        return "text-amber-600 bg-amber-50 dark:bg-amber-950/30";
      case "FAILED":
        return "text-red-600 bg-red-50 dark:bg-red-950/30";
      case "PROCESSING":
        return "text-blue-600 bg-blue-50 dark:bg-blue-950/30";
      default:
        return "text-zinc-600 bg-zinc-50 dark:bg-zinc-950/30";
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
            <Link href="/ledger" className="text-sm font-medium transition-colors hover:text-blue-600">
              Ledger
            </Link>
            <Link href="/monitoring" className="text-sm font-medium text-zinc-600 transition-colors hover:text-blue-600 dark:text-zinc-400">
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
            Ledger
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            Complete audit trail of all AI requests and billing
          </p>
        </div>

        {/* Filters and Actions */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilter("all")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                filter === "all"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-zinc-700 border border-zinc-200 hover:bg-zinc-50 dark:bg-zinc-950 dark:text-zinc-300 dark:border-zinc-800"
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilter("reconciled")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                filter === "reconciled"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-zinc-700 border border-zinc-200 hover:bg-zinc-50 dark:bg-zinc-950 dark:text-zinc-300 dark:border-zinc-800"
              }`}
            >
              Reconciled
            </button>
            <button
              onClick={() => setFilter("partial")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                filter === "partial"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-zinc-700 border border-zinc-200 hover:bg-zinc-50 dark:bg-zinc-950 dark:text-zinc-300 dark:border-zinc-800"
              }`}
            >
              Partial
            </button>
            <button
              onClick={() => setFilter("failed")}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                filter === "failed"
                  ? "bg-blue-600 text-white"
                  : "bg-white text-zinc-700 border border-zinc-200 hover:bg-zinc-50 dark:bg-zinc-950 dark:text-zinc-300 dark:border-zinc-800"
              }`}
            >
              Failed
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button className="flex items-center gap-2 px-4 py-2 rounded-md border border-zinc-200 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Export CSV
            </button>
            <button className="flex items-center gap-2 px-4 py-2 rounded-md border border-zinc-200 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
              </svg>
              Advanced Filter
            </button>
          </div>
        </div>

        {/* Ledger Table */}
        <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Correlation ID
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Provider
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Tokens
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Created At
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-zinc-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {filteredEntries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-zinc-900 dark:text-zinc-100">
                      {entry.correlation_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                      {entry.provider}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                      {entry.model}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(entry.status)}`}>
                        {entry.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-900 dark:text-zinc-100">
                      {entry.token_count.toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-900 dark:text-zinc-100">
                      ${entry.estimated_cost.toFixed(4)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-zinc-600 dark:text-zinc-400">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300">
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Pagination */}
        <div className="mt-4 flex items-center justify-between">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Showing {filteredEntries.length} entries
          </p>
          <div className="flex items-center gap-2">
            <button className="px-3 py-1 rounded-md border border-zinc-200 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              Previous
            </button>
            <button className="px-3 py-1 rounded-md bg-blue-600 text-white text-sm">
              1
            </button>
            <button className="px-3 py-1 rounded-md border border-zinc-200 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              2
            </button>
            <button className="px-3 py-1 rounded-md border border-zinc-200 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              3
            </button>
            <button className="px-3 py-1 rounded-md border border-zinc-200 text-sm hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
              Next
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
