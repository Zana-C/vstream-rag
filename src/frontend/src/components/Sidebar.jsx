import React, { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { MessageSquare, Video, Database, Trash2 } from 'lucide-react';

const Sidebar = () => {
  const [sessions, setSessions] = useState([]);
  const navigate = useNavigate();
  const location = useLocation();

  const fetchSessions = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/sessions');
      const data = await res.json();
      setSessions(data);
    } catch(err) { console.error(err); }
  };

  useEffect(() => {
    fetchSessions();

    const handleRefresh = () => fetchSessions();
    window.addEventListener('refreshSessions', handleRefresh);
    return () => window.removeEventListener('refreshSessions', handleRefresh);
  }, []);

  const handleOpenSession = (id) => {
    navigate(`/chat?session_id=${id}`);
  };

  const handleDeleteSession = async (e, id) => {
    e.stopPropagation();
    if (!window.confirm('Delete this chat session completely?')) return;
    try {
      const res = await fetch(`http://localhost:8000/api/sessions/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.status === 'success') {
        setSessions(s => s.filter(x => x.id !== id));
        // If they are currently viewing this session, navigate to new chat
        const currentParams = new URLSearchParams(window.location.search);
        if (currentParams.get('session_id') === id) {
          navigate('/chat');
          window.dispatchEvent(new Event('sessionDeleted'));
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Get active session ID from URL to highlight it
  const currentParams = new URLSearchParams(location.search);
  const activeSessionId = currentParams.get('session_id');

  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col h-full shrink-0">
      <div className="p-4 flex items-center gap-2 font-bold text-lg text-gray-800">
        <div className="w-8 h-8 rounded bg-blue-600 flex items-center justify-center text-white shadow-sm">V</div>
        VisionStream AI
      </div>
      
      <nav className="px-3 py-4 space-y-1">
        <NavLink 
          to="/chat" 
          end
          className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm ${isActive && !activeSessionId ? 'bg-gray-200 text-gray-900 font-semibold' : 'text-gray-700 hover:bg-gray-100 font-medium'}`}
        >
          <MessageSquare size={18} />
          New Chat
        </NavLink>
        
        <NavLink 
          to="/processor" 
          className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm ${isActive ? 'bg-gray-200 text-gray-900 font-semibold' : 'text-gray-700 hover:bg-gray-100 font-medium'}`}
        >
          <Video size={18} />
          Video Processor
        </NavLink>
        
        <NavLink 
          to="/database" 
          className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm ${isActive ? 'bg-gray-200 text-gray-900 font-semibold' : 'text-gray-700 hover:bg-gray-100 font-medium'}`}
        >
          <Database size={18} />
          Database Manager
        </NavLink>
      </nav>
      
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        <div className="text-xs text-gray-400 font-bold uppercase tracking-wider mb-2 mt-2 px-3">Recent Chats</div>
        <div className="space-y-1">
          {sessions.map(s => (
            <div 
              key={s.id}
              onClick={() => handleOpenSession(s.id)}
              className={`flex items-center justify-between group cursor-pointer text-sm py-2 px-3 rounded-lg transition-colors ${activeSessionId === s.id ? 'bg-blue-100 text-blue-900 font-medium shadow-sm ring-1 ring-blue-200' : 'text-gray-600 hover:bg-gray-100'}`}
            >
              <div className="truncate pr-2">{s.title || 'New Chat'}</div>
              <button 
                onClick={(e) => handleDeleteSession(e, s.id)}
                className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-red-500 hover:bg-white rounded p-1 transition-all shrink-0"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="text-xs text-gray-400 px-3 py-2">No previous chats.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
