import { useEffect } from 'react';
import { usePipelineStore } from './hooks/usePipelineStore';
import Sidebar from './components/Sidebar';
import PipelineCanvas from './components/PipelineCanvas';
import ConfigPanel from './components/ConfigPanel';
import Toolbar from './components/Toolbar';
import CheckpointPanel from './components/CheckpointPanel';
import type { PipelineNode } from './types';

function getAgentRole(agentName: string): string {
  const roles: Record<string, string> = {
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
  return roles[agentName] || agentName;
}

function App() {
  const {
    loadTemplates,
    templates,
    selectedTemplate,
    customConfig,
    selectedNode,
    validationResult,
    previewResult,
    isLoading,
    error,
    selectTemplate,
    setCustomConfig,
    validate,
    preview,
    runPipeline,
    selectNode,
    // Checkpoint state
    isPaused,
    checkpoints,
  } = usePipelineStore();

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  const handleRun = async () => {
    const projectId = `project-${Date.now()}`;
    const feature = customConfig.description || customConfig.name;
    const jobId = await runPipeline(feature, projectId);
    if (jobId) {
      alert(`Pipeline started! Job ID: ${jobId}\nProject: ${projectId}`);
    }
  };

  const handleAddAgent = (agentName: string) => {
    if (customConfig.agents.some((a) => a.agent === agentName)) {
      alert(`Agent "${agentName}" is already in the pipeline`);
      return;
    }

    const newAgent = { agent: agentName, enabled: true, model: 'claude-sonnet-4-5' };
    setCustomConfig({ ...customConfig, agents: [...customConfig.agents, newAgent] });

    const store = usePipelineStore.getState();
    const newNode: PipelineNode = {
      id: agentName,
      type: 'agent',
      position: { x: 100 + store.nodes.length * 100, y: 100 + store.edges.length * 50 },
      data: { agentName, agentRole: getAgentRole(agentName), config: newAgent },
    };
    store.addNode(newNode);
  };

  const handleUpdateNode = (nodeId: string, updates: Partial<PipelineNode>) => {
    const store = usePipelineStore.getState();
    store.updateNode(nodeId, updates);

    const agentIndex = customConfig.agents.findIndex((a) => a.agent === nodeId);
    if (agentIndex !== -1) {
      const newAgents = [...customConfig.agents];
      newAgents[agentIndex] = { ...newAgents[agentIndex], ...(updates.data?.config || {}) };
      setCustomConfig({ ...customConfig, agents: newAgents });
    }
  };

  const handleDeleteNode = (nodeId: string) => {
    const store = usePipelineStore.getState();
    store.removeNode(nodeId);
    setCustomConfig({
      ...customConfig,
      agents: customConfig.agents.filter((a) => a.agent !== nodeId),
      edges: customConfig.edges?.filter((e) => e.source !== nodeId && e.target !== nodeId),
    });
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1 className="app-title">🤖 AI Agent Org - Pipeline Builder</h1>
        <div className="app-header-actions">
          {error && <span className="error-message">{error}</span>}
          <Toolbar
            onValidate={validate}
            onPreview={preview}
            onRun={handleRun}
            isValid={validationResult?.valid || false}
            isLoading={isLoading}
          />
        </div>
      </header>

      <div className="pipeline-builder" style={{ position: 'relative' }}>
        <Sidebar
          templates={templates}
          selectedTemplate={selectedTemplate}
          onSelectTemplate={selectTemplate}
          customConfig={customConfig}
          onConfigChange={setCustomConfig}
          onAddAgent={handleAddAgent}
          validationResult={validationResult}
          previewResult={previewResult}
        />

        <main className="main-canvas">
          <PipelineCanvas onNodeSelect={selectNode} selectedNodeId={null} />
        </main>

        <aside className="config-panel">
          <ConfigPanel node={selectedNode} onUpdate={handleUpdateNode} onDelete={handleDeleteNode} />
        </aside>

        {/* Checkpoint Panel Overlay */}
        {isPaused && (
          <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 400, zIndex: 1000 }}>
            <CheckpointPanel onClose={() => {}} />
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
