import { useState } from 'react';
import { usePipelineStore } from '../hooks/usePipelineStore';
import type { CheckpointInfo } from '../types';

interface CheckpointPanelProps {
  onClose: () => void;
}

export default function CheckpointPanel({ onClose }: CheckpointPanelProps) {
  const {
    checkpoints,
    isPaused,
    approveCheckpoint,
    rejectCheckpoint,
  } = usePipelineStore();

  const [selectedCheckpointId, setSelectedCheckpointId] = useState<string | null>(null);
  const [approverEmail, setApproverEmail] = useState('');
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pendingCheckpoints = checkpoints.filter((c) => c.status === 'pending');
  const selectedCheckpoint = checkpoints.find((c) => c.id === selectedCheckpointId);

  const handleApprove = async () => {
    if (!selectedCheckpointId) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await approveCheckpoint(selectedCheckpointId, approverEmail || undefined, reason || undefined);
      setSelectedCheckpointId(null);
      setApproverEmail('');
      setReason('');
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to approve checkpoint');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!selectedCheckpointId) return;
    if (!reason.trim()) {
      setError('Please provide a reason for rejection');
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await rejectCheckpoint(selectedCheckpointId, approverEmail || undefined, reason || undefined);
      setSelectedCheckpointId(null);
      setApproverEmail('');
      setReason('');
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to reject checkpoint');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isPaused || pendingCheckpoints.length === 0) {
    return null;
  }

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        width: 400,
        height: '100%',
        background: 'white',
        borderLeft: '2px solid #e5e7eb',
        boxShadow: '-4px 0 12px rgba(0,0,0,0.1)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid #e5e7eb',
          background: '#fef3c7',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#92400e' }}>
            ⏸️ Pipeline Paused
          </h3>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#b45309' }}>
            {pendingCheckpoints.length} checkpoint{pendingCheckpoints.length !== 1 ? 's' : ''} pending approval
          </p>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            fontSize: '20px',
            cursor: 'pointer',
            color: '#92400e',
          }}
          title="Close"
        >
          ×
        </button>
      </div>

      {/* Checkpoint List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
        <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600 }}>Pending Checkpoints</h4>

        {pendingCheckpoints.map((cp) => (
          <div
            key={cp.id}
            onClick={() => setSelectedCheckpointId(cp.id)}
            style={{
              padding: '12px',
              marginBottom: '8px',
              border: `2px solid ${selectedCheckpointId === cp.id ? '#f59e0b' : '#e5e7eb'}`,
              borderRadius: '8px',
              background: selectedCheckpointId === cp.id ? '#fef3c7' : 'white',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4, fontSize: '14px' }}>
              {cp.checkpoint_type}
            </div>
            <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: 8 }}>
              {cp.message}
            </div>
            <div style={{ fontSize: '11px', color: '#9ca3af' }}>
              Created: {new Date(cp.created_at).toLocaleString()}
            </div>
            {cp.metadata?.approvers && (
              <div style={{ fontSize: '11px', color: '#6b7280', marginTop: 4 }}>
                Approvers: {Array.isArray(cp.metadata.approvers) ? cp.metadata.approvers.join(', ') : cp.metadata.approvers}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Approval Form */}
      {selectedCheckpoint && (
        <div
          style={{
            padding: '16px',
            borderTop: '1px solid #e5e7eb',
            background: '#f9fafb',
          }}
        >
          <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600 }}>
            Action: {selectedCheckpoint.checkpoint_type}
          </h4>

          {error && (
            <div
              style={{
                padding: '8px 12px',
                background: '#fee2e2',
                border: '1px solid #fecaca',
                borderRadius: '4px',
                color: '#b91c1c',
                fontSize: '13px',
                marginBottom: '12px',
              }}
            >
              {error}
            </div>
          )}

          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: 4 }}>
              Your Email (optional)
            </label>
            <input
              type="email"
              value={approverEmail}
              onChange={(e) => setApproverEmail(e.target.value)}
              placeholder="you@company.com"
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '14px',
              }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: 4 }}>
              {selectedCheckpoint.checkpoint_type === 'human_approval' ? 'Comments' : 'Reason'}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                selectedCheckpoint.checkpoint_type === 'human_approval'
                  ? 'Add any comments...'
                  : 'Reason for rejection (required for reject)'
              }
              rows={3}
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '14px',
                resize: 'vertical',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleReject}
              disabled={isSubmitting}
              style={{
                flex: 1,
                padding: '10px 16px',
                background: '#fee2e2',
                color: '#b91c1c',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '14px',
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.6 : 1,
              }}
            >
              {isSubmitting ? 'Rejecting...' : '❌ Reject'}
            </button>
            <button
              onClick={handleApprove}
              disabled={isSubmitting}
              style={{
                flex: 1,
                padding: '10px 16px',
                background: '#d1fae5',
                color: '#047857',
                border: '1px solid #a7f3d0',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '14px',
                cursor: isSubmitting ? 'not-allowed' : 'pointer',
                opacity: isSubmitting ? 0.6 : 1,
              }}
            >
              {isSubmitting ? 'Approving...' : '✅ Approve'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
