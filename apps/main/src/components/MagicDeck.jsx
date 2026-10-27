import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X } from 'lucide-react';

// ── Constants ────────────────────────────────────────────────────────────────
const GOLD = '#c9a64d';
const GOLD_DIM = '#c9a64d99';
const GOLD_GLOW = 'rgba(201,166,77,0.22)';

// ── Team Data ────────────────────────────────────────────────────────────────
const teamMembers = [
  { id: 0, name: "Aaradhya Rawat", role: "Frontend Developer", archetype: "The Creator", claimToFame: "Master of component reusability", tech: "React, Next.js", image: "/team/aaradhya.jpeg" },
  { id: 1, name: "Aryan Singh", role: "Backend Developer", archetype: "The Engineer", claimToFame: "Zero downtime deployment streak", tech: "Python, FastAPI", image: "/team/aryan.jpeg" },
  { id: 2, name: "Mansi Singh", role: "Cloud & Deploy", archetype: "The Sentinel", claimToFame: "Pipelines run on her watch", tech: "GitHub Actions, Terraform", image: "/team/mansi.jpeg" },
  { id: 3, name: "Nischal Saxena", role: "Backend Developer", archetype: "The Optimizer", claimToFame: "O(1) time complexity fanatic", tech: "Go, PostgreSQL", image: "/team/nischal.jpeg" },
  { id: 4, name: "Parv Agarwal", role: "AI Product Engineer", archetype: "The Architect", claimToFame: "FastAPI + Agents = Happy place", tech: "FastAPI, LangGraph,Lanchain", image: "/team/parv.jpeg" },
  { id: 5, name: "Samarth Verma", role: "AI Agent Developer", archetype: "The Thinker", claimToFame: "Agent wrote this claim to fame", tech: "LangChain, OpenAI", image: "/team/samarth.png" },
  { id: 6, name: "Saurav Shandilya", role: "Cloud & Deploy", archetype: "The Guardian", claimToFame: "Never missed an AWS bill alert", tech: "AWS, Docker, K8s", image: "/team/saurav.jpeg" },
  { id: 7, name: "Yash Jain", role: "Frontend Developer", archetype: "The Visionary", claimToFame: "Pixel-perfect CSS blindfolded", tech: "React, Tailwind, Framer", image: "/team/yash.jpeg" },
];

const alphabeticalMembers = [...teamMembers].sort((a, b) => a.name.localeCompare(b.name));

const scatterPositions = teamMembers.map((_, i) => {
  const angle = (i / teamMembers.length) * Math.PI * 2 - Math.PI / 2;
  return { x: Math.cos(angle) * 310, y: Math.sin(angle) * 310, rotate: ((i * 137.5) % 60) - 30 };
});

// Cards spread in an arc (fan deal)
const FAN_POS = [
  { x: -460, y: 190, rotate: -72, delay: 0.00 },
  { x: -345, y: 120, rotate: -56, delay: 0.07 },
  { x: -240, y: 65, rotate: -41, delay: 0.14 },
  { x: -145, y: 24, rotate: -28, delay: 0.21 },
  { x: -62, y: -3, rotate: -16, delay: 0.28 },
  { x: 16, y: -17, rotate: -5, delay: 0.35 },
  { x: 94, y: -12, rotate: 6, delay: 0.42 },
  { x: 165, y: 6, rotate: 15, delay: 0.49 },
];

// Final positions cards "gather" to before deck loads
const GATHER_POS = [
  { x: -330, y: 0, rotate: -7, delay: 0.00 },
  { x: -326, y: -5, rotate: -4, delay: 0.04 },
  { x: -322, y: -10, rotate: -2, delay: 0.08 },
  { x: 0, y: 0, rotate: 0, delay: 0.12 },
  { x: 320, y: -8, rotate: 2, delay: 0.16 },
  { x: 325, y: -4, rotate: 4, delay: 0.20 },
  { x: 330, y: 0, rotate: 6, delay: 0.24 },
  { x: 335, y: 4, rotate: 8, delay: 0.28 },
];

