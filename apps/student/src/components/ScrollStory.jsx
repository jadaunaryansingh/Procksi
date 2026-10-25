import React, { useEffect, useRef } from 'react';
import { motion, useTransform, useMotionValueEvent } from 'framer-motion';

// Module scope: it reads nothing from the component but the canvas, which is
// passed in. Declared in the body it was recreated every render, and the load
// effect called it before its own declaration was reached.
const paintFrame = (canvas, imgArray, index) => {
    if (!canvas || imgArray.length === 0) return;
    const ctx = canvas.getContext('2d');
    const img = imgArray[Math.floor(index)];
    if (img && img.complete) {
        // Match the canvas resolution to the image's native resolution.
        if (canvas.width !== img.width) canvas.width = img.width;
        if (canvas.height !== img.height) canvas.height = img.height;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    }
};

const ScrollStory = ({ smoothProgress }) => {
    // --- TYPOGRAPHY OPACITIES (Left Side) ---
    // Initially hidden. Fades in as team appears (5% to 10%), stays till 30%, fades out by 34%
    const text1Opacity = useTransform(smoothProgress, [0, 0.05, 0.10, 0.30, 0.34], [0, 0, 1, 1, 0]);
    
    // Phase 2 (Planning): 32% to 57%
    const text2Opacity = useTransform(smoothProgress, [0.32, 0.35, 0.53, 0.57], [0, 1, 1, 0]);
    
    // Phase 3 (Execution): 55% to 80%
    const text3Opacity = useTransform(smoothProgress, [0.55, 0.58, 0.76, 0.80], [0, 1, 1, 0]);
    
    // Phase 4 (Evaluation): 78% to 100%
    const text4Opacity = useTransform(smoothProgress, [0.78, 0.81, 1], [0, 1, 1]);

    const instructionOpacity = useTransform(smoothProgress, [0, 0.05], [1, 0]);

    // --- CANVAS IMAGE SEQUENCE ---
    const canvasRef = useRef(null);
    // Preloaded <img> objects. This is an external resource cache, not render
    // state -- nothing in the JSX reads it, so a ref avoids a needless re-render.
    const imagesRef = useRef([]);
    const frameCount = 240;
    
    // Map smoothProgress (0 to 1) to a frame index (0 to 239)
    // We want the sequence to finish slightly before the very end (e.g., at 0.9) so it settles
    const frameIndex = useTransform(smoothProgress, [0, 0.9], [0, frameCount - 1]);

    // Preload images
    useEffect(() => {
        // Frames live on the CDN (main-site S3/CloudFront bucket), not in this
        // portal's own build, so we don't ship 151 MB of PNGs in the EC2 image.
        // Override the origin with VITE_SCROLL_FRAMES_BASE if needed.
        const base = import.meta.env.VITE_SCROLL_FRAMES_BASE || 'https://glapms.in';
        const loadedImages = [];

        for (let i = 0; i < frameCount; i++) {
            const img = new Image();
            // Format number to 6 digits (e.g., 000000, 000001)
            const paddedNumber = i.toString().padStart(6, '0');
            img.src = `${base}/scroll_frames/frame_${paddedNumber}.webp`;

            // Paint frame 0 the instant it arrives instead of blocking on all
            // 240 frames — otherwise the canvas stays blank until the entire
            // sequence has downloaded.
            if (i === 0) {
                img.onload = () => paintFrame(canvasRef.current, loadedImages, 0);
            }

            loadedImages.push(img);
        }

        // Expose the array immediately so scrubbing works as frames stream in;
        // paintFrame guards on img.complete, so not-yet-loaded frames are skipped.
        imagesRef.current = loadedImages;
    }, []);

    // Whenever smoothProgress changes, redraw the canvas
    useMotionValueEvent(frameIndex, "change", (latest) => {
        if (imagesRef.current.length > 0) {
            paintFrame(canvasRef.current, imagesRef.current, latest);
        }
    });

    return (
        <div className="h-[800vh] bg-slate-950 relative w-full">
            {/* Sticky Container */}
            <div className="sticky top-0 h-screen w-full overflow-hidden">
                
                {/* Premium Background Layer (Behind everything) */}
                <div className="absolute inset-0 bg-slate-950 pointer-events-none">
                    {/* We let the video frames provide the primary environment pattern */}
                </div>

                {/* FULL SCREEN IMAGE SEQUENCE BACKGROUND */}
                <div className="absolute inset-0 w-full h-full pointer-events-none z-10">
                    <canvas 
                        ref={canvasRef} 
                        className="w-full h-full object-cover"
                    />
                    {/* Subtle dark gradient on the left to ensure text is always readable over the video */}
                    <div className="absolute inset-0 w-[50%] bg-gradient-to-r from-slate-950/80 via-slate-950/40 to-transparent pointer-events-none"></div>
                </div>

                {/* Split Layout Container for Content */}
                <div className="absolute inset-0 flex pointer-events-none z-20">
                    
                    {/* LEFT 40%: DYNAMIC TEXT DESCRIPTIONS */}
                    <div className="w-full md:w-[45%] h-full relative pl-8 md:pl-20 lg:pl-32 pointer-events-none">
                        <div className="absolute top-[65vh] w-[90%] h-40 pointer-events-auto">
                            <motion.div style={{ opacity: text1Opacity, position: 'absolute', top: 0, left: 0 }}>
                                <h3 className="text-2xl md:text-3xl text-white font-bold mb-2">Phase 1: Team Onboarding</h3>
                                <p className="text-slate-400 text-lg max-w-md leading-relaxed">Gather your squad and prepare for launch. Every great project starts with a great team.</p>
                            </motion.div>

                            <motion.div style={{ opacity: text2Opacity, position: 'absolute', top: 0, left: 0 }}>
                                <h3 className="text-2xl md:text-3xl text-white font-bold mb-2">Phase 2: Planning</h3>
                                <p className="text-slate-400 text-lg max-w-md leading-relaxed">Define your goals, submit your proposal, and get mentor approval to secure your mission.</p>
                            </motion.div>

                            <motion.div style={{ opacity: text3Opacity, position: 'absolute', top: 0, left: 0 }}>
                                <h3 className="text-2xl md:text-3xl text-white font-bold mb-2">Phase 3: Execution</h3>
                                <p className="text-slate-400 text-lg max-w-md leading-relaxed">Dodge missed deadlines, overcome technical hurdles, and keep your project on course.</p>
                            </motion.div>

                            <motion.div style={{ opacity: text4Opacity, position: 'absolute', top: 0, left: 0 }}>
                                <h3 className="text-2xl md:text-3xl text-white font-bold mb-2">Phase 4: Evaluation</h3>
                                <p className="text-slate-400 text-lg max-w-md leading-relaxed">Cross the finish line, present your hard work, and achieve top marks.</p>
                            </motion.div>
                        </div>
                    </div>

                    {/* RIGHT 55%: SCROLL INSTRUCTION */}
                    <div className="hidden md:flex w-[55%] h-full relative items-center justify-center pointer-events-none z-40">
                        {/* Initial Scroll Instruction */}
                        <motion.div 
                            style={{ opacity: instructionOpacity }}
                            className="absolute bottom-10 flex flex-col items-center text-slate-400 animate-bounce pointer-events-auto z-50"
                        >
                            <span className="text-sm font-medium tracking-widest uppercase">Scroll Down</span>
                            <div className="w-px h-12 bg-slate-400 mt-2"></div>
                        </motion.div>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default ScrollStory;
