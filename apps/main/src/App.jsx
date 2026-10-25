import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';

// Views
import MainLanding from './pages/MainLanding';
import StaffLanding from './pages/StaffLanding';
import SmoothScroll from './components/SmoothScroll';

export default function App() {
  // Read the stored preference during the first render rather than rendering
  // light and correcting it from an effect.
  const [isDark, setIsDark] = useState(() => localStorage.getItem('pms-theme') === 'dark');

  // Two separate side effects, neither of which sets state:
  // seed the default on a first visit, and keep the class in sync.
  useEffect(() => {
    if (!localStorage.getItem('pms-theme')) {
      localStorage.setItem('pms-theme', 'light');
    }
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark);
  }, [isDark]);

  const toggleTheme = () => {
    setIsDark(!isDark);
    if (!isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('pms-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('pms-theme', 'light');
    }
  };

  return (
    <>
      <SmoothScroll />
      <Routes>
        <Route path="/" element={<MainLanding isDark={isDark} toggleTheme={toggleTheme} />} />
        <Route path="/staff" element={<StaffLanding />} />
        <Route path="*" element={<MainLanding isDark={isDark} toggleTheme={toggleTheme} />} />
      </Routes>
    </>
  );
}
