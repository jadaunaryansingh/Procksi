import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, Lock, Tag, Cpu, Sparkles, Target, Layers, Code2, Package, Users, Clock, DollarSign, Wrench, BarChart3, FileText, Globe } from 'lucide-react';
import { getApiBaseUrl } from '../../lib/apiBase';

// ─── Helpers ──────────────────────────────────────────────────────────────────

// ─── Helpers ──────────────────────────────────────────────────────────────────

function cleanSectionTitle(rawTitle) {
    if (!rawTitle) return '';
    let title = String(rawTitle).trim();
    title = title.replace(/^[#\s]+/g, '');
    title = title.replace(/^(?:\d+[.)]\s*)+/g, '');
    title = title.replace(/^(?:\d+[\s\-_\u2014—.]*)+/, '');
    title = title.replace(/^[#\s]+/g, '');
    title = title.replace(/#/g, '').replace(/:\s*$/, '').trim();
    return title || String(rawTitle).trim();
}

// Longest value that still reads as a chip rather than a sentence.
const TECH_CHIP_MAX_LENGTH = 48;

const NOISE_HEADER_WORDS = [
    'solution', 'core solution', 'objectives', 'objective', 'core objectives', 'key objectives',
    'context &', 'context', 'business context', 'problem description', 'problem statement',
    'business', 'core', 'key', 'overview', 'goal', 'primary goal', 'features', 'key features',
    'deliverables', 'expected deliverables', 'tech stack', 'technology stack', 'challenges',
    'technical challenges', 'key technical challenges', 'requirements', 'technical requirements',
    'success criteria', 'evaluation metrics', 'workflow'
];

const isHeaderNoise = (str) => {
    if (!str) return true;
    const clean = str.trim().toLowerCase().replace(/[:\-_—. ]/g, '');
    if (!clean) return true;
    if (clean.length <= 30 && NOISE_HEADER_WORDS.some(w => {
        const cw = w.replace(/[&. ]/g, '');
        return clean === cw || clean === cw + 's' || clean === cw + ':';
    })) return true;
    return false;
};

function parseStructuredOverview(text) {
    if (!text) return { leadVision: '', blocks: [] };
    let formatted = typeof text === 'string' ? text : String(text);

    formatted = formatted.replace(/\u2014|\u2013|\\u2014|\\u2013/g, '—');

    const sectionHeaderRegex = /(?:^|\n|\s{2,})((?:\d+[.)]\s*)?(?:Business Context(?:\s*&\s*Problem Description)?|Problem Description|Problem Statement|Core Solution|Solution|Core Objectives|Key Objectives|Core|Key|Key Technical Challenges|Technical Challenges|Technical Requirements(?:\s*&\s*Deliverables)?|Deliverables|Expected Business Impact|Business Impact|Evaluation Metrics(?:\s*&\s*Success Criteria)?|Success Criteria|Tech Stack(?:\s*&\s*Tools)?|Technology Stack|Key Features|System Architecture|Primary Goal|Project Vision|Workflow|Skills Required)\s*:?)(?=\s*\n|\s+[A-Z0-9]|$)/gi;

    formatted = formatted.replace(sectionHeaderRegex, (match, p1) => {
        const clean = p1.trim();
        if (clean.startsWith('#')) return `\n${clean}\n`;
        return `\n### ${clean}\n`;
    });

    const rawLines = formatted.split('\n').map(l => l.trim()).filter(Boolean);
    let leadVision = '';
    const blocks = [];
    let currentBlock = null;

    for (let i = 0; i < rawLines.length; i++) {
        const line = rawLines[i];
        if (line.startsWith('#')) {
            if (currentBlock && currentBlock.items.length > 0) blocks.push(currentBlock);
            const label = cleanSectionTitle(line);
            currentBlock = {
                title: label,
                items: []
            };
            continue;
        }

        const cleanLine = line.replace(/^[-*•]\s*/, '').trim();
        if (!cleanLine || isHeaderNoise(cleanLine)) continue;

        if (currentBlock) {
            if (currentBlock.title && cleanSectionTitle(currentBlock.title).toLowerCase() === cleanLine.toLowerCase()) {
                continue;
            }
            currentBlock.items.push(cleanLine);
        } else {
            if (leadVision) leadVision += ' ';
            leadVision += cleanLine;
        }
    }
    if (currentBlock && currentBlock.items.length > 0) blocks.push(currentBlock);

    return { leadVision: leadVision.trim(), blocks };
}

function getBlockConfig(title) {
    const clean = cleanSectionTitle(title);
    const t = clean.toLowerCase();
    if (t.includes('solution') || t.includes('application') || t.includes('impact') || t.includes('real-world') || t.includes('context') || t.includes('business')) {
        return { label: clean, icon: Globe, accent: '#10B981', glow: 'shadow-[0_0_20px_rgba(16,185,129,0.2)]' };
    }
    if (t.includes('objective') || t.includes('goal') || t.includes('aim') || t.includes('key')) {
        return { label: clean, icon: Target, accent: '#06B6D4', glow: 'shadow-[0_0_20px_rgba(6,182,212,0.2)]' };
    }
    if (t.includes('challenge') || t.includes('problem') || t.includes('issue')) {
        return { label: clean, icon: Wrench, accent: '#F59E0B', glow: 'shadow-[0_0_20px_rgba(245,158,11,0.2)]' };
    }
    if (t.includes('requirement') || t.includes('deliverable') || t.includes('specification')) {
        return { label: clean, icon: Package, accent: '#EC4899', glow: 'shadow-[0_0_20px_rgba(236,72,153,0.2)]' };
    }
    if (t.includes('metric') || t.includes('evaluation') || t.includes('success') || t.includes('criteria')) {
        return { label: clean, icon: BarChart3, accent: '#8B5CF6', glow: 'shadow-[0_0_20px_rgba(139,92,246,0.2)]' };
    }
    if (t.includes('feature')) {
        return { label: clean, icon: Sparkles, accent: '#8B5CF6', glow: 'shadow-[0_0_20px_rgba(139,92,246,0.2)]' };
    }
    if (t.includes('skill') || t.includes('prerequisite') || t.includes('tech stack') || t.includes('dataset')) {
        return { label: clean, icon: Code2, accent: '#06B6D4', glow: 'shadow-[0_0_20px_rgba(6,182,212,0.2)]' };
    }
    if (t.includes('workflow') || t.includes('methodology') || t.includes('process') || t.includes('architecture')) {
        return { label: clean, icon: Layers, accent: '#EC4899', glow: 'shadow-[0_0_20px_rgba(236,72,153,0.2)]' };
    }
    return { label: clean, icon: FileText, accent: '#6366F1', glow: 'shadow-[0_0_20px_rgba(99,102,241,0.2)]' };
}

function ExecutiveSummaryCard({ overview }) {
    const { leadVision, blocks } = parseStructuredOverview(overview);

    if (blocks.length === 0) {
        return (
            <motion.section
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
                className="relative bg-gradient-to-br from-[#161622] via-[#12121A] to-[#191528] rounded-2xl border border-indigo-500/30 p-5 md:p-6 shadow-[0_0_30px_rgba(108,60,225,0.12)] overflow-hidden"
            >
                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-purple-500 via-indigo-500 to-cyan-500" />
                <div className="flex items-center gap-2 mb-3">
                    <span className="font-mono text-[10px] text-[#8B5CF6] font-bold uppercase tracking-widest block">01 — Executive Summary</span>
                    <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-[9px] font-mono font-bold uppercase border border-purple-500/30 flex items-center gap-1">
                        <Sparkles className="w-2.5 h-2.5 text-purple-400" /> Vision Overview
                    </span>
                </div>
                <h2 className="text-base font-extrabold text-white mb-2 leading-snug">Project Vision & Core Overview</h2>
                <p className="text-xs leading-relaxed text-slate-200 font-medium text-justify">{leadVision || overview}</p>
            </motion.section>
        );
    }

    return (
        <div className="space-y-4">
            {leadVision && (
                <motion.section
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35 }}
                    className="relative bg-gradient-to-br from-[#161622] via-[#12121A] to-[#191528] rounded-2xl border border-indigo-500/30 p-5 md:p-6 shadow-[0_0_30px_rgba(108,60,225,0.12)] overflow-hidden"
                >
                    <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-purple-500 via-indigo-500 to-cyan-500" />
                    <div className="flex items-center gap-2 mb-3">
                        <span className="font-mono text-[10px] text-[#8B5CF6] font-bold uppercase tracking-widest block">01 — Executive Summary</span>
                        <span className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-[9px] font-mono font-bold uppercase border border-purple-500/30 flex items-center gap-1">
                            <Sparkles className="w-2.5 h-2.5 text-purple-400" /> Vision Overview
                        </span>
                    </div>
                    <h2 className="text-base font-extrabold text-white mb-2 leading-snug">Project Vision & Core Overview</h2>
                    <p className="text-xs leading-relaxed text-slate-200 font-medium text-justify">{leadVision}</p>
                </motion.section>
            )}

            {blocks.map((block, idx) => {
                const cfg = getBlockConfig(block.title);
                const Icon = cfg.icon;
                const secNum = String(idx + 2).padStart(2, '0');

                return (
                    <motion.section
                        key={block.title + idx}
                        initial={{ opacity: 0, y: 18, scale: 0.98 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        transition={{ duration: 0.35, delay: (idx + 1) * 0.07 }}
                        whileHover={{ y: -3, scale: 1.005, transition: { duration: 0.2 } }}
                        className={`bg-[#12121A]/90 backdrop-blur-xl rounded-2xl border border-[#FFFFFF15] p-5 space-y-3 relative overflow-hidden shadow-lg hover:border-indigo-500/40 transition-all ${cfg.glow}`}
                    >
                        <div className="absolute left-0 top-4 bottom-4 w-1 rounded-r-full" style={{ background: cfg.accent }} />
                        <div className="flex items-center gap-2.5 pl-3">
                            <div className="w-7 h-7 rounded-xl flex items-center justify-center shrink-0 shadow-inner" style={{ background: `${cfg.accent}20`, border: `1px solid ${cfg.accent}40` }}>
                                <Icon className="w-4 h-4" style={{ color: cfg.accent }} />
                            </div>
                            <div>
                                <span className="font-mono text-[10px] font-bold uppercase tracking-widest block" style={{ color: cfg.accent }}>
                                    {secNum} — {cfg.label}
                                </span>
                                <h3 className="text-sm font-bold text-white leading-tight">{cfg.label}</h3>
                            </div>
                        </div>

                        <div className="pl-3 pt-1">
                            {cfg.label.includes('Skills') ? (
                                <div className="flex flex-wrap gap-2 pt-1">
                                    {block.items.flatMap(item => item.split(/[,;\n]/)).map(s => s.trim()).filter(Boolean).map((skill, i) => (
                                        <motion.span
                                            key={i}
                                            whileHover={{ scale: 1.05 }}
                                            className="px-3 py-1.5 bg-[#1A1A28] border border-amber-500/30 rounded-xl text-xs font-mono font-semibold text-amber-300 shadow-sm flex items-center gap-1.5"
                                        >
                                            <Wrench className="w-3 h-3 text-amber-400" />
                                            {skill}
                                        </motion.span>
                                    ))}
                                </div>
                            ) : block.items.length === 1 && !block.items[0].includes(':') ? (
                                <div className="p-3.5 rounded-xl bg-[#1A1A26]/70 border border-[#FFFFFF0A]">
                                    <p className="text-xs leading-relaxed text-slate-200 font-medium">{block.items[0]}</p>
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                                    {block.items.map((item, i) => {
                                        const colonIdx = item.indexOf(':');
                                        const rawLabel = colonIdx > 0 && colonIdx < 35 ? item.slice(0, colonIdx).replace(/\*\*/g, '').trim() : '';
                                        const noiseWords = ['solution', 'core solution', 'objectives', 'core objectives', 'key objectives', 'problem statement', 'business context', 'expected business impact', 'business impact', 'deliverables', 'tech stack', 'technology stack', 'key features', 'requirements', 'primary goal', 'context'];
                                        const isNoiseLabel = rawLabel && noiseWords.some(w => rawLabel.toLowerCase() === w || rawLabel.toLowerCase().endsWith(' ' + w));
                                        const hasLabel = Boolean(rawLabel && !isNoiseLabel);
                                        const labelText = hasLabel ? rawLabel : '';
                                        const detailText = hasLabel ? item.slice(colonIdx + 1).trim() : item;

                                        return (
                                            <motion.div
                                                key={i}
                                                whileHover={{ scale: 1.01 }}
                                                className="flex items-start gap-2.5 p-3 rounded-xl bg-[#1A1A26]/70 border border-[#FFFFFF0A] hover:border-[#FFFFFF20] transition-all shadow-sm"
                                            >
                                                <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5" style={{ background: cfg.accent, boxShadow: `0 0 8px ${cfg.accent}` }} />
                                                <div className="text-xs text-slate-200 font-medium leading-relaxed">
                                                    {hasLabel && (
                                                        <span className="font-bold text-white uppercase tracking-wider block text-[11px] mb-0.5" style={{ color: cfg.accent }}>
                                                            {labelText}
                                                        </span>
                                                    )}
                                                    <span>{detailText}</span>
                                                </div>
                                            </motion.div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </motion.section>
                );
            })}
        </div>
    );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function flattenToStrings(val) {
    if (!val) return [];
    if (typeof val === 'string') return val.split('\n').map(s => s.trim()).filter(Boolean);
    if (Array.isArray(val)) return val.flatMap(v => flattenToStrings(v));
    if (typeof val === 'object') {
        return Object.entries(val).flatMap(([k, v]) => {
            const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const lines = flattenToStrings(v);
            if (lines.length === 1) return [`${label}: ${lines[0]}`];
            return [label + ':', ...lines.map(l => `  \u2022 ${l}`)];
        });
    }
    return [String(val)];
}

function tryParseJson(text) {
    if (!text) return null;
    if (typeof text === 'object' && !Array.isArray(text)) return text;
    if (typeof text !== 'string') return null;
    
    let trimmed = text.trim();
    if (!trimmed) return null;

    trimmed = trimmed.replace(/^```json?\s*/i, '').replace(/```\s*$/, '').trim();

    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;

    // Strict parse first; if it fails we fall through to the repair pass below.
    try { return JSON.parse(trimmed); } catch {
        // fall through to the newline-escaping repair attempt
    }

    try {
        let inString = false, escaped = false, result = '';
        for (let i = 0; i < trimmed.length; i++) {
            const char = trimmed[i];
            if (char === '"' && !escaped) {
                inString = !inString;
                result += char;
            } else if (inString) {
                if (char === '\n') result += '\\n';
                else if (char === '\r') result += '\\r';
                else if (char === '\t') result += '\\t';
                else result += char;
            } else {
                result += char;
            }
            escaped = (char === '\\' && !escaped);
        }
        return JSON.parse(result);
    } catch {
        // Repair pass failed too — the caller treats null as "not JSON".
    }

    return null;
}

const KEY_CONFIG = {
    overview:         { label: 'Project Vision & Overview', icon: FileText,   accent: '#8B5CF6', isText: true },
    summary:          { label: 'Project Vision & Overview', icon: FileText,   accent: '#8B5CF6', isText: true },
    main_description: { label: 'Project Vision & Overview', icon: FileText,   accent: '#8B5CF6', isText: true },
    objectives:       { label: 'Core Objectives',           icon: Target,     accent: '#06B6D4' },
    objective:        { label: 'Core Objectives',           icon: Target,     accent: '#06B6D4' },
    goals:            { label: 'Core Objectives',           icon: Target,     accent: '#06B6D4' },
    scope:            { label: 'Project Scope',             icon: Layers,     accent: '#10B981' },
    methodology:      { label: 'Methodology',               icon: Wrench,     accent: '#F59E0B' },
    approach:         { label: 'Methodology',               icon: Wrench,     accent: '#F59E0B' },
    tech_stack:       { label: 'Tech Stack',                icon: Code2,      accent: '#06B6D4', isTech: true },
    technology:       { label: 'Tech Stack',                icon: Code2,      accent: '#06B6D4', isTech: true },
    technologies:     { label: 'Tech Stack',                icon: Code2,      accent: '#06B6D4', isTech: true },
    deliverables:     { label: 'Deliverables',              icon: Package,    accent: '#10B981' },
    deliverable:      { label: 'Deliverables',              icon: Package,    accent: '#10B981' },
    outcomes:         { label: 'Deliverables',              icon: Package,    accent: '#10B981' },
    stakeholders:     { label: 'Stakeholders',              icon: Users,      accent: '#EC4899' },
    timeline:         { label: 'Project Timeline',          icon: Clock,      accent: '#8B5CF6' },
    phases:           { label: 'Project Timeline',          icon: Clock,      accent: '#8B5CF6' },
    budget_estimate:  { label: 'Budget Estimate',           icon: DollarSign, accent: '#F59E0B' },
    budget:           { label: 'Budget Estimate',           icon: DollarSign, accent: '#F59E0B' },
    ai_suggestions:   { label: 'AI Suggestions & Strategy', icon: Sparkles,   accent: '#8B5CF6' },
    recommendations:  { label: 'AI Suggestions & Strategy', icon: Sparkles,   accent: '#8B5CF6' },
    architecture:     { label: 'System Architecture',       icon: BarChart3,  accent: '#06B6D4' },
    system_design:    { label: 'System Architecture',       icon: BarChart3,  accent: '#06B6D4' },
};

const KEY_ORDER = ['overview','summary','main_description','objectives','objective','goals','scope','methodology','approach','tech_stack','technology','technologies','deliverables','deliverable','outcomes','ai_suggestions','recommendations','architecture','system_design','stakeholders','timeline','phases','budget_estimate','budget'];

const NOISE_KEYS = new Set([
    'id', 'ps_id', 'created_at', 'updated_at', 'is_active', 'status', 
    'validationstatus', 'isvalid', 'code', 'number', 'serial_number', 
    'sno', 'ps_code', 'ps_number', 'team_id', 'mentor', 'createdat'
]);

function buildJsonSections(obj) {
    if (!obj || Array.isArray(obj)) return { overview: '', sections: [], isJson: false };
    const usedKeys = new Set();
    let overview = '';
    for (const k of ['overview','summary','main_description','description']) {
        if (obj[k] && typeof obj[k] === 'string') { overview = obj[k]; usedKeys.add(k); break; }
    }
    const allKeys = [
        ...KEY_ORDER.filter(k => obj[k] !== undefined && !usedKeys.has(k)),
        ...Object.keys(obj).filter(k => {
            const cleanKey = k.toLowerCase().replace(/[\s\-_]+/g, '');
            if (NOISE_KEYS.has(cleanKey) || usedKeys.has(k) || KEY_ORDER.includes(k)) return false;
            if (/^\d+$/.test(k) || /^id$/i.test(cleanKey) || /^0\d/i.test(cleanKey)) return false;
            return true;
        })
    ];
    const sections = allKeys.map(key => {
        usedKeys.add(key);
        const val = obj[key];
        const cfg = KEY_CONFIG[key] || { label: key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), icon: FileText, accent: '#6C3CE1' };
        return { key, label: cfg.label, icon: cfg.icon, accent: cfg.accent, isTech: cfg.isTech || false, isText: cfg.isText || false, raw: val, bullets: flattenToStrings(val) };
    });
    return { overview, sections, isJson: true };
}

function parseDocText(text) {
    if (!text) return { overview: '', sections: [], isJson: false };
    const safeText = typeof text === 'string' ? text : Array.isArray(text) ? text.join('\n') : JSON.stringify(text, null, 2);
    let normalized = safeText.replace(/\\u2014/g, '—').replace(/\\u2013/g, '–').replace(/\r\n/g, '\n');

    // Auto-inject markdown headers before numbered section titles and standard PS section markers (only if line does not start with #)
    // "Primary Goal:" opens virtually every problem statement and is the document's
    // lead summary, not a section. Promoting it to a header at offset 0 would make
    // the first header start at index 0 and leave `overview` empty, suppressing the
    // Executive Summary card. Only treat it as a header when it appears mid-document.
    normalized = normalized.replace(
        /(\bPrimary Goal\s*:)/gi,
        (match, label, offset) => (offset === 0 ? match : `\n### ${label}\n`)
    );
    normalized = normalized.replace(/(?:\n|^)(?!\s*#)(\d+[.)]\s+[A-Z][A-Za-z0-9\s&,/\-–—]+?)(?=\s*:|\s*\n|$)/g, '\n### $1\n');
    normalized = normalized.replace(/(?:\n|^)(?!\s*#)((?:Business Context|Problem Description|Problem Statement|Core Solution|Core Objectives|Key Objectives|Key Technical Challenges|Technical Requirements|Deliverables|Evaluation Metrics|Success Criteria|Tech Stack|Features|Workflow)\s*:?)/gi, '\n### $1\n');
    normalized = normalized.replace(/\n+([\u{1F310}\u{1F3AF}\u{1F4C4}\u{1F504}\u{1F4E5}\u{1F4CA}\u2699\u{1F916}\u{1F9EA}\u{1F680}\u{1F4C8}\u{1F6E0}\u{1F4C2}\u{1F4DD}]\s+)/gu, '\n### $1');

    const firstHeaderIndex = normalized.search(/\n+###?\s+/);
    let overview = '';
    let rest = normalized;

    if (firstHeaderIndex !== -1) {
        overview = normalized.slice(0, firstHeaderIndex).trim();
        rest = normalized.slice(firstHeaderIndex).trim();
    } else {
        overview = normalized.trim();
        rest = '';
    }

    overview = overview
        .replace(/^#+\s*(?:Project\s*Overview|Overview|Project\s*Vision\s*&\s*Overview)\s*\n*/i, '')
        .replace(/^(?:Short\s*Description|Description|Overview|Project\s*Overview|Abstract|Problem\s*Statement|Primary\s*Goal)\s*:\s*/i, '')
        .trim();

    const sections = [];
    const prependedRest = rest.startsWith('#') ? '\n' + rest : rest;
    const regex = /\n*#+\s+([^\n]+)\n+([\s\S]*?)(?=\n+#+|$)/g;
    let match;
    while ((match = regex.exec(prependedRest)) !== null) {
        let rawTitle = match[1].trim();
        const content = match[2].trim();
        let title = cleanSectionTitle(rawTitle);
        title = title.replace(/\\u2014/gi, '—').replace(/\\u2013/gi, '–');
        title = title.replace(/^[\u{1F300}-\u{1F9FF}]\s*/gu, '').trim();
        // "Problem Statement 7" is an index artifact, but a bare "Problem Statement" is a
        // real section heading — the majority of PS documents open with one. Requiring a
        // digit keeps the artifact cleanup while no longer erasing the genuine heading
        // (which emptied `title` and silently dropped the whole section and its body).
        const withoutIndexPrefix = title.replace(/^Problem Statement\s*:?\s*\d+\s*[-\u2013\u2014:]*\s*/i, '').trim();
        if (withoutIndexPrefix) {
            title = withoutIndexPrefix;
        }
        const isNoise = /^(?:no\.?|s\.?no\.?|serial no\.?|\d+|problem statement\s*\d+|id|ps_id|code)$/i.test(title) || /^—?\s*id$/i.test(title) || title.toUpperCase() === 'ID';
        const cleanTitleLower = title.toLowerCase().replace(/[\s\-_]+/g, '');
        const isDupDesc = ['shortdescription','description','overview','projectvisionoverview','projectoverview','maindescription','briefdescription','problemdescription'].includes(cleanTitleLower) ||
                          (overview && content.trim().toLowerCase() === overview.trim().toLowerCase());

        if (title && content && !isNoise && !isDupDesc) {
            const bullets = content.split('\n')
                .map(l => l.trim().replace(/^[-*\u2022]\s*/, ''))
                .filter(l => l.length > 0 && !isHeaderNoise(l));
            // Chip rendering only suits short, token-like values ("React", "PostgreSQL").
            // Titles alone are not enough: "Technical Requirements & Deliverables" holds
            // full sentences, and forcing those into inline pills breaks the layout.
            const titleSuggestsTech = ['tech stack','technology','dataset','input','technical requirements'].some(k => title.toLowerCase().includes(k));
            const isTech = titleSuggestsTech && bullets.length > 0 && bullets.every(b => b.length <= TECH_CHIP_MAX_LENGTH);
            sections.push({ key: title, label: title, icon: FileText, accent: '#06B6D4', isTech, isText: false, raw: content, bullets });
        }
    }
    return { overview, sections, isJson: false };
}

function parseDoc(text) {
    if (!text) return { overview: '', sections: [], isJson: false };
    const parsed = tryParseJson(text);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const jsonResult = buildJsonSections(parsed);
        if (jsonResult.overview && (jsonResult.overview.includes('#') || jsonResult.overview.includes('\n\n'))) {
            const nestedDoc = parseDocText(jsonResult.overview);
            if (nestedDoc.sections.length > 0) {
                jsonResult.overview = nestedDoc.overview;
                jsonResult.sections = [...nestedDoc.sections, ...jsonResult.sections];
            } else if (nestedDoc.overview) {
                jsonResult.overview = nestedDoc.overview;
            }
        }
        return jsonResult;
    }
    return parseDocText(text);
}

// ─── Section Card ─────────────────────────────────────────────────────────────
function SectionCard({ section, index }) {
    const Icon = section.icon || FileText;
    const accent = section.accent || '#06B6D4';
    const secNumber = String(index + 2).padStart(2, '0');
    return (
        <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.04 }}
            className="bg-[#13131A] rounded-2xl border border-[#FFFFFF10] p-4 md:p-5 space-y-3 relative overflow-hidden shadow-md hover:border-indigo-500/30 transition-all"
        >
            <div className="absolute left-0 top-4 bottom-4 w-0.5 rounded-full" style={{ background: accent }} />
            <div className="flex items-center gap-2.5 pl-3">
                <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${accent}20`, border: `1px solid ${accent}40` }}>
                    <Icon className="w-3.5 h-3.5" style={{ color: accent }} />
                </div>
                <div>
                    <span className="font-mono text-[10px] font-bold uppercase tracking-widest block" style={{ color: accent }}>{secNumber} — {section.label}</span>
                    <h2 className="text-sm font-bold text-white leading-tight">{section.label}</h2>
                </div>
            </div>
            <div className="ml-3 w-10 h-0.5 rounded-full" style={{ background: `linear-gradient(to right, ${accent}, transparent)` }} />
            <div className="pl-3">
                {section.isTech && section.bullets.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                        {section.bullets.map((tech, i) => (
                            <span key={i} className="px-2.5 py-1 bg-[#1A1A28] border border-[#FFFFFF15] rounded-lg text-[11px] font-mono font-medium text-indigo-300 shadow-sm">{tech}</span>
                        ))}
                    </div>
                ) : section.isText || section.bullets.length === 0 ? (
                    <p className="text-xs leading-relaxed text-slate-300 whitespace-pre-wrap font-normal">{typeof section.raw === 'string' ? section.raw : section.bullets.join('\n') || 'No content.'}</p>
                ) : (
                    <ul className="space-y-2 pt-1">
                        {section.bullets.map((bullet, i) => {
                            const isSubHeading = bullet.endsWith(':') && bullet.length < 60;
                            const isIndented = bullet.startsWith('  \u2022');
                            const cleanBullet = bullet.replace(/^ {2}\u2022\s*/, '');
                            if (isSubHeading) return (<li key={i} className="text-[11px] font-bold text-white/80 mt-3 first:mt-0 uppercase tracking-wider">{bullet}</li>);

                            if (cleanBullet.includes(' | ')) {
                                const parts = cleanBullet.split(/\s*\|\s*/);
                                const col1 = parts[0];
                                const col2 = parts.slice(1).join(' | ');
                                const isHeaderRow = i === 0 && (col1.toLowerCase().includes('metric') || col1.toLowerCase().includes('name') || col1.toLowerCase().includes('item'));

                                if (isHeaderRow) {
                                    return (
                                        <li key={i} className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] font-black uppercase tracking-wider text-slate-400 p-2 border-b border-[#FFFFFF15] mb-1">
                                            <span>{col1}</span>
                                            <span>{col2}</span>
                                        </li>
                                    );
                                }

                                return (
                                    <li key={i} className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs leading-relaxed p-2.5 rounded-xl bg-[#1A1A28]/60 border border-[#FFFFFF0A] hover:border-[#FFFFFF20] transition-all">
                                        <span className="font-bold text-white flex items-center gap-2">
                                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: accent }} />
                                            {col1}
                                        </span>
                                        <span className="text-slate-300 font-mono text-[11px] bg-slate-900/40 px-2 py-1 rounded-md border border-[#FFFFFF0A] self-start">{col2}</span>
                                    </li>
                                );
                            }

                            return (
                                <li key={i} className={`flex items-start gap-2.5 text-xs text-slate-300 leading-relaxed p-2.5 rounded-xl border border-[#FFFFFF08] ${isIndented ? 'ml-4 bg-[#1A1A28]/30' : 'bg-[#1A1A28]/50'}`}>
                                    <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5" style={{ background: accent }} />
                                    <span className="flex-1">{cleanBullet}</span>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </motion.section>
    );
}

export default function PsArchitecturePlanModal({ ps, onClose, onGenerateAi, aiGenerating = false, allocation = null, _isStudent = false }) {
    // The `if (!ps) return null` guard that used to sit here ran BEFORE the hooks
    // below, so a render with no `ps` executed zero hooks and the next render
    // executed five — React throws "Rendered more hooks than during the previous
    // render". Every hook is now unconditional and the guard moved below the last
    // one; the derived values in between are null-safe so they survive ps == null.
    const [currentPs, setCurrentPs] = useState(ps);
    const [isGenerating, setIsGenerating] = useState(false);
    const autoEnrichedPsIdRef = useRef(null);

    useEffect(() => {
        if (ps) {
            const incomingDesc = ps.description || '';
            const cleanTitle = (ps.title || '').trim().toLowerCase();
            const cleanDesc = incomingDesc.trim().toLowerCase();
            const isTitleOnly = !incomingDesc || cleanDesc === cleanTitle || cleanDesc.replace(/^[\s#\-*:]+/, '') === cleanTitle || incomingDesc.length < 60;
            const hasIncomingBlueprint = !isTitleOnly && (incomingDesc.includes('###') || incomingDesc.length > 200);

            if (currentPs?.id !== ps.id || hasIncomingBlueprint) {
                setCurrentPs(ps);
            }
        }
    }, [ps?.id, ps?.description]);

    const doc = parseDoc(currentPs?.description);
    const descText = (currentPs?.description || '').trim();
    const cleanTitle = (currentPs?.title || '').trim().toLowerCase();
    const cleanDesc = descText.toLowerCase();
    const isTitleOnly = !descText || cleanDesc === cleanTitle || cleanDesc.replace(/^[\s#\-*:]+/, '') === cleanTitle || descText.length < 60;
    const hasRealBlueprint = !isTitleOnly && ((doc?.sections?.length || 0) > 0 || descText.includes('### Real-World') || descText.includes('### Core Objectives') || descText.includes('### Key Features') || descText.includes('### Tech Stack') || descText.length > 200);

    const isLoading = aiGenerating || isGenerating;
    const showLoading = isLoading;

    const handleEnrich = async () => {
        if (isGenerating) return;
        setIsGenerating(true);
        try {
            let enrichedData = null;
            if (onGenerateAi) {
                try {
                    const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('AI generation timed out')), 15000));
                    const res = await Promise.race([onGenerateAi(currentPs), timeoutPromise]);
                    if (res && res.description) {
                        enrichedData = res;
                    }
                } catch (aiErr) {
                    console.warn("AI generation failed or timed out:", aiErr);
                }
            }

            if (!enrichedData) {
                try {
                    const apiBase = getApiBaseUrl();
                    const token = localStorage.getItem('token') || localStorage.getItem('student_token') || localStorage.getItem('adminToken') || sessionStorage.getItem('token');
                    const reqHeaders = {
                        'Content-Type': 'application/json',
                        ...(token ? { 'Authorization': `Bearer ${token}` } : {})
                    };
                    const payloadStr = JSON.stringify({
                        id: currentPs.id,
                        title: currentPs.title,
                        description: currentPs.description,
                        domain: currentPs.domain,
                        difficulty: currentPs.difficulty
                    });

                    const url = `${apiBase}/api/student/problem-statements/generate-ai-suggestions`;
                    const controller = new AbortController();
                    const timer = setTimeout(() => controller.abort(), 5000);
                    const resp = await fetch(url, { method: 'POST', headers: reqHeaders, body: payloadStr, signal: controller.signal });
                    clearTimeout(timer);
                    if (resp.ok) {
                        const resData = await resp.json();
                        const data = resData.data || resData;
                        if (data && data.description) {
                            enrichedData = data;
                        }
                    }
                } catch (fetchErr) {
                    console.warn("Direct fetch suggestions fallback failed:", fetchErr);
                }
            }

            let finalDesc = enrichedData?.description || '';
            if (!finalDesc || !finalDesc.includes('###')) {
                finalDesc = `${currentPs.title} is an engineering project focused on building an end-to-end scalable application.

### Real-World Application
- Automated processing and real-time monitoring for ${currentPs.title}.
- Data-driven insights and optimization workflows.

### Core Objectives
- Design and develop the core application system architecture.
- Implement robust backend data processing pipelines and APIs.
- Provide an intuitive interactive dashboard interface.

### Key Features
- High-performance data ingestion and real-time processing module.
- Modular architecture with secure authentication and role management.
- Comprehensive analytics reporting and monitoring interface.

### Tech Stack & Tools
- ${currentPs.domain === 'Hardware' ? 'Arduino / Raspberry Pi / C++ / Embedded C' : 'Python / Node.js / React / FastAPI / PyTorch'}
- PostgreSQL / MongoDB
- Docker & CI/CD Pipelines

### Expected Deliverables
- Fully functional source code repository with technical documentation.
- System Architecture Diagram and API specification document.
- Live demonstration prototype and final project report.`;
            }

            setCurrentPs(prev => ({
                ...prev,
                description: finalDesc,
                domain: enrichedData?.domain || prev.domain,
                difficulty: enrichedData?.difficulty || prev.difficulty
            }));
        } catch (err) {
            console.error('Self AI generation error:', err);
        } finally {
            setIsGenerating(false);
        }
    };

    useEffect(() => {
        if (!currentPs || !currentPs.id) return;
        if (!hasRealBlueprint && !isGenerating) {
            if (autoEnrichedPsIdRef.current !== currentPs.id) {
                autoEnrichedPsIdRef.current = currentPs.id;
                handleEnrich();
            }
        }
    }, [currentPs?.id, currentPs?.description]);

    // Now that every hook above has run unconditionally, it is safe to bail out.
    if (!ps || !currentPs) return null;
    return (
        <AnimatePresence>
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-3 sm:p-4 overflow-hidden">
                {/* Dark Backdrop */}
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={onClose}
                    className="fixed inset-0 bg-[#060609]/80 backdrop-blur-md"
                />

                {/* Main Modal Container styled after HireAI - Compact Version */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.96, y: 15 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.96, y: 15 }}
                    transition={{ type: 'spring', damping: 25, stiffness: 240 }}
                    className="relative w-full max-w-3xl bg-[#0A0A0F] text-[#E8E6E1] rounded-2xl shadow-[0_0_50px_rgba(108,60,225,0.25)] border border-[#FFFFFF15] overflow-hidden z-10 flex flex-col max-h-[85vh] font-[#DM Sans]"
                >
                    {/* Background Radial Lights */}
                    <div className="absolute top-0 right-0 w-[350px] h-[350px] bg-[radial-gradient(circle,rgba(108,60,225,0.15)_0%,transparent_70%)] pointer-events-none rounded-full" />
                    <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-[radial-gradient(circle,rgba(16,185,129,0.1)_0%,transparent_70%)] pointer-events-none rounded-full" />

                    {/* Top Fixed Nav Bar */}
                    <div className="sticky top-0 z-50 bg-[#0A0A0FB5] backdrop-blur-2xl border-b border-[#FFFFFF10] px-5 py-3 flex items-center justify-between shrink-0">
                        <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#6C3CE1] to-[#06B6D4] flex items-center justify-center text-white font-black text-[11px] shadow-sm">
                                AI
                            </div>
                            <h4 className="text-xs font-bold tracking-tight text-white flex items-center gap-2">
                                PMS Architecture Blueprint
                                <span className="px-2 py-0.5 rounded-full bg-[#6C3CE1]/20 border border-[#6C3CE1]/40 text-[#8B5CF6] text-[10px] font-mono font-bold uppercase">
                                    {String(currentPs.id).startsWith('PS-') ? currentPs.id : `PS-${currentPs.id}`}
                                </span>
                            </h4>
                        </div>

                        <div className="flex items-center gap-2">
                            <button
                                onClick={onClose}
                                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-[#FFFFFF10] transition-colors cursor-pointer"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        </div>
                    </div>

                    {/* Scrollable Body */}
                    <div className="p-4 md:p-6 space-y-4 overflow-y-auto flex-1 custom-scrollbar relative z-10">

                        {/* Hero Header Section - Compact */}
                        <div className="relative p-5 bg-[#13131A] rounded-2xl border border-[#FFFFFF10] overflow-hidden shadow-md space-y-3">
                            <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-[#6C3CE1] via-[#06B6D4] to-[#10B981]" />
                            <div className="space-y-2">
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-[#6C3CE1]/15 text-[#8B5CF6] border border-[#6C3CE1]/30 rounded-full text-[10px] font-mono font-semibold uppercase tracking-wider">
                                    <Sparkles className="w-3 h-3" /> Project Specification Blueprint
                                </div>
                                <h2 className="text-lg md:text-xl font-bold text-white tracking-tight leading-snug">
                                    {currentPs.title}
                                </h2>
                                <div className="flex flex-wrap items-center gap-2 pt-1">
                                    <span className="px-2.5 py-1 bg-[#FFFFFF08] border border-[#FFFFFF10] text-slate-300 rounded-lg text-xs font-medium flex items-center gap-1.5">
                                        <Tag className="w-3 h-3 text-[#06B6D4]" /> Domain: {currentPs.domain || 'General'}
                                    </span>
                                    {allocation ? (
                                        <div className="px-2.5 py-1 bg-[#6C3CE1]/10 border border-[#6C3CE1]/30 text-[#8B5CF6] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <Users className="w-3 h-3" /> {String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id || '').trim()
                                                ? `Allocated to ${String(allocation.team_label || allocation.team_name || allocation.team_id || allocation.id).trim()}`
                                                : 'Allocated'}
                                        </div>
                                    ) : (
                                        <div className="px-2.5 py-1 bg-[#10B981]/10 border border-[#10B981]/30 text-[#10B981] rounded-lg text-xs font-medium flex items-center gap-1">
                                            <CheckCircle className="w-3 h-3" /> Available for Selection
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Executive Summary Card */}
                        {hasRealBlueprint && doc.overview && (
                            <ExecutiveSummaryCard overview={doc.overview} />
                        )}

                        {/* Loading State / Shimmer Skeleton */}
                        {showLoading && (
                            <div className="bg-[#13131A] rounded-2xl border border-[#6C3CE1]/30 p-6 text-center space-y-4 shadow-lg relative overflow-hidden">
                                <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-[#6C3CE1] via-[#06B6D4] to-[#10B981] animate-pulse" />
                                <Sparkles className="w-8 h-8 text-[#8B5CF6] animate-spin mx-auto" />
                                <div className="space-y-1">
                                    <h3 className="text-xs font-mono font-bold tracking-widest text-[#8B5CF6] uppercase">AI Agent Generating Blueprint Specs...</h3>
                                    <p className="text-[11px] text-slate-400">Expanding project objectives, tech stack, deliverables & system architecture using OpenAI.</p>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                                    <div className="h-16 bg-[#1A1A28]/80 rounded-xl border border-[#FFFFFF08] animate-pulse"></div>
                                    <div className="h-16 bg-[#1A1A28]/80 rounded-xl border border-[#FFFFFF08] animate-pulse"></div>
                                    <div className="h-16 bg-[#1A1A28]/80 rounded-xl border border-[#FFFFFF08] animate-pulse"></div>
                                    <div className="h-16 bg-[#1A1A28]/80 rounded-xl border border-[#FFFFFF08] animate-pulse"></div>
                                </div>
                            </div>
                        )}

                        {/* Dynamic Sections */}
                        {hasRealBlueprint && doc.sections.map((section, idx) => (
                            <SectionCard key={section.key + idx} section={section} index={idx} />
                        ))}

                        {/* Plain Description Fallback when no structured blueprint headers exist */}
                        {!hasRealBlueprint && !showLoading && (
                            <div className="bg-[#13131A] rounded-2xl border border-[#FFFFFF10] p-5 space-y-3">
                                <h4 className="text-xs font-mono font-bold tracking-wider text-[#06B6D4] uppercase flex items-center gap-2">
                                    <Sparkles className="w-4 h-4 text-[#06B6D4]" /> Project Overview & Description
                                </h4>
                                <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-line">
                                    {descText || `${currentPs.title} is an engineering project focused on building an end-to-end scalable application.`}
                                </p>
                            </div>
                        )}

                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
}
