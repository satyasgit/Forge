import { useEffect, useState } from 'react';

interface ChatMessage {
  id: string;
  sender: string;
  channel: string;
  message_type: string;
  content: string;
  timestamp: string;
}

export default function TeamChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [channel, setChannel] = useState('all');

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8000/api/ws/status');
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // data could be a list of existing messages or a single new message
        if (Array.isArray(data)) {
            // Unlikely from standard FastAPI endpoint but handle just in case
        } else if (data.message_type) {
          // This looks like an AgentMessage
          setMessages(prev => [...prev, {
            id: data.id || Date.now().toString(),
            sender: data.sender || 'system',
            channel: data.channel || 'general',
            message_type: data.message_type || 'status',
            content: data.content || '',
            timestamp: data.timestamp || new Date().toISOString()
          }]);
        }
      } catch (err) {
        console.error("Failed to parse websocket message", err);
      }
    };
    
    // Add some initial mock history to make it look active if no messages come in
    setMessages([
      { id: '1', sender: 'ceo', channel: 'general', message_type: 'broadcast', content: 'Welcome to the Live Sprint! Connecting to MessageBus...', timestamp: new Date(Date.now() - 60000).toISOString() },
    ]);

    return () => {
      ws.close();
    };
  }, []);

  const filteredMessages = channel === 'all' 
    ? messages 
    : messages.filter(m => m.channel === channel || m.channel === 'general');

  const getSenderColor = (sender: string) => {
    const colors: Record<string, string> = {
      ceo: '#7c3aed',
      vp_eng: '#2563eb',
      pm: '#059669',
      backend: '#dc2626',
      frontend: '#d97706',
      security: '#4f46e5',
      qa: '#0891b2'
    };
    return colors[sender] || '#475569';
  };

  const getMessageTypeIcon = (type: string) => {
    switch(type) {
      case 'question': return '❓';
      case 'answer': return '💡';
      case 'blocker': return '🛑';
      case 'broadcast': return '📢';
      default: return '💬';
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sidebar for channels */}
      <div style={{ width: '200px', backgroundColor: '#f1f5f9', borderRight: '1px solid #e2e8f0', padding: '20px' }}>
        <h3 style={{ marginTop: 0 }}>Channels</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {['all', 'general', 'sprint-12', 'code-review'].map(c => (
            <li 
              key={c}
              onClick={() => setChannel(c)}
              style={{ 
                padding: '8px 12px', 
                cursor: 'pointer',
                borderRadius: '4px',
                backgroundColor: channel === c ? '#e2e8f0' : 'transparent',
                fontWeight: channel === c ? 'bold' : 'normal'
              }}
            >
              # {c}
            </li>
          ))}
        </ul>
      </div>

      {/* Main chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'white' }}>
        <div style={{ padding: '15px 20px', borderBottom: '1px solid #e2e8f0' }}>
          <h2 style={{ margin: 0 }}># {channel}</h2>
        </div>
        
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '15px' }}>
          {filteredMessages.map(msg => (
            <div key={msg.id} style={{ display: 'flex', gap: '12px' }}>
              <div style={{ 
                width: '40px', height: '40px', borderRadius: '50%', 
                backgroundColor: getSenderColor(msg.sender), 
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', fontWeight: 'bold', fontSize: '1.2em'
              }}>
                {msg.sender.substring(0, 1).toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 'bold' }}>{msg.sender}</span>
                  <span style={{ fontSize: '0.8em', color: '#94a3b8' }}>
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                  {msg.channel !== channel && channel === 'all' && (
                    <span style={{ fontSize: '0.75em', backgroundColor: '#f1f5f9', padding: '2px 6px', borderRadius: '4px' }}>
                      in #{msg.channel}
                    </span>
                  )}
                </div>
                <div style={{ backgroundColor: '#f8fafc', padding: '10px 15px', borderRadius: '0 8px 8px 8px', border: '1px solid #e2e8f0', display: 'inline-block', maxWidth: '80%' }}>
                  <span style={{ marginRight: '8px' }}>{getMessageTypeIcon(msg.message_type)}</span>
                  {msg.content}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
