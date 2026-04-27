import { create } from 'zustand';
import type {
  TemplateMetadata,
  PipelineConfig,
  PipelineNode,
  PipelineEdge,
  ValidationResponse,
  PipelinePreviewResponse,
  CheckpointListResponse,
  CheckpointDecisionRequest,
} from '../types';
import * as api from '../api';

interface PipelineStore {
  // Templates
  templates: TemplateMetadata[];
  selectedTemplate: TemplateMetadata | null;
  loadTemplates: () => Promise<void>;
  selectTemplate: (template: TemplateMetadata | null) => void;
  loadTemplateConfig: (templateName: string) => Promise<void>;

  // Config
  customConfig: PipelineConfig;
  setCustomConfig: (config: PipelineConfig) => void;
  resetConfig: () => void;

  // Graph
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  setNodes: (nodes: PipelineNode[]) => void;
  setEdges: (edges: PipelineEdge[]) => void;
  addNode: (node: PipelineNode) => void;
  removeNode: (id: string) => void;
  updateNode: (id: string, updates: Partial<PipelineNode>) => void;
  addEdge: (edge: PipelineEdge) => void;
  removeEdge: (edgeId: string) => void;
  clearGraph: () => void;
  buildGraphFromConfig: (config: PipelineConfig) => void;

  // Selection
  selectedNodeId: string | null;
  selectNode: (id: string | null) => void;
  selectedNode: PipelineNode | null;

  // Validation & Preview
  validationResult: ValidationResponse | null;
  previewResult: PipelinePreviewResponse | null;
  validate: () => Promise<void>;
  preview: () => Promise<void>;

  // Execution
  isLoading: boolean;
  error: string | null;
  runPipeline: (feature: string, projectId: string) => Promise<string | null>;
  runId: string | null;  // Current pipeline run ID (for checkpoints)
  isPaused: boolean;
  checkpoints: CheckpointListResponse['checkpoints'];
  setRunId: (runId: string | null) => void;
  setIsPaused: (paused: boolean) => void;
  setCheckpoints: (checkpoints: CheckpointListResponse['checkpoints']) => void;
  pollCheckpoints: (runId: string) => Promise<void>;  // Poll for pending checkpoints
  startCheckpointPolling: (runId: string) => void;
  stopCheckpointPolling: () => void;
  pollingInterval: number | undefined;
  approveCheckpoint: (checkpointId: string, approver?: string, reason?: string) => Promise<void>;
  rejectCheckpoint: (checkpointId: string, approver?: string, reason?: string) => Promise<void>;

  // Utils
  generateId: () => string;
}

const DEFAULT_POSITIONS: Record<string, { x: number; y: number }> = {
  pm: { x: 100, y: 100 },
  ui_ux: { x: 300, y: 50 },
  frontend: { x: 300, y: 200 },
  mobile: { x: 300, y: 350 },
  backend: { x: 550, y: 100 },
  security: { x: 550, y: 250 },
  code_review: { x: 550, y: 400 },
  qa: { x: 800, y: 100 },
  monetisation: { x: 800, y: 250 },
  devops: { x: 800, y: 400 },
};

