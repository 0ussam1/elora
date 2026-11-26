export interface ResearchJob {
  id: string;
  query: string;
  mode: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  selected_sources: string[];
  limit_per_source: number;
  total_results_count: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export type ValidationStatus =
  | 'VERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'INACCESSIBLE'
  | 'DELETED'
  | 'NOT_FOUND'
  | 'MISMATCH'
  | 'UNCHECKED';

export interface ResearchResult {
  id: string;
  job_id: string;
  source_name: string;
  source_item_id?: string;
  title: string;
  content_snippet?: string;
  source_url: string;
  author?: string;
  published_at?: string;
  collected_at: string;
  content_type: string;
  engagement_metrics: Record<string, any>;
  metadata_fields: Record<string, any>;
  relevance_score: number;
  is_duplicate: boolean;
  duplicate_of?: string;
  validation_status?: ValidationStatus;
  canonical_url?: string;
  final_url?: string;
  http_status?: number;
  validation_method?: string;
  validation_reason?: string;
  validated_at?: string;
  content_extraction_status?: string;
  content_availability_status?: string;
}

export interface SourceInfo {
  id: string;
  name: string;
  description?: string;
  category: string;
  is_enabled: boolean;
  requires_auth: boolean;
  auth_status: string;
  supported_content_types: string[];
  rate_limit_per_minute: number;
  health_status: string;
  message?: string;
}

export interface SourceDiagnostic {
  source_id: string;
  configured: boolean;
  authorized: boolean;
  connected: boolean;
  status: string;
  message: string;
  last_checked_at: string;
  details?: Record<string, any>;
}

export interface CollectionLog {
  id: number;
  source_name: string;
  status: string;
  message: string;
  items_collected: number;
  duration_ms: number;
  created_at: string;
}

export interface ResearchReport {
  id: string;
  job_id: string;
  executive_summary: string;
  main_findings: Array<{
    theme: string;
    description: string;
    evidence_sources: Array<{
      id: string;
      title: string;
      source_name: string;
      url: string;
      relevance: number;
    }>;
  }>;
  recurring_problems: Array<{
    problem: string;
    frequency: number;
    evidence_id: string;
    evidence_title: string;
    evidence_url: string;
    source_name: string;
  }>;
  perspectives: Array<{
    platform: string;
    perspective: string;
    sample_title: string;
    sample_url: string;
  }>;
  existing_solutions: Array<{
    solution_title: string;
    summary: string;
    source_name: string;
    url: string;
  }>;
  potential_opportunities: Array<{
    opportunity: string;
    actionable_insight: string;
  }>;
  limitations: string[];
  collection_stats: {
    total_collected: number;
    unique_items: number;
    sources: Record<string, number>;
    avg_relevance: number;
  };
  created_at: string;
}

// ── Discovery Mode Types ──────────────────────────────────────────────────────
export interface DiscoveryChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface DiscoveryIntent {
  objective: string;
  category: string;
  main_topic: string;
  related_topics: string[];
  detected_language: string;
  missing_information?: string | null;
}

export interface DiscoverySearchPlan {
  queries: string[];
  recommended_sources: string[];
  resource_types: string[];
  reasoning?: string;
}

export interface DiscoveryChatResponse {
  status: 'success' | 'clarification' | 'not_configured' | 'error';
  configured: boolean;
  message: string;
  understanding?: string | null;
  needs_clarification: boolean;
  clarification_question?: string | null;
  intent?: DiscoveryIntent | null;
  search_plan?: DiscoverySearchPlan | null;
  error_detail?: string | null;
}

export interface DiscoverySearchResponse {
  job_id: string;
  queries_executed: string[];
  total_results: number;
  results: ResearchResult[];
  grouped_by_type: Record<string, ResearchResult[]>;
  summary?: string | null;
  sources_queried: string[];
}

export interface DiscoveryStatus {
  configured: boolean;
  provider: string;
  model?: string | null;
  base_url?: string | null;
  message?: string | null;
}

