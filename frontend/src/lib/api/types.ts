export type EvaluationSummaryRef = {
  status: "not_available" | "partial" | "complete";
  trace_id: string;
  has_response_quality: boolean;
  response_quality_overall_score?: number | null;
  has_trajectory_evaluation: boolean;
  trajectory_score?: number | null;
  trajectory_violation_count?: number | null;
};

export type TicketRunSummary = {
  run_id: string;
  trace_id: string;
  status: string;
  final_action?: string | null;
  evaluation_summary_ref: EvaluationSummaryRef;
};

export type TicketDraftSummary = {
  draft_id: string;
  qa_status: string;
};

export type TicketSummary = {
  ticket_id: string;
  business_status: string;
  processing_status: string;
  claimed_by?: string | null;
  claimed_at?: string | null;
  lease_until?: string | null;
  priority: string;
  primary_route?: string | null;
  multi_intent: boolean;
  tags: string[];
  version: number;
};

export type TicketListItem = {
  ticket_id: string;
  customer_id?: string | null;
  customer_email_raw: string;
  subject: string;
  business_status: string;
  processing_status: string;
  priority: string;
  primary_route?: string | null;
  multi_intent: boolean;
  version: number;
  updated_at: string;
  latest_run?: TicketRunSummary | null;
  latest_draft?: TicketDraftSummary | null;
};

export type TicketListResponse = {
  items: TicketListItem[];
  page: number;
  page_size: number;
  total: number;
};

export type TicketListQuery = {
  page?: number;
  page_size?: number;
  business_status?: string;
  processing_status?: string;
  primary_route?: string;
  has_draft?: boolean;
  awaiting_review?: boolean;
  query?: string;
};

export type TicketRunHistoryItem = {
  run_id: string;
  trace_id: string;
  trigger_type: string;
  triggered_by?: string | null;
  status: string;
  final_action?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  attempt_index: number;
  is_human_action: boolean;
  evaluation_summary_ref: EvaluationSummaryRef;
};

export type TicketRunsResponse = {
  ticket_id: string;
  items: TicketRunHistoryItem[];
  page: number;
  page_size: number;
  total: number;
};

export type TicketDraftDetail = {
  draft_id: string;
  run_id: string;
  version_index: number;
  draft_type: string;
  qa_status: string;
  content_text: string;
  source_evidence_summary?: string | null;
  gmail_draft_id?: string | null;
  created_at: string;
};

export type TicketDraftsResponse = {
  ticket_id: string;
  items: TicketDraftDetail[];
};

export type TicketSnapshotResponse = {
  ticket: TicketSummary;
  latest_run?: TicketRunSummary | null;
  latest_draft?: TicketDraftSummary | null;
  messages: TicketMessage[];
};

export type TicketMessage = {
  ticket_message_id: string;
  run_id?: string | null;
  draft_id?: string | null;
  source_message_id: string;
  direction: string;
  message_type: string;
  sender_email?: string | null;
  recipient_emails: string[];
  subject?: string | null;
  body_text?: string | null;
  reply_to_source_message_id?: string | null;
  customer_visible: boolean;
  message_timestamp: string;
  metadata?: Record<string, unknown> | null;
};

export type TraceEventResponse = {
  event_id: string;
  event_type: string;
  event_name: string;
  node_name?: string | null;
  start_time: string;
  end_time?: string | null;
  latency_ms?: number | null;
  status: string;
  metadata?: Record<string, unknown> | null;
};

export type TicketTraceResponse = {
  ticket_id: string;
  run_id: string;
  trace_id: string;
  latency_metrics?: Record<string, unknown> | null;
  resource_metrics?: Record<string, unknown> | null;
  response_quality?: Record<string, unknown> | null;
  trajectory_evaluation?: Record<string, unknown> | null;
  events: TraceEventResponse[];
};

export type MetricsLatencySummary = {
  p50_ms?: number | null;
  p95_ms?: number | null;
};

