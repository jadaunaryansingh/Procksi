import React from 'react';
import { motion } from 'framer-motion';
import ChromaGrid from './ChromaGrid';

export default function TeamSection() {
  const teamMembers = [
    {
      image: "https://i.pravatar.cc/300?img=12",
      title: "Parv Agarwal",
      subtitle: "AI Product Engineer",
      handle: "@parv_ai",
      borderColor: "#d946ef",
      gradient: "linear-gradient(145deg, #d946ef, #000)",
    },
    {
      image: "https://i.pravatar.cc/300?img=68",
      title: "Yash Jain",
      subtitle: "Frontend Developer",
      handle: "@yash_dev",
      borderColor: "#3B82F6",
      gradient: "linear-gradient(180deg, #3B82F6, #000)",
    },
    {
      image: "/team/aaradhya.png",
      title: "Aaradhya Rawat",
      subtitle: "Frontend Developer",
      handle: "@aaradhya_r",
      borderColor: "#0ea5e9",
      gradient: "linear-gradient(135deg, #0ea5e9, #000)",
    },
    {
      image: "/team/aryan.jpeg",
      title: "Aryan Singh Jadaun",
      subtitle: "Backend Developer",
      handle: "@aryan_backend",
      borderColor: "#10B981",
      gradient: "linear-gradient(210deg, #10B981, #000)",
    },
    {
      image: "https://i.pravatar.cc/300?img=33",
      title: "Nischal Saxena",
      subtitle: "Backend Developer",
      handle: "@nischal_dev",
      borderColor: "#059669",
      gradient: "linear-gradient(165deg, #059669, #000)",
    },
    {
      image: "https://i.pravatar.cc/300?img=15",
      title: "Samarth Verma",
      subtitle: "AI Agent Developer",
      handle: "@samarth_ai",
      borderColor: "#a855f7",
      gradient: "linear-gradient(195deg, #a855f7, #000)",
    },
    {
      image: "https://i.pravatar.cc/300?img=11",
      title: "Saurav",
      subtitle: "Cloud & Deploy",
      handle: "@saurav_cloud",
      borderColor: "#f59e0b",
      gradient: "linear-gradient(225deg, #f59e0b, #000)",
    },
    {
      image: "https://i.pravatar.cc/300?img=5",
      title: "Mansi Singh",
      subtitle: "Cloud & Deploy",
      handle: "@mansi_cloud",
      borderColor: "#f97316",
      gradient: "linear-gradient(135deg, #f97316, #000)",
    }
  ];

  return (
    <section className="py-24 relative overflow-hidden bg-slate-950 border-t border-slate-800">
      {/* Cool animated SVG Background */}
      <div className="absolute inset-0 z-0 opacity-20 pointer-events-none mix-blend-screen" style={{ backgroundImage: 'radial-gradient(circle at 2px 2px, rgba(255,255,255,0.15) 1px, transparent 0)', backgroundSize: '32px 32px' }}></div>
      {/* Background ambient lighting */}
      <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/4 left-1/4 w-[40%] h-[40%] bg-indigo-600/10 rounded-full blur-[120px]"></div>
        <div className="absolute bottom-1/4 right-1/4 w-[30%] h-[30%] bg-purple-600/10 rounded-full blur-[100px]"></div>
      </div>

      <div className="max-w-7xl mx-auto px-6 relative z-10">
        <div className="text-center mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <h2 className="text-4xl md:text-5xl font-extrabold mb-4 tracking-tight text-white">
              Meet The <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">Architects</span>
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto">
              The creative minds and technical wizards behind the Procksi.
            </p>
          </motion.div>
        </div>

        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          className="w-full flex justify-center pb-20 relative"
        >
          <div className="w-full max-w-[1200px] relative z-10 p-8 md:p-12 bg-slate-900/40 backdrop-blur-2xl rounded-xl border border-white/5 shadow-2xl" style={{ minHeight: '800px' }}>
            
            {/* Cool Tech SVG Corner Accents */}
            <svg className="absolute top-0 left-0 w-12 h-12 text-indigo-500 -translate-x-2 -translate-y-2 pointer-events-none z-20" viewBox="0 0 100 100" fill="none">
              <path d="M 2 40 V 2 H 40" stroke="currentColor" strokeWidth="3" />
              <rect x="0" y="0" width="8" height="8" fill="currentColor" />
            </svg>
            <svg className="absolute top-0 right-0 w-12 h-12 text-purple-500 translate-x-2 -translate-y-2 pointer-events-none z-20" viewBox="0 0 100 100" fill="none">
              <path d="M 98 40 V 2 H 60" stroke="currentColor" strokeWidth="3" />
              <rect x="92" y="0" width="8" height="8" fill="currentColor" />
            </svg>
            <svg className="absolute bottom-0 left-0 w-12 h-12 text-cyan-500 -translate-x-2 translate-y-2 pointer-events-none z-20" viewBox="0 0 100 100" fill="none">
              <path d="M 2 60 V 98 H 40" stroke="currentColor" strokeWidth="3" />
              <rect x="0" y="92" width="8" height="8" fill="currentColor" />
            </svg>
            <svg className="absolute bottom-0 right-0 w-12 h-12 text-pink-500 translate-x-2 translate-y-2 pointer-events-none z-20" viewBox="0 0 100 100" fill="none">
              <path d="M 98 60 V 98 H 60" stroke="currentColor" strokeWidth="3" />
              <rect x="92" y="92" width="8" height="8" fill="currentColor" />
            </svg>

            <ChromaGrid 
              items={teamMembers}
              radius={400}
              damping={0.5}
              fadeOut={0.7}
              ease="power3.out"
            />
          </div>
        </motion.div>
      </div>
    </section>
  );
}
