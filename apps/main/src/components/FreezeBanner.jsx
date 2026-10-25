/**
 * FreezeBanner — shows a dismissible banner when the system is frozen by admin.
 * Import and render near the top of any portal layout.
 */
import React from 'react';
import { ShieldAlert } from 'lucide-react';
import { useFreezeStatus } from '../hooks/useFreezeStatus';

export default function FreezeBanner() {
  const isFrozen = useFreezeStatus();
  if (!isFrozen) return null;
  return (
    <div className="sticky top-0 z-[200] w-full bg-red-600 text-white text-xs font-black uppercase tracking-widest flex items-center justify-center gap-2 py-2 px-4 shadow-lg animate-pulse-slow">
      <ShieldAlert className="w-4 h-4 shrink-0" />
      SYSTEM FROZEN — All modifications are locked by administrator. View only mode active.
    </div>
  );
}