const AGENT_ROLES: Record<string, string> = {
  pm: 'Senior Product Manager',
  ui_ux: 'Senior Product Designer',
  frontend: 'Senior Frontend Engineer',
  mobile: 'Senior Mobile Engineer',
  backend: 'Senior Backend Engineer',
  security: 'Senior Security Engineer',
  code_review: 'Principal Engineer',
  qa: 'Senior QA Engineer / SDET',
  monetisation: 'Growth Engineer',
  devops: 'DevOps Engineer',
};

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  // Templates
  templates: [],
  selectedTemplate: null,
  loadTemplates: async () => {
    try {
      const data = await api.getTemplates();
      set({ templates: data.templates, error: null });
    } catch (err: any) {
      set({ error: err.message || 'Failed to load templates' });
    }
  },
  selectTemplate: async (template) => {
    set({ selectedTemplate: template, error: null });
    if (template) {
      await get().loadTemplateConfig(template.name);
    } else {
      get().resetConfig();
    }
  },
  loadTemplateConfig: async (templateName: string) => {
    try {
      const data = await api.getTemplate(templateName);
      const config = data.template;
      set({ customConfig: config });
      get().buildGraphFromConfig(config);
    } catch (err: any) {
      set({ error: err.message || 'Failed to load template' });
    }
  },

  // Config
  customConfig: {
    version: '1.0',
    name: 'custom_pipeline',
    description: '',
    agents: [],
    edges: [],
    auto_resolve: true,
    strict_validation: false,
  },
  setCustomConfig: (config) => set({ customConfig: config }),
  resetConfig: () =>
    set({
      customConfig: {
        version: '1.0',
        name: 'custom_pipeline',
        description: '',
        agents: [],
        edges: [],
        auto_resolve: true,
        strict_validation: false,
      },
      nodes: [],
      edges: [],
      selectedTemplate: null,
      validationResult: null,
      previewResult: null,
      runId: null,
      isPaused: false,
      checkpoints: [],
    }),

  // Graph
  nodes: [],
  edges: [],
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  addNode: (node) => set((state) => ({ nodes: [...state.nodes, node] })),
  removeNode: (id) =>
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
      edges: state.edges.filter((e) => e.source !== id && e.target !== id),
      selectedNodeId: state.selectedNodeId === id ? null : state.selectedNodeId,
    })),
  updateNode: (id, updates) =>
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, ...updates } : n)),
    })),
  addEdge: (edge) => set((state) => ({ edges: [...state.edges, edge] })),
  removeEdge: (edgeId) =>
    set((state) => ({
      edges: state.edges.filter((e) => e.id !== edgeId),
    })),
  clearGraph: () => set({ nodes: [], edges: [] }),
  buildGraphFromConfig: (config) => {
    const nodes: PipelineNode[] = config.agents
      .filter((a) => a.enabled)
      .map((agentConfig) => {
        const agentName = agentConfig.agent;
        // Check if this is a checkpoint agent
        const isCheckpoint = agentName === 'checkpoint' || agentConfig.meta?.checkpoint;
        return {
          id: agentName,
          type: isCheckpoint ? ('checkpoint' as const) : ('agent' as const),
          position: DEFAULT_POSITIONS[agentName] || {
            x: Math.random() * 400,
            y: Math.random() * 300,
          },
          data: {
            agentName,
            agentRole: AGENT_ROLES[agentName] || agentName,
            config: agentConfig,
            ...(isCheckpoint && {
              isCheckpoint: true,
              checkpointType: agentConfig.meta?.checkpoint?.checkpoint_type || 'human_approval',
              checkpointStatus: 'pending',
              checkpointMessage: agentConfig.meta?.checkpoint?.message || 'Action required',
            }),
          },
        };
      });

    const edges: PipelineEdge[] = (config.edges || []).map((edge) => ({
      id: `${edge.source}->${edge.target}`,
      source: edge.source,
      target: edge.target,
      type: edge.type || 'smoothstep',
    }));

    set({ nodes, edges });
  },

  // Selection
  selectedNodeId: null,
  selectNode: (id) => set({ selectedNodeId: id }),
  get selectedNode() {
    return get().nodes.find((n) => n.id === get().selectedNodeId) || null;
  },

  // Validation & Preview
  validationResult: null,
  previewResult: null,
  validate: async () => {
    const { customConfig } = get();
    set({ isLoading: true, error: null });
    try {
      const result = await api.validateConfig(customConfig);
      set({ validationResult: result, isLoading: false });
    } catch (err: any) {
      set({ error: err.message || 'Validation failed', isLoading: false });
    }
  },
  preview: async () => {
    const { customConfig } = get();
    set({ isLoading: true, error: null });
    try {
      const result = await api.previewPipeline(customConfig);
      set({
        previewResult: result,
        isLoading: false,
        nodes: result.dag.nodes.map((n) => ({
          id: n.id,
          type: n.type as 'agent' | 'checkpoint',
          position: n.position,
          data: {
            agentName: n.data.agentName,
            agentRole: n.data.agentRole,
          },
        })),
        edges: result.dag.edges,
      });
    } catch (err: any) {
      set({ error: err.message || 'Preview failed', isLoading: false });
    }
  },

  // Execution & Checkpoints
  isLoading: false,
  error: null,
  runId: null,
  isPaused: false,
  checkpoints: [],
  setRunId: (runId) => set({ runId }),
  setIsPaused: (isPaused) => set({ isPaused }),
  setCheckpoints: (checkpoints) => set({ checkpoints }),

  runPipeline: async (feature: string, projectId: string) => {
    const { customConfig } = get();
    set({ isLoading: true, error: null, isPaused: false, checkpoints: [] });
    try {
      const result = await api.runPipeline({
        feature,
        project_id: projectId,
        config: customConfig,
      });
      set({ isLoading: false });
      // API returns {"run": {"job_id": "...", "status": "pending"}, "run_id": "...", "message": "...", "success": true}
      const jobId = result.run?.job_id ?? null;
      const runId = (result as any).run_id ?? null;
      if (runId) {
        set({ runId });
        // Start polling for checkpoints
        get().startCheckpointPolling(runId);
      }
      return jobId;
    } catch (err: any) {
      set({ error: err.message || 'Pipeline run failed', isLoading: false });
      return null;
    }
  },

  // Checkpoint polling (runs in background)
  pollingInterval: undefined,
  startCheckpointPolling: (runId: string) => {
    if (get().pollingInterval !== undefined) {
      clearInterval(get().pollingInterval);
    }
    // Poll every 3 seconds
    const interval = window.setInterval(async () => {
      await get().pollCheckpoints(runId);
    }, 3000);
    set({ pollingInterval: interval });
  },
  stopCheckpointPolling: () => {
    if (get().pollingInterval !== undefined) {
      clearInterval(get().pollingInterval);
      set({ pollingInterval: undefined });
    }
  },

  pollCheckpoints: async (runId: string) => {
    const { runId: currentRunId, isPaused } = get();
    if (!runId || runId !== currentRunId || isPaused) return; // Already paused, don't poll

    try {
      const data = await api.getCheckpoints(runId, get().customConfig.name || 'default');
      const pendingCheckpoints = data.checkpoints.filter((c) => c.status === 'pending');
      set({ checkpoints: data.checkpoints });

      if (pendingCheckpoints.length > 0 && !isPaused) {
        // Pipeline is waiting for approval
        set({ isPaused: true });
        // Mark checkpoint nodes as pending
        const nodes = get().nodes.map((node) => {
          if (node.data.checkpointId && pendingCheckpoints.some((c) => c.id === node.data.checkpointId)) {
            return {
              ...node,
              data: {
                ...node.data,
                checkpointStatus: 'pending' as const,
              },
            };
          }
          return node;
        });
        set({ nodes: nodes as PipelineNode[] });
      }

      // Check if all checkpoints are resolved (approved/rejected)
      const resolved = data.checkpoints.every((c) => c.status !== 'pending');
      if (resolved && data.checkpoints.length > 0) {
        // Pipeline should have resumed or finished - stop polling
        get().stopCheckpointPolling();
        // Refresh node statuses
        const nodes = get().nodes.map((node) => {
          const checkpoint = data.checkpoints.find((c) => c.id === node.data.checkpointId);
          if (checkpoint) {
            return {
              ...node,
              data: {
                ...node.data,
                checkpointStatus: checkpoint.status as 'approved' | 'rejected',
              },
            };
          }
          return node;
        });
        set({ nodes: nodes as PipelineNode[], isPaused: false });
      }
    } catch (err: any) {
      console.error('Failed to poll checkpoints:', err);
    }
  },

  approveCheckpoint: async (checkpointId: string, approver?: string, reason?: string) => {
    const { runId } = get();
    if (!runId) throw new Error('No active pipeline run');

    const decision: CheckpointDecisionRequest = {
      decision: 'approved',
      approver,
      reason,
    };
    const result = await api.resumeCheckpoint(runId, decision);

    set({
      isPaused: result.status === 'paused',
      checkpoints: get().checkpoints.map((c) =>
        c.id === checkpointId ? { ...c, status: 'approved', approver } : c
      ),
    });

    if (result.status !== 'paused') {
      // Pipeline completed or aborted - stop polling
      get().stopCheckpointPolling();
      if (result.status === 'completed') {
        alert('✅ Pipeline completed successfully!');
      } else if (result.status === 'aborted') {
        alert(`❌ Pipeline aborted: ${result.summary || 'Checkpoint rejected'}`);
      }
    }
  },

  rejectCheckpoint: async (checkpointId: string, approver?: string, reason?: string) => {
    const { runId } = get();
    if (!runId) throw new Error('No active pipeline run');

    const decision: CheckpointDecisionRequest = {
      decision: 'rejected',
      approver,
      reason,
    };
    const result = await api.resumeCheckpoint(runId, decision);

    set({
      isPaused: result.status === 'paused',
      checkpoints: get().checkpoints.map((c) =>
        c.id === checkpointId ? { ...c, status: 'rejected', approver } : c
      ),
    });

    get().stopCheckpointPolling();
    if (result.status === 'aborted') {
      alert(`❌ Pipeline aborted: ${reason || 'Checkpoint rejected'}`);
    }
  },

  // Utils
  generateId: () => Math.random().toString(36).substring(2, 9),
}));

// loadTemplateConfig is now defined directly in the store above