// ── SVG Triangle (like reference — pyramid with rays) ─────────────────────────
const TriangleSVG = () => (
  <svg viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
    {[...Array(30)].map((_, i) => {
      const a = (i / 30) * Math.PI * 2;
      return (
        <line key={i}
          x1={100 + Math.cos(a) * 60} y1={100 + Math.sin(a) * 60}
          x2={100 + Math.cos(a) * 96} y2={100 + Math.sin(a) * 96}
          stroke={GOLD} strokeWidth="0.7" opacity="0.65"
        />
      );
    })}
    <polygon points="100,15 188,162 12,162" stroke={GOLD} strokeWidth="2" fill="rgba(201,166,77,0.04)" />
    <polygon points="100,42 168,150 32,150" stroke={GOLD} strokeWidth="0.8" fill="none" opacity="0.35" />
    <circle cx="100" cy="116" r="20" fill="rgba(201,166,77,0.1)" />
    <circle cx="100" cy="116" r="8" fill="rgba(201,166,77,0.18)" />
  </svg>
);

// ── Card Back (Procksi branding) ─────────────────────────────────────────────
const CardBack = ({ small = false }) => (
  <div className="w-full h-full relative overflow-hidden flex flex-col items-center justify-center"
    style={{
      background: 'linear-gradient(155deg,#0d1629,#060c1a)',
      borderRadius: small ? '10px' : '1.4rem',
      border: `2px solid ${GOLD}55`,
      boxShadow: `0 8px 32px rgba(0,0,0,0.5), inset 0 0 30px rgba(0,0,0,0.4)`,
    }}
  >
    {/* Corner brackets */}
    {[['top-2.5 left-2.5', 'top right'], ['top-2.5 right-2.5', 'top left'], ['bottom-2.5 left-2.5', 'bottom right'], ['bottom-2.5 right-2.5', 'bottom left']].map(([pos, dirs]) => {
      const [v, h] = dirs.split(' ');
      return (
        <div key={pos} className={`absolute ${pos} w-4 h-4`} style={{
          borderTop: v === 'top' ? `1.5px solid ${GOLD}` : 'none',
          borderBottom: v === 'bottom' ? `1.5px solid ${GOLD}` : 'none',
          borderLeft: h === 'left' ? `1.5px solid ${GOLD}` : 'none',
          borderRight: h === 'right' ? `1.5px solid ${GOLD}` : 'none',
        }} />
      );
    })}
    {/* Radial bg */}
    <div className="absolute inset-0 opacity-[0.055]" style={{ backgroundImage: 'repeating-conic-gradient(from 0deg, transparent 0deg 10deg, white 10deg 20deg)' }} />
    {/* Content */}
    <div className="flex flex-col items-center z-10" style={{ gap: small ? 4 : 6 }}>
      <Sparkles style={{ width: small ? 14 : 28, height: small ? 14 : 28, color: GOLD, opacity: 0.8 }} />
      <span style={{
        fontSize: small ? 16 : 28,
        fontWeight: 900,
        lineHeight: 1.15,
        textAlign: 'center',
        background: `linear-gradient(180deg, #e8d5a3, ${GOLD})`,
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        letterSpacing: '0.1em',
        textShadow: `none`,
      }}>Procksi</span>
      {!small && (
        <>
          <div style={{ width: 28, height: 1, background: `${GOLD}66`, marginTop: 2 }} />
          <span style={{ fontSize: 7, color: `${GOLD}55`, letterSpacing: '0.4em', textTransform: 'uppercase', fontFamily: 'monospace', textAlign: 'center', lineHeight: 1.6 }}>
            Project<br />Management
          </span>
        </>
      )}
    </div>
  </div>
);

// ── Views ────────────────────────────────────────────────────────────────────
const VIEW = { BOX: 'box', FANNING: 'fanning', DECK: 'deck', SCATTER: 'scatter' };

const cardVariants = {
  enter: (d) => ({ opacity: 0, x: d > 0 ? 130 : -130, rotateY: d > 0 ? -25 : 25, scale: 0.88 }),
  center: { opacity: 1, x: 0, rotateY: 0, scale: 1, transition: { type: 'spring', stiffness: 230, damping: 24 } },
  exit: (d) => ({ opacity: 0, x: d > 0 ? -130 : 130, rotateY: d > 0 ? 25 : -25, scale: 0.88, transition: { duration: 0.22 } }),
};

