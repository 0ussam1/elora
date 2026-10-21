import axios from 'axios';
import type { ResearchJob, ResearchResult, SourceInfo, ResearchReport, CollectionLog, SourceDiagnostic } from '../types';

const API_BASE = 'http://127.0.0.1:8000/api';

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
    params?: { source?: string; content_type?: string; min_relevance?: number; include_duplicates?: boolean }
  ): Promise<ResearchResult[]> => {
    const res = await axios.get(`${API_BASE}/research/${jobId}/results`, { params });
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
  }
};
