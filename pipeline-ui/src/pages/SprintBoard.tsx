import { useEffect, useState } from 'react';

// Mock types until we connect to actual FastAPI endpoints
interface Story {
  id: string;
  title: string;
  description: string;
  status: 'todo' | 'in_progress' | 'review' | 'done';
  assigned_to: string;
  points: number;
}

export default function SprintBoard() {
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchSprintData() {
      try {
        // Fetch all sprints
        const sprintsRes = await fetch('http://localhost:8000/api/sprints');
        const sprints = await sprintsRes.json();
        
        if (sprints && sprints.length > 0) {
          const activeSprint = sprints[0]; // Simplification: pick the first one
          
          // Fetch stories for the active sprint
          const storiesRes = await fetch(`http://localhost:8000/api/sprints/${activeSprint.id}/stories`);
          const storiesData = await storiesRes.json();
          setStories(storiesData || []);
        } else {
          setStories([]);
        }
      } catch (err) {
        console.error("Failed to fetch sprint data:", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchSprintData();
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'todo': return '#e2e8f0';
      case 'in_progress': return '#bfdbfe';
      case 'review': return '#fef08a';
      case 'done': return '#bbf7d0';
      default: return '#e2e8f0';
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'todo': return 'To Do';
      case 'in_progress': return 'In Progress';
      case 'review': return 'In Review';
      case 'done': return 'Done';
      default: return status;
    }
  };

  const columns = ['todo', 'in_progress', 'review', 'done'];

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <h2>Active Sprint Board</h2>
      {loading ? (
        <p>Loading stories...</p>
      ) : (
        <div style={{ display: 'flex', gap: '20px', height: 'calc(100% - 60px)' }}>
          {columns.map(col => (
            <div key={col} style={{ flex: 1, backgroundColor: '#f8fafc', borderRadius: '8px', padding: '15px' }}>
              <h3 style={{ marginTop: 0, paddingBottom: '10px', borderBottom: '2px solid #e2e8f0' }}>
                {getStatusLabel(col)}
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '15px' }}>
                {stories.filter(s => s.status === col).map(story => (
                  <div 
                    key={story.id} 
                    style={{ 
                      backgroundColor: 'white', 
                      padding: '12px', 
                      borderRadius: '6px', 
                      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                      borderLeft: `4px solid ${getStatusColor(story.status)}`
                    }}
                  >
                    <div style={{ fontWeight: 'bold', marginBottom: '5px' }}>{story.title}</div>
                    <div style={{ fontSize: '0.85em', color: '#64748b', marginBottom: '10px' }}>
                      {story.description}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8em' }}>
                      <span style={{ backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                        🤖 {story.assigned_to}
                      </span>
                      <span style={{ fontWeight: 'bold' }}>{story.points} pts</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
