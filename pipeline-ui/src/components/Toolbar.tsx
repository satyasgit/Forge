import { useState } from 'react';

interface ToolbarProps {
  onValidate: () => void;
  onPreview: () => void;
  onRun: (projectId: string) => void;
  isValid: boolean;
  isLoading: boolean;
}

export default function Toolbar({
  onValidate,
  onPreview,
  onRun,
  isValid,
  isLoading,
}: ToolbarProps) {
  const [projectId, setProjectId] = useState('');
  const [showRunModal, setShowRunModal] = useState(false);

  const handleRunClick = () => {
    if (!isValid) {
      alert('Please validate your pipeline configuration first.');
      return;
    }
    setShowRunModal(true);
  };

  const handleRunConfirm = async () => {
    if (!projectId.trim()) {
      alert('Please enter a project ID');
      return;
    }
    setShowRunModal(false);
    onRun(projectId);
  };

  return (
    <>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <button
          className="btn btn-secondary"
          onClick={() => onValidate()}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <span className="loading-spinner" style={{ marginRight: 8 }} />
              Loading...
            </>
          ) : (
            '🔍 Validate'
          )}
        </button>

        <button
          className="btn btn-secondary"
          onClick={() => onPreview()}
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <span className="loading-spinner" style={{ marginRight: 8 }} />
              Loading...
            </>
          ) : (
            '👁 Preview'
          )}
        </button>

        <button
          className="btn btn-success"
          onClick={handleRunClick}
          disabled={isLoading || !isValid}
        >
          {isLoading ? (
            <>
              <span className="loading-spinner" style={{ marginRight: 8 }} />
              Running...
            </>
          ) : (
            '▶️ Run Pipeline'
          )}
        </button>
      </div>

      {showRunModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowRunModal(false)}
        >
          <div
            style={{
              background: 'white',
              padding: '24px',
              borderRadius: '12px',
              minWidth: '400px',
              maxWidth: '500px',
              boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 style={{ margin: '0 0 16px 0' }}>Run Pipeline</h2>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: 8, fontWeight: 500 }}>
                Project ID
              </label>
              <input
                type="text"
                className="form-input"
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                placeholder="my-awesome-project"
                autoFocus
              />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowRunModal(false)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleRunConfirm}>
                Start Pipeline
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
