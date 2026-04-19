import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Network } from 'lucide-react';

import PipelineBuilder from './pages/PipelineBuilder';
import SprintBoard from './pages/SprintBoard';
import TeamChat from './pages/TeamChat';

function Navigation() {
  const location = useLocation();
  
  const navItems = [
    { path: '/', label: 'Sprint Board', icon: <LayoutDashboard size={18} /> },
    { path: '/chat', label: 'Team Chat', icon: <MessageSquare size={18} /> },
    { path: '/pipeline', label: 'Pipeline Builder', icon: <Network size={18} /> },
  ];

  return (
    <nav style={{
      display: 'flex',
      backgroundColor: '#1e293b',
      color: 'white',
      padding: '0 20px',
      alignItems: 'center',
      height: '50px'
    }}>
      <div style={{ fontWeight: 'bold', marginRight: '30px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        🤖 AI Agent Org
      </div>
      <ul style={{
        display: 'flex',
        listStyle: 'none',
        margin: 0,
        padding: 0,
        gap: '20px'
      }}>
        {navItems.map(item => {
          const isActive = location.pathname === item.path;
          return (
            <li key={item.path}>
              <Link 
                to={item.path} 
                style={{
                  color: isActive ? '#38bdf8' : '#cbd5e1',
                  textDecoration: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '14px 0',
                  borderBottom: isActive ? '2px solid #38bdf8' : '2px solid transparent',
                  fontWeight: isActive ? '600' : 'normal'
                }}
              >
                {item.icon}
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', backgroundColor: '#f8fafc' }}>
        <Navigation />
        <main style={{ flex: 1, overflow: 'hidden' }}>
          <Routes>
            <Route path="/" element={<SprintBoard />} />
            <Route path="/chat" element={<TeamChat />} />
            <Route path="/pipeline" element={<PipelineBuilder />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
