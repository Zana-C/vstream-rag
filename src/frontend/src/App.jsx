import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Chat from './pages/Chat';
import VideoProcessor from './pages/VideoProcessor';
import DatabaseManager from './pages/DatabaseManager';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="chat" element={<Chat />} />
          <Route path="processor" element={<VideoProcessor />} />
          <Route path="database" element={<DatabaseManager />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
