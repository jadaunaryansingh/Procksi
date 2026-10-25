import React from 'react';
import { motion } from 'framer-motion';
import { Mail, Phone, MapPin, Clock, BookOpen, GraduationCap } from 'lucide-react';
import { useMentor } from '../hooks/useStudentData';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

const BANNER_GRADIENTS = [
    'from-indigo-500 via-purple-500 to-pink-500',
    'from-emerald-500 via-teal-500 to-cyan-500',
    'from-amber-500 via-orange-500 to-rose-500',
    'from-sky-500 via-blue-500 to-violet-500',
];

function MentorCard({ mentor, idx }) {
    const gradient = BANNER_GRADIENTS[idx % BANNER_GRADIENTS.length];
    const expertiseList = Array.isArray(mentor.expertise) ? mentor.expertise : [mentor.expertise].filter(Boolean);
    const skillsList = Array.isArray(mentor.skills) ? mentor.skills : [mentor.skills].filter(Boolean);
    const domainsList = Array.isArray(mentor.domains) ? mentor.domains : [mentor.domains].filter(Boolean);

    // Merge all tags to show
    const tags = Array.from(new Set([...expertiseList, ...skillsList, ...domainsList]));

    return (
        <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 overflow-hidden shadow-sm hover:shadow-lg transition-shadow"
        >
            {/* Banner */}
            <div className={`h-28 md:h-36 bg-gradient-to-r ${gradient} relative overflow-hidden`}>
                <svg className="absolute inset-0 w-full h-full opacity-20 mix-blend-overlay pointer-events-none" xmlns="http://www.w3.org/2000/svg">
                    <defs>
                        <pattern id={`mentor-pattern-${idx}`} width="40" height="40" patternUnits="userSpaceOnUse">
                            <path d="M0 40L40 0H20L0 20M40 40V20L20 40" stroke="currentColor" strokeWidth="2" fill="none" />
                        </pattern>
                    </defs>
                    <rect width="100%" height="100%" fill={`url(#mentor-pattern-${idx})`} />
                </svg>
            </div>

            <div className="px-6 md:px-8 pb-8 relative">
                {/* Avatar + name row */}
                <div className="flex flex-col sm:flex-row sm:items-end gap-5 -mt-12 md:-mt-16 mb-6">
                    <img
                        src={mentor.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(mentor.name)}&background=6366f1&color=fff&size=200`}
                        alt={mentor.name}
                        className="w-24 h-24 md:w-32 md:h-32 rounded-full border-4 border-white dark:border-slate-800 shadow-lg object-cover bg-white dark:bg-slate-900 relative z-10 shrink-0"
                    />
                    <div className="flex-1 sm:pb-2">
                        <h3 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white leading-tight">{mentor.name}</h3>
                        <p className="text-slate-500 dark:text-slate-400 font-medium mt-0.5">{mentor.department || 'Faculty'}</p>
                    </div>
                    <div className="flex gap-2 sm:pb-2 shrink-0">
                        {mentor.email && (
                            <a
                                href={`mailto:${mentor.email}`}
                                className="flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold text-sm shadow-sm transition-colors group"
                            >
                                <Mail className="w-4 h-4 mr-1.5 group-hover:scale-110 transition-transform" /> Email
                            </a>
                        )}
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Expertise/Skills tag list */}
                    <div className="bg-slate-50 dark:bg-slate-900/50 p-5 rounded-2xl border border-slate-100 dark:border-slate-700/50">
                        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-3 flex items-center">
                            <BookOpen className="w-4 h-4 mr-2 text-indigo-500" /> Area of Expertise & Skills
                        </h4>
                        <div className="flex flex-wrap gap-2">
                            {tags.length > 0 ? tags.map((skill, i) => (
                                <span key={i} className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500/50 text-slate-700 dark:text-slate-300 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all">
                                    {skill}
                                </span>
                            )) : (
                                <span className="text-slate-400 text-sm italic">Not specified</span>
                            )}
                        </div>
                    </div>

                    {/* Contact */}
                    <div data-tour="student-mentor-contact" className="bg-slate-50 dark:bg-slate-900/50 p-5 rounded-2xl border border-slate-100 dark:border-slate-700/50 space-y-4">
                        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-1 border-b border-slate-200 dark:border-slate-700 pb-3">Contact Details</h4>

                        {mentor.email && (
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-full bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center shrink-0">
                                    <Mail className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                </div>
                                <div>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">Email</p>
                                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 break-all">{mentor.email}</p>
                                </div>
                            </div>
                        )}

                        {mentor.phone && (
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-full bg-emerald-100 dark:bg-emerald-500/10 flex items-center justify-center shrink-0">
                                    <Phone className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                                </div>
                                <div>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">Mobile</p>
                                    <a href={`tel:${mentor.phone}`} className="text-sm font-semibold text-slate-800 dark:text-slate-200 hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors">
                                        {mentor.phone}
                                    </a>
                                </div>
                            </div>
                        )}

                        {mentor.availability && (
                            <div className="flex items-center gap-3">
                                <div className="w-9 h-9 rounded-full bg-purple-100 dark:bg-purple-500/10 flex items-center justify-center shrink-0">
                                    <Clock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                                </div>
                                <div>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">Office Hours / Availability</p>
                                    <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">{mentor.availability}</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </motion.div>
    );
}

export default function MentorView() {
    const { data: mentor, loading, error, refetch } = useMentor();

    if (loading) {
        return (
            <div className="space-y-6">
                <LoadingSkeleton lines={6} />
            </div>
        );
    }

    if (error && error !== "No mentor assigned to your team yet" && error !== "Student is not assigned to a team") {
        return <ErrorCard message={error} onRetry={refetch} />;
    }

    // Normalize
    const mentorList = Array.isArray(mentor) ? mentor : (mentor ? [mentor] : []);

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center">
                    <GraduationCap className="w-6 h-6 mr-3 text-indigo-500" />
                    {mentorList.length > 1 ? 'My Assigned Mentors' : 'My Assigned Mentor'}
                    {mentorList.length > 0 && (
                        <span className="ml-3 text-sm font-semibold px-3 py-1 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-700 dark:text-indigo-400 rounded-full">
                            {mentorList.length} Assigned
                        </span>
                    )}
                </h2>
            </div>

            {mentorList.length === 0 ? (
                <div className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 p-14 text-center shadow-sm">
                    <GraduationCap className="w-16 h-16 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                    <h3 className="text-xl font-bold text-slate-800 dark:text-slate-100 mb-2">No Mentor Assigned Yet</h3>
                    <p className="text-slate-500 dark:text-slate-400 max-w-md mx-auto text-sm">
                        Your team will be assigned a mentor soon. Keep checking back here or watch your notifications for updates.
                    </p>
                </div>
            ) : (
                mentorList.map((m, idx) => (
                    <MentorCard key={m.id || m.name || idx} mentor={m} idx={idx} />
                ))
            )}
        </div>
    );
}
