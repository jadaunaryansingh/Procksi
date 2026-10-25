/**
 * PmsChatToggleModal
 *
 * Per-portal PMS-Chat switches for the semester currently selected in the
 * global filter. Opened from the ON/OFF control in the PMS-Chat header.
 *
 * Deliberately states which semester is being edited: the switches are scoped
 * to it, and changing the global semester changes what these control. Without
 * saying so, an admin could reasonably read them as system-wide.
 */
import { AnimatePresence, motion } from 'framer-motion';
import { X, MessageSquare, AlertTriangle, Loader2, Database } from 'lucide-react';
import { PORTALS } from '../hooks/usePmsChatToggles';

export default function PmsChatToggleModal({ open, onClose, toggles }) {
    const { values, loading, saving, error, columnsMissing, semesterLabel, setPortal } = toggles;

    return (
        <AnimatePresence>
            {open && (
                <motion.div
                    initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
                    onClick={onClose}
                >
                    <motion.div
                        initial={{ opacity: 0, scale: 0.97, y: 8 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.97, y: 8 }}
                        transition={{ duration: 0.18 }}
                        onClick={(e) => e.stopPropagation()}
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="pms-chat-toggle-title"
                        className="w-full max-w-md bg-white dark:bg-slate-800 rounded-3xl shadow-2xl
                            border border-slate-200 dark:border-slate-700 overflow-hidden"
                    >
                        <div className="px-6 pt-6 pb-4 flex items-start justify-between gap-4">
                            <div className="flex items-start gap-3">
                                <div className="w-10 h-10 rounded-2xl bg-sky-50 dark:bg-sky-500/10 flex items-center justify-center shrink-0">
                                    <MessageSquare className="w-5 h-5 text-sky-600 dark:text-sky-400" />
                                </div>
                                <div>
                                    <h2 id="pms-chat-toggle-title"
                                        className="text-base font-black text-slate-900 dark:text-white leading-tight">
                                        PMS-Chat availability
                                    </h2>
                                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400 mt-1">
                                        {semesterLabel
                                            ? <>Applies to <span className="font-bold text-slate-700 dark:text-slate-300">{semesterLabel}</span></>
                                            : 'Applies to the selected semester'}
                                    </p>
                                </div>
                            </div>
                            <button onClick={onClose} aria-label="Close"
                                className="p-1.5 -m-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 rounded-lg transition-colors shrink-0">
                                <X className="w-4 h-4" />
                            </button>
                        </div>

                        {columnsMissing && (
                            <div className="mx-6 mb-4 p-3 rounded-xl bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 flex gap-2.5">
                                <Database className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                                <p className="text-[11px] font-medium text-amber-800 dark:text-amber-200 leading-relaxed">
                                    These switches are not stored yet. Apply
                                    <code className="mx-1 px-1 py-0.5 bg-amber-100 dark:bg-amber-500/20 rounded font-mono">
                                        202608240001_pms_chat_toggles.sql
                                    </code>
                                    to your Supabase project, then reopen this window.
                                </p>
                            </div>
                        )}

                        {error && (
                            <div className="mx-6 mb-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 flex gap-2.5">
                                <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
                                <p className="text-[11px] font-medium text-rose-800 dark:text-rose-200">{error}</p>
                            </div>
                        )}

                        <div className="px-6 pb-2 space-y-1">
                            {loading ? (
                                <div className="py-10 flex items-center justify-center text-slate-400">
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                </div>
                            ) : PORTALS.map((portal) => {
                                const on = values[portal.key];
                                const busy = saving === portal.key;
                                const disabled = columnsMissing || busy;
                                return (
                                    <div key={portal.key}
                                        className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700/50 last:border-0">
                                        <div>
                                            <p className="text-sm font-bold text-slate-800 dark:text-slate-100">{portal.label}</p>
                                            <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500">
                                                {on ? 'Visible to users of this portal' : 'Hidden and unreachable'}
                                            </p>
                                        </div>
                                        <button
                                            type="button"
                                            role="switch"
                                            aria-checked={on}
                                            aria-label={`PMS-Chat for ${portal.label}`}
                                            disabled={disabled}
                                            onClick={() => setPortal(portal.key, !on)}
                                            className={`relative w-12 h-7 rounded-full transition-colors shrink-0
                                                focus:outline-none focus:ring-2 focus:ring-sky-500/60 focus:ring-offset-2
                                                dark:focus:ring-offset-slate-800
                                                ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
                                                ${on ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}`}
                                        >
                                            <motion.span
                                                layout
                                                transition={{ type: 'spring', stiffness: 500, damping: 34 }}
                                                className="absolute top-1 w-5 h-5 rounded-full bg-white shadow flex items-center justify-center"
                                                style={{ left: on ? 26 : 4 }}
                                            >
                                                {busy && <Loader2 className="w-3 h-3 animate-spin text-slate-400" />}
                                            </motion.span>
                                        </button>
                                    </div>
                                );
                            })}
                        </div>

                        <div className="px-6 py-4 bg-slate-50 dark:bg-slate-900/40 border-t border-slate-100 dark:border-slate-700/50">
                            <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 leading-relaxed">
                                Turning a portal off hides PMS-Chat from its sidebar and redirects the page.
                                Existing conversations are kept, not deleted.
                            </p>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}
