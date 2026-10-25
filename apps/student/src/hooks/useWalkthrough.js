/**
 * useWalkthrough -- per-page walkthrough driver.
 *
 * Extends the mentor portal's first-login tour with per-page tours. Two
 * things are remembered separately in localStorage:
 *
 *   <prefix>-overview   the first-login orientation has been seen
 *   <prefix>-<route>    that page's own tour has been seen
 *
 * So a first-time user gets the orientation once, then a short page tour the
 * first time they open each page, and never sees either again. The help
 * button replays whichever tour belongs to the page currently showing.
 *
 * Keys are versioned via KEY_PREFIX. Bump it when the navigation or a page
 * changes materially and every tour runs once more.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

const MOBILE_QUERY = '(max-width: 767px)';
const ANCHOR_WAIT_MS = 2500;
const ANCHOR_POLL_MS = 100;

function seenKey(prefix, tourId) {
    return `${prefix}-${tourId}`;
}

function hasSeen(prefix, tourId) {
    try {
        return localStorage.getItem(seenKey(prefix, tourId)) === 'seen';
    } catch {
        // Storage unavailable (private mode). Treat as seen -- a tour that
        // cannot remember being dismissed would reopen on every navigation.
        return true;
    }
}

function markSeen(prefix, tourId) {
    try {
        localStorage.setItem(seenKey(prefix, tourId), 'seen');
    } catch {
        // Nothing to do -- see hasSeen().
    }
}

function anchorPresent(step) {
    if (!step?.anchor) return true;
    return Boolean(document.querySelector(`[data-tour="${step.anchor}"]`));
}

/**
 * @param {object}  config
 * @param {object}  config.tours     route path (or 'overview') -> step array
 * @param {string}  config.prefix    localStorage key prefix, versioned
 * @param {string}  config.rootPath  the portal root, e.g. '/panel'
 */
export function useWalkthrough({ tours, prefix, rootPath }) {
    const location = useLocation();
    const [isMobile, setIsMobile] = useState(
        () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches,
    );
    const [isOpen, setIsOpen] = useState(false);
    const [index, setIndex] = useState(0);
    const [activeTour, setActiveTour] = useState(null);
    const [presentIds, setPresentIds] = useState(null);

    const restoreFocusRef = useRef(null);

    // Trailing slashes and the root index route both need to resolve to a key
    // that exists in `tours`.
    const routeKey = useMemo(() => {
        const path = location.pathname.replace(/\/+$/, '') || rootPath;
        return tours[path] ? path : null;
    }, [location.pathname, tours, rootPath]);

    const allSteps = useMemo(() => {
        if (!activeTour) return [];
        const steps = tours[activeTour] || [];
        if (!isMobile) return steps;

        // On mobile the sidebar is a drawer, so its nav items are unmounted
        // and cannot be highlighted. Rather than dropping those steps and
        // leaving the overview as a single slide, they collapse into one
        // step anchored to the hamburger that opens the drawer.
        const sidebarStep = (s) => String(s.anchor || '').startsWith('nav-') || s.anchor === 'sidebar-nav';
        const rest = steps.filter((s) => !sidebarStep(s));
        if (rest.length === steps.length) return steps;

        const firstSidebarAt = steps.findIndex(sidebarStep);
        const collapsed = {
            id: 'mobile-menu',
            anchor: 'mobile-menu-button',
            placement: 'bottom',
            title: 'Your navigation',
            body: 'Every section of the portal lives in this menu.',
        };
        return [...rest.slice(0, firstSidebarAt), collapsed, ...rest.slice(firstSidebarAt)];
    }, [activeTour, tours, isMobile]);

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

    // Decide which tour, if any, should open for the current route. The
    // overview wins on a first visit; after that each page offers its own.
    useEffect(() => {
        if (isOpen) return undefined;

        const candidate = !hasSeen(prefix, 'overview')
            ? 'overview'
            : (routeKey && !hasSeen(prefix, routeKey) ? routeKey : null);

        if (!candidate) return undefined;

        let cancelled = false;
        const startedAt = Date.now();
        const candidateSteps = tours[candidate] || [];

        const tick = () => {
            if (cancelled) return;
            const found = candidateSteps.filter(anchorPresent).map((s) => s.id);
            const anchored = candidateSteps.filter((s) => s.anchor);
            // A tour of only centered steps has nothing to wait for.
            const ready = anchored.length === 0 || anchored.some((s) => found.includes(s.id));

            if (ready) {
                restoreFocusRef.current = document.activeElement;
                setPresentIds(found);
                setActiveTour(candidate);
                setIndex(0);
                setIsOpen(true);
                return;
            }
            if (Date.now() - startedAt > ANCHOR_WAIT_MS) return; // give up quietly
            window.setTimeout(tick, ANCHOR_POLL_MS);
        };

        const id = window.setTimeout(tick, ANCHOR_POLL_MS);
        return () => { cancelled = true; window.clearTimeout(id); };
    }, [routeKey, isOpen, prefix, tours]);

    const close = useCallback(() => {
        if (activeTour) markSeen(prefix, activeTour);
        setIsOpen(false);
        setActiveTour(null);
        const el = restoreFocusRef.current;
        if (el && typeof el.focus === 'function') el.focus();
        restoreFocusRef.current = null;
    }, [activeTour, prefix]);

    const next = useCallback(() => {
        setIndex((i) => {
            if (Math.min(i, steps.length - 1) >= steps.length - 1) {
                queueMicrotask(close);
                return i;
            }
            return i + 1;
        });
    }, [steps.length, close]);

    const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

    /** Replay the tour for the page currently showing, or the overview. */
    const restart = useCallback(() => {
        const target = routeKey || 'overview';
        const targetSteps = tours[target] || [];
        if (!targetSteps.length) return;
        restoreFocusRef.current = document.activeElement;
        setPresentIds(targetSteps.filter(anchorPresent).map((s) => s.id));
        setActiveTour(target);
        setIndex(0);
        setIsOpen(true);
    }, [routeKey, tours]);

    // Derived rather than corrected in an effect, so there is never a frame
    // where `index` points past the end of `steps`.
    const safeIndex = steps.length ? Math.min(index, steps.length - 1) : 0;

    return {
        isOpen: isOpen && steps.length > 0,
        index: safeIndex,
        steps,
        step: steps[safeIndex] ?? null,
        isFirst: safeIndex === 0,
        isLast: safeIndex === steps.length - 1,
        hasTourForPage: Boolean(routeKey) || !hasSeen(prefix, 'overview'),
        next,
        back,
        close,
        restart,
    };
}
