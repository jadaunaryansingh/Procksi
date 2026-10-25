/**
 * WalkthroughOverlay
 *
 * Spotlight + tooltip for the mentor first-login tour.
 *
 * Built on framer-motion rather than a tour library: framer-motion is
 * already a dependency and is what the rest of this portal animates with,
 * so the overlay inherits the existing dark-mode tokens instead of needing
 * a library's theme overridden into shape.
 *
 * The spotlight is one full-screen element with a very large box-shadow
 * spread. The shadow paints the dim everywhere except the element's own
 * rect, which gives a cutout without an SVG mask or four separate panels.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { X, ArrowLeft, ArrowRight } from 'lucide-react';

const PADDING = 8;      // breathing room between the highlight and the element
const GAP = 14;         // distance from the highlight to the tooltip
const TOOLTIP_W = 320;
const MARGIN = 12;      // keep the tooltip this far from the viewport edge

function rectOf(anchor) {
    if (!anchor) return null;
    const el = document.querySelector(`[data-tour="${anchor}"]`);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    // A zero-size rect means the element is present but not laid out
    // (display:none, or an unmounted drawer). Treat it as absent.
    if (r.width === 0 && r.height === 0) return null;
    return r;
}

/**
 * Choose where the tooltip sits. `placement` is a preference; a tooltip
 * that would land off-screen flips to the opposite side, and one that fits
 * nowhere falls back to centered.
 */
function positionFor(rect, placement) {
    if (!rect) return { centered: true };

    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const fits = {
        right: rect.right + GAP + TOOLTIP_W + MARGIN < vw,
        left: rect.left - GAP - TOOLTIP_W - MARGIN > 0,
        bottom: rect.bottom + GAP + 160 + MARGIN < vh,
        top: rect.top - GAP - 160 - MARGIN > 0,
    };

    const order = {
        right: ['right', 'left', 'bottom', 'top'],
        left: ['left', 'right', 'bottom', 'top'],
        bottom: ['bottom', 'top', 'right', 'left'],
        top: ['top', 'bottom', 'right', 'left'],
    }[placement] || ['bottom', 'top', 'right', 'left'];

    const chosen = order.find((p) => fits[p]);
    if (!chosen) return { centered: true };

    if (chosen === 'right' || chosen === 'left') {
        const left = chosen === 'right' ? rect.right + GAP : rect.left - GAP - TOOLTIP_W;
        // Vertically centre on the element, then clamp into the viewport.
        const top = Math.min(
            Math.max(rect.top + rect.height / 2 - 80, MARGIN),
            vh - 160 - MARGIN,
        );
        return { top, left, centered: false };
    }

    const top = chosen === 'bottom' ? rect.bottom + GAP : rect.top - GAP - 160;
    const left = Math.min(
        Math.max(rect.left + rect.width / 2 - TOOLTIP_W / 2, MARGIN),
        vw - TOOLTIP_W - MARGIN,
    );
    return { top, left, centered: false };
}

