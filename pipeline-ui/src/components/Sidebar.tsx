import type { TemplateMetadata, PipelineConfig } from '../types';

interface SidebarProps {
  templates: TemplateMetadata[];
  selectedTemplate: TemplateMetadata | null;
  onSelectTemplate: (template: TemplateMetadata | null) => void;
  customConfig: PipelineConfig;
  onConfigChange: (config: PipelineConfig) => void;
  onAddAgent: (agentName: string) => void;
  validationResult: any;
  previewResult: any;
}

const ALL_AGENTS = [
  { name: 'pm', role: 'Product Manager' },
  { name: 'ui_ux', role: 'Product Designer' },
  { name: 'frontend', role: 'Frontend Engineer' },
  { name: 'mobile', role: 'Mobile Engineer' },
  { name: 'backend', role: 'Backend Engineer' },
  { name: 'security', role: 'Security Engineer' },
  { name: 'code_review', role: 'Code Reviewer' },
  { name: 'qa', role: 'QA Engineer' },
  { name: 'monetisation', role: 'Growth Engineer' },
  { name: 'devops', role: 'DevOps Engineer' },
];

export default function Sidebar({
  templates,
  selectedTemplate,
  onSelectTemplate,
  customConfig,
  onConfigChange,
  onAddAgent,
  validationResult,
  previewResult,
}: SidebarProps) {
  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onConfigChange({ ...customConfig, name: e.target.value });
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onConfigChange({ ...customConfig, description: e.target.value });
  };

  const handleAddAgent = (agentName: string) => {
    onAddAgent(agentName);
  };

  const handleRemoveAgent = (agentName: string) => {
    const newAgents = customConfig.agents.filter((a) => a.agent !== agentName);
    onConfigChange({ ...customConfig, agents: newAgents });
  };

  const enabledAgentNames = new Set(customConfig.agents.filter((a) => a.enabled).map((a) => a.agent));

  return (
    <div className="sidebar">
      {/* Template Selector */}
      <div className="card">
        <h3 className="card-title">📋 Templates</h3>
        <select
          className="form-select"
          value={selectedTemplate?.name || ''}
          onChange={(e) => {
            const template = templates.find((t) => t.name === e.target.value) || null;
            onSelectTemplate(template);
          }}
        >
          <option value="">Select a template...</option>
          {templates.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name} ({t.agent_count} agents)
            </option>
          ))}
        </select>
      </div>

      {/* Pipeline Config */}
      <div className="card">
        <h3 className="card-title">⚙️ Pipeline Config</h3>
        <div className="form-group">
          <label className="form-label">Name</label>
          <input
            type="text"
            className="form-input"
            value={customConfig.name}
            onChange={handleNameChange}
            placeholder="My Pipeline"
          />
        </div>
        <div className="form-group">
          <label className="form-label">Description</label>
          <textarea
            className="form-textarea"
            value={customConfig.description || ''}
            onChange={handleDescriptionChange}
            placeholder="What should this pipeline build?"
            rows={3}
          />
        </div>
      </div>

      {/* Agent Palette */}
      <div className="card">
        <h3 className="card-title">🧩 Agents</h3>
        <p style={{ fontSize: '12px', color: '#6b7280', marginBottom: 12 }}>
          Click to add agent to pipeline:
        </p>
        <div className="agent-list">
          {ALL_AGENTS.map((agent) => (
            <div
              key={agent.name}
              className="agent-item"
              onClick={() => handleAddAgent(agent.name)}
            >
              <div className="agent-name">{agent.name}</div>
              <div className="agent-role">{agent.role}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Enabled Agents */}
      <div className="card">
        <h3 className="card-title">✅ Enabled ({enabledAgentNames.size})</h3>
        <div className="agent-list">
          {customConfig.agents
            .filter((a) => a.enabled)
            .map((agent) => (
              <div
                key={agent.agent}
                style={{
                  padding: '8px 12px',
                  background: '#f0fdf4',
                  border: '1px solid #bbf7d0',
                  borderRadius: 6,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontWeight: 500 }}>{agent.agent}</div>
                  {agent.model && (
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>{agent.model}</div>
                  )}
                </div>
                <button
                  onClick={() => handleRemoveAgent(agent.agent)}
                  style={{
                    background: '#fee2e2',
                    border: 'none',
                    borderRadius: 4,
                    padding: '2px 8px',
                    cursor: 'pointer',
                    color: '#dc2626',
                  }}
                >
                  ×
                </button>
              </div>
            ))}
        </div>
      </div>

      {/* Validation */}
      {validationResult && (
        <div className="card">
          <h3 className="card-title">🔍 Validation</h3>
          <div
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              background: validationResult.valid ? '#f0fdf4' : '#fef2f2',
              border: `1px solid ${validationResult.valid ? '#bbf7d0' : '#fecaca'}`,
            }}
          >
            {validationResult.valid ? (
              <div className="success-message">✓ Valid configuration</div>
            ) : (
              <div className="error-message">✗ Invalid configuration</div>
            )}
            {validationResult.warnings.length > 0 && (
              <div style={{ marginTop: 8, fontSize: '12px', color: '#f59e0b' }}>
                ⚠ {validationResult.warnings.length} warning(s)
              </div>
            )}
          </div>
        </div>
      )}

      {/* Preview */}
      {previewResult && (
        <div className="card">
          <h3 className="card-title">📊 Preview</h3>
          <div className="metadata-grid">
            <div>
              <div style={{ fontSize: '12px', color: '#6b7280' }}>Agents</div>
              <div style={{ fontSize: '18px', fontWeight: 600 }}>{previewResult.agent_count}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#6b7280' }}>Cost</div>
              <div style={{ fontSize: '18px', fontWeight: 600 }}>
                ${previewResult.estimated_cost_usd.toFixed(2)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#6b7280' }}>Duration</div>
              <div style={{ fontSize: '18px', fontWeight: 600 }}>
                {previewResult.estimated_duration_minutes.toFixed(0)}m
              </div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#6b7280' }}>DAG Nodes</div>
              <div style={{ fontSize: '18px', fontWeight: 600 }}>
                {previewResult.dag.nodes.length}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
