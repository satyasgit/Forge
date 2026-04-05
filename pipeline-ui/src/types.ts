// Agent definition from registry
export interface AgentInfo {
  name: string;
  role: string;
  description?: string;
}

// Pipeline configuration (matches API schema)
export interface AgentTaskConfig {
  agent: string;
  enabled: boolean;
  task?: string;
  model?: string;
  max_tokens?: number;
  depends_on?: string[];
  meta?: Record<string, any>;
}

export interface PipelineConfig {
  version: string;
  name: string;
  description?: string;
  project_types?: string[];
  agents: AgentTaskConfig[];
  edges?: { source: string; target: string; type?: string }[];
  auto_resolve?: boolean;
  strict_validation?: boolean;
  settings?: Record<string, any>;
  metadata?: Record<string, any>;
}

// API Response types
export interface TemplateMetadata {
  name: string;
  description: string;
  project_types: string[];
  agent_count: number;
  file: string;
}

export interface TemplateListResponse {
  templates: TemplateMetadata[];
}

export interface TemplateDetailResponse {
  template: PipelineConfig;
}

export interface ValidationResponse {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface PipelinePreviewResponse {
  agents: string[];
  agent_count: number;
  estimated_cost_usd: number;
  estimated_duration_minutes: number;
  dag: {
    nodes: {
      id: string;
      type: string;
      data: { agentName: string; agentRole: string };
      position: { x: number; y: number };
    }[];
    edges: { id: string; source: string; target: string; type: string }[];
  };
  validation?: ValidationResponse;
}

export interface PipelineRunResponse {
  message: string;
  run: {
    job_id: string;
    status: string;
  };
  success: boolean;
}

export interface RunPipelineRequest {
  feature: string;
  project_id: string;
  config: PipelineConfig;
}

// Checkpoint API types
export interface CheckpointInfo {
  id: string;
  checkpoint_type: string;
  agent_name: string;
  status: string;
  message: string;
  created_at: string;
  approver?: string;
  metadata?: Record<string, any>;
}

export interface CheckpointListResponse {
  project_id: string;
  run_id: string;
  checkpoints: CheckpointInfo[];
}

export interface CheckpointDecisionRequest {
  decision: 'approved' | 'rejected';
  approver?: string;
  reason?: string;
}

export interface ResumeResponse {
  run_id: string;
  status: 'completed' | 'aborted' | 'paused';
  checkpoint_id?: string;
  checkpoint_type?: string;
  results?: Record<string, any>;
  summary?: string;
}

// React Flow types
export interface NodeData {
  agentName: string;
  agentRole: string;
  config?: AgentTaskConfig;
  // Checkpoint-specific fields
  isCheckpoint?: boolean;
  checkpointId?: string;
  checkpointType?: string;
  checkpointStatus?: 'pending' | 'approved' | 'rejected' | 'timeout';
  checkpointMessage?: string;
}

export interface PipelineNode {
  id: string;
  type: 'agent' | 'checkpoint';
  position: { x: number; y: number };
  data: NodeData;
}

export interface PipelineEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

export interface PipelineGraph {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
}

// App state
export interface AppState {
  // Templates
  templates: TemplateMetadata[];
  selectedTemplate: TemplateMetadata | null;
  customConfig: PipelineConfig;

  // Graph state
  nodes: PipelineNode[];
  edges: PipelineEdge[];

  // UI state
  selectedNodeId: string | null;
  validationResult: ValidationResponse | null;
  previewResult: PipelinePreviewResponse | null;

  // API state
  isLoading: boolean;
  error: string | null;
}
