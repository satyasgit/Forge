import { Handle, Position, NodeProps } from 'reactflow';
import { NodeData } from '../types';

export default function AgentNode({ data, selected }: NodeProps<NodeData>) {
  const isCheckpoint = data.isCheckpoint;
  const checkpointStatus = data.checkpointStatus;

  // Checkpoint node styling (octagon shape with different colors)
  const getCheckpointStyle = () => {
    const baseStyle: React.CSSProperties = {
      padding: '10px 14px',
      borderRadius: '12px', // More rounded for checkpoint
      border: `2px solid ${selected ? '#f59e0b' : '#d97706'}`,
      background: selected ? '#fef3c7' : '#ffedd5',
      minWidth: '180px',
      boxShadow: selected
        ? '0 4px 12px rgba(245, 158, 11, 0.3)'
        : '0 2px 4px rgba(0,0,0,0.1)',
      cursor: 'pointer',
      position: 'relative',
    };

    // Add status border color
    if (checkpointStatus === 'approved') {
      baseStyle.borderColor = selected ? '#10b981' : '#059669';
      baseStyle.background = selected ? '#d1fae5' : '#ecfdf5';
    } else if (checkpointStatus === 'rejected') {
      baseStyle.borderColor = selected ? '#ef4444' : '#dc2626';
      baseStyle.background = selected ? '#fee2e2' : '#fef2f2';
    } else if (checkpointStatus === 'timeout') {
      baseStyle.borderColor = selected ? '#6b7280' : '#4b5563';
      baseStyle.background = selected ? '#e5e7eb' : '#f3f4f6';
    }

    return baseStyle;
  };

  // Regular agent styling
  const getAgentStyle = () => ({
    padding: '12px 16px',
    borderRadius: '8px',
    border: `2px solid ${selected ? '#2563eb' : '#e5e7eb'}`,
    background: selected ? '#eff6ff' : 'white',
    minWidth: '160px',
    boxShadow: selected
      ? '0 4px 12px rgba(37, 99, 235, 0.2)'
      : '0 2px 4px rgba(0,0,0,0.1)',
    cursor: 'pointer',
  });

  const containerStyle = isCheckpoint ? getCheckpointStyle() : getAgentStyle();

  // Checkpoint icon
  const renderCheckpointIcon = () => {
    if (!isCheckpoint) return null;
    let icon = '⏸️';
    let label = 'PAUSED';
    if (checkpointStatus === 'approved') {
      icon = '✅';
      label = 'APPROVED';
    } else if (checkpointStatus === 'rejected') {
      icon = '❌';
      label = 'REJECTED';
    } else if (checkpointStatus === 'timeout') {
      icon = '⏰';
      label = 'TIMEOUT';
    }
    return (
      <div
        style={{
          position: 'absolute',
          top: '-10px',
          right: '-10px',
          background: '#f59e0b',
          color: 'white',
          borderRadius: '50%',
          width: '24px',
          height: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '12px',
          fontWeight: 'bold',
          border: '2px solid white',
          boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
        }}
        title={label}
      >
        {icon}
      </div>
    );
  };

  // Position handles for checkpoint (circle instead of square-ish)
  const handleStyle = isCheckpoint
    ? { background: '#d97706', width: 10, height: 10, border: '2px solid white' }
    : { background: '#9ca3af', width: 8, height: 8 };

  return (
    <div style={containerStyle}>
      {renderCheckpointIcon()}

      <Handle
        type="target"
        position={Position.Top}
        style={{
          ...handleStyle,
          top: isCheckpoint ? '-6px' : undefined,
        }}
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
        {isCheckpoint ? `${data.checkpointType || 'checkpoint'} • ${data.checkpointStatus || 'pending'}` : data.agentRole}
      </div>

      {isCheckpoint && data.checkpointMessage && (
        <div
          style={{
            marginTop: 6,
            fontSize: '10px',
            color: '#4b5563',
            fontStyle: 'italic',
            borderTop: '1px solid rgba(0,0,0,0.1)',
            paddingTop: 4,
          }}
        >
          {data.checkpointMessage.length > 50
            ? data.checkpointMessage.substring(0, 50) + '...'
            : data.checkpointMessage}
        </div>
      )}

      {!isCheckpoint && data.config?.model && (
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
        style={{
          ...handleStyle,
          bottom: isCheckpoint ? '-6px' : undefined,
        }}
      />
    </div>
  );
}
