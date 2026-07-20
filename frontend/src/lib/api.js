/**
 * Ledgerline API Client
 * Provides hooks and services for interacting with backend APIs
 */

import { useState, useEffect } from 'react';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class APIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.data = data;
  }
}

async function fetchAPI(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  try {
    const response = await fetch(url, {
      ...options,
      headers,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new APIError(
        data.message || `API Error: ${response.statusText}`,
        response.status,
        data
      );
    }

    return data;
  } catch (error) {
    if (error instanceof APIError) throw error;
    throw new APIError('Network error', 0, { original: error.message });
  }
}

// Ledger API
export const ledgerAPI = {
  async getLedgerEntries(params = {}) {
    const queryParams = new URLSearchParams(params).toString();
    return fetchAPI(`/v1/ledger?${queryParams}`);
  },

  async getLedgerEntry(correlationId) {
    return fetchAPI(`/v1/ledger/${correlationId}`);
  },

  async exportLedger(format = 'csv') {
    return fetchAPI(`/v1/ledger/export?format=${format}`);
  },
};

// Dispatcher API
export const dispatcherAPI = {
  async submitRequest(data) {
    return fetchAPI('/v1/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getStatus(correlationId) {
    return fetchAPI(`/v1/status/${correlationId}`);
  },

  async reconcile(correlationId, data) {
    return fetchAPI(`/v1/reconcile`, {
      method: 'POST',
      body: JSON.stringify({ correlation_id: correlationId, ...data }),
    });
  },
};

// Manual Review API
export const reviewAPI = {
  async getQueue(status = 'pending') {
    return fetchAPI(`/v1/manual-review?status=${status}`);
  },

  async resolveReview(reviewId, action, notes) {
    return fetchAPI(`/v1/manual-review/resolve`, {
      method: 'POST',
      body: JSON.stringify({ review_id: reviewId, action, notes }),
    });
  },

  async assignReview(reviewId, assignee) {
    return fetchAPI(`/v1/manual-review/assign`, {
      method: 'POST',
      body: JSON.stringify({ review_id: reviewId, assignee }),
    });
  },
};

// Tenant API
export const tenantAPI = {
  async getTenantInfo() {
    return fetchAPI('/v1/tenant');
  },

  async updateConfig(config) {
    return fetchAPI('/v1/tenant/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  async getRateLimits() {
    return fetchAPI('/v1/tenant/rate-limits');
  },

  async updateRateLimits(limits) {
    return fetchAPI('/v1/tenant/rate-limits', {
      method: 'PUT',
      body: JSON.stringify(limits),
    });
  },
};

// Monitoring API
export const monitoringAPI = {
  async getMetrics(timeRange = '1h') {
    return fetchAPI(`/v1/metrics?range=${timeRange}`);
  },

  async getSystemHealth() {
    return fetchAPI('/health');
  },

  async getProviderStatus() {
    return fetchAPI('/v1/providers/status');
  },
};

// A/B Testing API
export const abTestingAPI = {
  async getTests() {
    return fetchAPI('/v1/ab-tests');
  },

  async createTest(test) {
    return fetchAPI('/v1/ab-tests', {
      method: 'POST',
      body: JSON.stringify(test),
    });
  },

  async getTestResults(testId) {
    return fetchAPI(`/v1/ab-tests/${testId}/results`);
  },

  async updateTest(testId, updates) {
    return fetchAPI(`/v1/ab-tests/${testId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  },
};

// React hooks for data fetching
export function useLedger(params) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    ledgerAPI
      .getLedgerEntries(params)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [JSON.stringify(params)]);

  return { data, loading, error };
}

export function useReviewQueue(status) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    reviewAPI
      .getQueue(status)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [status]);

  const resolve = async (reviewId, action, notes) => {
    try {
      await reviewAPI.resolveReview(reviewId, action, notes);
      // Refresh data
      const newData = await reviewAPI.getQueue(status);
      setData(newData);
    } catch (err) {
      setError(err);
    }
  };

  return { data, loading, error, resolve };
}

export function useMetrics(timeRange) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    monitoringAPI
      .getMetrics(timeRange)
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [timeRange]);

  return { data, loading, error };
}
