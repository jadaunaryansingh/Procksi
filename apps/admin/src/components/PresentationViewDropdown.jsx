import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import { BarChart3, UserCircle, ShieldCheck, ChevronDown, Lock } from 'lucide-react';

// Analysis view selector. Lives in the top nav (left of the global search) and
// syncs the chosen presentation to the `?p=` URL param, which the Analysis page
// reads. Mentor / Panel analysis are placeholders for future work.
// Not exported: nothing outside this file imports it, and a non-component
// export here is what breaks Fast Refresh for the component below.
const VIEWS = [
    { id: 0, label: 'Ideation Round', enabled: true, icon: BarChart3 },
    { id: 1, label: 'Mid Term', enabled: true, icon: BarChart3 },
    { id: 2, label: 'End Term', enabled: true, icon: BarChart3 },
    { id: 'mentor', label: 'Mentor Analysis', enabled: false, icon: UserCircle, note: 'future work' },
    { id: 'panel', label: 'Panel Analysis', enabled: false, icon: ShieldCheck, note: 'future work' },
];

export default function PresentationViewDropdown() {
    const [params, setParams] = useSearchParams();
    const current = Math.min(2, Math.max(0, parseInt(params.get('p') || '0', 10) || 0));
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, []);

    const select = (id) => {
        const next = new URLSearchParams(params);
        next.set('p', String(id));
        setParams(next, { replace: true });
        setOpen(false);
    };

    const active = VIEWS.find((v) => v.id === current) || VIEWS[0];

    return (
        <div className="relative shrink-0" ref={ref}>
            <button onClick={() => setOpen((o) => !o)}
                className="flex items-center gap-2 px-3 h-9 rounded-full bg-slate-100/60 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/70 shadow-inner text-xs font-bold text-slate-600 dark:text-slate-300 hover:border-indigo-400 transition-colors max-w-[13rem]">
                <active.icon className="w-4 h-4 text-indigo-500 shrink-0" />
                <span className="truncate flex-1 text-left">{active.label}</span>
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
                {open && (
                    <motion.ul
                        initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        className="absolute z-50 mt-2 w-56 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl overflow-hidden p-1.5">
                        {VIEWS.map((v) => (
                            <li key={String(v.id)}>
                                <button
                                    disabled={!v.enabled}
                                    onClick={() => v.enabled && select(v.id)}
                                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm font-bold text-left transition-colors
                                        ${!v.enabled ? 'text-slate-300 dark:text-slate-600 cursor-not-allowed'
                                            : v.id === current ? 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-300'
                                                : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                    <v.icon className="w-4 h-4 shrink-0" />
                                    <span className="flex-1 truncate">{v.label}</span>
                                    {!v.enabled && <span className="text-[9px] font-black uppercase tracking-wider flex items-center gap-1 text-slate-300 dark:text-slate-600"><Lock className="w-3 h-3" />{v.note}</span>}
                                </button>
                            </li>
                        ))}
                    </motion.ul>
                )}
            </AnimatePresence>
        </div>
    );
}