export default function WalkthroughOverlay({
    isOpen, step, index, steps, isFirst, isLast, next, back, close,
}) {
    const [rect, setRect] = useState(null);
    const cardRef = useRef(null);

    const anchor = step?.anchor ?? null;

    const measure = useCallback(() => {
        setRect(rectOf(anchor));
    }, [anchor]);

    // Scroll the anchor into view, then measure once the scroll settles.
    //
    // Measuring is a DOM read, which is exactly the external-system
    // synchronisation an effect is for -- the rect cannot be derived during
    // render because it does not exist until after layout. The measurement
    // is therefore scheduled rather than called synchronously, so this stays
    // off the render path.
    useLayoutEffect(() => {
        if (!isOpen) return undefined;

        const el = anchor ? document.querySelector(`[data-tour="${anchor}"]`) : null;

        if (el) {
            const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            el.scrollIntoView({
                block: 'center',
                inline: 'nearest',
                behavior: reduced ? 'auto' : 'smooth',
            });
        }

        // Measure on the next frame, then again as the smooth scroll settles.
        // rectOf() returns null for a missing or unlaid-out anchor, so a step
        // without one correctly falls back to the centered treatment.
        const frame = requestAnimationFrame(measure);
        const timers = [60, 160, 320, 520].map((ms) => window.setTimeout(measure, ms));
        return () => {
            cancelAnimationFrame(frame);
            timers.forEach(window.clearTimeout);
        };
    }, [isOpen, anchor, measure]);

    // Rects go stale on resize and when the sidebar rail collapses.
    useEffect(() => {
        if (!isOpen) return undefined;
        const onChange = () => measure();
        window.addEventListener('resize', onChange);
        window.addEventListener('scroll', onChange, true);
        return () => {
            window.removeEventListener('resize', onChange);
            window.removeEventListener('scroll', onChange, true);
        };
    }, [isOpen, measure]);

    // Keyboard: Escape dismisses (counts as Skip), arrows move.
    useEffect(() => {
        if (!isOpen) return undefined;
        const onKey = (e) => {
            if (e.key === 'Escape') { e.preventDefault(); close(); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); next(); }
            else if (e.key === 'ArrowLeft' && !isFirst) { e.preventDefault(); back(); }
        };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [isOpen, close, next, back, isFirst]);

    // Move focus into the card so the tour is reachable without a mouse.
    useEffect(() => {
        if (isOpen && cardRef.current) cardRef.current.focus();
    }, [isOpen, index]);

    if (!isOpen || !step) return null;

    const pos = positionFor(rect, step.placement);

    return createPortal(
        <AnimatePresence>
            <motion.div
                key="walkthrough"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="fixed inset-0 z-[100]"
                aria-live="polite"
            >
                {/* Dim + cutout. Clicking the dim skips, matching the close button. */}
                {rect ? (
                    <motion.div
                        className="absolute rounded-xl pointer-events-none"
                        initial={false}
                        animate={{
                            top: rect.top - PADDING,
                            left: rect.left - PADDING,
                            width: rect.width + PADDING * 2,
                            height: rect.height + PADDING * 2,
                        }}
                        transition={{ type: 'spring', stiffness: 380, damping: 34 }}
                        style={{ boxShadow: '0 0 0 9999px rgba(2, 6, 23, 0.72)' }}
                    />
                ) : (
                    <div className="absolute inset-0 bg-slate-950/72" />
                )}

                {/* Click-catcher for the dimmed area. */}
                <button
                    type="button"
                    aria-label="Skip walkthrough"
                    onClick={close}
                    className="absolute inset-0 w-full h-full cursor-default"
                    tabIndex={-1}
                />

                <motion.div
                    ref={cardRef}
                    tabIndex={-1}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="walkthrough-title"
                    initial={{ opacity: 0, scale: 0.97 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.18 }}
                    className={`absolute w-[320px] max-w-[calc(100vw-24px)] bg-white dark:bg-slate-800
                        border border-slate-200 dark:border-slate-700 rounded-2xl shadow-2xl p-5
                        focus:outline-none focus:ring-2 focus:ring-indigo-500/60 ${
                        pos.centered ? 'left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2' : ''
                    }`}
                    style={pos.centered ? undefined : { top: pos.top, left: pos.left }}
                >
                    <div className="flex items-start justify-between gap-3 mb-2">
                        <h2
                            id="walkthrough-title"
                            className="text-base font-black text-slate-900 dark:text-slate-100 leading-snug"
                        >
                            {step.title}
                        </h2>
                        <button
                            type="button"
                            onClick={close}
                            aria-label="Skip walkthrough"
                            className="p-1 -m-1 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200
                                rounded-lg transition-colors shrink-0"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed mb-4">
                        {step.body}
                    </p>

                    <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-1.5" aria-hidden="true">
                            {steps.map((s, i) => (
                                <span
                                    key={s.id}
                                    className={`h-1.5 rounded-full transition-all ${
                                        i === index
                                            ? 'w-4 bg-indigo-500'
                                            : 'w-1.5 bg-slate-300 dark:bg-slate-600'
                                    }`}
                                />
                            ))}
                        </div>

                        <div className="flex items-center gap-2">
                            {!isFirst && (
                                <button
                                    type="button"
                                    onClick={back}
                                    className="p-2 text-slate-500 hover:text-slate-800 dark:text-slate-400
                                        dark:hover:text-slate-100 rounded-lg hover:bg-slate-100
                                        dark:hover:bg-slate-700/60 transition-colors"
                                    aria-label="Previous step"
                                >
                                    <ArrowLeft className="w-4 h-4" />
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={next}
                                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600
                                    hover:bg-indigo-700 text-white text-sm font-bold transition-colors
                                    focus:outline-none focus:ring-2 focus:ring-indigo-500/60"
                            >
                                {isLast ? 'Done' : 'Next'}
                                {!isLast && <ArrowRight className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    <p className="sr-only">
                        Step {index + 1} of {steps.length}
                    </p>
                </motion.div>
            </motion.div>
        </AnimatePresence>,
        document.body,
    );
}
