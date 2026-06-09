import React, { useState, useEffect, useRef } from 'react';
import { Upload, Play, Save } from 'lucide-react';

const VideoProcessor = () => {
  const [course, setCourse] = useState('New Course');
  const [existingCourses, setExistingCourses] = useState([]);
  const [slides, setSlides] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [progress, setProgress] = useState(0);
  
  const [sampleRate, setSampleRate] = useState(1.0);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.85);

  const pollingTimeout = useRef(null);

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

    // Check for active job recovery on mount
    const activeJobId = sessionStorage.getItem('active_job_id');
    if (activeJobId) {
      setIsProcessing(true);
      pollStatus(activeJobId);
    }

    // Cleanup timeout on unmount
    return () => {
      if (pollingTimeout.current) {
        clearTimeout(pollingTimeout.current);
      }
    };
  }, []);

  const pollStatus = async (jobId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/jobs/${jobId}/status`);
      const data = await res.json();
      if (data.status === 'completed') {
        setProgress(100);
        setSlides(data.slides);
        setIsProcessing(false);
        sessionStorage.removeItem('active_job_id');
      } else if (data.status === 'error') {
        alert('Error processing video: ' + data.message);
        setIsProcessing(false);
        sessionStorage.removeItem('active_job_id');
      } else {
        setProgress(data.progress || 0);
        pollingTimeout.current = setTimeout(() => pollStatus(jobId), 2000);
      }
    } catch (err) {
      alert('Network error while polling status.');
      setIsProcessing(false);
      sessionStorage.removeItem('active_job_id');
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('sample_rate', sampleRate);
    formData.append('similarity_threshold', similarityThreshold);

    setIsProcessing(true);
    setProgress(0);
    setSlides([]);
    try {
      const res = await fetch('http://localhost:8000/api/video/process', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.status === 'success' && data.job_id) {
        sessionStorage.setItem('active_job_id', data.job_id);
        pollStatus(data.job_id);
      } else {
        alert('Error starting video processing: ' + data.message);
        setIsProcessing(false);
      }
    } catch (err) {
      alert('Network error during upload.');
      setIsProcessing(false);
    }
  };

  const handleSave = async () => {
    if (slides.length === 0) return;
    setIsSaving(true);
    
    // Map slides to the format expected by the backend
    const slidesData = slides.map(s => ({
      extracted_text: s.text,
      image_path: "" 
    }));

    try {
      const res = await fetch('http://localhost:8000/api/slides/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ course, slides: slidesData })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(`Saved ${data.saved_count} slides to Database!`);
        setSlides([]);
      } else {
        alert('Error saving slides: ' + data.message);
      }
    } catch (err) {
      alert('Network error while saving.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="h-14 border-b border-gray-200 flex items-center px-6 bg-white sticky top-0">
        <h1 className="font-semibold text-gray-800">Video Processor & Visual Debug</h1>
      </div>
      
      <div className="p-6 max-w-5xl mx-auto w-full space-y-8">
        
        {/* Settings Section */}
        <div className="grid grid-cols-2 gap-6 bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Sample Rate (Seconds per Frame): {sampleRate}s
            </label>
            <input 
              type="range" min="0.1" max="10.0" step="0.1" 
              value={sampleRate} onChange={e => setSampleRate(parseFloat(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-1">Lower = more frames checked (slower but accurate).</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Similarity Threshold: {Math.round(similarityThreshold * 100)}%
            </label>
            <input 
              type="range" min="0.5" max="1.0" step="0.01" 
              value={similarityThreshold} onChange={e => setSimilarityThreshold(parseFloat(e.target.value))}
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-1">Higher = stricter deduplication.</p>
          </div>
        </div>

        {/* Upload Section */}
        <div className="bg-gray-50 border border-dashed border-gray-300 rounded-xl p-8 text-center flex flex-col items-center justify-center relative overflow-hidden">
          {isProcessing ? (
            <div className="flex flex-col items-center justify-center animate-pulse w-full max-w-md mx-auto">
              <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
              <h3 className="text-lg font-medium text-blue-600 mb-2">Processing Video... {progress}%</h3>
              <div className="w-full bg-gray-200 rounded-full h-2.5 mb-2">
                <div className="bg-blue-600 h-2.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
              </div>
              <p className="text-sm text-gray-500">Extracting frames, applying OCR, and deduplicating. This may take a minute.</p>
            </div>
          ) : (
            <>
              <Upload size={40} className="text-gray-400 mb-4" />
              <h3 className="text-lg font-medium text-gray-900 mb-1">Upload Lecture Video</h3>
              <p className="text-sm text-gray-500 mb-4">Select an MP4 file to extract questions</p>
              <label className="bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded shadow-sm hover:bg-gray-50 font-medium text-sm cursor-pointer inline-block">
                Select File
                <input type="file" accept="video/mp4,video/*" className="hidden" onChange={handleFileUpload} />
              </label>
            </>
          )}
        </div>

        {/* Gallery Section */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium text-gray-800">Extracted Slides (Review & Edit)</h2>
            <div className="flex items-center gap-3">
              <div className="flex flex-col">
                <input 
                  list="course-list"
                  value={course}
                  onChange={e => setCourse(e.target.value)}
                  placeholder="Enter or select course"
                  className="border border-gray-300 rounded px-3 py-1.5 text-sm outline-none focus:border-blue-500"
                />
                <datalist id="course-list">
                  {existingCourses.map(c => <option key={c} value={c} />)}
                </datalist>
              </div>
              <button 
                onClick={handleSave}
                disabled={isSaving || slides.length === 0 || !course.trim()}
                className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-blue-700 flex items-center gap-2 shadow-sm disabled:opacity-50"
              >
                <Save size={16} /> {isSaving ? 'Saving...' : 'Save to Database'}
              </button>
            </div>
          </div>
          
          <div className="grid grid-cols-1 gap-6">
            {slides.map((s) => (
              <div key={s.id} className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm flex flex-col">
                <div className="flex border-b border-gray-200 bg-gray-50 p-3 items-center justify-between">
                  <span className="text-sm font-medium text-gray-600">Slide #{s.id}</span>
                  <button 
                    onClick={() => setSlides(prev => prev.filter(item => item.id !== s.id))}
                    className="text-red-500 hover:text-red-700 text-sm font-medium px-2 py-1"
                  >
                    Delete
                  </button>
                </div>
                
                <div className="flex flex-col md:flex-row">
                  {/* Images */}
                  <div className="flex-1 p-4 border-r border-gray-200 flex flex-col gap-2">
                    <div>
                      <div className="text-xs text-gray-500 mb-1 font-medium">Original Frame</div>
                      <img src={s.original} className="w-full h-auto rounded border border-gray-200" alt="Original" />
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1 font-medium">Warped & Enhanced (OCR Input)</div>
                      <img src={s.warped} className="w-full h-auto rounded border border-gray-200" alt="Warped" />
                    </div>
                  </div>
                  
                  {/* Text Edit */}
                  <div className="flex-1 p-4 flex flex-col">
                    <div className="text-xs text-gray-500 mb-1 font-medium">Extracted OCR Text</div>
                    <textarea 
                      className="w-full h-full min-h-[200px] border border-gray-200 rounded p-3 text-sm font-mono focus:border-blue-500 outline-none resize-none"
                      value={s.text}
                      onChange={e => {
                        const newText = e.target.value;
                        setSlides(prev => prev.map(item => item.id === s.id ? { ...item, text: newText } : item));
                      }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        
      </div>
    </div>
  );
};

export default VideoProcessor;
