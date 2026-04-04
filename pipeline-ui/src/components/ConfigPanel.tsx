import type { PipelineNode, AgentTaskConfig } from '../types';

interface ConfigPanelProps {
  node: PipelineNode | null;
  onUpdate: (id: string, updates: Partial<PipelineNode>) => void;
  onDelete: (id: string) => void;
}

export default function ConfigPanel({ node, onUpdate, onDelete }: ConfigPanelProps) {
  if (!node) {
    return (
      <div className="config-panel">
        <div className="card">
          <h3 className="card-title">⚙️ Configuration</h3>
          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Select a node to view and edit its configuration.
          </p>
        </div>
      </div>
    );
  }

  const { data } = node;
  const config: AgentTaskConfig = data.config || { agent: data.agentName, enabled: true };

  const handleTaskChange = (task: string) => {
    onUpdate(node.id, {
      data: { ...data, config: { ...config, agent: data.agentName, enabled: config.enabled ?? true, task } },
    });
  };

  const handleModelChange = (model: string) => {
    onUpdate(node.id, {
      data: { ...data, config: { ...config, agent: data.agentName, enabled: config.enabled ?? true, model } },
    });
  };

  const handleEnabledToggle = (enabled: boolean) => {
    onUpdate(node.id, {
      data: { ...data, config: { ...config, agent: data.agentName, enabled, task: config.task, model: config.model } },
    });
  };

  return (
    <div className="config-panel">
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h3 className="card-title" style={{ margin: 0 }}>⚙️ {data.agentName}</h3>
          <button onClick={() => onDelete(node.id)} style={{ background: '#dc2626', color: 'white', border: 'none', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: '12px' }}>
            Delete
          </button>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '12px', color: '#6b7280', display: 'block', marginBottom: 4 }}>Role</label>
          <div style={{ fontSize: '14px', fontWeight: 500 }}>{data.agentRole}</div>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '12px', color: '#6b7280', display: 'block', marginBottom: 4 }}>Enabled</label>
          <input type="checkbox" checked={config.enabled ?? true} onChange={(e) => handleEnabledToggle(e.target.checked)} />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="form-label">Model</label>
          <select className="form-select" value={config.model || 'claude-sonnet-4-5'} onChange={(e) => handleModelChange(e.target.value)}>
            <option value="claude-opus-4-6">Claude Opus 4.6 (best)</option>
            <option value="claude-sonnet-4-6">Claude Sonnet 4.6 (balanced)</option>
            <option value="claude-haiku-4-5">Claude Haiku 4.5 (fast)</option>
          </select>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label className="form-label">Task Prompt</label>
          <textarea
            className="form-textarea"
            value={config.task || ''}
            onChange={(e) => handleTaskChange(e.target.value)}
            placeholder={`Describe what ${data.agentName} should do...`}
            rows={4}
          />
        </div>
      </div>
    </div>
  );
}
