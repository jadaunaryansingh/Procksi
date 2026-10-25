/**
 * useWalkthrough
 *
 * Owns the first-login walkthrough: whether it is open, which step is
 * showing, and the localStorage flag that stops it running twice.
 *
 * The portal has no notion of a "new" mentor -- there is no first_login or
 * created_at check in AuthContext -- so "has this been seen" is the absence
 * of the storage key. Existing mentors therefore see it once, which is the
 * intended behaviour for a first rollout.
 *
 * The key is versioned. When the navigation changes materially, bump it so
 * the tour runs once more for everyone rather than leaving mentors on a
 * stale mental model.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DESKTOP_STEPS, MOBILE_STEPS } from '../components/Walkthrough/steps';

export const WALKTHROUGH_KEY = 'pms-mentor-walkthrough-v1';

/** Matches Tailwind's `md`. Below this the sidebar is a drawer. */
const MOBILE_QUERY = '(max-width: 767px)';

/** How long to wait for the dashboard's first fetch to paint before giving up. */
const ANCHOR_WAIT_MS = 2000;
const ANCHOR_POLL_MS = 100;

function hasSeen() {
    try {
        return localStorage.getItem(WALKTHROUGH_KEY) === 'seen';
    } catch {
        // Private mode or storage disabled. Treat as seen: a tour that
        // cannot remember being dismissed would reopen on every navigation,
        // which is far worse than never showing it.
        return true;
    }
}

function markSeen() {
    try {
        localStorage.setItem(WALKTHROUGH_KEY, 'seen');
    } catch {
        // Nothing to do -- see hasSeen().
    }
}

function anchorPresent(step) {
    if (!step?.anchor) return true; // centered steps need no anchor
    return Boolean(document.querySelector(`[data-tour="${step.anchor}"]`));
}

export function useWalkthrough() {
    const [isMobile, setIsMobile] = useState(
        () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches,
    );
    const [isOpen, setIsOpen] = useState(false);
    const [index, setIndex] = useState(0);

    // Which element had focus when the tour opened, so it can be restored.
    const restoreFocusRef = useRef(null);

    const allSteps = isMobile ? MOBILE_STEPS : DESKTOP_STEPS;

    // Steps whose anchor is actually on the page. A mentor with no assigned
    // teams may never render the stat cards, and a step pointing at a missing
    // element would spotlight nothing.
    const [presentIds, setPresentIds] = useState(null);

    const steps = useMemo(() => {
        if (!presentIds) return allSteps;
        return allSteps.filter((s) => presentIds.includes(s.id));
    }, [allSteps, presentIds]);

    useEffect(() => {
        const mql = window.matchMedia(MOBILE_QUERY);
        const onChange = (e) => setIsMobile(e.matches);
        mql.addEventListener('change', onChange);
        return () => mql.removeEventListener('change', onChange);
    }, []);

    // Open on first visit -- but only once the anchors exist. MentorHome
    // fetches on mount, so the stat cards are absent for the first few
    // hundred milliseconds and opening immediately would spotlight a
    // half-built page.
    useEffect(() => {
        if (hasSeen()) return undefined;

        let cancelled = false;
        const startedAt = Date.now();

        const tick = () => {
            if (cancelled) return;

            const found = allSteps.filter(anchorPresent).map((s) => s.id);
            const anchored = allSteps.filter((s) => s.anchor);
            const anyAnchorReady = anchored.some((s) => found.includes(s.id));

            if (anyAnchorReady || Date.now() - startedAt > ANCHOR_WAIT_MS) {
                // Give up quietly if nothing ever appeared: better to show no
                // tour than one that highlights empty space.
                if (!anyAnchorReady) return;
                restoreFocusRef.current = document.activeElement;
                setPresentIds(found);
                setIndex(0);
                setIsOpen(true);
                return;
            }
            window.setTimeout(tick, ANCHOR_POLL_MS);
        };

        const id = window.setTimeout(tick, ANCHOR_POLL_MS);
        return () => {
            cancelled = true;
            window.clearTimeout(id);
        };
    }, [allSteps]);

    const close = useCallback(() => {
        markSeen();
        setIsOpen(false);
        const el = restoreFocusRef.current;
        if (el && typeof el.focus === 'function') el.focus();
        restoreFocusRef.current = null;
    }, []);

    const next = useCallback(() => {
        setIndex((i) => {
            if (Math.min(i, steps.length - 1) >= steps.length - 1) {
                // Defer so we are not calling close() during the updater.
                queueMicrotask(close);
                return i;
            }
            return i + 1;
        });
    }, [steps.length, close]);

    const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

    /** Replay from the help button: clear the flag and reopen at step 0. */
    const restart = useCallback(() => {
        const found = allSteps.filter(anchorPresent).map((s) => s.id);
        restoreFocusRef.current = document.activeElement;
        setPresentIds(found);
        setIndex(0);
        setIsOpen(true);
    }, [allSteps]);

    // Guard against the step list shrinking under us (e.g. a resize swaps the
    // desktop steps for the shorter mobile list while the tour is open).
    // Derived during render rather than corrected in an effect, so there is
    // no frame where `index` points past the end of `steps`.
    const safeIndex = steps.length ? Math.min(index, steps.length - 1) : 0;

    return {
        isOpen,
        index: safeIndex,
        steps,
        step: steps[safeIndex] ?? null,
        isFirst: safeIndex === 0,
        isLast: safeIndex === steps.length - 1,
        next,
        back,
        close,
        restart,
    };
}