export type MetricsResourcesSummary = {
  avg_total_tokens?: number | null;
  avg_llm_call_count?: number | null;
  avg_actual_token_call_count?: number | null;
  avg_estimated_token_call_count?: number | null;
  avg_unavailable_token_call_count?: number | null;
  avg_token_coverage_ratio?: number | null;
};

export type MetricsResponseQualitySummary = {
  avg_overall_score?: number | null;
};

export type MetricsTrajectorySummary = {
  avg_score?: number | null;
};

export type MetricsSummaryResponse = {
  window: {
    from: string;
    to: string;
  };
  latency: MetricsLatencySummary;
  resources: MetricsResourcesSummary;
  response_quality: MetricsResponseQualitySummary;
  trajectory_evaluation: MetricsTrajectorySummary;
};

export type GmailScanPreviewRequest = {
  max_results?: number;
};

export type GmailScanPreviewResponse = {
  gmail_enabled: boolean;
  requested_max_results: number;
  summary: {
    candidate_threads: number;
    skipped_existing_draft_threads: number;
    skipped_self_sent_threads: number;
  };
  items: Array<{
    source_thread_id: string;
    source_message_id?: string | null;
    sender_email_raw: string;
    subject: string;
    skip_reason?: string | null;
  }>;
};

export type GmailScanRequest = {
  max_results?: number;
  enqueue?: boolean;
};

export type GmailScanResponse = {
  scan_id: string;
  status: "accepted";
  gmail_enabled: boolean;
  requested_max_results: number;
  enqueue: boolean;
  summary: {
    fetched_threads: number;
    ingested_tickets: number;
    queued_runs: number;
    skipped_existing_draft_threads: number;
    skipped_self_sent_threads: number;
    errors: number;
  };
  items: Array<{
    source_thread_id: string;
    ticket_id?: string | null;
    created_ticket: boolean;
    queued_run_id?: string | null;
  }>;
};

export type OpsStatusResponse = {
  gmail: {
    enabled: boolean;
    account_email?: string | null;
    last_scan_at?: string | null;
    last_scan_status?: string | null;
  };
  worker: {
    healthy?: boolean | null;
    worker_count?: number | null;
    last_heartbeat_at?: string | null;
  };
  queue: {
    queued_runs: number;
    running_runs: number;
    waiting_external_tickets: number;
    error_tickets: number;
  };
  dependencies: {
    database: string;
    gmail: string;
    llm: string;
    checkpointing: string;
  };
  recent_failure?: {
    ticket_id: string;
    run_id: string;
    trace_id: string;
    error_code?: string | null;
    occurred_at?: string | null;
  } | null;
};

export type TestEmailRequest = {
  sender_email_raw: string;
  subject: string;
  body_text: string;
  references?: string | null;
  auto_enqueue?: boolean;
  scenario_label?: string | null;
};

export type TestEmailResponse = {
  ticket: {
    ticket_id: string;
    created: boolean;
    business_status: string;
    processing_status: string;
    version: number;
  };
  run?: {
    run_id: string;
    trace_id: string;
    processing_status: string;
  } | null;
  test_metadata: {
    scenario_label?: string | null;
    auto_enqueue: boolean;
    source_channel: string;
  };
};

export type RetryTicketRequest = {
  ticket_version: number;
};

export type RunTicketResponse = {
  ticket_id: string;
  run_id: string;
  trace_id: string;
  processing_status: string;
};

export type ApproveTicketRequest = {
  ticket_version: number;
  draft_id: string;
  comment?: string | null;
};

export type EditAndApproveTicketRequest = {
  ticket_version: number;
  draft_id: string;
  comment?: string | null;
  edited_content_text: string;
};

export type RewriteTicketRequest = {
  ticket_version: number;
  draft_id: string;
  comment?: string | null;
  rewrite_reasons: string[];
};

export type EscalateTicketRequest = {
  ticket_version: number;
  comment?: string | null;
  target_queue: string;
};

export type CloseTicketRequest = {
  ticket_version: number;
  reason: string;
};

export type TicketActionResponse = {
  ticket_id: string;
  review_id?: string | null;
  business_status: string;
  processing_status: string;
  version: number;
};
