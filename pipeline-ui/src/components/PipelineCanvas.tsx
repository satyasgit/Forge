import { useCallback, useEffect } from 'react';
import ReactFlow,
  {
    Node,
    Edge,
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    Connection,
    NodeTypes,
    MarkerType,
    BackgroundVariant,
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
    setNodesState(storeNodes as Node[]);
  }, [storeNodes, setNodesState]);

  useEffect(() => {
    setEdgesState(storeEdges as Edge[]);
  }, [storeEdges, setEdgesState]);

  const onConnect = useCallback((_params: Connection) => {}, []);

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
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
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
