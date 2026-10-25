import React from 'react';
import { motion } from 'framer-motion';
import { X, Loader2, Bot, ClipboardCheck, Users, MessageSquare, GitBranch, AlertTriangle } from 'lucide-react';

/**
 * Rendering for the /report command.
 *
 * Two components live here, and the split matters:
 *
 *   ChatReportCard    — the transient composer affordance. It shows the option
 *                       picker, the "working" state, and any failure. It is
 *                       never the report itself.
 *   ChatReportMessage — a stored report, posted into the thread by PMSbot and
 *                       read back out of conversation_messages like any other
 *                       message. Everyone in the thread sees it, and it stays.
 *
 * Every figure here is computed server-side from database rows. The only
 * model-derived content is the task list, and each task carries the sentence it
 * was read from — shown in the UI, so a reader can check the machine's work
 * rather than take it on trust.
 */

const Stat = ({ label, value, tone = 'plain' }) => (
    <div className="bg-slate-50 dark:bg-slate-900/40 rounded-xl p-2.5">
        <p className="text-[9px] font-black uppercase tracking-widest text-slate-400">{label}</p>
        <p className={`text-lg font-black ${tone === 'warn'
            ? 'text-amber-600 dark:text-amber-400'
            : 'text-slate-800 dark:text-white'}`}>
            {value ?? '—'}
        </p>
    </div>
);

const Section = ({ icon: Icon, title, children }) => (
    <div className="border-t border-slate-100 dark:border-slate-700/50 pt-3 mt-3 first:border-0 first:pt-0 first:mt-0">
        <p className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">
            <Icon className="w-3 h-3" /> {title}
        </p>
        {children}
    </div>
);

const Unavailable = ({ children }) => (
    <p className="flex items-start gap-2 text-xs font-medium text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 rounded-xl p-2.5">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>{children}</span>
    </p>
);

/**
 * The report itself. Driven entirely by the stored payload, so it renders the
 * same whether the report was generated a second ago or last month.
 */