// ── Main Component ───────────────────────────────────────────────────────────
export default function MagicDeck() {
  const [view, setView] = useState(VIEW.BOX);
  const [lidOpen, setLidOpen] = useState(false);
  const [fanPhase, setFanPhase] = useState('spread'); // 'spread' | 'gather'
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [direction, setDirection] = useState(1);
  const [selectedFromScatter, setSelectedFromScatter] = useState(null);

  const activeMember = teamMembers[currentIndex];
  const prevCount = Math.min(currentIndex, 5);
  const nextCount = Math.min(teamMembers.length - currentIndex - 1, 5);

  const handleBoxClick = () => {
    if (lidOpen) return;
    setLidOpen(true);
    setTimeout(() => { setFanPhase('spread'); setView(VIEW.FANNING); }, 800);
    setTimeout(() => setFanPhase('gather'), 800 + 1300);
    setTimeout(() => setView(VIEW.DECK), 800 + 1300 + 800);
  };

  const changeCard = (newIndex, dir) => {
    setIsFlipped(false);
    setDirection(dir);
    setTimeout(() => setCurrentIndex(newIndex), 80);
  };
  const handleNext = () => { if (currentIndex < teamMembers.length - 1) changeCard(currentIndex + 1, 1); };
  const handlePrev = () => { if (currentIndex > 0) changeCard(currentIndex - 1, -1); };

  const selectFromScatter = (memberId) => {
    const idx = teamMembers.findIndex(m => m.id === memberId);
    setSelectedFromScatter(memberId);
    setIsFlipped(false);
    setTimeout(() => { setCurrentIndex(idx); setView(VIEW.DECK); setSelectedFromScatter(null); }, 640);
  };

  return (
    <section id="team" className="py-16 relative overflow-hidden flex flex-col border-t border-slate-800/50"
      style={{ minHeight: '100vh', background: '#080f1e' }}>
      {/* Ambient */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-1/4 w-1/2 h-1/2 rounded-full blur-[160px]" style={{ background: 'rgba(99,102,241,0.1)' }} />
        <div className="absolute bottom-0 right-1/4 w-1/3 h-1/3 rounded-full blur-[120px]" style={{ background: 'rgba(139,92,246,0.08)' }} />
      </div>

      <div className="relative z-10 w-full max-w-6xl mx-auto px-6 flex-1 flex flex-col">
        <AnimatePresence mode="wait">

          {/* ═══════════════ BOX VIEW ═══════════════ */}
          {view === VIEW.BOX && (
            <motion.div key="box"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.3 } }}
              className="flex-1 flex flex-col items-center justify-center gap-10"
            >
              <motion.div className="text-center"
                initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
                <h2 className="text-3xl md:text-5xl font-black text-white leading-tight">
                  The Minds That Built<br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
                    Something Remarkable
                  </span>
                </h2>
              </motion.div>

              {/* ── THE BOX ── */}
              <motion.div
                initial={{ opacity: 0, y: 50, scale: 0.85 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ delay: 0.4, type: 'spring', stiffness: 150, damping: 18 }}
                onClick={handleBoxClick}
                style={{ perspective: 1100, cursor: lidOpen ? 'default' : 'pointer' }}
              >
                <div style={{ width: 270, height: 415, position: 'relative' }}>

                  {/* ── LID ── */}
                  <motion.div
                    animate={{ rotateX: lidOpen ? -145 : 0 }}
                    transition={{ type: 'spring', stiffness: 105, damping: 14, delay: 0.05 }}
                    style={{
                      position: 'absolute', top: 0, left: 0, right: 0, height: 58,
                      background: 'linear-gradient(180deg,#141d35,#0b1220)',
                      border: `2.5px solid ${GOLD}`,
                      borderBottom: 'none',
                      borderRadius: '10px 10px 0 0',
                      transformOrigin: 'top center',
                      transformStyle: 'preserve-3d',
                      zIndex: 30,
                      boxShadow: `0 -4px 20px ${GOLD_GLOW}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    {/* Lid inner line */}
                    <div style={{ position: 'absolute', inset: '5px 8px', border: `1px solid ${GOLD}33`, borderRadius: 6, bottom: -1 }} />
                    {/* Corner dots */}
                    {['top-1.5 left-2', 'top-1.5 right-2'].map(c => (
                      <div key={c} className={`absolute ${c} w-2 h-2 rounded-sm`} style={{ background: GOLD, opacity: 0.5 }} />
                    ))}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px', width: '100%' }}>
                      <div style={{ flex: 1, height: 1, background: `linear-gradient(to right, transparent, ${GOLD}88)` }} />
                      <span style={{ color: GOLD, fontWeight: 900, fontSize: 11, letterSpacing: '0.55em', textTransform: 'uppercase' }}>PROCKSI</span>
                      <div style={{ flex: 1, height: 1, background: `linear-gradient(to left, transparent, ${GOLD}88)` }} />
                    </div>
                  </motion.div>

                  {/* ── BOX BODY ── */}
                  <div style={{
                    position: 'absolute', top: 55, left: 0, right: 0, bottom: 0,
                    background: 'linear-gradient(160deg,#08101f 0%,#040810 100%)',
                    border: `2.5px solid ${GOLD}`,
                    borderTop: `1px solid ${GOLD}33`,
                    borderRadius: '0 0 12px 12px',
                    overflow: 'hidden',
                    boxShadow: `0 24px 70px rgba(0,0,0,0.7), 0 0 35px ${GOLD_GLOW}, inset 0 0 50px rgba(0,0,0,0.7)`,
                  }}>
                    {/* Inner decorative border */}
                    <div style={{ position: 'absolute', inset: 10, border: `1px solid ${GOLD}33`, borderRadius: 6, zIndex: 1, pointerEvents: 'none' }}>
                      {/* Inner corner ornaments */}
                      {[[-3, -3, 'top left'], [-3, 'auto', 'top right'], ['auto', -3, 'bottom left'], ['auto', 'auto', 'bottom right']].map(([t, r, label], idx) => (
                        <div key={idx} style={{
                          position: 'absolute',
                          top: typeof t === 'number' ? t : undefined,
                          bottom: t === 'auto' ? -3 : undefined,
                          left: typeof r === 'number' ? r : undefined,
                          right: r === 'auto' ? -3 : undefined,
                          width: 12, height: 12,
                          borderTop: label.includes('top') ? `2px solid ${GOLD}` : 'none',
                          borderBottom: label.includes('bottom') ? `2px solid ${GOLD}` : 'none',
                          borderLeft: label.includes('left') ? `2px solid ${GOLD}` : 'none',
                          borderRight: label.includes('right') ? `2px solid ${GOLD}` : 'none',
                        }} />
                      ))}
                    </div>

                    {/* Background repeating text pattern */}
                    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', zIndex: 0 }}>
                      <p style={{
                        fontSize: 8.5, color: GOLD, opacity: 0.065,
                        lineHeight: 1.9, padding: '12px 14px', wordBreak: 'break-all',
                        fontFamily: 'monospace', letterSpacing: '0.12em',
                      }}>
                        {Array(90).fill('✦ PROCKSI · PROJECT MANAGEMENT PLATFORM ').join('')}
                      </p>
                    </div>

                    {/* Triangle with rays (center piece) */}
                    <div style={{ position: 'absolute', top: '8%', left: '10%', right: '10%', bottom: '26%', zIndex: 2 }}>
                      <TriangleSVG />
                    </div>

                    {/* Golden center radial glow */}
                    <div style={{
                      position: 'absolute', top: '12%', left: '18%', right: '18%', bottom: '34%', zIndex: 2,
                      background: `radial-gradient(ellipse at center, ${GOLD_GLOW} 0%, transparent 70%)`,
                      pointerEvents: 'none',
                    }} />

                    {/* Four corner ✦ symbols */}
                    {['12px 12px', '12px auto', 'auto 12px', 'auto auto'].map((pos, i) => {
                      const [t, r] = pos.split(' ');
                      return (
                        <span key={i} style={{
                          position: 'absolute', fontSize: 10, color: GOLD, opacity: 0.55, zIndex: 3,
                          top: t !== 'auto' ? parseInt(t) + 16 : undefined,
                          bottom: t === 'auto' ? 46 : undefined,
                          left: r !== 'auto' ? parseInt(r) + 4 : undefined,
                          right: r === 'auto' ? 4 : undefined,
                        }}>✦</span>
                      );
                    })}

                    {/* Bottom "Procksi" label */}
                    <div style={{
                      position: 'absolute', bottom: 14, left: 0, right: 0,
                      display: 'flex', alignItems: 'center', gap: 10, padding: '0 18px', zIndex: 3
                    }}>
                      <div style={{ flex: 1, height: 1, background: `linear-gradient(to right, transparent, ${GOLD}88)` }} />
                      <span style={{ color: GOLD, fontWeight: 900, fontSize: 11, letterSpacing: '0.55em', textTransform: 'uppercase' }}>PROCKSI</span>
                      <div style={{ flex: 1, height: 1, background: `linear-gradient(to left, transparent, ${GOLD}88)` }} />
                    </div>

                    {/* OPEN BOX badge */}
                    {!lidOpen && (
                      <motion.div
                        className="absolute inset-0 flex items-center justify-center z-20"
                        animate={{ opacity: [0.65, 1, 0.65] }}
                        transition={{ repeat: Infinity, duration: 2.2, ease: 'easeInOut' }}
                      >
                        <div style={{
                          background: 'rgba(79,70,229,0.9)',
                          backdropFilter: 'blur(10px)',
                          border: '1.5px solid rgba(255,255,255,0.22)',
                          borderRadius: 22,
                          padding: '10px 26px',
                          color: 'white',
                          fontWeight: 800,
                          fontSize: 12,
                          letterSpacing: '0.22em',
                          textTransform: 'uppercase',
                          boxShadow: '0 4px 24px rgba(79,70,229,0.5)',
                        }}>
                          OPEN BOX
                        </div>
                      </motion.div>
                    )}
                  </div>

                  {/* Box ground shadow */}
                  <div style={{
                    position: 'absolute', bottom: -12, left: 20, right: 20, height: 16,
                    borderRadius: '50%', filter: 'blur(12px)',
                    background: GOLD_GLOW,
                  }} />
                </div>
              </motion.div>

              {/* Footer text that fades out when the box is clicked */}
              <motion.div 
                animate={{ opacity: lidOpen ? 0 : 1, y: lidOpen ? 10 : 0 }}
                transition={{ duration: 0.3 }}
                className="mt-8"
              >
                  <p className="text-xs font-bold tracking-widest uppercase text-slate-500/80 flex items-center justify-center gap-2">
                      Made with <span className="text-red-500/90 text-sm">❤️</span> by team Procksi
                  </p>
              </motion.div>
            </motion.div>
          )}

          {/* ═══════════════ FANNING VIEW ═══════════════ */}
          {view === VIEW.FANNING && (
            <motion.div key="fanning"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.4 } }}
              className="flex-1 flex items-center justify-center relative"
              style={{ minHeight: 580, overflow: 'visible' }}
            >
              {FAN_POS.map((fp, i) => {
                const gp = GATHER_POS[i];
                const isGathering = fanPhase === 'gather';
                return (
                  <motion.div key={i}
                    className="absolute w-[138px] h-[196px]"
                    style={{ transformOrigin: 'bottom center', zIndex: i }}
                    initial={{ x: 0, y: 60, rotate: 0, opacity: 0, scale: 0.5 }}
                    animate={isGathering ? {
                      x: gp.x, y: gp.y, rotate: gp.rotate, opacity: 1, scale: i === 3 ? 1.05 : 0.9,
                    } : {
                      x: fp.x, y: fp.y, rotate: fp.rotate, opacity: 1, scale: 1,
                    }}
                    transition={isGathering ? {
                      type: 'spring', stiffness: 230, damping: 22, delay: gp.delay,
                    } : {
                      type: 'spring', stiffness: 125, damping: 16, delay: fp.delay,
                    }}
                  >
                    <CardBack />
                  </motion.div>
                );
              })}
            </motion.div>
          )}

          {/* ═══════════════ DECK VIEW ═══════════════ */}
          {view === VIEW.DECK && (
            <motion.div key="deck"
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.92, transition: { duration: 0.3 } }}
              transition={{ type: 'spring', stiffness: 200, damping: 22, delay: 0.1 }}
              className="flex-1 flex flex-col items-center justify-center"
            >
              <div className="text-center mb-10">
                <h2 className="text-3xl md:text-5xl font-black text-white leading-tight mb-2">
                  The Minds That Built<br />
                  <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">Something Remarkable</span>
                </h2>
                <p className="font-medium tracking-[0.25em] uppercase text-xs mt-3" style={{ color: 'rgba(165,180,252,0.5)' }}>
                  Click a card to reveal the architect behind it
                </p>
              </div>

              <div className="flex items-center justify-center gap-6 md:gap-12 w-full h-[520px]">

                {/* Left Stack */}
                <motion.div animate={{ opacity: prevCount > 0 ? 1 : 0 }} transition={{ duration: 0.35 }}
                  className={`hidden md:block relative w-[220px] h-[320px] cursor-pointer group ${prevCount === 0 ? 'pointer-events-none' : ''}`}
                  onClick={handlePrev}
                >
                  {[...Array(prevCount)].map((_, i) => (
                    <motion.div key={i} className="absolute inset-0" style={{ zIndex: 10 - i }}
                      animate={{ x: -i * 4, y: i * 4, rotate: -i * 2 }}
                      whileHover={{ x: -i * 4 - 7 }} transition={{ type: 'spring', stiffness: 200, damping: 20 }}>
                      <CardBack />
                    </motion.div>
                  ))}
                  <div className="absolute inset-0 flex items-end justify-center pb-2 opacity-0 group-hover:opacity-100 transition-opacity z-30">
                    <span className="text-[10px] font-bold text-white tracking-widest uppercase backdrop-blur-md px-3 py-1.5 rounded-full shadow"
                      style={{ background: 'rgba(15,23,42,0.85)', border: '1px solid rgba(255,255,255,0.1)' }}>Previous Card</span>
                  </div>
                </motion.div>

                {/* Center Card */}
                <div className="relative w-[300px] md:w-[340px] h-[460px] md:h-[500px]" style={{ perspective: 1200 }}>
                  <AnimatePresence custom={direction} mode="wait">
                    <motion.div key={currentIndex} custom={direction} variants={cardVariants}
                      initial="enter" animate="center" exit="exit"
                      className="absolute inset-0 cursor-pointer" style={{ transformStyle: 'preserve-3d' }}
                      onClick={() => setIsFlipped(f => !f)}
                    >
                      <motion.div className="w-full h-full" style={{ transformStyle: 'preserve-3d' }}
                        animate={{ rotateY: isFlipped ? 180 : 0 }}
                        transition={{ type: 'spring', stiffness: 185, damping: 23 }}>
                        {/* FRONT */}
                        <div className="absolute inset-0 bg-slate-800 rounded-[2rem] shadow-2xl flex flex-col overflow-hidden"
                          style={{ backfaceVisibility: 'hidden', border: '3px solid rgba(100,116,139,0.5)' }}>
                          <div className="flex-1 overflow-hidden relative">
                            <img src={activeMember.image} alt={activeMember.name} className="w-full h-full object-cover" />
                            <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-slate-800 to-transparent" />
                          </div>
                          <div className="bg-slate-100 px-5 py-4 text-center">
                            <p className="text-[10px] font-bold tracking-widest text-indigo-500 uppercase mb-0.5">{activeMember.archetype}</p>
                            <h3 className="text-xl font-black text-slate-900 uppercase leading-tight">{activeMember.name}</h3>
                          </div>
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity rounded-[2rem]">
                            <div className="w-20 h-20 bg-indigo-600/90 backdrop-blur-sm rounded-full flex items-center justify-center shadow-xl"
                              style={{ border: '1.5px solid rgba(255,255,255,0.2)' }}>
                              <span className="text-[9px] font-black text-white text-center leading-tight tracking-widest">SHOW<br />DETAILS</span>
                            </div>
                          </div>
                        </div>
                        {/* BACK */}
                        <div className="absolute inset-0 rounded-[2rem] shadow-2xl bg-[#0b1322] flex flex-col overflow-hidden"
                          style={{ backfaceVisibility: 'hidden', transform: 'rotateY(180deg)', border: '3px solid rgba(99,102,241,0.4)' }}>
                          <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: 'radial-gradient(circle, #6366f1 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
                          <div className="absolute top-0 left-0 right-0 h-24 bg-gradient-to-b from-indigo-600/25 to-transparent" />
                          <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-indigo-600/20 to-transparent" />
                          <svg className="absolute top-3 left-3 w-8 h-8 text-indigo-500/50" viewBox="0 0 32 32" fill="none"><path d="M2 16V2h14" stroke="currentColor" strokeWidth="2" /><rect x="0" y="0" width="5" height="5" fill="currentColor" /></svg>
                          <svg className="absolute top-3 right-3 w-8 h-8 text-indigo-500/50" viewBox="0 0 32 32" fill="none"><path d="M30 16V2H16" stroke="currentColor" strokeWidth="2" /><rect x="27" y="0" width="5" height="5" fill="currentColor" /></svg>
                          <svg className="absolute bottom-3 left-3 w-8 h-8 text-indigo-500/50" viewBox="0 0 32 32" fill="none"><path d="M2 16v14h14" stroke="currentColor" strokeWidth="2" /><rect x="0" y="27" width="5" height="5" fill="currentColor" /></svg>
                          <svg className="absolute bottom-3 right-3 w-8 h-8 text-indigo-500/50" viewBox="0 0 32 32" fill="none"><path d="M30 16v14H16" stroke="currentColor" strokeWidth="2" /><rect x="27" y="27" width="5" height="5" fill="currentColor" /></svg>
                          <div className="relative z-10 flex flex-col h-full justify-between p-7">
                            <div className="flex flex-col items-center text-center">
                              <Sparkles className="w-7 h-7 text-indigo-400 mb-3" />
                              <h3 className="text-2xl font-black text-white uppercase tracking-wider leading-tight">{activeMember.name}</h3>
                              <p className="text-xs font-bold tracking-[0.3em] text-indigo-400 uppercase mt-1">{activeMember.archetype}</p>
                              <div className="w-16 h-px bg-indigo-500/40 mt-4" />
                            </div>
                            <div className="flex flex-col gap-5 bg-white/5 border border-white/5 rounded-2xl px-5 py-6 backdrop-blur-sm">
                              <div className="text-center">
                                <p className="text-[9px] font-bold tracking-[0.3em] text-indigo-400 uppercase mb-1">Role</p>
                                <p className="text-sm font-black text-white uppercase">{activeMember.role}</p>
                              </div>
                              <div className="w-8 h-px bg-indigo-500/25 mx-auto" />
                              <div className="text-center">
                                <p className="text-[9px] font-bold tracking-[0.3em] text-indigo-400 uppercase mb-1">Claim to Fame</p>
                                <p className="text-sm font-medium text-slate-300 italic leading-snug">"{activeMember.claimToFame}"</p>
                              </div>
                              <div className="w-8 h-px bg-indigo-500/25 mx-auto" />
                              <div className="text-center">
                                <p className="text-[9px] font-bold tracking-[0.3em] text-indigo-400 uppercase mb-1">Favorite Tech</p>
                                <p className="text-sm font-bold text-white">{activeMember.tech}</p>
                              </div>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    </motion.div>
                  </AnimatePresence>
                </div>

                {/* Right Stack */}
                <motion.div animate={{ opacity: nextCount > 0 ? 1 : 0 }} transition={{ duration: 0.35 }}
                  className={`hidden md:block relative w-[220px] h-[320px] cursor-pointer group ${nextCount === 0 ? 'pointer-events-none' : ''}`}
                  onClick={handleNext}
                >
                  {[...Array(nextCount)].map((_, i) => (
                    <motion.div key={i} className="absolute inset-0" style={{ zIndex: i }}
                      animate={{ x: i * 4, y: -i * 4 }}
                      whileHover={{ x: i * 4 + 7 }} transition={{ type: 'spring', stiffness: 200, damping: 20 }}>
                      <CardBack />
                    </motion.div>
                  ))}
                  <div className="absolute inset-0 flex items-end justify-center pb-2 opacity-0 group-hover:opacity-100 transition-opacity z-30">
                    <span className="text-[10px] font-bold text-white tracking-widest uppercase backdrop-blur-md px-3 py-1.5 rounded-full shadow"
                      style={{ background: 'rgba(15,23,42,0.85)', border: '1px solid rgba(255,255,255,0.1)' }}>Next Card</span>
                  </div>
                </motion.div>
              </div>

              {/* Progress dots */}
              <div className="flex gap-2 mt-2">
                {teamMembers.map((_, i) => (
                  <button key={i} onClick={() => changeCard(i, i > currentIndex ? 1 : -1)}
                    className={`h-1.5 rounded-full transition-all duration-300 ${i === currentIndex ? 'w-6 bg-indigo-400' : 'w-1.5 bg-slate-600 hover:bg-slate-400'}`}
                  />
                ))}
              </div>

              <div className="mt-8 text-center">
                <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.97 }}
                  onClick={() => { setIsFlipped(false); setView(VIEW.SCATTER); }}
                  className="text-white border backdrop-blur-md px-8 py-3 rounded-full font-bold text-sm tracking-[0.2em] uppercase transition-colors shadow-lg"
                  style={{ background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.12)' }}
                >
                  See All Cards
                </motion.button>
              </div>
            </motion.div>
          )}

          {/* ═══════════════ SCATTER VIEW ═══════════════ */}
          {view === VIEW.SCATTER && (
            <motion.div key="scatter"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              exit={{ opacity: 0, transition: { duration: 0.3 } }}
              className="flex-1 w-full flex flex-col items-center justify-center"
            >
              <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15, duration: 0.5 }} className="text-center mb-6">
                <h2 className="text-5xl md:text-7xl font-black tracking-tight text-white mb-3"
                  style={{ filter: 'drop-shadow(0 0 20px rgba(99,102,241,0.55))' }}>
                  PICK A CARD
                </h2>
                <p className="font-medium tracking-[0.3em] uppercase text-sm" style={{ color: 'rgba(165,180,252,0.6)' }}>
                  Meet the Troupe of Architects
                </p>
              </motion.div>

              <div className="relative flex items-center justify-center w-full" style={{ height: 700 }}>
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.25, type: 'spring', stiffness: 200, damping: 22 }}
                  className="relative z-50 flex flex-col items-center px-10 py-8 rounded-3xl shadow-2xl"
                  style={{ background: 'rgba(15,23,42,0.78)', backdropFilter: 'blur(24px)', border: '1px solid rgba(255,255,255,0.1)' }}
                >
                  <button onClick={() => setView(VIEW.DECK)} className="absolute top-4 right-4 text-slate-500 hover:text-white transition-colors">
                    <X className="w-4 h-4" />
                  </button>
                  <div className="flex items-center gap-2 mb-5">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <p className="text-xs font-bold text-indigo-400 tracking-[0.3em] uppercase">Select a Developer</p>
                  </div>
                  <div className="flex flex-col items-center gap-2 divide-y w-full" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
                    {alphabeticalMembers.map((member) => (
                      <motion.button key={member.id} whileHover={{ scale: 1.07, x: 5 }}
                        onClick={() => selectFromScatter(member.id)}
                        className="w-full text-center pt-2 text-base font-black uppercase tracking-wider transition-colors"
                        style={{ color: selectedFromScatter === member.id ? '#a5b4fc' : 'rgba(203,213,225,0.85)' }}
                      >
                        {member.name}
                      </motion.button>
                    ))}
                  </div>
                </motion.div>

                {teamMembers.map((member, i) => {
                  const pos = scatterPositions[i];
                  const isSel = selectedFromScatter === member.id;
                  return (
                    <motion.div key={member.id}
                      className="absolute top-1/2 left-1/2 w-[170px] h-[250px] -ml-[85px] -mt-[125px] cursor-pointer"
                      style={{ zIndex: isSel ? 60 : 10 }}
                      initial={{ x: 0, y: 0, rotate: 0, opacity: 0, scale: 0.3 }}
                      animate={isSel ? { x: 0, y: 0, rotate: 0, scale: 1.4, opacity: 1 } : { x: pos.x, y: pos.y, rotate: pos.rotate, opacity: 1, scale: 1 }}
                      transition={isSel ? { type: 'spring', stiffness: 190, damping: 18 } : { type: 'spring', stiffness: 110, damping: 18, delay: 0.3 + i * 0.05 }}
                      whileHover={isSel ? {} : { scale: 1.15, rotate: 0, zIndex: 55, transition: { duration: 0.2 } }}
                      onClick={() => selectFromScatter(member.id)}
                    >
                      <CardBack small />
                    </motion.div>
                  );
                })}
              </div>

              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }} className="mt-4">
                <button onClick={() => setView(VIEW.DECK)}
                  className="text-xs tracking-widest uppercase transition-colors text-slate-500 hover:text-slate-300">
                  ← Back to Deck
                </button>
              </motion.div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </section>
  );
}
