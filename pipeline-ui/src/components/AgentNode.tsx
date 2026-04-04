import { Handle, Position, NodeProps } from 'reactflow';
import { NodeData } from '../types';

export default function AgentNode({ data, selected }: NodeProps<NodeData>) {
  return (
    <div
      style={{
        padding: '12px 16px',
        borderRadius: '8px',
        border: `2px solid ${selected ? '#2563eb' : '#e5e7eb'}`,
        background: selected ? '#eff6ff' : 'white',
        minWidth: '160px',
        boxShadow: selected
          ? '0 4px 12px rgba(37, 99, 235, 0.2)'
          : '0 2px 4px rgba(0,0,0,0.1)',
        cursor: 'pointer',
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: '#9ca3af', width: 8, height: 8 }}
      />

      <div style={{ fontWeight: 600, color: '#111827', marginBottom: 4 }}>
        {data.agentName}
      </div>
      <div
        style={{
          fontSize: '11px',
          color: '#6b7280',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {data.agentRole}
      </div>

      {data.config?.model && (
        <div
          style={{
            marginTop: 8,
            fontSize: '10px',
            color: '#4b5563',
            background: '#f3f4f6',
            padding: '2px 6px',
            borderRadius: 4,
            display: 'inline-block',
          }}
        >
          {data.config.model}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: '#9ca3af', width: 8, height: 8 }}
      />
    </div>
  );
}
