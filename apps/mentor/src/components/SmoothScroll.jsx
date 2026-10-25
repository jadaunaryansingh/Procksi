import { useEffect } from 'react';
import Lenis from 'lenis';
import 'lenis/dist/lenis.css';

export default function SmoothScroll() {
    useEffect(() => {
        if ('scrollRestoration' in history) {
            history.scrollRestoration = 'manual';
        }

        const lenis = new Lenis({
            duration: 1.0,
            smoothWheel: true,
            wheelMultiplier: 1.0,
            touchMultiplier: 1.0,
            prevent: (node) => {
                return (
                    node.classList?.contains('overflow-y-auto') ||
                    node.classList?.contains('overflow-auto') ||
                    node.closest('.overflow-y-auto') ||
                    node.closest('.overflow-auto') ||
                    node.tagName === 'MAIN' ||
                    node.closest('main') ||
                    node.closest('[role="dialog"]')
                );
            }
        });

        let animationFrameId;
        function raf(time) {
            lenis.raf(time);
            animationFrameId = requestAnimationFrame(raf);
        }
        animationFrameId = requestAnimationFrame(raf);

        return () => {
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
            lenis.destroy();
        };
    }, []);

    return null;
}
