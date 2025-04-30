// src/App.jsx
import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { onAuthStateChanged } from 'firebase/auth';
import { auth } from './firebase';

import AuthPage from './components/AuthPage';
import ExamGenerator from './components/ExamGenerator';
import Navbar from './components/Navbar'; // 👉 new navbar
import LegalContactPage from './components/LegalContactPage'; // 👉 new legal contact page

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, u => {
      setUser(u);
      setChecking(false);
    });
    return unsub;
  }, []);

  if (checking) return null; // loader can be added here

  return (
    <BrowserRouter>
      <Navbar user={user} />
      <div className="app-container">
      <Routes>
        <Route path="/" element={<ExamGenerator user={user} />} />
        <Route path="/auth" element={user ? <Navigate to="/" replace /> : <AuthPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
        <Route path="/LegalContactPage" element={<LegalContactPage />} />
      </Routes>
      </div>
    </BrowserRouter>
  );
}
