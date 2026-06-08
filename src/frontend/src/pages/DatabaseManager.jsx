import React, { useState, useEffect } from 'react';
import { Search, Edit2, Trash2, Check, X } from 'lucide-react';

const DatabaseManager = () => {
  const [courseFilter, setCourseFilter] = useState('All');
  const [existingCourses, setExistingCourses] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');

  useEffect(() => {
    const fetchCourses = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/courses');
        const data = await res.json();
        if (data.status === 'success' && data.courses) {
          setExistingCourses(data.courses);
        }
      } catch(err) { console.error(err); }
    };
    fetchCourses();
  }, []);

  const fetchSlides = async () => {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/slides?course=${courseFilter}`);
      const data = await res.json();
      if (data.status === 'success') {
        setQuestions(data.slides);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSlides();
  }, [courseFilter]);

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to delete this slide?')) return;
    try {
      const res = await fetch(`http://localhost:8000/api/slides/${id}`, { method: 'DELETE' });
      const data = await res.json();
      if (data.status === 'success') {
        setQuestions(q => q.filter(x => x.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleEdit = (q) => {
    setEditingId(q.id);
    setEditText(q.text);
  };

  const handleSaveEdit = async (id) => {
    try {
      const res = await fetch(`http://localhost:8000/api/slides/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: editText })
      });
      const data = await res.json();
      if (data.status === 'success') {
        setQuestions(q => q.map(x => x.id === id ? { ...x, text: editText } : x));
        setEditingId(null);
      } else {
        alert('Error updating slide: ' + data.message);
      }
    } catch (err) {
      console.error(err);
      alert('Network error while updating.');
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-y-auto">
      <div className="h-14 border-b border-gray-200 flex items-center px-6 bg-white sticky top-0 justify-between shadow-sm z-10">
        <h1 className="font-semibold text-gray-800">Database Manager</h1>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-2 text-gray-400" size={16} />
            <input 
              type="text" 
              placeholder="Search text or ID..." 
              className="pl-8 pr-3 py-1 text-sm border border-gray-300 rounded outline-none focus:border-blue-500 w-64"
            />
          </div>
          <div className="flex flex-col relative">
            <input 
              list="db-course-list"
              value={courseFilter}
              onChange={e => setCourseFilter(e.target.value)}
              placeholder="All or enter course..."
              className="border border-gray-300 rounded px-3 py-1 text-sm outline-none focus:border-blue-500 w-48"
            />
            <datalist id="db-course-list">
              <option value="All">All Courses</option>
              {existingCourses.map(c => <option key={c} value={c} />)}
            </datalist>
          </div>
        </div>
      </div>
      
      <div className="p-6 max-w-6xl mx-auto w-full space-y-8">
        <div>
          <h2 className="text-lg font-bold text-gray-800 mb-4">Slides Database</h2>
          <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-xs uppercase tracking-wider text-gray-500">
                  <th className="p-3 font-medium">Global ID</th>
                  <th className="p-3 font-medium">Course</th>
                  <th className="p-3 font-medium w-1/2">OCR Text</th>
                  <th className="p-3 font-medium">Date Added</th>
                  <th className="p-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="text-sm text-gray-700">
                {questions.map((q) => (
                  <tr key={q.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="p-3 font-medium text-blue-600">{q.id}</td>
                    <td className="p-3">
                      <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded text-xs font-medium">
                        {q.course}
                      </span>
                    </td>
                    <td className="p-3 text-gray-600">
                      {editingId === q.id ? (
                        <textarea 
                          className="w-full h-32 p-2 border border-blue-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono text-xs"
                          value={editText}
                          onChange={e => setEditText(e.target.value)}
                        />
                      ) : (
                        <div className="truncate max-w-md">{q.text}</div>
                      )}
                    </td>
                    <td className="p-3 text-gray-500">Just now</td>
                    <td className="p-3 flex justify-end gap-2">
                      {editingId === q.id ? (
                        <>
                          <button onClick={() => handleSaveEdit(q.id)} className="p-1.5 text-green-600 hover:bg-green-50 rounded transition-colors">
                            <Check size={16} />
                          </button>
                          <button onClick={() => setEditingId(null)} className="p-1.5 text-gray-500 hover:bg-gray-100 rounded transition-colors">
                            <X size={16} />
                          </button>
                        </>
                      ) : (
                        <>
                          <button onClick={() => handleEdit(q)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50 transition-colors">
                            <Edit2 size={16} />
                          </button>
                          <button 
                            onClick={() => handleDelete(q.id)}
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded hover:bg-red-50 transition-colors"
                          >
                            <Trash2 size={16} />
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
                {questions.length === 0 && !loading && (
                  <tr>
                    <td colSpan="5" className="p-8 text-center text-gray-500">No questions found.</td>
                  </tr>
                )}
                {loading && (
                  <tr>
                    <td colSpan="5" className="p-8 text-center text-gray-500">Loading database...</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DatabaseManager;
