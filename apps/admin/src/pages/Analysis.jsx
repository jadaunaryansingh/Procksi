import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'react-router-dom';
import {
    BarChart3, TrendingUp, Trophy, Users, ShieldCheck, UserCircle,
    UserMinus, AlertTriangle, Loader2, RefreshCw, Filter,
    Github, MessageSquareWarning, Grid3x3, MoreVertical, Maximize2, X, ChevronDown, Check, Download,
} from 'lucide-react';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { aggregatePresentation } from '../lib/presentationAnalysis';


/* ---------- small chart primitives (single-hue magnitude = indigo) ---------- */

function Card({ title, subtitle, icon: Icon, children, className = '', badge, action }) {
    return (
        <div className={`bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl border border-slate-200/50 dark:border-slate-700/50 shadow-sm p-6 ${className}`}>
            <div className="flex items-center gap-2 mb-5">
                {Icon && <Icon className="w-4 h-4 text-indigo-500 shrink-0" />}
                <div className="min-w-0 flex-1">
                    <h3 className="text-sm font-black text-slate-800 dark:text-white tracking-tight truncate">{title}</h3>
                    {subtitle && <p className="text-[11px] text-slate-400 font-medium truncate">{subtitle}</p>}
                </div>
                {badge != null && <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500 shrink-0">{badge}</span>}
                {action}
            </div>
            {children}
        </div>
    );
}

// --- CSV export helpers -------------------------------------------------
// Build a CSV string from an array of rows (each row an array of cells) and
// trigger a browser download. Values with commas/quotes/newlines are escaped.
function downloadCsv(filename, rows) {
    const esc = (v) => {
        const s = v == null ? '' : String(v);
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = rows.map((r) => r.map(esc).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' }); // BOM → Excel opens UTF-8 cleanly
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Small icon button placed in a card header to export that card's data as CSV.
function DownloadBtn({ onClick, title = 'Download CSV' }) {
    return (
        <button onClick={onClick} title={title}
            className="no-print p-1.5 rounded-lg text-slate-400 hover:text-indigo-500 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors shrink-0">
            <Download className="w-4 h-4" />
        </button>
    );
}

function StatTile({ label, value, sub, icon: Icon, danger, tone }) {
    const green = tone === 'emerald';
    return (
        <div className={`backdrop-blur-xl rounded-2xl border shadow-sm p-4 flex flex-col ${green
            ? 'bg-emerald-50/80 dark:bg-emerald-500/10 border-emerald-200/60 dark:border-emerald-500/30'
            : 'bg-white/90 dark:bg-slate-800/90 border-slate-200/50 dark:border-slate-700/50'}`}>
            <div className="flex items-center justify-between mb-1">
                <span className={`text-[10px] font-black uppercase tracking-widest ${green ? 'text-emerald-600/80 dark:text-emerald-400/80' : 'text-slate-400'}`}>{label}</span>
                {Icon && <Icon className={`w-4 h-4 ${danger ? 'text-rose-500' : green ? 'text-emerald-500' : 'text-indigo-400'}`} />}
            </div>
            <span className={`text-2xl font-black tracking-tight ${danger ? 'text-rose-600 dark:text-rose-400' : green ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-800 dark:text-white'}`}>{value}</span>
            {sub && <span className={`text-[11px] font-semibold mt-0.5 ${green ? 'text-emerald-600/70 dark:text-emerald-400/70' : 'text-slate-400'}`}>{sub}</span>}
        </div>
    );
}

function BarRow({ label, value, max, suffix = '', barClass = 'bg-indigo-500', valueText, onClick, active = false }) {
    const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
    return (
        <div className={`group ${onClick ? 'cursor-pointer' : ''}`} title={`${label}: ${value}${suffix}`} onClick={onClick}>
            <div className="flex items-center justify-between mb-1">
                <span className={`text-xs font-bold truncate pr-2 ${active ? 'text-indigo-600 dark:text-indigo-300' : 'text-slate-600 dark:text-slate-300'}`}>{label}</span>
                <span className="text-xs font-black text-slate-500 dark:text-slate-400 tabular-nums shrink-0">{valueText ?? `${value}${suffix}`}</span>
            </div>
            <div className={`h-2.5 rounded-full bg-slate-100 dark:bg-slate-700/40 overflow-hidden ${active ? 'ring-2 ring-indigo-400/60' : ''}`}>
                <div className={`h-full rounded-full ${barClass} transition-all group-hover:opacity-80`} style={{ width: `${pct}%` }} />
            </div>
        </div>
    );
}

function Histogram({ data, valueKey = 'count', labelKey = 'label' }) {
    const max = Math.max(1, ...data.map((d) => d[valueKey]));
    return (
        <div className="flex items-end justify-between gap-1.5 h-40 pt-4">
            {data.map((d, i) => (
                <div key={i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${d[labelKey]}: ${d[valueKey]}`}>
                    <span className="text-[10px] font-black text-slate-500 dark:text-slate-400 mb-1 tabular-nums">{d[valueKey]}</span>
                    <div className="w-full rounded-t-md bg-indigo-500 hover:bg-indigo-400 transition-all"
                        style={{ height: `${Math.max(3, (d[valueKey] / max) * 100)}%` }} />
                    <span className="text-[9px] font-semibold text-slate-400 mt-1.5 text-center leading-tight">{d[labelKey]}</span>
                </div>
            ))}
        </div>
    );
}

// Pick a "nice" axis ceiling + step giving ~4-6 rounded gridlines.
function niceScale(max) {
    if (!max || max <= 0) return { niceMax: 5, step: 1 };
    const rough = max / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const norm = rough / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
    return { niceMax: Math.ceil(max / step) * step, step };
}

// Axis + gridlines bar chart with gradient bars (used by Marks Distribution).
// `onBarClick(i)` + `activeIndex` make bars a drill-down control.
function AxisBarChart({ data, unit = 'students', onBarClick, activeIndex = null }) {
    const [hover, setHover] = useState(null);
    const max = Math.max(0, ...data.map((d) => d.count));
    const { niceMax, step } = niceScale(max);
    const ticks = [];
    for (let v = niceMax; v >= 0; v -= step) ticks.push(v);
    return (
        <div className="flex gap-2 pt-2">
            {/* Y axis */}
            <div className="relative h-56 w-8 shrink-0">
                {ticks.map((t) => (
                    <span key={t} className="absolute right-0 -translate-y-1/2 text-[11px] font-semibold text-slate-400 tabular-nums"
                        style={{ top: `${(1 - t / niceMax) * 100}%` }}>{t}</span>
                ))}
            </div>
            {/* Plot + x labels */}
            <div className="flex-1 min-w-0">
                <div className="relative h-56">
                    {ticks.map((t) => (
                        <div key={t} className="absolute left-0 right-0 border-t border-slate-100 dark:border-slate-700/40"
                            style={{ top: `${(1 - t / niceMax) * 100}%` }} />
                    ))}
                    <div className="absolute inset-0 flex items-end justify-around gap-3">
                        {data.map((d, i) => {
                            const h = niceMax ? Math.max(d.count > 0 ? 2 : 0, (d.count / niceMax) * 100) : 0;
                            return (
                                <div key={i} className="relative flex-1 flex items-end justify-center h-full cursor-pointer"
                                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                                    onClick={() => onBarClick && d.count > 0 && onBarClick(i)}>
                                    <div className={`w-full max-w-[64px] rounded-t-lg bg-gradient-to-b from-indigo-500 to-indigo-300 dark:from-indigo-400 dark:to-indigo-600 transition-all ${hover === i || activeIndex === i ? 'from-indigo-600 to-indigo-400' : ''} ${activeIndex === i ? 'ring-2 ring-indigo-400 ring-offset-1 dark:ring-offset-slate-800' : ''}`}
                                        style={{ height: `${h}%` }} />
                                    {hover === i && (
                                        <div className="absolute left-1/2 -translate-x-1/2 z-20 px-3 py-1.5 rounded-lg bg-slate-800 text-white shadow-xl whitespace-nowrap pointer-events-none text-center"
                                            style={{ bottom: `calc(${h}% + 8px)` }}>
                                            <p className="text-xs font-black leading-tight">{d.label}</p>
                                            <p className="text-[10px] text-slate-300">{d.count} {unit}</p>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
                <div className="flex justify-around gap-3 pt-2">
                    {data.map((d, i) => (
                        <span key={i} className="flex-1 text-center text-xs font-semibold text-slate-500 dark:text-slate-400">{d.label}</span>
                    ))}
                </div>
            </div>
        </div>
    );
}

// Reusable drill-down list revealed when a bar/row is clicked. `heading` names
// the selection; `sub` is the count line; `items` = [{ name, meta, score }],
// rendered highest score first.
function DrillPanel({ open, heading, sub, items = [], onClose }) {
    return (
        <AnimatePresence>
            {open && (
                <motion.div
                    initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }} className="overflow-hidden">
                    <div className="mt-4 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/40">
                        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 dark:border-slate-700">
                            <p className="text-xs font-black text-slate-700 dark:text-slate-200 truncate pr-2">
                                {heading} · <span className="text-indigo-600 dark:text-indigo-300">{sub}</span>
                            </p>
                            <button onClick={onClose} title="Close"
                                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 dark:hover:bg-slate-700/60 transition-colors shrink-0">
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                        {items.length ? (
                            <div className="max-h-[240px] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-700/50">
                                {[...items].sort((a, b) => b.score - a.score).map((it, i) => (
                                    <div key={i} className="flex items-center gap-3 px-4 py-2">
                                        <span className="w-6 shrink-0 text-[11px] font-bold text-slate-400 tabular-nums">{i + 1}</span>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{it.name}</p>
                                            {it.meta && it.meta !== '—' && <p className="text-[10px] text-slate-400 truncate">{it.meta}</p>}
                                        </div>
                                        <span className="shrink-0 text-xs font-black text-slate-600 dark:text-slate-300 tabular-nums">{it.score}</span>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="px-4 py-4 text-[11px] font-semibold text-slate-400 text-center">No detail available.</p>
                        )}
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}

function EmptyState({ message, icon: Icon = BarChart3 }) {
    return (
        <div className="flex flex-col items-center justify-center text-center py-10 px-4">
            <Icon className="w-8 h-8 text-slate-300 dark:text-slate-600 mb-2" />
            <p className="text-xs font-semibold text-slate-400 dark:text-slate-500 max-w-xs">{message}</p>
        </div>
    );
}

// SVG radar / spider chart. `series` = [{ label, color, values:number[] }],
// `axes` = string[] (one per value). Scale auto-fits the data to rounded ticks.
// `legend`: 'top' (default) or 'right'. `animate`: pop-in entrance for the plot.
function RadarChart({ axes, series, legend = 'top', animate = false, toggleSeries = false }) {
    // When toggleSeries is on, exactly ONE series is drawn at a time (the one
    // picked from the legend); nothing shows until the user picks one. Otherwise
    // all series show.
    const [visible, setVisible] = useState(null);
    const [hovered, setHovered] = useState(null);    // { si, i } of the vertex under the cursor
    const [menuOpen, setMenuOpen] = useState(false);
    const menuRef = useRef(null);
    const shownAt = (i) => !toggleSeries || visible === i;
    const toggle = (i) => setVisible((prev) => (prev === i ? null : i));
    useEffect(() => {
        const onDoc = (e) => { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false); };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, []);
    const W = 380, H = 320, cx = W / 2, cy = 152, R = 92, labelR = R + 24;
    const N = axes.length;
    const vals = series.flatMap((s) => s.values);
    const dmin = Math.min(...vals), dmax = Math.max(...vals);
    const min = Math.max(0, Math.floor((dmin - 4) / 5) * 5);
    const max = Math.ceil(dmax / 5) * 5;
    const levels = Math.min(4, Math.max(2, Math.round((max - min) / 5)));
    const ang = (i) => (-90 + i * (360 / N)) * Math.PI / 180;
    const at = (r, i) => [cx + r * Math.cos(ang(i)), cy + r * Math.sin(ang(i))];
    const rFor = (v) => ((v - min) / (max - min || 1)) * R;
    const polyPts = (radii) => radii.map((r, i) => at(r, i).join(',')).join(' ');

    const legendList = series.map((s, si) => {
        const shown = shownAt(si);
        return (
            <button key={s.label} type="button" onClick={toggleSeries ? () => toggle(si) : undefined}
                className={`flex items-center gap-2 text-sm font-bold text-slate-500 dark:text-slate-300 transition-opacity ${toggleSeries ? 'cursor-pointer' : 'cursor-default'} ${toggleSeries && !shown ? 'opacity-45' : 'opacity-100'}`}>
                <span className="w-7 h-4 rounded-md border-2" style={{ borderColor: s.color, background: shown ? `${s.color}22` : 'transparent' }} />
                {s.label}
            </button>
        );
    });

    const svg = (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full overflow-visible">
            {Array.from({ length: levels }, (_, l) => (
                <polygon key={l} points={polyPts(axes.map(() => (R * (l + 1)) / levels))}
                    className="fill-none stroke-slate-200 dark:stroke-slate-700/50" strokeWidth="1" />
            ))}
            {axes.map((_, i) => {
                const [x, y] = at(R, i);
                return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="stroke-slate-200 dark:stroke-slate-700/50" strokeWidth="1" />;
            })}
            {Array.from({ length: levels }, (_, l) => {
                const val = Math.round(min + ((max - min) * (l + 1)) / levels);
                return <text key={l} x={cx + 5} y={cy - (R * (l + 1)) / levels + 3} className="fill-slate-400 text-[10px] font-semibold">{val}</text>;
            })}
            {series.map((s, si) => {
                if (!shownAt(si)) return null;
                const radii = s.values.map((v) => rFor(v));
                const G = animate || toggleSeries ? motion.g : 'g';
                const gProps = (animate || toggleSeries)
                    ? { initial: { opacity: 0, scale: 0.2 }, animate: { opacity: 1, scale: 1 }, transition: { type: 'spring', duration: 0.5 }, style: { transformBox: 'fill-box', transformOrigin: 'center' } }
                    : {};
                return (
                    <G key={s.label} {...gProps}
                        onClick={toggleSeries ? () => toggle(si) : undefined}
                        style={{ ...(gProps.style || {}), cursor: toggleSeries ? 'pointer' : 'default' }}>
                        <polygon points={polyPts(radii)} fill={s.color} fillOpacity="0.2" stroke={s.color} strokeWidth="2.5" strokeLinejoin="round" />
                        {radii.map((r, i) => {
                            const [x, y] = at(r, i);
                            const hov = hovered && hovered.si === si && hovered.i === i;
                            return <circle key={i} cx={x} cy={y} r={hov ? 5.5 : 3.5} fill={s.color}
                                onMouseEnter={() => setHovered({ si, i })} onMouseLeave={() => setHovered(null)}
                                style={{ transition: 'r .12s' }} className="cursor-pointer" />;
                        })}
                    </G>
                );
            })}
            {axes.map((a, i) => {
                const [x, y] = at(labelR, i);
                const anchor = Math.abs(x - cx) < 8 ? 'middle' : (x > cx ? 'start' : 'end');
                return <text key={a} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" className="fill-slate-500 dark:fill-slate-400 text-[12px] font-bold">{a}</text>;
            })}
            {/* hover tooltip on a vertex */}
            {hovered && (() => {
                const s = series[hovered.si]; if (!s) return null;
                const v = s.values[hovered.i];
                const [hx, hy] = at(rFor(v), hovered.i);
                const label = `${s.label} · ${axes[hovered.i]}: ${v}`;
                const w = label.length * 6.2 + 20;
                const tx = hx + 12 + w > W ? hx - 12 - w : hx + 12;
                const ty = hy - 30 < 0 ? hy + 10 : hy - 30;
                return (
                    <g pointerEvents="none">
                        <rect x={tx} y={ty} width={w} height={24} rx={7} fill="#1e293b" />
                        <text x={tx + 10} y={ty + 16} fill="#fff" className="text-[11px] font-bold">{label}</text>
                    </g>
                );
            })()}
        </svg>
    );

    const seriesDropdown = (
        <div className="relative" ref={menuRef}>
            <button type="button" onClick={() => setMenuOpen((o) => !o)}
                className="flex items-center gap-2 px-3 h-9 rounded-full bg-slate-100 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600 shadow-sm text-sm font-bold text-slate-600 dark:text-slate-200 hover:border-indigo-400 transition-colors min-w-[9.5rem]">
                {visible != null
                    ? <><span className="w-5 h-4 rounded-md border-2 shrink-0" style={{ borderColor: series[visible].color, background: `${series[visible].color}22` }} /><span className="flex-1 text-left truncate">{series[visible].label}</span></>
                    : <span className="flex-1 text-left text-slate-400">Select section</span>}
                <ChevronDown className={`w-4 h-4 text-slate-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
                {menuOpen && (
                    <motion.ul
                        initial={{ opacity: 0, y: 6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 6, scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        className={`absolute z-30 top-full mt-2 left-0 w-48 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl shadow-xl p-1.5 ${series.length > 5 ? 'max-h-56 overflow-y-auto' : 'overflow-hidden'}`}>
                        {series.map((s, si) => (
                            <li key={s.label}>
                                <button type="button" onClick={() => { toggle(si); setMenuOpen(false); }}
                                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-bold text-left transition-colors ${visible === si ? 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-300' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                    <span className="w-5 h-4 rounded-md border-2 shrink-0" style={{ borderColor: s.color, background: `${s.color}22` }} />
                                    <span className="flex-1 truncate">{s.label}</span>
                                    {visible === si && <Check className="w-4 h-4 shrink-0" />}
                                </button>
                            </li>
                        ))}
                    </motion.ul>
                )}
            </AnimatePresence>
        </div>
    );

    if (legend === 'right') {
        // Centered radar; series chooser (dropdown when toggleSeries) bottom-right.
        return (
            <div className="relative w-full">
                <div className="w-full max-w-[560px] mx-auto">{svg}</div>
                <div className="absolute top-1 left-1 sm:top-3 sm:left-3 z-30 flex flex-col gap-2 items-start">
                    {toggleSeries ? seriesDropdown : legendList}
                </div>
            </div>
        );
    }
    return (
        <div className="flex flex-col items-center">
            <div className="flex items-center justify-center gap-5 mb-2 flex-wrap">{legendList}</div>
            <div className="w-full max-w-[380px]">{svg}</div>
        </div>
    );
}

// Section-competency radar helpers. Axis keys come from evaluation scores_json
// (q1..qN). The four rubric categories map to q1-q4 in order; unknown keys fall
// back to an uppercased label.
const CRITERION_LABELS = { q1: 'Innovation', q2: 'Technical', q3: 'Project Mgmt', q4: 'Presentation', q5: 'Q&A' };
const mapAxis = (k) => CRITERION_LABELS[k] || String(k).toUpperCase();
// All radar series share one neutral purple (only one shows at a time anyway).
const RADAR_COLOR = '#8b5cf6';
const toRadarSeries = (section) => ({ label: section.label, color: RADAR_COLOR, values: section.values });
// One series averaging every section per-axis — the overall competency profile.
const avgRadarSeries = (sections) => ({
    label: 'Average',
    color: RADAR_COLOR,
    values: sections.length
        ? sections[0].values.map((_, i) =>
            Math.round((sections.reduce((sum, s) => sum + (s.values[i] ?? 0), 0) / sections.length) * 10) / 10)
        : [],
});

// Simple scrollable data table.
function DataTable({ columns, rows, empty, emptyIcon }) {
    if (!rows.length) return <EmptyState icon={emptyIcon} message={empty} />;
    return (
        // Show ~5 rows; the rest scroll, with the header pinned.
        <div className={`overflow-x-auto -mx-2 ${rows.length > 5 ? 'max-h-[300px] overflow-y-auto' : ''}`}>
            <table className="w-full text-left border-collapse">
                <thead className="sticky top-0 z-10">
                    <tr className="border-b border-slate-100 dark:border-slate-700/50">
                        {columns.map((c) => (
                            <th key={c.key} className="px-2 py-2 text-[10px] font-black uppercase tracking-wider text-slate-400 whitespace-nowrap bg-white dark:bg-slate-800">{c.header}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className="border-b border-slate-50 dark:border-slate-700/30 last:border-0 hover:bg-slate-50/60 dark:hover:bg-slate-900/30">
                            {columns.map((c) => (
                                <td key={c.key} className="px-2 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 align-top">
                                    {c.render ? c.render(r, i) : (r[c.key] ?? '—')}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}


// Horizontal bar chart on a 0-max axis with gridlines and a hover tooltip.
function HBarChart({ data, max = 100, tooltipLabel = 'Value', onBarClick, activeIndex = null }) {
    const [hover, setHover] = useState(null);
    const ticks = Array.from({ length: 6 }, (_, i) => Math.round((max / 5) * i));
    return (
        <div className="pt-2">
            <div className={`space-y-4 ${data.length > 5 ? 'max-h-[280px] overflow-y-auto overflow-x-visible pr-1' : ''}`}>
                {data.map((row, i) => (
                    <div key={row.label} className="flex items-center gap-3">
                        <span className="w-24 shrink-0 text-right text-sm font-bold text-slate-500 dark:text-slate-300 truncate" title={row.label}>{row.label}</span>
                        <div className="relative flex-1 h-7">
                            {ticks.map((t) => (
                                <div key={t} className="absolute top-0 bottom-0 border-l border-slate-100 dark:border-slate-700/40" style={{ left: `${(t / max) * 100}%` }} />
                            ))}
                            <div className={`absolute left-0 top-1/2 -translate-y-1/2 h-6 rounded-r-md transition-colors ${onBarClick ? 'cursor-pointer' : 'cursor-default'} ${activeIndex === i ? 'ring-2 ring-teal-500/60' : ''}`}
                                style={{ width: `${Math.min(100, Math.max(row.value > 0 ? 1 : 0, (row.value / max) * 100))}%`, background: (hover === i || activeIndex === i) ? '#3f9e8d' : '#57b3a3' }}
                                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                                onClick={() => onBarClick && onBarClick(i)} />
                            {hover === i && (
                                <div className="absolute z-20 bottom-full mb-2 px-4 py-2 rounded-xl bg-slate-800 text-white shadow-xl whitespace-nowrap pointer-events-none -translate-x-1/2"
                                    style={{ left: `${Math.max(14, Math.min(86, (row.value / max) * 100))}%` }}>
                                    <p className="text-sm font-black leading-tight">{row.label}</p>
                                    <p className="text-xs text-slate-300">{tooltipLabel}: {row.value}</p>
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
            <div className="flex items-center gap-3 mt-2">
                <span className="w-24 shrink-0" />
                <div className="relative flex-1 h-4">
                    {ticks.map((t) => (
                        <span key={t} className="absolute -translate-x-1/2 text-[11px] font-semibold text-slate-400 tabular-nums" style={{ left: `${(t / max) * 100}%` }}>{t}</span>
                    ))}
                </div>
            </div>
        </div>
    );
}

// Scatter plot correlating two metrics, with gridlines, axis titles and a
// hover tooltip. `points` = [{ x, y, team }].
// `onExpand` (optional): clicking the empty plot area (not a dot) calls it —
// used to open the fullscreen view.
function ScatterPlot({ points, xLabel, yLabel, tip, onExpand }) {
    const [hover, setHover] = useState(null);
    const W = 560, H = 360, mL = 48, mR = 16, mT = 12, mB = 44;
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const xmin = Math.floor((Math.min(...xs) - 5) / 10) * 10, xmax = Math.ceil((Math.max(...xs) + 5) / 10) * 10;
    const ymin = Math.floor((Math.min(...ys) - 3) / 5) * 5, ymax = Math.ceil((Math.max(...ys) + 3) / 5) * 5;
    const xStep = Math.max(10, Math.round((xmax - xmin) / 8 / 10) * 10);
    const px = (x) => mL + ((x - xmin) / (xmax - xmin || 1)) * (W - mL - mR);
    const py = (y) => H - mB - ((y - ymin) / (ymax - ymin || 1)) * (H - mT - mB);
    const xticks = []; for (let v = xmin; v <= xmax; v += xStep) xticks.push(v);
    const yticks = []; for (let v = ymin; v <= ymax; v += 5) yticks.push(v);
    // Shrink dots as the cloud gets denser so hundreds of teams don't blob
    // together — ~7px for a handful, down to ~2.5px for 100+ points. Thinner
    // stroke and lower opacity at small sizes keep overlaps readable.
    const dotR = Math.max(2.5, Math.min(7, 280 / Math.max(points.length, 1)));
    const dotStroke = dotR > 4 ? 1.5 : 1;
    const dotFill = points.length > 100 ? 0.55 : 0.65;
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className={`w-full overflow-visible ${onExpand ? 'cursor-zoom-in' : ''}`}
            onClick={onExpand ? () => onExpand() : undefined}>
            {xticks.map((t) => <line key={`x${t}`} x1={px(t)} y1={mT} x2={px(t)} y2={H - mB} className="stroke-slate-100 dark:stroke-slate-700/40" strokeWidth="1" />)}
            {yticks.map((t) => <line key={`y${t}`} x1={mL} y1={py(t)} x2={W - mR} y2={py(t)} className="stroke-slate-100 dark:stroke-slate-700/40" strokeWidth="1" />)}
            {xticks.map((t) => <text key={`xl${t}`} x={px(t)} y={H - mB + 16} textAnchor="middle" className="fill-slate-400 text-[11px] font-semibold">{t}</text>)}
            {yticks.map((t) => <text key={`yl${t}`} x={mL - 8} y={py(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px] font-semibold">{t}</text>)}
            <text x={(mL + W - mR) / 2} y={H - 6} textAnchor="middle" className="fill-slate-500 dark:fill-slate-400 text-[12px] font-bold">{xLabel}</text>
            <text x={13} y={(mT + H - mB) / 2} textAnchor="middle" transform={`rotate(-90 13 ${(mT + H - mB) / 2})`} className="fill-slate-500 dark:fill-slate-400 text-[12px] font-bold">{yLabel}</text>
            {points.map((p, i) => (
                <circle key={i} cx={px(p.x)} cy={py(p.y)} r={hover === i ? dotR + 1.5 : dotR} fill="#8b5cf6" fillOpacity={hover === i ? 0.95 : dotFill} stroke="#fff" strokeWidth={dotStroke}
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                    onClick={(e) => e.stopPropagation()} className="cursor-pointer transition-all" />
            ))}
            {hover != null && (() => {
                const p = points[hover]; const cx = px(p.x), cy = py(p.y);
                const label = tip ? tip(p) : `${p.x}, ${p.y}`;
                const w = label.length * 6.6 + 22;
                const flip = cx + 14 + w > W;
                const tx = flip ? cx - 14 - w : cx + 14;
                return (
                    <g pointerEvents="none">
                        <rect x={tx} y={cy - 15} width={w} height={30} rx={8} fill="#1e293b" />
                        <text x={tx + 11} y={cy + 5} fill="#fff" className="text-[12px] font-bold">{label}</text>
                    </g>
                );
            })()}
        </svg>
    );
}

/* --------------------------------- top performers spotlight --------------------------------- */

const AVATAR_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#ef4444', '#14b8a6'];
const initials = (name) => {
    const p = String(name || '').trim().split(/\s+/);
    return (((p[0] || '')[0] || '') + ((p[1] || '')[0] || '')).toUpperCase() || '—';
};
const avatarColor = (name) => {
    let h = 0; for (const c of String(name || '')) h = (h * 31 + c.charCodeAt(0)) >>> 0;
    return AVATAR_COLORS[h % AVATAR_COLORS.length];
};
const spotlightStatus = (s) => {
    const green = 'text-emerald-600 dark:text-emerald-400 border-emerald-200 bg-emerald-50 dark:bg-emerald-500/10 dark:border-emerald-500/30';
    if (s == null) return { label: 'Unscored', cls: 'text-slate-400 border-slate-200 dark:border-slate-600' };
    if (s >= 98) return { label: 'Exceptional', cls: green };
    if (s >= 90) return { label: 'Excellent', cls: green };
    if (s >= 75) return { label: 'Good', cls: green };
    if (s >= 50) return { label: 'Fair', cls: 'text-amber-600 dark:text-amber-400 border-amber-200 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/30' };
    return { label: 'At Risk', cls: 'text-rose-600 dark:text-rose-400 border-rose-200 bg-rose-50 dark:bg-rose-500/10 dark:border-rose-500/30' };
};

function RankMedallion({ rank }) {
    if (rank === 1) {
        return <div className="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-500/20 flex items-center justify-center shrink-0"><Trophy className="w-5 h-5 text-amber-500" /></div>;
    }
    return <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-700/50 flex items-center justify-center text-sm font-black text-slate-500 dark:text-slate-300 shrink-0">{rank}</div>;
}

// Defined at module scope so it keeps one identity across renders. Declared
// inside SpotlightTable it was a new component type every render, so React
// unmounted and remounted every header cell on each pass.
const Th = ({ children, right }) => <th className={`px-2 py-2 text-[10px] font-black uppercase tracking-wider text-slate-400 whitespace-nowrap bg-white dark:bg-slate-800 ${right ? 'text-right' : ''}`}>{children}</th>;

function SpotlightTable({ rows, profileHeader, teamHeader, emptyMsg }) {
    if (!rows.length) return <EmptyState icon={Trophy} message={emptyMsg} />;
    return (
        // Show ~5 rows; the rest scroll. Header stays pinned while scrolling.
        <div className={`overflow-x-auto -mx-2 ${rows.length > 5 ? 'max-h-[400px] overflow-y-auto' : ''}`}>
            <table className="w-full text-left border-collapse">
                <thead className="sticky top-0 z-10">
                    <tr className="border-b border-slate-100 dark:border-slate-700/50">
                        <Th>Rank</Th><Th>{profileHeader}</Th><Th>{teamHeader}</Th><Th>Avg Score</Th><Th right>Status</Th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((r) => {
                        const st = spotlightStatus(r.score);
                        return (
                            <tr key={r.rank} className="border-b border-slate-50 dark:border-slate-700/30 last:border-0 hover:bg-slate-50/60 dark:hover:bg-slate-900/30">
                                <td className="px-2 py-3"><RankMedallion rank={r.rank} /></td>
                                <td className="px-2 py-3">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full flex items-center justify-center text-white text-xs font-black shrink-0" style={{ background: avatarColor(r.name) }}>{initials(r.name)}</div>
                                        <div className="min-w-0">
                                            <p className="text-sm font-black text-slate-800 dark:text-white truncate">{r.name}</p>
                                            <p className="text-[11px] font-semibold text-slate-400 truncate">{r.subtitle}</p>
                                        </div>
                                    </div>
                                </td>
                                <td className="px-2 py-3 text-sm font-semibold text-slate-600 dark:text-slate-300">{r.team}</td>
                                <td className="px-2 py-3 text-base font-black text-indigo-600 dark:text-indigo-400 tabular-nums">{r.score ?? '—'}</td>
                                <td className="px-2 py-3 text-right"><span className={`inline-block text-[11px] font-bold px-3 py-1 rounded-full border ${st.cls}`}>{st.label}</span></td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}

function SpotlightToggle({ tab, onChange }) {
    return (
        <div className="flex items-center gap-1 p-1 rounded-xl bg-slate-100 dark:bg-slate-700/50 shrink-0">
            {['students', 'teams'].map((t) => (
                <button key={t} onClick={() => onChange(t)}
                    className={`px-3 py-1 rounded-lg text-xs font-bold capitalize transition-colors ${tab === t ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-300 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700'}`}>
                    {t}
                </button>
            ))}
        </div>
    );
}

// Compact week selector for Activity vs. Performance. `weeks` = count available.
function WeekDropdown({ week, weeks, onChange }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
        const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, []);
    return (
        <div className="relative shrink-0" ref={ref}>
            <button onClick={() => setOpen((o) => !o)}
                className="flex items-center gap-2 px-3 h-8 rounded-lg bg-slate-100 dark:bg-slate-700/50 border border-transparent hover:border-indigo-400 text-xs font-bold text-slate-600 dark:text-slate-300 transition-colors">
                Week {week + 1}
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
                {open && (
                    <motion.ul
                        initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.98 }}
                        transition={{ duration: 0.15 }}
                        className="absolute z-50 mt-2 right-0 w-36 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl p-1.5 max-h-56 overflow-y-auto">
                        {Array.from({ length: weeks }, (_, i) => (
                            <li key={i}>
                                <button onClick={() => { onChange(i); setOpen(false); }}
                                    className={`w-full text-left px-3 py-2 rounded-lg text-sm font-bold transition-colors ${i === week ? 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-600 dark:text-indigo-300' : 'text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40'}`}>
                                    Week {i + 1}
                                </button>
                            </li>
                        ))}
                    </motion.ul>
                )}
            </AnimatePresence>
        </div>
    );
}

/* --------------------------------- page --------------------------------- */

export default function Analysis() {
    const { filterRows, activeFilterCount, filters } = useGlobalFilters();
    const [params] = useSearchParams();
    const [raw, setRaw] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [radarOpen, setRadarOpen] = useState(false);   // Section Competencies expand modal
    const [spotlightTab, setSpotlightTab] = useState('students'); // Top Performers: 'students' | 'teams'
    const [marksTab, setMarksTab] = useState('students'); // Marks Distribution: 'students' | 'teams'
    const [marksDrill, setMarksDrill] = useState(null); // selected band index for the drill-down (or null)
    const [panelDrill, setPanelDrill] = useState(null); // Panel-wise: selected panel index (or null)
    const [mentorDrill, setMentorDrill] = useState(null); // Mentor Impact: selected mentor index (or null)
    const [activityWeek, setActivityWeek] = useState(0); // Activity vs. Performance: selected week index
    const [scatterOpen, setScatterOpen] = useState(false); // Activity vs. Performance: fullscreen view

    const fetchAnalysis = () => api.getAnalysisData()
        .then(setRaw)
        .catch((e) => setError(e.message || 'Failed to load'))
        .finally(() => setLoading(false));

    // Retry needs the spinner and the cleared error; the mount path does not,
    // because `loading` already starts true and `error` starts empty. Passing
    // `load` straight to useEffect ran both setters synchronously inside the
    // effect, which is the cascading render the compiler flags.
    const load = () => {
        setLoading(true); setError('');
        return fetchAnalysis();
    };

    useEffect(() => { fetchAnalysis(); }, []);

    // The presentation is chosen from the view dropdown in the top nav (?p=0/1/2);
    // the widget search reuses the global "Search all pages" bar.
    const presIndex = Math.min(2, Math.max(0, parseInt(params.get('p') || '0', 10) || 0));
    const search = filters?.search || '';
    const d = useMemo(
        () => (raw ? aggregatePresentation(raw, filterRows, presIndex, search) : null),
        [raw, filterRows, presIndex, search],
    );

    const maxBar = (arr, key = 'avg') => Math.max(1, ...arr.map((x) => x[key] || 0));

    // Activity vs. Performance scatter data — derived once so both the inline
    // card and the fullscreen modal render the same points/labels.
    const scatter = useMemo(() => {
        if (!d) return null;
        const weekCount = Math.max(0, ...d.github_vs_presentation.map((g) => (Array.isArray(g.weeks) ? g.weeks.length : 0)));
        const wk = weekCount ? Math.min(activityWeek, weekCount - 1) : 0;
        const pts = d.github_vs_presentation
            .filter((g) => g.presentation != null)
            .map((g) => ({ x: (weekCount && g.weeks) ? g.weeks[wk] : g.commits30d, y: g.presentation, team: g.team }))
            .filter((p) => p.x != null);
        return {
            weekCount, wk, pts,
            xLabel: weekCount ? `GitHub Commits (Week ${wk + 1})` : 'GitHub Commits (Est.)',
            subtitle: weekCount ? `GitHub Commits (Week ${wk + 1}) vs Pres Score` : 'Correlation: GitHub Commits vs Pres Score',
        };
    }, [d, activityWeek]);

    // --- Per-widget CSV exports (only invoked from buttons inside the `d` block) ---
    // Marks Distribution — both the student and team histograms in one file.
    const csvMarks = () => {
        const s = d.marks_distribution.students, t = d.marks_distribution.teams;
        const labels = (s.length ? s : t).map((b) => b.label);
        const rows = [['Band', 'Students', 'Teams']];
        labels.forEach((label, i) => rows.push([label, s[i]?.count ?? '', t[i]?.count ?? '']));
        downloadCsv('marks-distribution.csv', rows);
    };
    // Section Competencies — one row per section with its per-criterion values.
    const csvSections = () => {
        const axes = d.section_competencies.axes.map(mapAxis);
        const rows = [['Section', ...axes, 'Average', 'N']];
        d.section_competencies.sections.forEach((sec) => rows.push([sec.label, ...sec.values, sec.avg, sec.n]));
        downloadCsv('section-competencies.csv', rows);
    };
    // Top Performers — exports whichever tab (students / teams) is showing.
    const csvSpotlight = () => {
        if (spotlightTab === 'students') {
            const rows = [['Rank', 'Name', 'Section', 'Student ID', 'Team', 'Score']];
            d.top_students.forEach((s) => rows.push([s.rank, s.name, s.section, s.studentId, s.team, s.score]));
            downloadCsv('top-students.csv', rows);
        } else {
            const rows = [['Rank', 'Team', 'Marks', 'Domain', 'Section', 'Mentor']];
            d.top_performers.forEach((t) => rows.push([t.rank, t.team || t.title, t.marks, t.domain, t.section, t.mentor]));
            downloadCsv('top-teams.csv', rows);
        }
    };
    // Panel-wise — the panel average AND each evaluated team's score.
    const csvPanels = () => {
        const rows = [['Panel', 'Panel Average', 'Evaluations', 'Team', 'Team Score']];
        d.panel_averages.forEach((p) => {
            if (p.teams && p.teams.length) p.teams.forEach((tm) => rows.push([p.label, p.avg, p.count, tm.name, tm.score]));
            else rows.push([p.label, p.avg, p.count, '', '']);
        });
        downloadCsv('panel-averages.csv', rows);
    };
    // Mentor Impact — the mentor's average AND each of their team's scores.
    const csvMentors = () => {
        const rows = [['Mentor', 'Avg Score', 'Teams', 'Team', 'Team Score']];
        d.mentor_analysis.forEach((m) => {
            if (m.teams && m.teams.length) m.teams.forEach((tm) => rows.push([m.label, m.avg, m.count, tm.name, tm.score]));
            else rows.push([m.label, m.avg, m.count, '', '']);
        });
        downloadCsv('mentor-impact.csv', rows);
    };
    // Activity vs. Performance — every week's commit count plus the presentation
    // score, one row per (team, week).
    const csvActivity = () => {
        const rows = [['Team', 'Week', 'GitHub Commits', 'Presentation Score']];
        d.github_vs_presentation.forEach((g) => {
            const weeks = Array.isArray(g.weeks) && g.weeks.length ? g.weeks : (g.commits30d != null ? [g.commits30d] : []);
            if (weeks.length) weeks.forEach((c, w) => rows.push([g.team, w + 1, c, g.presentation]));
            else rows.push([g.team, '', '', g.presentation]);
        });
        downloadCsv('activity-vs-performance.csv', rows);
    };
    // Absent Students.
    const csvAbsent = () => {
        const rows = [['#', 'Name', 'Roll', 'Team', 'Reason', 'Status']];
        d.absent_details.forEach((a, i) => rows.push([i + 1, a.name, a.roll, a.team, a.reason, a.status]));
        downloadCsv('absent-students.csv', rows);
    };

    // Export the whole dashboard to PDF. Tailwind v4 emits oklch() colours that
    // html2canvas 1.4.1 can't parse, and the app shell is a fixed-height scroll
    // container that clips in-page printing — so we clone the dashboard into a
    // clean popup that inherits the page stylesheets and print that. The browser's
    // own engine renders oklch + the SVG charts and paginates cleanly. The user
    // picks "Save as PDF" in the print dialog.
    const handleDownloadPdf = () => {
        const node = document.getElementById('analysis-dashboard');
        if (!node) return;
        const win = window.open('', '_blank', 'width=1200,height=900');
        if (!win) { window.alert('Please allow pop-ups to download the dashboard as PDF.'); return; }
        const styles = Array.from(document.querySelectorAll('link[rel="stylesheet"], style'))
            .map((n) => n.outerHTML).join('\n');
        const htmlClass = document.documentElement.className;
        const dark = document.documentElement.classList.contains('dark');
        const bg = dark ? '#0f172a' : '#ffffff';
        win.document.write(`<!doctype html><html class="${htmlClass}"><head><meta charset="utf-8">
            <title>Analysis Dashboard</title>${styles}
            <style>
                html,body{background:${bg};margin:0;padding:0;}
                .pdf-wrap{padding:24px;}
                .pdf-wrap *{max-height:none !important;overflow:visible !important;min-height:0 !important;}
                .no-print{display:none !important;}
                @page{margin:12mm;}
                @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
            </style></head>
            <body><div class="pdf-wrap">${node.outerHTML}</div></body></html>`);
        win.document.close();
        win.focus();
        // Let the copied stylesheets apply before invoking the print dialog.
        setTimeout(() => { win.print(); }, 600);
    };

    return (
        <div id="analysis-dashboard" className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
                className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-blue-800 rounded-3xl p-8 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden flex flex-col md:flex-row items-center justify-between border border-indigo-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 w-full lg:w-2/3">
                    <div className="flex items-center gap-3 mb-4">
                        <button onClick={handleDownloadPdf} title="Download dashboard as PDF"
                            className="no-print shrink-0 h-10 w-10 flex items-center justify-center rounded-full bg-white/15 hover:bg-white/25 backdrop-blur-md border border-white/25 shadow-sm transition-colors active:scale-95">
                            <Download className="w-5 h-5" />
                        </button>
                        <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider border border-white/20 shadow-sm">
                            <TrendingUp className="w-4 h-4 mr-2" /> Insights Engine
                        </div>
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Analysis</h1>
                    <p className="text-indigo-100/90 leading-relaxed text-sm md:text-base max-w-lg">Presentation-wise performance across teams, panels, sections and mentors — spot outliers and drill into the marks that matter.</p>
                    {activeFilterCount > 0 && (
                        <div className="inline-flex items-center gap-1.5 mt-4 px-3 py-1.5 bg-white/15 backdrop-blur-md rounded-full text-[11px] font-bold border border-white/20">
                            <Filter className="w-3.5 h-3.5" /> Scoped by the Filter Bar ({activeFilterCount} active)
                        </div>
                    )}
                </div>
                <div className="hidden lg:block relative z-10 transform scale-110 translate-x-4 opacity-90 pointer-events-none drop-shadow-2xl">
                    <svg viewBox="0 0 200 200" fill="none" className="w-56 h-56 text-indigo-100">
                        <rect x="52" y="112" width="28" height="53" rx="5" fill="currentColor" opacity="0.45" />
                        <rect x="92" y="82" width="28" height="83" rx="5" fill="currentColor" opacity="0.6" />
                        <rect x="132" y="48" width="28" height="117" rx="5" fill="currentColor" opacity="0.8" />
                        <line x1="28" y1="168" x2="176" y2="168" stroke="#fff" strokeWidth="7" strokeLinecap="round" />
                        <path d="M66 118 L106 84 L146 50" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                </div>
            </motion.div>

            {loading && (
                <div className="flex items-center justify-center py-24 text-slate-400"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Crunching the numbers…</div>
            )}
            {error && !loading && (
                <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-400 px-5 py-4 rounded-2xl text-sm font-semibold flex items-center justify-between">
                    <span className="flex items-center"><AlertTriangle className="w-5 h-5 mr-2" />{error}</span>
                    <button onClick={load} className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-lg bg-white/60 dark:bg-slate-800/60"><RefreshCw className="w-3.5 h-3.5" /> Retry</button>
                </div>
            )}

            {d && !loading && (
                <>
                    {/* KPI strip: averages + student totals (#4, #6) */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <StatTile label="Total Project Teams" value={d.counts.teams} sub={`${d.counts.scored} scored`} icon={Users} />
                        <StatTile label="Total Students" value={d.student_totals.total} sub="in scope" icon={Users} />
                        <StatTile label="Attendance" tone="emerald" icon={TrendingUp}
                            value={`${d.student_totals.total ? Math.round((d.student_totals.present / d.student_totals.total) * 1000) / 10 : 0}%`}
                            sub={`${d.student_totals.present}/${d.student_totals.total} present`} />
                        <StatTile label="Absent" value={d.student_totals.absent} sub="this semester" icon={UserMinus} danger={d.student_totals.absent > 0} />
                    </div>

                    {/* #1 marks distribution + #7 section-wise */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card title="Marks Distribution"
                            subtitle={marksTab === 'students' ? 'Number of students per score range' : 'Number of teams per score range'}
                            icon={BarChart3}
                            action={<div className="flex items-center gap-2 shrink-0"><DownloadBtn onClick={csvMarks} title="Download (students + teams) CSV" /><SpotlightToggle tab={marksTab} onChange={(t) => { setMarksTab(t); setMarksDrill(null); }} /></div>}>
                            {d.marks_distribution[marksTab].length ? (
                                <>
                                    <AxisBarChart data={d.marks_distribution[marksTab]} unit={marksTab}
                                        activeIndex={marksDrill}
                                        onBarClick={(i) => setMarksDrill((prev) => (prev === i ? null : i))} />
                                    <DrillPanel open={marksDrill != null}
                                        heading={marksDrill != null ? `Score ${d.marks_distribution[marksTab][marksDrill].label}` : ''}
                                        sub={marksDrill != null ? `${d.marks_distribution[marksTab][marksDrill].count} ${marksTab}` : ''}
                                        items={marksDrill != null ? (d.marks_distribution[marksTab][marksDrill].items || []) : []}
                                        onClose={() => setMarksDrill(null)} />
                                </>
                            ) : <EmptyState message={`No ${marksTab === 'students' ? 'student' : 'team'} marks recorded for this presentation yet. This chart fills in as teams are marked.`} />}
                        </Card>
                        <Card title="Section Competencies"
                            subtitle={d.section_competencies.sections.length ? `Average across ${d.section_competencies.sections.length} section${d.section_competencies.sections.length > 1 ? 's' : ''}` : 'Competency profile by section'}
                            icon={Grid3x3}
                            action={(
                                <div className="flex items-center gap-1 shrink-0">
                                    <DownloadBtn onClick={csvSections} />
                                    <button onClick={() => setRadarOpen(true)} title="Expand"
                                        className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-500 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors shrink-0">
                                        <Maximize2 className="w-4 h-4" />
                                    </button>
                                </div>
                            )}>
                            {d.section_competencies.sections.length
                                ? <RadarChart
                                    axes={d.section_competencies.axes.map(mapAxis)}
                                    series={[avgRadarSeries(d.section_competencies.sections)]} />
                                : <EmptyState icon={Grid3x3} message="Section competencies appear once evaluated teams carry a section. None are assigned yet." />}
                        </Card>
                    </div>

                    {/* #2 top performers + #5 critical observations */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card title="Top Performers Spotlight"
                            subtitle={spotlightTab === 'students' ? 'Highest-scoring students' : 'Highest-scoring teams'}
                            icon={Trophy}
                            action={<div className="flex items-center gap-2 shrink-0"><DownloadBtn onClick={csvSpotlight} title={`Download ${spotlightTab} CSV`} /><SpotlightToggle tab={spotlightTab} onChange={setSpotlightTab} /></div>}>
                            {spotlightTab === 'students'
                                ? <SpotlightTable
                                    profileHeader="Student Profile" teamHeader="Team Name"
                                    rows={d.top_students.map((s) => ({
                                        rank: s.rank, name: s.name, subtitle: `${s.section} • ID: ${s.studentId}`, team: s.team, score: s.score,
                                    }))}
                                    emptyMsg="Per-student ranking appears once teams are scored and members are linked to student records. Marks are team-level today." />
                                : <SpotlightTable
                                    profileHeader="Team" teamHeader="Domain"
                                    rows={d.top_performers.map((t) => ({
                                        rank: t.rank, name: t.title || t.team, subtitle: [t.section, t.mentor].filter(Boolean).join(' • '), team: t.domain, score: t.marks,
                                    }))}
                                    emptyMsg="Top teams appear once marks are entered for this presentation." />}
                        </Card>
                        <Card title="Critical Observations by Panel" subtitle="Flagged panel remarks" icon={MessageSquareWarning} badge={d.critical_observations.filter((o) => o.critical).length || null}>
                            {d.critical_observations.length ? (
                                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                                    {d.critical_observations.map((o, i) => (
                                        <div key={i} className={`p-3 rounded-2xl border ${o.critical ? 'bg-rose-50/60 dark:bg-rose-500/10 border-rose-200 dark:border-rose-500/30' : 'bg-slate-50 dark:bg-slate-900/40 border-slate-100 dark:border-slate-700/50'}`}>
                                            <div className="flex items-center justify-between gap-2 mb-1">
                                                <span className="text-xs font-black text-slate-800 dark:text-white truncate">{o.team}</span>
                                                <span className="text-[10px] font-bold text-slate-400 shrink-0">{o.panel}{o.score != null ? ` · ${o.score}` : ''}</span>
                                            </div>
                                            <p className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">{o.remark}</p>
                                            {o.critical && <span className="inline-block mt-1.5 text-[9px] font-black uppercase tracking-wider text-rose-500">⚠ Critical</span>}
                                        </div>
                                    ))}
                                </div>
                            ) : <EmptyState icon={MessageSquareWarning} message="No panel remarks recorded yet. Panel evaluations with remarks appear here." />}
                        </Card>
                    </div>

                    {/* #8 panel-wise + #9 mentor-wise */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card title="Panel-wise Average Marks" subtitle="Mean evaluation score per panel" icon={ShieldCheck} badge={d.panel_averages.length || null}
                            action={<DownloadBtn onClick={csvPanels} title="Download (average + each team) CSV" />}>
                            {d.panel_averages.length
                                ? <>
                                    <div className={`space-y-3 ${d.panel_averages.length > 5 ? 'max-h-[280px] overflow-y-auto pr-1' : ''}`}>
                                        {d.panel_averages.map((p, i) => (
                                            <BarRow key={p.label} label={`${p.label} (${p.count})`} value={p.avg ?? 0} max={maxBar(d.panel_averages)} valueText={p.avg ?? '—'}
                                                active={panelDrill === i}
                                                onClick={() => setPanelDrill((prev) => (prev === i ? null : i))} />
                                        ))}
                                    </div>
                                    <DrillPanel open={panelDrill != null}
                                        heading={panelDrill != null ? d.panel_averages[panelDrill].label : ''}
                                        sub={panelDrill != null ? `${d.panel_averages[panelDrill].teams.length} team${d.panel_averages[panelDrill].teams.length === 1 ? '' : 's'}` : ''}
                                        items={panelDrill != null ? d.panel_averages[panelDrill].teams : []}
                                        onClose={() => setPanelDrill(null)} />
                                </>
                                : <EmptyState icon={ShieldCheck} message="Panel averages appear once panels submit scored evaluations." />}
                        </Card>
                        <Card title="Mentor Impact (Avg Score)" subtitle="Average team score per mentor" icon={UserCircle} badge={d.mentor_analysis.length || null}
                            action={<DownloadBtn onClick={csvMentors} title="Download (avg + each team) CSV" />}>
                            {d.mentor_analysis.length
                                ? <>
                                    <HBarChart tooltipLabel="Avg Team Score"
                                        data={d.mentor_analysis.map((m) => ({ label: m.label, value: m.avg ?? 0, count: m.count }))}
                                        activeIndex={mentorDrill}
                                        onBarClick={(i) => setMentorDrill((prev) => (prev === i ? null : i))} />
                                    <DrillPanel open={mentorDrill != null}
                                        heading={mentorDrill != null ? d.mentor_analysis[mentorDrill].label : ''}
                                        sub={mentorDrill != null ? `${d.mentor_analysis[mentorDrill].teams.length} team${d.mentor_analysis[mentorDrill].teams.length === 1 ? '' : 's'}` : ''}
                                        items={mentorDrill != null ? d.mentor_analysis[mentorDrill].teams : []}
                                        onClose={() => setMentorDrill(null)} />
                                </>
                                : <EmptyState icon={UserCircle} message="Mentor averages appear once their teams are marked for this presentation." />}
                        </Card>
                    </div>

                    {/* #10 github vs presentation + #3 absent details */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <Card title="Activity vs. Performance"
                            subtitle={scatter.subtitle}
                            action={<div className="flex items-center gap-2 shrink-0">
                                <DownloadBtn onClick={csvActivity} title="Download (weekly commits + score) CSV" />
                                {scatter.weekCount
                                    ? <WeekDropdown week={scatter.wk} weeks={scatter.weekCount} onChange={setActivityWeek} />
                                    : <div className="p-2 rounded-xl bg-slate-100 dark:bg-slate-700/50 shrink-0"><Github className="w-5 h-5 text-slate-600 dark:text-slate-300" /></div>}
                            </div>}>
                            {scatter.pts.length
                                ? <ScatterPlot points={scatter.pts} xLabel={scatter.xLabel} yLabel="Presentation Score"
                                    tip={(p) => `${p.team} · Commits: ${p.x} | Score: ${p.y}`}
                                    onExpand={() => setScatterOpen(true)} />
                                : <EmptyState icon={Github} message="Plots each team's GitHub commit activity against its presentation score — appears once repos are analysed and marks are entered." />}
                        </Card>
                        <Card title="Absent Students" subtitle="Absentee details this semester" icon={UserMinus} badge={d.absent_details.length || null}
                            action={<DownloadBtn onClick={csvAbsent} />}>
                            <DataTable
                                columns={[
                                    { key: '_sno', header: '#', render: (r, i) => <span className="font-black text-slate-400 tabular-nums">{i + 1}</span> },
                                    { key: 'name', header: 'Name', render: (r) => <span className="font-black text-slate-800 dark:text-white">{r.name}</span> },
                                    { key: 'roll', header: 'Roll' },
                                    { key: 'team', header: 'Team' },
                                ]}
                                rows={d.absent_details}
                                emptyIcon={UserMinus}
                                empty="No absentees recorded for this semester." />
                        </Card>
                    </div>
                </>
            )}

            {/* Section Competencies — expand modal (all sections overlaid) */}
            <AnimatePresence>
                {radarOpen && d && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={() => setRadarOpen(false)}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9, y: 16 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9, y: 16 }}
                            transition={{ type: 'spring', duration: 0.5, bounce: 0.28 }}
                            onClick={(e) => e.stopPropagation()}
                            className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-700 w-full max-w-4xl p-6 sm:p-10 relative">
                            <button onClick={() => setRadarOpen(false)}
                                className="absolute top-5 right-5 p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                            <h3 className="text-xl font-black text-slate-800 dark:text-white tracking-tight mb-1 text-center">Section Competencies</h3>
                            <p className="text-xs text-slate-400 font-medium mb-6 text-center">All sections · averaged panel evaluation criteria</p>
                            {d.section_competencies.sections.length
                                ? <RadarChart legend="right" toggleSeries
                                    axes={d.section_competencies.axes.map(mapAxis)}
                                    series={d.section_competencies.sections.map((s, i) => toRadarSeries(s, i))} />
                                : <EmptyState icon={Grid3x3} message="Section competencies appear once evaluated teams carry a section. None are assigned yet." />}
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Activity vs. Performance — fullscreen view (opened by clicking the plot's empty area) */}
            <AnimatePresence>
                {scatterOpen && scatter && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={() => setScatterOpen(false)}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9, y: 16 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9, y: 16 }}
                            transition={{ type: 'spring', duration: 0.5, bounce: 0.28 }}
                            onClick={(e) => e.stopPropagation()}
                            className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl border border-slate-200 dark:border-slate-700 w-full max-w-6xl p-6 sm:p-10 relative">
                            <button onClick={() => setScatterOpen(false)}
                                className="absolute top-5 right-5 p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                            <h3 className="text-xl font-black text-slate-800 dark:text-white tracking-tight mb-1 text-center">Activity vs. Performance</h3>
                            <p className="text-xs text-slate-400 font-medium mb-6 text-center">{scatter.subtitle}</p>
                            {scatter.pts.length
                                ? <ScatterPlot points={scatter.pts} xLabel={scatter.xLabel} yLabel="Presentation Score"
                                    tip={(p) => `${p.team} · Commits: ${p.x} | Score: ${p.y}`} />
                                : <EmptyState icon={Github} message="Plots each team's GitHub commit activity against its presentation score — appears once repos are analysed and marks are entered." />}
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