export const ReportBody = ({ data }) => {
    if (!data) return null;

    if (data.option === 'weekly-github') {
        return data.weeks_available === 0
            ? <Unavailable>{data.unavailable_reason}</Unavailable>
            : (
                <div className="space-y-1.5">
                    <p className="text-xs font-bold text-slate-500 dark:text-slate-400 mb-2">
                        {data.weeks_available} report{data.weeks_available === 1 ? '' : 's'} available
                    </p>
                    {(data.weeks || []).map(w => (
                        <div key={w.id} className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700">
                            <span className="min-w-0">
                                <span className="block text-sm font-bold text-slate-800 dark:text-white truncate">
                                    {/* A panel's report spans several teams, so each row
                                        names one. Single-team reports carry no label. */}
                                    {w.team_label ? `${w.team_label} · ` : ''}
                                    {new Date(w.generated_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                                </span>
                                {w.repository_url && (
                                    <span className="block text-[10px] font-medium text-slate-400 truncate">
                                        {w.repository_url}
                                    </span>
                                )}
                            </span>
                            <span className="shrink-0 text-[11px] font-medium text-slate-400 tabular-nums">
                                {w.commit_count_30d ?? '—'} commits
                            </span>
                        </div>
                    ))}
                </div>
            );
    }

    // Everything else is the analysis report. The panel calls its variant
    // "thread-analysis" because it covers its own conversations rather than a
    // team's, but the shape is identical, so it renders through here too.
    const health = data.health || {};
    const tasks = data.tasks || [];
    const workload = data.workload || {};
    const communication = data.communication || {};
    const extraction = data.extraction || {};
    const github = data.github || {};

    return (
        <div className="space-y-0">
            <Section icon={ClipboardCheck} title="Overall health">
                <div className="grid grid-cols-3 gap-2">
                    <Stat label="Tasks" value={`${health.tasks_completed ?? 0}/${health.tasks_total ?? 0}`} />
                    <Stat label="Overdue" value={health.tasks_overdue ?? 0}
                        tone={health.tasks_overdue > 0 ? 'warn' : 'plain'} />
                    <Stat label="Milestones" value={`${health.milestones_completed ?? 0}/${health.milestones_total ?? 0}`} />
                </div>
            </Section>

            <Section icon={Users} title="Tasks agreed in chat">
                {!extraction.available ? (
                    <Unavailable>{extraction.reason}</Unavailable>
                ) : tasks.length === 0 ? (
                    <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                        No tasks found in {extraction.messages_scanned ?? 0} messages. Tasks are picked up
                        when someone asks for specific work in the chat, e.g. “Aryan, please finish the
                        login page by Friday”.
                    </p>
                ) : (
                    <div className="space-y-1.5">
                        {tasks.map((t, i) => (
                            <div key={i} className="px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700">
                                <div className="flex items-start justify-between gap-2">
                                    <span className="text-sm font-bold text-slate-800 dark:text-white">{t.title}</span>
                                    <span className={`shrink-0 px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider ${t.status === 'done'
                                        ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                                        : 'bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-300'}`}>
                                        {t.status}
                                    </span>
                                </div>
                                <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mt-0.5">
                                    {t.assignee || 'Unassigned'}
                                    {t.due_date ? ` · due ${t.due_date}` : ''}
                                    {t.priority === 'high' ? ' · high priority' : ''}
                                </p>
                                {/* The receipt. Read from the thread, quoted back, so the
                                    reader can verify rather than trust. */}
                                <p className="text-[10px] italic text-slate-400 mt-1 truncate" title={t.evidence}>
                                    “{t.evidence}”
                                </p>
                            </div>
                        ))}
                    </div>
                )}
            </Section>

            {tasks.length > 0 && (
                <Section icon={Users} title="Workload">
                    <div className="grid grid-cols-2 gap-2 mb-2">
                        <Stat label="Most loaded" value={workload.most_loaded} />
                        <Stat label="Least loaded" value={workload.least_loaded} />
                    </div>
                    {workload.imbalanced && (
                        <Unavailable>
                            {workload.most_loaded} has {workload.imbalance} more open tasks than
                            {' '}{workload.least_loaded}. Worth redistributing.
                        </Unavailable>
                    )}
                </Section>
            )}

            <Section icon={MessageSquare} title="Communication">
                <div className="grid grid-cols-3 gap-2">
                    <Stat label="Messages" value={communication.messages_sent_total} />
                    <Stat label="Avg reply" value={communication.average_response_time_human} />
                    <Stat label="Unanswered" value={communication.unanswered_messages}
                        tone={communication.unanswered_messages > 0 ? 'warn' : 'plain'} />
                </div>
                {(communication.pending_questions || []).length > 0 && (
                    <div className="mt-2 space-y-1">
                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Waiting on a reply</p>
                        {communication.pending_questions.map(q => (
                            <p key={q.id} className="text-[11px] font-medium text-slate-500 dark:text-slate-400 truncate">
                                <span className="font-bold">{q.from}:</span> “{q.excerpt}”
                            </p>
                        ))}
                    </div>
                )}
            </Section>

            <Section icon={GitBranch} title="Repository">
                {!github.available ? (
                    <Unavailable>{github.reason}</Unavailable>
                ) : (
                    <div className="grid grid-cols-2 gap-2">
                        <Stat label="Total commits" value={github.total_commits} />
                        <Stat label="Contributors" value={github.contributors?.length ?? 0} />
                    </div>
                )}
            </Section>
        </div>
    );
};

/**
 * A stored report, in the thread, authored by PMSbot.
 *
 * `message` is a conversation_messages row. The structured payload lives in
 * metadata.report; message.body holds a plain-text rendering of the same thing
 * and is what we fall back to if an older row arrives without metadata.
 */
export const ChatReportMessage = ({ message, timeLabel }) => {
    const report = message?.metadata?.report ?? null;
    const title = report?.option === 'weekly-github' ? 'Weekly GitHub' : 'Analysis';

    return (
        <div className="w-full rounded-2xl border border-sky-200 dark:border-sky-500/30 bg-white dark:bg-slate-800 shadow-sm overflow-hidden">
            <div className="px-4 py-2.5 bg-sky-50 dark:bg-sky-500/10 flex items-center gap-2">
                <Bot className="w-3.5 h-3.5 text-sky-500 dark:text-sky-300" />
                <p className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300">
                    PMSbot
                </p>
                <span className="text-[10px] font-black uppercase tracking-widest text-sky-400 font-mono">
                    /report · {title}
                </span>
                {timeLabel && (
                    <span className="ml-auto text-[10px] font-semibold tabular-nums text-sky-400">
                        {timeLabel}
                    </span>
                )}
            </div>
            <div className="p-4">
                {report
                    ? <ReportBody data={report} />
                    : <p className="text-sm font-medium whitespace-pre-wrap text-slate-700 dark:text-slate-200">
                        {message?.body}
                    </p>}
            </div>
        </div>
    );
};

/**
 * The composer affordance: pick what to run, watch it run, see it fail.
 *
 * It deliberately never renders a finished report. The report is a message now,
 * so showing it here as well would put the same content on screen twice and
 * imply it was private.
 */
export const ChatReportCard = ({ state, onChoose, onDismiss }) => {
    const { loading, error, data } = state;

    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-sky-200 dark:border-sky-500/30 bg-white dark:bg-slate-800 shadow-lg overflow-hidden">

            <div className="px-4 py-2.5 bg-sky-50 dark:bg-sky-500/10 flex items-center justify-between gap-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-sky-700 dark:text-sky-300 font-mono">
                    /report
                </p>
                <button type="button" onClick={onDismiss} title="Dismiss"
                    className="p-1 text-sky-400 hover:text-sky-700 dark:hover:text-sky-200 rounded-md">
                    <X className="w-3.5 h-3.5" />
                </button>
            </div>

            <div className="p-4">
                {loading && (
                    <p className="flex items-center gap-2 text-sm font-bold text-slate-400">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Working — PMSbot will post the report in this chat…
                    </p>
                )}

                {!loading && error && <Unavailable>{error}</Unavailable>}

                {!loading && !error && data?.step === 'choose' && (
                    <div className="space-y-2">
                        {data.options.map(opt => (
                            <button key={opt.id} type="button" onClick={() => onChoose(opt.id)}
                                className="w-full text-left px-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:border-sky-400 hover:bg-sky-50/50 dark:hover:bg-sky-500/10 transition-colors">
                                <span className="block text-sm font-black text-slate-800 dark:text-white">{opt.label}</span>
                                <span className="block text-[11px] font-medium text-slate-500 dark:text-slate-400">{opt.description}</span>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </motion.div>
    );
};

export default ChatReportCard;
