import axios from 'axios';
import type { 
  ResearchJob, ResearchResult, SourceInfo, ResearchReport, 
  CollectionLog, SourceDiagnostic, DiscoveryChatMessage, 
  DiscoveryChatResponse, DiscoverySearchResponse, DiscoveryStatus, WishlistItem
} from '../types';

// Use relative '/api' with Vite proxy so it works on localhost, mobile, and LAN without CORS or IP mismatches
const API_BASE = import.meta.env.VITE_API_URL || '/api';

export const api = {
  getSources: async (): Promise<SourceInfo[]> => {
    const res = await axios.get(`${API_BASE}/sources`);
    return res.data;
  },

  testSource: async (sourceId: string): Promise<SourceDiagnostic> => {
    const res = await axios.get(`${API_BASE}/sources/${sourceId}/test`);
    return res.data;
  },

  createJob: async (data: {
    query: string;
    sources?: string[];
    mode?: string;
    limit_per_source?: number;
    filters?: Record<string, any>;
  }): Promise<ResearchJob> => {
    const res = await axios.post(`${API_BASE}/research`, data);
    return res.data;
  },

  getJob: async (jobId: string): Promise<ResearchJob> => {
    const res = await axios.get(`${API_BASE}/research/${jobId}`);
    return res.data;
  },

  getHistory: async (): Promise<ResearchJob[]> => {
    const res = await axios.get(`${API_BASE}/research/history`);
    return res.data;
  },

  deleteJob: async (jobId: string): Promise<any> => {
    const res = await axios.delete(`${API_BASE}/research/${jobId}`);
    return res.data;
  },

  clearHistory: async (): Promise<any> => {
    const res = await axios.delete(`${API_BASE}/research/history`);
    return res.data;
  },

  cancelJob: async (jobId: string): Promise<any> => {
    const res = await axios.post(`${API_BASE}/research/${jobId}/cancel`);
    return res.data;
  },

  getResults: async (
    jobId: string,
    params?: {
      source?: string;
      content_type?: string;
      language?: string;
      verification_status?: string;
      academic_only?: boolean;
      open_access_only?: boolean;
      min_relevance?: number;
      include_duplicates?: boolean;
      sort_by?: 'newest' | 'relevant' | 'oldest';
    }
  ): Promise<ResearchResult[]> => {
    const res = await axios.get(`${API_BASE}/research/${jobId}/results`, { params });
    return res.data;
  },

  submitFeedback: async (
    jobId: string,
    resultId: string,
    feedback_type: string,
    comment?: string
  ): Promise<any> => {
    const res = await axios.post(`${API_BASE}/research/${jobId}/results/${resultId}/feedback`, {
      feedback_type,
      comment,
    });
    return res.data;
  },

  // ── Research Wishlist API ───────────────────────────────────────────────────
  getWishlist: async (params?: {
    source?: string;
    content_type?: string;
    q?: string;
    sort_by?: 'saved_at' | 'relevance' | 'newest' | 'oldest';
  }): Promise<WishlistItem[]> => {
    const res = await axios.get(`${API_BASE}/wishlist`, { params });
    return res.data;
  },

  addToWishlist: async (item: ResearchResult): Promise<WishlistItem> => {
    const res = await axios.post(`${API_BASE}/wishlist`, {
      result_id: item.id,
      job_id: item.job_id,
      source_name: item.source_name,
      source_item_id: item.source_item_id,
      title: item.title,
      content_snippet: item.content_snippet,
      source_url: item.source_url,
      canonical_url: item.source_url,
      author: item.author,
      content_type: item.content_type,
      published_at: item.published_at,
      saved_relevance_score: item.relevance_score,
      validation_status: item.metadata_fields?.validation_status || 'UNCHECKED',
      metadata_fields: item.metadata_fields || {},
    });
    return res.data;
  },

  removeFromWishlist: async (itemId: string): Promise<void> => {
    await axios.delete(`${API_BASE}/wishlist/${itemId}`);
  },

  verifyWishlistItem: async (itemId: string): Promise<WishlistItem> => {
    const res = await axios.post(`${API_BASE}/wishlist/${itemId}/verify`);
    return res.data;
  },

  getReport: async (jobId: string): Promise<ResearchReport> => {
    const res = await axios.get(`${API_BASE}/research/${jobId}/report`);
    return res.data;
  },

  getLogs: async (jobId: string): Promise<CollectionLog[]> => {
    const res = await axios.get(`${API_BASE}/research/${jobId}/logs`);
    return res.data;
  },

  getExportUrl: (jobId: string, format: 'csv' | 'json' = 'csv'): string => {
    return `${API_BASE}/research/${jobId}/export?format=${format}`;
  },

  // ── Discovery Mode API ──────────────────────────────────────────────────────
  getDiscoveryStatus: async (): Promise<DiscoveryStatus> => {
    const res = await axios.get(`${API_BASE}/discovery/status`);
    return res.data;
  },

  sendDiscoveryChat: async (message: string, history: DiscoveryChatMessage[] = []): Promise<DiscoveryChatResponse> => {
    const res = await axios.post(`${API_BASE}/discovery/chat`, { message, history });
    return res.data;
  },

  executeDiscoverySearch: async (params: {
    queries: string[];
    sources?: string[];
    mode?: string;
    limit_per_source?: number;
    original_objective?: string;
    language?: string;
  }): Promise<DiscoverySearchResponse> => {
    const res = await axios.post(`${API_BASE}/discovery/search`, params);
    return res.data;
  }
};
