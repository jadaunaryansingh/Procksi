import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Loader2, Mail, Phone, GraduationCap, Github, BadgeCheck, X } from 'lucide-react';
import { api } from '../services/api';

/**
 * Name + roll rendered as a clickable chip. Clicking opens a details panel to
 * the right with everything the mentor can know about that student.
 *
 * The profile is fetched lazily on first open and cached per chip: the endpoint
 * joins the students table, so there is no reason to pay for it until a mentor
 * actually asks, and no reason to pay twice.
 */
const Row = ({ icon: Icon, label, value }) => {
  if (!value && value !== 0) return null;
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <Icon size={14} className="text-slate-400 mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</p>
        <p className="text-sm font-medium text-slate-700 dark:text-slate-200 break-words">{value}</p>
      </div>
    </div>
  );
};

const MemberProfileChip = ({ teamId, member }) => {
  const [open, setOpen] = useState(false);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const wrapRef = useRef(null);
  const panelRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  // Close on an outside click or Escape, the way a popover is expected to behave.
  // The member card and the form both set overflow-hidden (they clip the accent
  // bar to the rounded corner), which would slice a panel positioned inside
  // them. Render it in a portal at the document root and place it against the
  // chip's measured rect so no ancestor can clip it.
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const el = wrapRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const W = 288; // w-72
      const GAP = 12;
      // Flip to the left side when there is not enough room on the right.
      const spillsRight = r.right + GAP + W > window.innerWidth - 8;
      const left = spillsRight
        ? Math.max(8, r.left - GAP - W)
        : r.right + GAP;
      const height = panelRef.current?.offsetHeight || 220;
      const top = Math.max(8, Math.min(r.top, window.innerHeight - height - 8));
      setPos({ top, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, profile, loading, error]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (wrapRef.current && wrapRef.current.contains(e.target)) return;
      if (panelRef.current && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (!next || profile || loading) return;
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/teams/${teamId}/members/${member.id}`);
      setProfile(res.data?.data || res.data || {});
    } catch {
      setError('Could not load this profile.');
    } finally {
      setLoading(false);
    }
  };

  const rollText = member.roll || (member.id !== member.name ? member.id : '');

  return (
    <div className="relative inline-block" ref={wrapRef}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        title="View student details"
        className={`text-left rounded-xl border px-3.5 py-2 cursor-pointer transition-all duration-200
          ${open
            ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-500/15 dark:border-emerald-500/60 shadow-sm'
            : 'border-emerald-200 dark:border-emerald-700/50 bg-emerald-50/60 dark:bg-emerald-500/10 hover:border-emerald-400 hover:bg-emerald-100/70 dark:hover:bg-emerald-500/20'}`}
      >
        <span className="block font-bold text-base text-slate-800 dark:text-slate-100 leading-tight">
          {member.name}
        </span>
        {rollText ? (
          <span className="block text-xs font-mono text-slate-500 mt-0.5">{rollText}</span>
        ) : null}
      </button>

      {open && createPortal((
        <div
          ref={panelRef}
          role="dialog"
          style={{ position: 'fixed', top: pos.top, left: pos.left, width: 288 }}
          className="z-[60] rounded-2xl border border-slate-200 dark:border-slate-700
                     bg-white dark:bg-slate-900 shadow-xl p-4"
        >
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="min-w-0">
              <p className="font-bold text-slate-800 dark:text-slate-100 truncate">{member.name}</p>
              {rollText ? <p className="text-xs font-mono text-slate-500">{rollText}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0"
              aria-label="Close"
            >
              <X size={14} />
            </button>
          </div>

          {loading && (
            <div className="flex items-center gap-2 py-4 text-slate-500 text-sm">
              <Loader2 size={14} className="animate-spin" /> Loading details...
            </div>
          )}

          {!loading && error && (
            <p className="py-3 text-sm text-rose-600 dark:text-rose-400">{error}</p>
          )}

          {!loading && !error && profile && (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              <Row icon={BadgeCheck} label="Role" value={profile.role ? String(profile.role).toLowerCase() : ''} />
              <Row
                icon={GraduationCap}
                label="Programme"
                value={[profile.branch, profile.section && `Section ${profile.section}`, profile.year && `Year ${profile.year}`]
                  .filter(Boolean).join(' - ')}
              />
              <Row icon={Mail} label="Email" value={profile.email} />
              <Row icon={Phone} label="Phone" value={profile.phone} />
              <Row icon={Github} label="GitHub" value={profile.github_username} />
              <Row
                icon={BadgeCheck}
                label="Skills"
                value={Array.isArray(profile.skills) ? profile.skills.join(', ') : profile.skills}
              />
              {profile.found === false && (
                <p className="pt-2 text-xs text-slate-400">
                  No student record matched this roll number, so only team data is shown.
                </p>
              )}
            </div>
          )}
        </div>
      ), document.body)}
    </div>
  );
};

export default MemberProfileChip;
