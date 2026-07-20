"use client";

import { useState } from "react";
import Link from "next/link";

export default function ManualReviewPage() {
  const [reviews, setReviews] = useState([
    {
      id: "review_1",
      correlation_id: "corr_5m7p9r1s",
      tenant_id: "tenant_001",
      provider: "openai",
      model: "gpt-4-turbo",
      checkpoint_tokens: 1456,
      review_status: "pending",
      recommended_action: "approve_at_checkpoint",
      created_at: "2024-07-18T10:15:28Z",
      metadata: {
        reason: "orphaned_stream_timeout",
        last_heartbeat: "2024-07-18T10:15:58Z"
      }
    },
    {
      id: "review_2",
      correlation_id: "corr_2k8n4m1p",
      tenant_id: "tenant_001",
      provider: "anthropic",
      model: "claude-3-opus",
      checkpoint_tokens: 892,
      review_status: "in_review",
      recommended_action: "requires_info",
      assigned_to: "admin@ledgerline.ai",
      created_at: "2024-07-18T09:42:15Z",
      metadata: {
        reason: "provider_api_timeout",
        error: "Connection timeout after 30s"
      }
    },
    {
      id: "review_3",
      correlation_id: "corr_9x3k7n2q",
      tenant_id: "tenant_001",
      provider: "openai",
      model: "gpt-4",
      checkpoint_tokens: 2134,
      review_status: "pending",
      recommended_action: "approve_at_zero",
      created_at: "2024-07-18T08:22:45Z",
      metadata: {
        reason: "duplicate_idempotency_detected",
        note: "Possible race condition in lock acquisition"
      }
    }
  ]);

  const [selectedReview, setSelectedReview] = useState(null);
  const [resolutionNotes, setResolutionNotes] = useState("");

  const getStatusColor = (status) => {
    switch (status) {
      case "pending":
        return "text-amber-600 bg-amber-50 dark:bg-amber-950/30";
      case "in_review":
        return "text-blue-600 bg-blue-50 dark:bg-blue-950/30";
      case "approved":
        return "text-green-600 bg-green-50 dark:bg-green-950/30";
      case "rejected":
        return "text-red-600 bg-red-50 dark:bg-red-950/30";
      default:
        return "text-zinc-600 bg-zinc-50 dark:bg-zinc-950/30";
    }
  };

  const handleResolve = (reviewId, action) => {
    console.log(`Resolving review ${reviewId} with action: ${action}`);
    console.log(`Notes: ${resolutionNotes}`);
    
    // Update the review status
    setReviews(reviews.map(r => 
      r.id === reviewId 
        ? { ...r, review_status: action === "approve_at_checkpoint" ? "approved" : "rejected" }
        : r
    ));
    
    setSelectedReview(null);
    setResolutionNotes("");
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
            <Link href="/manual-review" className="text-sm font-medium transition-colors hover:text-blue-600">
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
            Manual Review Queue
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            Resolve PARTIAL states and reconcile orphaned streams
          </p>
        </div>

        {/* Stats */}
        <div className="grid gap-4 md:grid-cols-3 mb-8">
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Pending</p>
            <p className="text-2xl font-bold text-amber-600 mt-2">
              {reviews.filter(r => r.review_status === "pending").length}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">In Review</p>
            <p className="text-2xl font-bold text-blue-600 mt-2">
              {reviews.filter(r => r.review_status === "in_review").length}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Resolved Today</p>
            <p className="text-2xl font-bold text-green-600 mt-2">12</p>
          </div>
        </div>

        {/* Review Items */}
        <div className="space-y-4">
          {reviews.map((review) => (
            <div key={review.id} className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50 font-mono">
                      {review.correlation_id}
                    </h3>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(review.review_status)}`}>
                      {review.review_status}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm text-zinc-600 dark:text-zinc-400">
                    <div>
                      <span className="font-medium">Provider:</span> {review.provider}
                    </div>
                    <div>
                      <span className="font-medium">Model:</span> {review.model}
                    </div>
                    <div>
                      <span className="font-medium">Checkpoint Tokens:</span> {review.checkpoint_tokens.toLocaleString()}
                    </div>
                    <div>
                      <span className="font-medium">Created:</span> {new Date(review.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2 ml-4">
                  <span className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
                    Recommended: {review.recommended_action.replace(/_/g, " ")}
                  </span>
                  {review.assigned_to && (
                    <span className="text-xs text-blue-600">
                      Assigned to: {review.assigned_to}
                    </span>
                  )}
                </div>
              </div>

              {/* Metadata */}
              <div className="rounded-md bg-zinc-50 dark:bg-zinc-900 p-4 mb-4">
                <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50 mb-2">Details</p>
                <div className="space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
                  <div><span className="font-medium">Reason:</span> {review.metadata.reason}</div>
                  {review.metadata.error && (
                    <div><span className="font-medium">Error:</span> {review.metadata.error}</div>
                  )}
                  {review.metadata.last_heartbeat && (
                    <div><span className="font-medium">Last Heartbeat:</span> {new Date(review.metadata.last_heartbeat).toLocaleString()}</div>
                  )}
                  {review.metadata.note && (
                    <div><span className="font-medium">Note:</span> {review.metadata.note}</div>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              {review.review_status === "pending" && (
                <div className="flex gap-2">
                  <button
                    onClick={() => setSelectedReview(review)}
                    className="flex-1 px-4 py-2 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-700 transition-colors"
                  >
                    Approve at Checkpoint
                  </button>
                  <button
                    onClick={() => {
                      if (confirm("Approve at zero tokens? This will mark the request as complete with no usage.")) {
                        handleResolve(review.id, "approve_at_zero");
                      }
                    }}
                    className="flex-1 px-4 py-2 rounded-md bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                  >
                    Approve at Zero
                  </button>
                  <button
                    onClick={() => setSelectedReview(review)}
                    className="flex-1 px-4 py-2 rounded-md border border-zinc-300 text-zinc-700 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900 transition-colors"
                  >
                    Request More Info
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {reviews.length === 0 && (
          <div className="rounded-lg border border-zinc-200 bg-white p-12 text-center dark:border-zinc-800 dark:bg-zinc-950">
            <svg className="mx-auto h-12 w-12 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 className="mt-4 text-lg font-medium text-zinc-900 dark:text-zinc-50">No pending reviews</h3>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              All requests have been reconciled successfully!
            </p>
          </div>
        )}
      </main>

      {/* Resolution Modal */}
      {selectedReview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-950">
            <h2 className="text-xl font-bold text-zinc-900 dark:text-zinc-50 mb-4">
              Resolve Review
            </h2>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-4">
              Correlation ID: <span className="font-mono">{selectedReview.correlation_id}</span>
            </p>
            <div className="mb-4">
              <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                Resolution Notes
              </label>
              <textarea
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
                rows={4}
                placeholder="Add notes about your decision..."
              />
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  handleResolve(selectedReview.id, "approve_at_checkpoint");
                }}
                className="flex-1 px-4 py-2 rounded-md bg-green-600 text-white text-sm font-medium hover:bg-green-700 transition-colors"
              >
                Confirm Approval
              </button>
              <button
                onClick={() => {
                  setSelectedReview(null);
                  setResolutionNotes("");
                }}
                className="flex-1 px-4 py-2 rounded-md border border-zinc-300 text-zinc-700 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
