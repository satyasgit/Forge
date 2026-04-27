import { useCallback, useEffect } from 'react';
import ReactFlow,
  {
    Node,
    Edge,
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    NodeTypes,
    MarkerType,
    BackgroundVariant,
    addEdge as rfAddEdge,
    OnConnect,
    OnNodesChange,
    OnEdgesChange,
  } from 'reactflow';
import 'reactflow/dist/style.css';

import { usePipelineStore } from '../hooks/usePipelineStore';
import AgentNode from './AgentNode';

const nodeTypes: NodeTypes = {
  agent: AgentNode,
};

interface PipelineCanvasProps {
  onNodeSelect: (id: string | null) => void;
  selectedNodeId: string | null;
}

export default function PipelineCanvas({
  onNodeSelect,
  selectedNodeId: _selectedNodeId,
}: PipelineCanvasProps) {
  const { nodes: storeNodes, edges: storeEdges } = usePipelineStore();

  const [nodes, setNodesState, onNodesChange] = useNodesState(storeNodes as Node[]);
  const [edges, setEdgesState, onEdgesChange] = useEdgesState(storeEdges as Edge[]);

  useEffect(() => {
    // Ensure nodes from store are correctly typed for ReactFlow
    setNodesState(storeNodes as Node[]);
  }, [storeNodes, setNodesState]);

  useEffect(() => {
    // Map store edges to ReactFlow edges with proper styling/markers
    const rfEdges = storeEdges.map(edge => ({
      ...edge,
      type: edge.type || 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20, color: '#b1b1b7' },
    })) as Edge[];
    setEdgesState(rfEdges);
  }, [storeEdges, setEdgesState]);

  const onNodesChangeInternal: OnNodesChange = useCallback(
    (changes) => {
      onNodesChange(changes);
      // We don't sync EVERY node change (like position) to the store immediately 
      // to avoid performance issues, but for simplicity here we will.
      // In a real app, you might sync on 'onNodeDragStop'.
    },
    [onNodesChange]
  );

  const onEdgesChangeInternal: OnEdgesChange = useCallback(
    (changes) => {
      onEdgesChange(changes);
      
      // Sync removals to store
      const removals = changes.filter(c => c.type === 'remove');
      if (removals.length > 0) {
        const store = usePipelineStore.getState();
        removals.forEach(r => {
          if ('id' in r) {
            store.removeEdge(r.id);
            // Update customConfig
            const currentConfig = store.customConfig;
            const newEdges = store.edges.filter(e => e.id !== r.id).map(e => ({
              source: e.source,
              target: e.target,
              type: e.type || 'smoothstep'
            }));
            store.setCustomConfig({
              ...currentConfig,
              edges: newEdges
            });
          }
        });
      }
    },
    [onEdgesChange]
  );

  const onConnect: OnConnect = useCallback(
    (params) => {
      const newEdge = {
        ...params,
        id: `e-${params.source}-${params.target}`,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#b1b1b7' },
      };
      setEdgesState((eds) => rfAddEdge(newEdge, eds));
      // Sync to store
      const { source, target } = params;
      if (source && target) {
        const store = usePipelineStore.getState();
        store.addEdge({
          id: newEdge.id,
          source,
          target,
          type: 'smoothstep'
        });
        
        // Also update customConfig so the changes are sent to the backend
        const currentConfig = store.customConfig;
        store.setCustomConfig({
          ...currentConfig,
          edges: [...(currentConfig.edges || []), { source, target, type: 'smoothstep' }]
        });
      }
    },
    [setEdgesState]
  );

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    onNodeSelect(node.id);
  }, [onNodeSelect]);

  const onPaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  return (
    <div className="react-flow-wrapper">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChangeInternal}
        onEdgesChange={onEdgesChangeInternal}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        snapToGrid
        snapGrid={[20, 20]}
        defaultEdgeOptions={{
          type: 'smoothstep',
          markerEnd: { type: MarkerType.ArrowClosed, width: 20, height: 20, color: '#b1b1b7' },
        }}
      >
        <Controls />
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}
