"use client";

import { useState } from "react";
import Link from "next/link";

export default function ConfigurationPage() {
  const [tenant, setTenant] = useState({
    tenant_id: "tenant_001",
    name: "Development Tenant",
    email: "dev@ledgerline.ai",
    status: "active",
  });

  const [rateLimits, setRateLimits] = useState({
    tpm_limit: 100000,
    rpm_limit: 1000,
  });

  const [billing, setBilling] = useState({
    enabled: true,
    cost_multiplier: 1.0,
    currency: "USD",
  });

  const [retention, setRetention] = useState({
    retention_days: 90,
    auto_export: true,
    export_format: "parquet",
  });

  const [providers, setProviders] = useState([
    { name: "OpenAI", enabled: true, priority: 1, fallback: "Anthropic" },
    { name: "Anthropic", enabled: true, priority: 2, fallback: null },
    { name: "Cohere", enabled: false, priority: 3, fallback: null },
  ]);

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    console.log("Saving configuration:", { tenant, rateLimits, billing, retention, providers });
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
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
            <Link href="/config" className="text-sm font-medium transition-colors hover:text-blue-600">
              Configuration
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 container px-8 py-8">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
              Configuration
            </h1>
            <p className="text-zinc-600 dark:text-zinc-400 mt-2">
              Manage tenant settings, rate limits, and provider preferences
            </p>
          </div>
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-6 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            {saved ? (
              <>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Saved!
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                </svg>
                Save Changes
              </>
            )}
          </button>
        </div>

        <div className="space-y-6">
          {/* Tenant Information */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Tenant Information</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Tenant Name
                </label>
                <input
                  type="text"
                  value={tenant.name}
                  onChange={(e) => setTenant({ ...tenant, name: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Email
                </label>
                <input
                  type="email"
                  value={tenant.email}
                  onChange={(e) => setTenant({ ...tenant, email: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Tenant ID
                </label>
                <input
                  type="text"
                  value={tenant.tenant_id}
                  disabled
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Status
                </label>
                <select
                  value={tenant.status}
                  onChange={(e) => setTenant({ ...tenant, status: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                >
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                </select>
              </div>
            </div>
          </div>

          {/* Rate Limits */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Rate Limits</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Tokens Per Minute (TPM)
                </label>
                <input
                  type="number"
                  value={rateLimits.tpm_limit}
                  onChange={(e) => setRateLimits({ ...rateLimits, tpm_limit: parseInt(e.target.value) })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
                  Maximum tokens that can be processed per minute
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Requests Per Minute (RPM)
                </label>
                <input
                  type="number"
                  value={rateLimits.rpm_limit}
                  onChange={(e) => setRateLimits({ ...rateLimits, rpm_limit: parseInt(e.target.value) })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1">
                  Maximum number of requests per minute
                </p>
              </div>
            </div>
          </div>

          {/* Billing Configuration */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Billing Configuration</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  <input
                    type="checkbox"
                    checked={billing.enabled}
                    onChange={(e) => setBilling({ ...billing, enabled: e.target.checked })}
                    className="rounded"
                  />
                  Billing Enabled
                </label>
                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                  Track and charge for API usage
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Cost Multiplier
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={billing.cost_multiplier}
                  onChange={(e) => setBilling({ ...billing, cost_multiplier: parseFloat(e.target.value) })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Currency
                </label>
                <select
                  value={billing.currency}
                  onChange={(e) => setBilling({ ...billing, currency: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                >
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                </select>
              </div>
            </div>
          </div>

          {/* Data Retention */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Data Retention</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Retention Period (Days)
                </label>
                <input
                  type="number"
                  value={retention.retention_days}
                  onChange={(e) => setRetention({ ...retention, retention_days: parseInt(e.target.value) })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  <input
                    type="checkbox"
                    checked={retention.auto_export}
                    onChange={(e) => setRetention({ ...retention, auto_export: e.target.checked })}
                    className="rounded"
                  />
                  Auto Export
                </label>
                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                  Automatically export before deletion
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                  Export Format
                </label>
                <select
                  value={retention.export_format}
                  onChange={(e) => setRetention({ ...retention, export_format: e.target.value })}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                >
                  <option value="csv">CSV</option>
                  <option value="parquet">Parquet</option>
                  <option value="json">JSON</option>
                </select>
              </div>
            </div>
          </div>

          {/* Provider Configuration */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Provider Configuration</h2>
            <div className="space-y-3">
              {providers.map((provider, index) => (
                <div key={provider.name} className="flex items-center justify-between p-4 rounded-lg border border-zinc-200 dark:border-zinc-800">
                  <div className="flex items-center gap-4 flex-1">
                    <input
                      type="checkbox"
                      checked={provider.enabled}
                      onChange={(e) => {
                        const newProviders = [...providers];
                        newProviders[index].enabled = e.target.checked;
                        setProviders(newProviders);
                      }}
                      className="rounded"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{provider.name}</p>
                      <p className="text-xs text-zinc-600 dark:text-zinc-400">
                        Priority: {provider.priority} {provider.fallback && `• Fallback: ${provider.fallback}`}
                      </p>
                    </div>
                  </div>
                  <button className="text-sm text-blue-600 hover:text-blue-700">
                    Configure
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Cost Allocation Tags */}
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 mb-4">Cost Allocation Tags</h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">
              Define custom tags for cost tracking and internal chargebacks
            </p>
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Tag name (e.g., department)"
                  className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <input
                  type="text"
                  placeholder="Description"
                  className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                />
                <button className="px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">
                  Add Tag
                </button>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                <div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">department</p>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400">Organizational department</p>
                </div>
                <button className="text-sm text-red-600 hover:text-red-700">Remove</button>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900">
                <div>
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">project</p>
                  <p className="text-xs text-zinc-600 dark:text-zinc-400">Project identifier</p>
                </div>
                <button className="text-sm text-red-600 hover:text-red-700">Remove</button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
