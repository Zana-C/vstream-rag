import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Send, Settings, MessageSquare, Save, X, Trash2 } from 'lucide-react';

const Chat = () => {
  const location = useLocation();
  const navigate = useNavigate();
  
  const [messages, setMessages] = useState([
    { id: 'welcome', role: 'assistant', content: 'Hello! I am VisionStream AI. How can I help you today?' }
  ]);
  const [input, setInput] = useState('');
  const [course, setCourse] = useState('All');
  const [existingCourses, setExistingCourses] = useState([]);
  
  const [sessionId, setSessionId] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef(null);

  // Settings
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState({ provider: 'ollama', model_name: 'qwen2.5:14b', api_key: '', base_url: 'http://127.0.0.1:11434' });
  const [savingSettings, setSavingSettings] = useState(false);

  // Parse session from URL
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const urlSessionId = params.get('session_id');
    
    if (urlSessionId && urlSessionId !== sessionId) {
      loadSession(urlSessionId);
    } else if (!urlSessionId && sessionId) {
      // User clicked New Chat
      setSessionId(null);
      setMessages([{ id: 'welcome', role: 'assistant', content: 'Hello! I am VisionStream AI. How can I help you today?' }]);
    }
  }, [location.search]);

  // Load Initial Data
  useEffect(() => {
    const fetchInitData = async () => {
      try {
        const [cRes, setRes] = await Promise.all([
          fetch('http://127.0.0.1:8000/api/courses'),
          fetch('http://127.0.0.1:8000/api/settings')
        ]);
        const cData = await cRes.json();
        if (cData.status === 'success' && cData.courses) setExistingCourses(cData.courses);

        const setData = await setRes.json();
        setSettings(setData);

      } catch(err) { console.error(err); }
    };
    fetchInitData();

    // Listen for session deletions from the Sidebar
    const handleSessionDeleted = () => {
      setSessionId(null);
      setMessages([{ id: 'welcome', role: 'assistant', content: 'Select a chat session or create a new one.' }]);
    };
    window.addEventListener('sessionDeleted', handleSessionDeleted);
    return () => window.removeEventListener('sessionDeleted', handleSessionDeleted);
  }, []);

  const loadSession = async (id) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/sessions/${id}/messages`);
      const msgs = await res.json();
      if (msgs.length > 0) {
        setMessages(msgs);
      } else {
        setMessages([{ id: 'welcome', role: 'assistant', content: 'Hello! I am VisionStream AI. How can I help you today?' }]);
      }
      setSessionId(id);
    } catch(err) { console.error(err); }
  };

  const createSession = async () => {
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/sessions?title=New+Chat&course=${encodeURIComponent(course)}`,
        { method: 'POST' }
      );
      const session = await res.json();
      setSessionId(session.id);
      setMessages([{ id: 'welcome', role: 'assistant', content: 'Hello! I am VisionStream AI. How can I help you today?' }]);
      
      // Update URL to point to this new session without unmounting
      navigate(`/chat?session_id=${session.id}`, { replace: true });
      window.dispatchEvent(new Event('refreshSessions'));
    } catch (err) {
      console.error('Failed to create session:', err);
    }
  };

  // Connect WebSocket
  useEffect(() => {
    if (!sessionId) return;
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`ws://127.0.0.1:8000/ws/chat/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => setIsConnected(false);
    ws.onerror = (err) => console.error('WebSocket error:', err);

    ws.onmessage = (event) => {
      const data = event.data;
      if (data === '[DONE]') {
        loadSession(sessionId);
        window.dispatchEvent(new Event('refreshSessions'));
        return;
      }

      setMessages(prev => {
        const newMsgs = [...prev];
        const last = newMsgs[newMsgs.length - 1];
        if (last && last.role === 'assistant' && last.id === 'streaming') {
          return [...newMsgs.slice(0, -1), { role: 'assistant', id: 'streaming', content: last.content + data }];
        } else {
          return [...newMsgs, { role: 'assistant', id: 'streaming', content: data }];
        }
      });
    };

    return () => ws.close();
  }, [sessionId]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      // If we don't have a session yet, create one FIRST, then send
      if (!sessionId) {
        await createSession();
        // createSession updates URL and state, but we need to wait for WS to connect.
        // It's safer to just require them to start typing after a session starts,
        // but let's handle auto-create if needed.
        // For now, if no session, just create it and don't send immediately.
      }
      return;
    }

    setMessages(prev => {
      const safeMsgs = prev.map(m => {
        if(m.id === 'streaming') return { ...m, id: 'temp' };
        return m;
      });
      return [...safeMsgs, { id: 'temp-user', role: 'user', content: input }];
    });
    
    wsRef.current.send(input);
    setInput('');
  };

  const handleDeleteMessage = async (msgId) => {
    if (msgId === 'welcome' || msgId === 'streaming' || typeof msgId === 'string' && msgId.startsWith('temp')) return;
    if (!window.confirm('Delete this message?')) return;
    
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/messages/${msgId}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.status === 'success') {
        setMessages(msgs => msgs.filter(m => m.id !== msgId));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveSettings = async () => {
    setSavingSettings(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert('Settings saved successfully!');
        setShowSettings(false);
      } else {
        alert('Error: ' + data.message);
      }
    } catch(err) { alert('Error saving settings.'); }
    setSavingSettings(false);
  };

  return (
    <div className="flex flex-col relative h-full bg-white">
      
      {/* Header */}
      <div className="h-14 border-b border-gray-200 flex items-center px-6 justify-between bg-white z-10 sticky top-0 shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="font-semibold text-gray-800">
            {sessionId ? `Chat Session` : 'New Chat'}
          </h1>
          {sessionId && (
            <div
              className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-400'}`}
              title={isConnected ? 'Connected' : 'Disconnected'}
            />
          )}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex flex-col relative">
            <input
              list="chat-course-list"
              value={course}
              onChange={e => setCourse(e.target.value)}
              placeholder="All or enter course..."
              className="border border-gray-300 rounded px-3 py-1 text-sm outline-none focus:border-blue-500 w-40 bg-gray-50"
            />
            <datalist id="chat-course-list">
              <option value="All">All Courses</option>
              {existingCourses.map(c => <option key={c} value={c} />)}
            </datalist>
          </div>
          <button 
            onClick={() => setShowSettings(true)}
            className="p-1.5 text-gray-500 hover:text-gray-800 rounded-full hover:bg-gray-100 transition"
          >
            <Settings size={20} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {!sessionId ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 pb-20">
            <MessageSquare size={48} className="mb-4 text-blue-200" />
            <p className="text-lg font-medium text-gray-600 mb-2">Welcome to VisionStream Chat</p>
            <p className="text-sm max-w-md text-center">Type a message below to start a new chat, or select a previous chat from the sidebar on the left.</p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto w-full space-y-6 pb-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-4 group ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                
                {m.role === 'user' && typeof m.id === 'number' && (
                  <button onClick={() => handleDeleteMessage(m.id)} className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 transition self-center bg-white border border-gray-100 shadow-sm rounded-full">
                    <Trash2 size={14} />
                  </button>
                )}

                {m.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 flex-shrink-0 text-xs font-bold shadow-sm border border-blue-200 mt-1">
                    AI
                  </div>
                )}
                
                <div className={`px-5 py-3.5 rounded-2xl max-w-[80%] whitespace-pre-wrap text-sm shadow-sm ${m.role === 'user' ? 'bg-blue-50 text-gray-800 border border-blue-100 rounded-tr-sm' : 'text-gray-800 bg-white border border-gray-200 rounded-tl-sm'}`}>
                  {m.content}
                </div>

                {m.role === 'assistant' && typeof m.id === 'number' && (
                  <button onClick={() => handleDeleteMessage(m.id)} className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-red-500 transition self-center bg-white border border-gray-100 shadow-sm rounded-full">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 bg-white border-t border-gray-100 shrink-0">
        <form onSubmit={handleSend} className="relative flex items-center max-w-4xl mx-auto w-full">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={sessionId && !isConnected ? "Connecting..." : "Ask about the slides..."}
            disabled={sessionId && !isConnected}
            className="w-full bg-gray-50 border border-gray-200 rounded-full px-6 py-3.5 pr-14 outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all disabled:opacity-60 text-sm shadow-inner"
          />
          <button
            type="submit"
            disabled={!input.trim()}
            className="absolute right-2 w-10 h-10 flex items-center justify-center bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors disabled:opacity-50 shadow-md hover:shadow-lg"
          >
            <Send size={18} className="ml-1" />
          </button>
        </form>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 border border-gray-100">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-gray-800">LLM Settings</h2>
              <button onClick={() => setShowSettings(false)} className="text-gray-400 hover:text-gray-700 bg-gray-50 hover:bg-gray-100 rounded-full p-1.5 transition">
                <X size={20} />
              </button>
            </div>
            
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Provider</label>
                <select 
                  value={settings.provider} 
                  onChange={e => setSettings({...settings, provider: e.target.value})}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 text-sm bg-gray-50"
                >
                  <option value="ollama">Ollama (Local)</option>
                  <option value="openai">OpenAI</option>
                  <option value="gemini">Google Gemini</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Model Name</label>
                <input 
                  type="text" 
                  value={settings.model_name}
                  onChange={e => setSettings({...settings, model_name: e.target.value})}
                  placeholder={settings.provider === 'openai' ? 'gpt-4o' : settings.provider === 'gemini' ? 'gemini-1.5-pro' : 'qwen2.5:14b'}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 text-sm bg-gray-50"
                />
              </div>

              {settings.provider === 'ollama' && (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">Ollama Server URL</label>
                  <input 
                    type="text" 
                    value={settings.base_url || 'http://127.0.0.1:11434'}
                    onChange={e => setSettings({...settings, base_url: e.target.value})}
                    placeholder="http://127.0.0.1:11434"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 text-sm bg-gray-50"
                  />
                </div>
              )}

              {settings.provider !== 'ollama' && (
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-1.5">API Key</label>
                  <input 
                    type="password" 
                    value={settings.api_key}
                    onChange={e => setSettings({...settings, api_key: e.target.value})}
                    placeholder="Enter API Key"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2.5 outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 text-sm bg-gray-50"
                  />
                </div>
              )}
            </div>

            <div className="mt-8 flex justify-end gap-3 pt-4 border-t border-gray-100">
              <button onClick={() => setShowSettings(false)} className="px-5 py-2.5 text-gray-600 hover:bg-gray-100 font-medium rounded-lg transition text-sm">
                Cancel
              </button>
              <button onClick={handleSaveSettings} disabled={savingSettings} className="px-5 py-2.5 bg-blue-600 text-white rounded-lg shadow hover:bg-blue-700 transition flex items-center gap-2 text-sm font-medium disabled:opacity-70">
                <Save size={16} /> {savingSettings ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Chat;
