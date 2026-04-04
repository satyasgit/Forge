import { create } from 'zustand';
import type {
  TemplateMetadata,
  PipelineConfig,
  PipelineNode,
  PipelineEdge,
  ValidationResponse,
  PipelinePreviewResponse,
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
        return {
          id: agentName,
          type: 'agent',
          position: DEFAULT_POSITIONS[agentName] || {
            x: Math.random() * 400,
            y: Math.random() * 300,
          },
          data: {
            agentName,
            agentRole: AGENT_ROLES[agentName] || agentName,
            config: agentConfig,
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
    try {
      const result = await api.validateConfig(customConfig);
      set({ validationResult: result, error: null });
    } catch (err: any) {
      set({ error: err.message || 'Validation failed' });
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
          type: n.type as 'agent',
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

  // Execution
  isLoading: false,
  error: null,
  runPipeline: async (feature: string, projectId: string) => {
    const { customConfig } = get();
    set({ isLoading: true, error: null });
    try {
      const result = await api.runPipeline({
        feature,
        project_id: projectId,
        config: customConfig,
      });
      set({ isLoading: false });
      // API returns {"run": {"job_id": "...", "status": "pending"}, "message": "...", "success": true}
      return result.run?.job_id ?? null;
    } catch (err: any) {
      set({ error: err.message || 'Pipeline run failed', isLoading: false });
      return null;
    }
  },

  // Utils
  generateId: () => Math.random().toString(36).substring(2, 9),
}));

// loadTemplateConfig is now defined directly in the store above
