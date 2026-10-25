import React, { useState, useEffect, useRef } from 'react';
import { Search, Filter, Edit2, ChevronLeft, ChevronRight, DownloadCloud, Plus, GraduationCap, X, UploadCloud, FileType, CheckCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useGlobalFilters } from '../context/useGlobalFilters';
import { apiDeleteRows, apiUpsertTable, apiFetchTable } from '../lib/api';
import { Trash2 } from 'lucide-react';

export default function StudentList() {
    const { filterRows } = useGlobalFilters();
    const [students, setStudents] = useState([]);
    // The value is not rendered anywhere, but setIsLoading is called around
    // each fetch, so the pair stays and only the unread half is elided.
    const [, setIsLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const navigate = useNavigate();
    const [semesters, setSemesters] = useState([]);
    const [uploadSemesterId, setUploadSemesterId] = useState('');
    const [currentPage, setCurrentPage] = useState(1);
    
    // Checkbox & Bulk Selection State
    const [selectedStudentIds, setSelectedStudentIds] = useState([]);

    // Status & Details Edit Modal State
    const [editingStudent, setEditingStudent] = useState(null);
    const [editStudentForm, setEditStudentForm] = useState({
        student_id: '',
        name: '',
        email: '',
        branch: '',
        section: '',
        year: '3',
        status: 'Active'
    });

    const handleOpenEditModal = (student) => {
        setEditingStudent(student);
        setEditStudentForm({
            student_id: student.student_id || student.id || '',
            name: student.name || '',
            email: student.email || '',
            branch: student.branch || 'BTech CSE',
            section: student.section || '',
            year: student.year ? String(student.year) : '3',
            status: student.status || 'Active'
        });
    };

    const handleEditStudentSubmit = async (e) => {
        e.preventDefault();
        if (!editingStudent) return;
        try {
            const updatedRoll = editStudentForm.student_id.trim();
            const updatedName = editStudentForm.name.trim();
            const updatedEmail = editStudentForm.email.trim();
            const updatedBranch = editStudentForm.branch.trim();
            const updatedYear = parseInt(editStudentForm.year) || 3;
            // Empty means "no section allocated" -- send NULL, not "", so the
            // column reads as unset rather than as a blank section name.
            const updatedSection = editStudentForm.section.trim() || null;
            const updatedStatus = editStudentForm.status;

            const row = {
                id: editingStudent.id,
                student_id: updatedRoll,
                roll_number: updatedRoll,
                name: updatedName,
                email: updatedEmail,
                branch: updatedBranch,
                year: updatedYear,
                section: updatedSection,
                status: updatedStatus,
                ...(editingStudent.semester_id ? { semester_id: editingStudent.semester_id } : {})
            };

            // 1. Update main `students` table in Supabase
            const response = await apiUpsertTable('students', [row], 'id');
            const saved = response?.data?.[0] || row;

            // 2. Cross-portal sync to `teams_validation`
            try {
                const teams = await apiFetchTable('teams_validation');
                const matchedStudentIds = new Set([
                    String(editingStudent.id).toLowerCase(),
                    String(editingStudent.student_id || '').toLowerCase(),
                    String(editingStudent.email || '').toLowerCase()
                ]);

                for (const team of teams) {
                    if (!team.members) continue;
                    let members = Array.isArray(team.members) ? team.members : [];
                    if (typeof team.members === 'string') {
                        try { members = JSON.parse(team.members); } catch (_) { members = []; }
                    }

                    let memberChanged = false;
                    const updatedMembers = members.map(m => {
                        const mId = String(m.id || m.student_id || m.roll || m.email || '').toLowerCase();
                        if (matchedStudentIds.has(mId)) {
                            memberChanged = true;
                            return {
                                ...m,
                                name: updatedName,
                                email: updatedEmail,
                                roll: updatedRoll,
                                student_id: updatedRoll,
                                branch: updatedBranch,
                                section: updatedSection,
                                year: updatedYear
                            };
                        }
                        return m;
                    });

                    if (memberChanged) {
                        await apiUpsertTable('teams_validation', [{
                            ...team,
                            members: updatedMembers
                        }], 'id');
                    }
                }
            } catch (syncErr) {
                console.warn("Teams validation cross-portal sync warning:", syncErr);
            }

            // 3. Cross-portal sync to `unassigned_students`
            try {
                const unassignedList = await apiFetchTable('unassigned_students');
                const matchedId = String(editingStudent.id).toLowerCase();
                const matched = unassignedList.find(u => 
                    String(u.id).toLowerCase() === matchedId || 
                    String(u.student_id || u.roll || '').toLowerCase() === matchedId || 
                    String(u.email || '').toLowerCase() === matchedId
                );
                if (matched) {
                    await apiUpsertTable('unassigned_students', [{
                        ...matched,
                        name: updatedName,
                        email: updatedEmail,
                        roll: updatedRoll,
                        student_id: updatedRoll,
                        branch: updatedBranch,
                        section: updatedSection,
                        year: updatedYear
                    }], 'id');
                }
            } catch (unassignedErr) {
                console.warn("Unassigned students sync warning:", unassignedErr);
            }

            setStudents(prev => prev.map(s => s.id === editingStudent.id ? { ...s, ...saved } : s));
            setEditingStudent(null);
            alert('Student details updated & synchronized across all portals successfully!');
        } catch (err) {
            console.error("Failed to update student details", err);
            alert("Error updating student details: " + err.message);
        }
    };

    // Add Student State
    const [isAddModalOpen, setIsAddModalOpen] = useState(false);
    const [newStudentForm, setNewStudentForm] = useState({
        student_id: '',
        name: '',
        email: '',
        branch: '',
        year: '3',
        section: 'A',
        status: 'Active'
    });

    const handleAddStudent = async (e) => {
        e.preventDefault();
        try {
            const row = {
                id: newStudentForm.student_id.trim(),
                student_id: newStudentForm.student_id.trim(),
                name: newStudentForm.name.trim(),
                email: newStudentForm.email.trim(),
                branch: newStudentForm.branch.trim(),
                year: parseInt(newStudentForm.year),
                section: newStudentForm.section.trim(),
                status: newStudentForm.status,
                semester_id: uploadSemesterId || semesters[0]?.id
            };
            const response = await apiUpsertTable('students', [row], 'id');
            const saved = response?.data?.[0] || row;
            setStudents(prev => [saved, ...prev]);
            setIsAddModalOpen(false);
            setNewStudentForm(prev => ({
                student_id: '',
                name: '',
                email: '',
                branch: 'BTech CSE',
                year: prev.year || '3',
                section: 'A',
                status: 'Active'
            }));
            alert('Student added successfully!');
        } catch (err) {
            console.error("Failed to add student", err);
            alert("Error adding student: " + err.message);
        }
    };

    const handleDeleteStudent = async (studentId) => {
        if (!confirm("Are you sure you want to delete this student record? This action cannot be undone.")) return;
        try {
            await apiDeleteRows('students', { id: studentId });
            setStudents(prev => prev.filter(s => s.id !== studentId));
            alert("Student deleted successfully.");
        } catch (err) {
            console.error("Failed to delete student", err);
            alert("Error deleting student: " + err.message);
        }
    };

    // Inline Upload State
    const [isUploadMode, setIsUploadMode] = useState(false);
    const [dragActive, setDragActive] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const fileInputRef = useRef(null);

    const itemsPerPage = 10;

    // Filters & Search
    const filteredStudents = filterRows(students).filter(s => {
        const matchesSearch = s.name.toLowerCase().includes(searchTerm.toLowerCase()) || (s.student_id || '').toLowerCase().includes(searchTerm.toLowerCase());
        return matchesSearch;
    });

    useEffect(() => {
        let isMounted = true;
        setIsLoading(true);

        Promise.all([
            api.getStudents().catch(err => { console.error("Could not load students", err); return { data: [] }; }),
            api.getSemesterConfig().catch(err => { console.error("Could not load semesters", err); return { data: [] }; })
        ]).then(([studentsRes, semestersRes]) => {
            if (isMounted) {
                setStudents(Array.isArray(studentsRes?.data) ? studentsRes.data : []);
                const sems = Array.isArray(semestersRes?.data) ? semestersRes.data : [];
                setSemesters(sems);
                if (sems.length > 0) {
                    const active = sems.find(s => s.is_active) || sems[0];
                    setUploadSemesterId(active.id);
                    let activeYearStr = '3';
                    if (active.year) {
                        activeYearStr = String(active.year).replace(/\D/g, '') || '3';
                    } else if (active.academic_year) {
                        activeYearStr = String(active.academic_year).replace(/\D/g, '') || '3';
                    } else if (active.name) {
                        const match = active.name.match(/(\d)(?:st|nd|rd|th)?\s*year/i);
                        if (match) activeYearStr = match[1];
                    }
                    setNewStudentForm(prev => ({
                        ...prev,
                        branch: prev.branch || 'BTech CSE',
                        year: activeYearStr
                    }));
                }
            }
        }).finally(() => {
            if (isMounted) setIsLoading(false);
        });

        return () => { isMounted = false; };
    }, []);

    const totalPages = Math.ceil(filteredStudents.length / itemsPerPage) || 1;
    const displayedStudents = filteredStudents.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

    const handleSelectAll = (e) => {
        if (e.target.checked) {
            const allIds = filteredStudents.map(s => s.id);
            setSelectedStudentIds(allIds);
        } else {
            setSelectedStudentIds([]);
        }
    };

    const handleSelectPageOnly = () => {
        const pageIds = displayedStudents.map(s => s.id);
        setSelectedStudentIds(pageIds);
    };

    const handleSelectAllFiltered = () => {
        const allIds = filteredStudents.map(s => s.id);
        setSelectedStudentIds(allIds);
    };

    const handleToggleSelect = (id) => {
        setSelectedStudentIds(prev => 
            prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
        );
    };

    const isAllSelected = filteredStudents.length > 0 && selectedStudentIds.length === filteredStudents.length;

    const handleBulkDelete = async () => {
        if (selectedStudentIds.length === 0) return;
        const totalToDelete = selectedStudentIds.length;
        const confirmMsg = `Are you sure you want to delete ALL ${totalToDelete} selected student record(s)? This will remove them permanently across all database tables and portals.`;
        if (!window.confirm(confirmMsg)) return;

        setIsLoading(true);
        try {
            const CHUNK_SIZE = 100;
            const idsToDelete = [...selectedStudentIds];
            for (let i = 0; i < idsToDelete.length; i += CHUNK_SIZE) {
                const chunk = idsToDelete.slice(i, i + CHUNK_SIZE);
                await apiDeleteRows('students', { id: `in.(${chunk.join(',')})` });
            }

            setStudents(prev => prev.filter(s => !idsToDelete.includes(s.id)));
            setSelectedStudentIds([]);
            alert(`Successfully deleted all ${totalToDelete} student record(s).`);
        } catch (err) {
            console.error("Failed to bulk delete students", err);
            alert("Error deleting students: " + err.message);
        } finally {
            setIsLoading(false);
        }
    };


    const handleExport = () => {
        if (filteredStudents.length === 0) return;
        
        // Define columns
        const headers = ['UUID', 'Roll Number', 'Name', 'Email', 'Branch', 'Year', 'Section', 'Status'];
        
        // Map data
        const csvRows = filteredStudents.map(s => [
            s.id,
            s.student_id || '',
            `"${s.name}"`,
            s.email,
            s.branch,
            s.year,
            s.section || '',
            s.status
        ].join(','));
        
        // Combine and add BOM for Excel
        const csvData = [headers.join(','), ...csvRows].join('\n');
        const blob = new Blob(['\uFEFF' + csvData], { type: 'text/csv;charset=utf-8;' });
        
        // Trigger download
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `students_export_${new Date().toISOString().split('T')[0]}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setSelectedFile(e.dataTransfer.files[0]);
        }
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setSelectedFile(e.target.files[0]);
        }
    };

    return (
        <div className="space-y-6 relative z-10 min-h-[calc(100vh-8rem)]">
            
            {/* Header Banner */}
            <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }} 
                className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-blue-800 rounded-3xl p-8 text-white shadow-xl shadow-indigo-500/20 relative overflow-hidden flex flex-col md:flex-row items-center justify-between border border-indigo-500/30">
                <div className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay">
                    <svg viewBox="0 0 1000 300" preserveAspectRatio="none" className="w-full h-full">
                        <path d="M0,0 C300,300 700,0 1000,300 L1000,0 Z" fill="currentColor"></path>
                    </svg>
                </div>
                <div className="relative z-10 w-full lg:w-2/3">
                    <div className="inline-flex items-center px-4 py-1.5 bg-white/10 backdrop-blur-md rounded-full text-xs font-bold uppercase tracking-wider mb-4 border border-white/20 shadow-sm">
                        <GraduationCap className="w-4 h-4 mr-2" /> Database Interface
                    </div>
                    <h1 className="text-3xl sm:text-4xl font-black mb-3">Student Master Data</h1>
                    <p className="text-indigo-100/90 leading-relaxed text-sm md:text-base max-w-lg">Manage and evaluate all registered candidate records. You can update registration statuses globally or upload batches via our smart CSV parser.</p>
                </div>
                <div className="hidden lg:block relative z-10 transform scale-125 translate-x-12 translate-y-8 opacity-80 pointer-events-none drop-shadow-2xl">
                    <svg viewBox="0 0 200 200" fill="none" className="w-56 h-56 text-indigo-200">
                        <circle cx="100" cy="100" r="80" stroke="currentColor" strokeWidth="8" strokeDasharray="20 10" />
                        <path d="M100 40 L160 80 L160 140 L100 180 L40 140 L40 80 Z" stroke="currentColor" strokeWidth="6" />
                        <circle cx="100" cy="110" r="30" fill="currentColor" opacity="0.5" />
                    </svg>
                </div>
            </motion.div>

            {/* Controls Bar */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }} className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl p-4 sm:p-5 rounded-2xl border border-slate-200/50 dark:border-slate-700/50 flex flex-col xl:flex-row gap-4 xl:items-center shadow-sm">
                
                {/* Search */}
                <div className="relative flex-1 w-full group">
                    <Search className="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
                    <input type="text" placeholder="Search by name or ID..." value={searchTerm} onChange={(e) => {setSearchTerm(e.target.value); setCurrentPage(1);}}
                        className="w-full pl-11 pr-4 py-3 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-medium focus:ring-2 focus:ring-indigo-500 dark:text-white outline-none transition-shadow shadow-sm focus:shadow-md" />
                </div>
                


                {/* Actions */}
                <div className="flex items-center gap-3 border-t xl:border-t-0 xl:border-l border-slate-200 dark:border-slate-700 pt-4 xl:pt-0 xl:pl-4 min-w-max w-full xl:w-auto relative">
                    <button 
                        onClick={handleExport}
                        disabled={filteredStudents.length === 0}
                        className="flex-1 xl:flex-none flex items-center justify-center px-5 py-2.5 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-sm font-bold hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <DownloadCloud className="w-4 h-4 mr-2" /> Export
                    </button>
                    <button onClick={() => setIsAddModalOpen(true)} className="flex-1 xl:flex-none flex items-center justify-center px-5 py-2.5 bg-emerald-600 border border-emerald-500/50 text-white rounded-xl text-sm font-bold hover:bg-emerald-700 shadow-md shadow-emerald-500/20 active:scale-95 transition-all">
                        <Plus className="w-4 h-4 mr-1 md:mr-2 text-emerald-200" /> Add Student
                    </button>
                    <button onClick={() => setIsUploadMode(!isUploadMode)} className="flex-1 xl:flex-none flex items-center justify-center px-5 py-2.5 bg-indigo-600 border border-indigo-500/50 text-white rounded-xl text-sm font-bold hover:bg-indigo-700 shadow-md shadow-indigo-500/20 active:scale-95 transition-all">
                        {isUploadMode ? <X className="w-4 h-4 mr-1 md:mr-2 text-indigo-200" /> : <Plus className="w-4 h-4 mr-1 md:mr-2 text-indigo-200" />} 
                        <span className="hidden md:inline">{isUploadMode ? 'Close Importer' : 'Bulk Add'}</span>
                        <span className="md:hidden">{isUploadMode ? 'Close' : 'Add'}</span>
                    </button>
                    <button
                        onClick={handleBulkDelete}
                        disabled={selectedStudentIds.length === 0}
                        title={selectedStudentIds.length === 0 ? "Select student records below to bulk delete" : "Delete selected student records"}
                        className={`flex-1 xl:flex-none flex items-center justify-center px-5 py-2.5 border rounded-xl text-sm font-bold transition-all ${
                            selectedStudentIds.length > 0
                                ? 'bg-rose-600 border-rose-500/50 text-white hover:bg-rose-700 shadow-md shadow-rose-500/20 active:scale-95'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-slate-200 dark:border-slate-700 opacity-60 cursor-not-allowed'
                        }`}
                    >
                        <Trash2 className="w-4 h-4 mr-2" />
                        <span>Bulk Delete{selectedStudentIds.length > 0 ? ` (${selectedStudentIds.length})` : ''}</span>
                    </button>
                </div>
            </motion.div>

            {/* Inline Upload Zone */}
            <AnimatePresence>
                {isUploadMode && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
                        <div className="bg-white/80 dark:bg-slate-800/80 backdrop-blur-xl rounded-3xl p-6 sm:p-8 border border-indigo-200 dark:border-indigo-500/30 shadow-lg shadow-indigo-500/5 mb-6">
                            <h3 className="text-xl font-black text-slate-800 dark:text-white mb-2 flex items-center"><UploadCloud className="w-5 h-5 mr-2 text-indigo-500" /> Secure Data Importer</h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">Upload CSV or Excel files containing student master records. The system will automatically parse and validate the dataset before committing to the database.</p>
                            
                            <div 
                                className={`relative border-2 border-dashed rounded-3xl p-10 flex flex-col items-center justify-center text-center transition-all duration-300 ${dragActive ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10' : 'border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-800'}`}
                                onDragEnter={handleDrag} onDragOver={handleDrag} onDragLeave={handleDrag} onDrop={handleDrop}
                            >
                                <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".csv,.xlsx,.xls" className="hidden" />
                                
                                {selectedFile ? (
                                    <div className="flex flex-col items-center">
                                        <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mb-4 border-4 border-white dark:border-slate-800 shadow-sm">
                                            <CheckCircle className="w-8 h-8" />
                                        </div>
                                        <h4 className="text-lg font-black text-slate-800 dark:text-white">{selectedFile.name}</h4>
                                        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 mb-6">File successfully staged for parsing.</p>
                                        <div className="flex gap-3 mt-4">
                                            <div className="relative">
                                                <select
                                                    value={uploadSemesterId}
                                                    onChange={(e) => setUploadSemesterId(e.target.value)}
                                                    className="appearance-none bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-sm font-bold rounded-xl px-4 py-2.5 pr-10 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm transition-all"
                                                >
                                                    {semesters.length === 0 && <option value="">No Semesters Found...</option>}
                                                    {semesters.map(sem => (
                                                         <option key={sem.id} value={sem.id}>
                                                             {sem.year} • {sem.semester_type.charAt(0).toUpperCase() + sem.semester_type.slice(1)}{sem.branch ? ` • ${sem.branch}` : ''} • Yr {sem.academic_level} {sem.is_active ? '(Active)' : ''}
                                                         </option>
                                                     ))}
                                                </select>
                                                <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                                                    <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"></path></svg>
                                                </div>
                                            </div>

                                            <button onClick={() => setSelectedFile(null)} className="px-6 py-2.5 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-xs font-black uppercase tracking-widest hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors">Discard</button>
                                            <button 
                                                onClick={() => {
                                                    // This importer never parsed or sent the file -- it only
                                                    // re-read the semester and reported the count as if it
                                                    // had imported. Hand the file to the page that does the
                                                    // real work rather than reimplementing it here.
                                                    navigate('/admin/students/upload');
                                                }} 
                                                className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-black uppercase tracking-widest hover:bg-indigo-700 shadow-lg shadow-indigo-500/30 transition-all flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <UploadCloud className="w-4 h-4 mr-2" /> Open Importer
                                            </button>
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div className="w-20 h-20 bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 rounded-full flex items-center justify-center mb-4 border-4 border-white dark:border-slate-800 shadow-sm relative group cursor-pointer" onClick={() => fileInputRef.current?.click()}>
                                            <UploadCloud className="w-8 h-8 group-hover:scale-110 transition-transform" />
                                            <div className="absolute -bottom-1 -right-1 w-8 h-8 bg-amber-400 rounded-full text-white flex items-center justify-center border-2 border-white dark:border-slate-800 shadow-sm">
                                                <FileType className="w-4 h-4" />
                                            </div>
                                        </div>
                                        <h4 className="text-xl font-black text-slate-800 dark:text-white mb-2">Drag & Drop your manifest here</h4>
                                        <p className="text-sm font-medium text-slate-500 dark:text-slate-400 max-w-md">Supported formats: <span className="font-bold text-slate-700 dark:text-slate-300 bg-slate-200 dark:bg-slate-700 px-1.5 rounded">.csv</span> or <span className="font-bold text-slate-700 dark:text-slate-300 bg-slate-200 dark:bg-slate-700 px-1.5 rounded">.xlsx</span>. Maximum file size of 10MB.</p>
                                        <div className="flex items-center w-64 my-6">
                                            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700"></div>
                                            <span className="px-4 text-xs font-black text-slate-400 uppercase tracking-widest">OR</span>
                                            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-700"></div>
                                        </div>
                                        <button onClick={() => fileInputRef.current?.click()} className="px-6 py-3 bg-white dark:bg-slate-800 text-slate-800 dark:text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-sm hover:shadow-md border border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-500/50 transition-all hover:-translate-y-0.5">
                                            Vfs Directory Browse
                                        </button>
                                    </>
                                )}
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Selection Summary Banner */}
            {selectedStudentIds.length > 0 && (
                <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/60 p-4 rounded-2xl flex flex-wrap items-center justify-between gap-3 text-sm font-medium text-indigo-900 dark:text-indigo-200 shadow-sm">
                    <div className="flex items-center gap-2">
                        <span className="font-black bg-indigo-600 text-white px-3 py-1 rounded-full text-xs shadow-sm">
                            {selectedStudentIds.length} Selected
                        </span>
                        <span className="text-xs sm:text-sm font-semibold">
                            {selectedStudentIds.length === filteredStudents.length
                                ? `All ${filteredStudents.length} students selected across all pages.`
                                : `Selected ${selectedStudentIds.length} of ${filteredStudents.length} students.`}
                        </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs font-bold">
                        {selectedStudentIds.length !== filteredStudents.length && (
                            <button
                                onClick={handleSelectAllFiltered}
                                className="px-3.5 py-1.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors shadow-sm active:scale-95"
                            >
                                Select All {filteredStudents.length} Students
                            </button>
                        )}
                        {selectedStudentIds.length !== displayedStudents.length && (
                            <button
                                onClick={handleSelectPageOnly}
                                className="px-3.5 py-1.5 bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-700 rounded-xl hover:bg-indigo-50 dark:hover:bg-slate-700 transition-colors"
                            >
                                Select Page ({displayedStudents.length})
                            </button>
                        )}
                        <button
                            onClick={() => setSelectedStudentIds([])}
                            className="px-3 py-1.5 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-white transition-colors"
                        >
                            Clear Selection
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Table wrapper */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.2 }} className="bg-white/90 dark:bg-slate-800/90 backdrop-blur-xl rounded-3xl shadow-sm border border-slate-200/50 dark:border-slate-700/50 overflow-hidden min-h-[400px] flex flex-col">
                <div className="overflow-x-auto flex-1">
                    <table className="w-full text-left border-collapse">
                        <thead className="bg-slate-50 dark:bg-slate-800/80 sticky top-0 border-b border-slate-200 dark:border-slate-700 z-10 backdrop-blur-md">
                            <tr>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider pl-6 w-12">
                                    <input
                                        type="checkbox"
                                        checked={isAllSelected}
                                        onChange={handleSelectAll}
                                        className="w-4 h-4 text-indigo-600 rounded border-slate-300 dark:border-slate-600 focus:ring-indigo-500 cursor-pointer"
                                        title={isAllSelected ? "Deselect all students" : `Select all ${filteredStudents.length} students`}
                                    />
                                </th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">ID</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Candidate / Email</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">Progression</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider text-center">Roster Status</th>
                                <th className="p-5 text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider text-right pr-6">Override</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {displayedStudents.map((student) => (
                                <tr key={student.id} className={`hover:bg-slate-50/80 dark:hover:bg-slate-700/30 transition-colors group ${selectedStudentIds.includes(student.id) ? 'bg-indigo-50/40 dark:bg-indigo-500/10' : ''}`}>
                                    <td className="p-5 pl-6 w-12">
                                        <input
                                            type="checkbox"
                                            checked={selectedStudentIds.includes(student.id)}
                                            onChange={() => handleToggleSelect(student.id)}
                                            className="w-4 h-4 text-indigo-600 rounded border-slate-300 dark:border-slate-600 focus:ring-indigo-500 cursor-pointer"
                                        />
                                    </td>
                                    <td className="p-5">
                                        <span className="text-sm font-black text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-3 py-1 rounded-lg border border-indigo-100 dark:border-indigo-500/20 shadow-sm">{student.student_id}</span>
                                    </td>
                                    <td className="p-5">
                                        <div className="text-sm font-bold text-slate-900 dark:text-white leading-tight">{student.name}</div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">{student.email}</div>
                                    </td>
                                    <td className="p-5">
                                        <div className="text-sm font-semibold text-slate-700 dark:text-slate-300 flex items-center">
                                            {student.branch} 
                                            <span className="mx-2 w-1 h-1 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                                            <span className="text-xs text-slate-500 dark:text-slate-400">{student.section ? `Sec ${student.section}` : 'No section'}</span>
                                        </div>
                                        <div className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mt-1 border border-slate-200 dark:border-slate-700 inline-block px-2 py-0.5 rounded-md">Year {student.year}</div>
                                    </td>
                                    <td className="p-5 text-center">
                                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border shadow-sm ${
                                            student.status === 'Active' ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/30' :
                                            student.status === 'Inactive' ? 'bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/30' :
                                            'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-700/50 dark:text-slate-300 dark:border-slate-600/50'
                                        }`}>
                                            {student.status === 'Active' && <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-2 animate-pulse"></span>}
                                            {student.status}
                                        </span>
                                    </td>
                                    <td className="p-5 text-right pr-6 flex justify-end items-center space-x-2">
                                        <button onClick={() => handleOpenEditModal(student)} className="p-2 text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-all rounded-xl hover:bg-indigo-50 dark:hover:bg-indigo-500/10 inline-flex shadow-sm opacity-60 group-hover:opacity-100 transform group-hover:scale-105" aria-label="Edit Student Details">
                                            <Edit2 className="w-4 h-4" />
                                        </button>
                                        <button onClick={() => handleDeleteStudent(student.id)} className="p-2 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 transition-all rounded-xl hover:bg-rose-50 dark:hover:bg-rose-500/10 inline-flex shadow-sm opacity-60 group-hover:opacity-100 transform group-hover:scale-105" aria-label="Delete Student">
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                            {displayedStudents.length === 0 && (
                                <tr>
                                    <td colSpan="6" className="p-12">
                                        <div className="flex flex-col items-center justify-center text-center">
                                            <div className="w-16 h-16 bg-slate-100 dark:bg-slate-800 rounded-2xl flex items-center justify-center mb-4 text-slate-400">
                                                <Search className="w-8 h-8" />
                                            </div>
                                            <h3 className="text-lg font-bold text-slate-700 dark:text-slate-200">No matches found</h3>
                                            <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">Adjust your search or filter parameters.</p>
                                        </div>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
                
                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="p-4 sm:px-6 border-t border-slate-100 dark:border-slate-700 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/50">
                        <div className="text-sm text-slate-500 dark:text-slate-400 font-medium hidden sm:block">
                            Showing <span className="text-slate-800 dark:text-white font-bold">{(currentPage - 1) * itemsPerPage + 1}</span> to <span className="text-slate-800 dark:text-white font-bold">{Math.min(currentPage * itemsPerPage, filteredStudents.length)}</span> of <span className="text-slate-800 dark:text-white font-bold">{filteredStudents.length}</span> students
                        </div>
                        <div className="flex space-x-2 w-full sm:w-auto justify-end">
                            <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 disabled:opacity-30 disabled:hover:text-slate-500 bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 transition-colors"><ChevronLeft className="w-5 h-5" /></button>
                            <div className="px-5 py-2 text-sm font-bold bg-white dark:bg-slate-800 text-slate-800 dark:text-white rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 flex items-center justify-center min-w-[3rem] tracking-widest">{currentPage} / {totalPages}</div>
                            <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="p-2 text-slate-500 hover:text-indigo-600 dark:text-slate-400 dark:hover:text-indigo-400 disabled:opacity-30 disabled:hover:text-slate-500 bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 transition-colors"><ChevronRight className="w-5 h-5" /></button>
                        </div>
                    </div>
                )}
            </motion.div>

            {/* Edit Student Modal */}
            <AnimatePresence>
                {editingStudent && (
                    <motion.div key="edit-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 shadow-2xl overflow-y-auto">
                        <motion.div key="edit-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden my-8">
                            <div className="bg-gradient-to-r from-indigo-600 to-indigo-800 p-6 flex justify-between items-start">
                                <div className="text-white">
                                    <h3 className="font-black text-xl">Edit Student Details</h3>
                                    <p className="text-xs text-indigo-100/90 mt-1 font-medium">{editingStudent.name} • {editingStudent.student_id || editingStudent.id}</p>
                                </div>
                                <button onClick={() => setEditingStudent(null)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-4 h-4"/></button>
                            </div>
                            <form onSubmit={handleEditStudentSubmit} className="p-6 space-y-4">
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Student ID / Roll No</label>
                                    <input type="text" required value={editStudentForm.student_id} onChange={(e) => setEditStudentForm(prev => ({...prev, student_id: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. 2415500410" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Full Name</label>
                                    <input type="text" required value={editStudentForm.name} onChange={(e) => setEditStudentForm(prev => ({...prev, name: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. Samarth Verma" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Email Address</label>
                                    <input type="email" required value={editStudentForm.email} onChange={(e) => setEditStudentForm(prev => ({...prev, email: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="e.g. student@gla.ac.in" />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Branch</label>
                                        <select required value={['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(editStudentForm.branch) ? editStudentForm.branch : 'custom'} onChange={(e) => {
                                            const val = e.target.value;
                                            setEditStudentForm(prev => ({...prev, branch: val === 'custom' ? '' : val}));
                                        }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer">
                                            <option value="BTech CSE">BTech CSE</option>
                                            <option value="Btech CS-AIML">Btech CS-AIML</option>
                                            <option value="BTech CS(AIML+IOT)">BTech CS(AIML+IOT)</option>
                                            <option value="custom">✏️ Custom (Write manually)...</option>
                                        </select>
                                        {!['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(editStudentForm.branch) && (
                                            <input type="text" required value={editStudentForm.branch} onChange={(e) => setEditStudentForm(prev => ({...prev, branch: e.target.value}))} className="mt-2 w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-indigo-300 dark:border-indigo-500 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Write custom branch" />
                                        )}
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Section</label>
                                        <select value={editStudentForm.section} onChange={(e) => setEditStudentForm(prev => ({...prev, section: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer">
                                            <option value="">No section allocated</option>
                                            {['A','B','C','D','E','F','G','H','I','J','CS-A','CS-B','CS-C','CS-D'].map(sec => (
                                                <option key={sec} value={sec}>Section {sec}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Year</label>
                                        <select value={editStudentForm.year} onChange={(e) => setEditStudentForm(prev => ({...prev, year: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer">
                                            <option value="1">1st Year</option>
                                            <option value="2">2nd Year</option>
                                            <option value="3">3rd Year</option>
                                            <option value="4">4th Year</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Status</label>
                                        <select value={editStudentForm.status} onChange={(e) => setEditStudentForm(prev => ({...prev, status: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm font-semibold dark:text-white outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer">
                                            <option value="Active">Active Student (Verified)</option>
                                            <option value="Inactive">Inactive / Suspended</option>
                                            <option value="Graduated">Alumni / Graduated</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 pt-4">
                                    <button type="button" onClick={() => setEditingStudent(null)} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" className="px-5 py-2.5 text-sm font-bold text-white bg-indigo-600 border border-indigo-500/50 hover:bg-indigo-700 rounded-xl transition-all shadow-lg shadow-indigo-500/30 active:scale-95">Save Changes</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Add Student Modal */}
            <AnimatePresence>
                {isAddModalOpen && (
                    <motion.div key="add-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 shadow-2xl overflow-y-auto">
                        <motion.div key="add-modal" initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} className="bg-white dark:bg-slate-800 rounded-3xl shadow-2xl w-full max-w-md border border-slate-200 dark:border-slate-700 overflow-hidden my-8">
                            <div className="bg-gradient-to-r from-emerald-600 to-emerald-800 p-6 flex justify-between items-start">
                                <div className="text-white">
                                    <h3 className="font-black text-xl">Add New Student</h3>
                                    <p className="text-xs text-emerald-100/90 mt-1 font-medium">Create a single student record manually</p>
                                </div>
                                <button onClick={() => setIsAddModalOpen(false)} className="p-1.5 bg-black/10 hover:bg-black/20 text-white rounded-full transition-colors"><X className="w-4 h-4"/></button>
                            </div>
                            <form onSubmit={handleAddStudent} className="p-6 space-y-4">
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Student ID / Roll No</label>
                                    <input type="text" required value={newStudentForm.student_id} onChange={(e) => setNewStudentForm(prev => ({...prev, student_id: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. 210150101" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Name</label>
                                    <input type="text" required value={newStudentForm.name} onChange={(e) => setNewStudentForm(prev => ({...prev, name: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Rahul Sharma" />
                                </div>
                                <div>
                                    <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Email</label>
                                    <input type="email" required value={newStudentForm.email} onChange={(e) => setNewStudentForm(prev => ({...prev, email: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="e.g. rahul@example.com" />
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Branch</label>
                                        <select required value={['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(newStudentForm.branch) ? newStudentForm.branch : 'custom'} onChange={(e) => {
                                            const val = e.target.value;
                                            setNewStudentForm(prev => ({...prev, branch: val === 'custom' ? '' : val}));
                                        }} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer">
                                            <option value="BTech CSE">BTech CSE</option>
                                            <option value="Btech CS-AIML">Btech CS-AIML</option>
                                            <option value="BTech CS(AIML+IOT)">BTech CS(AIML+IOT)</option>
                                            <option value="custom">✏️ Custom (Write manually)...</option>
                                        </select>
                                        {!['BTech CSE', 'Btech CS-AIML', 'BTech CS(AIML+IOT)'].includes(newStudentForm.branch) && (
                                            <input type="text" required value={newStudentForm.branch} onChange={(e) => setNewStudentForm(prev => ({...prev, branch: e.target.value}))} className="mt-2 w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-emerald-300 dark:border-emerald-500 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500" placeholder="Write custom branch manually" />
                                        )}
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Section</label>
                                        <select required value={newStudentForm.section} onChange={(e) => setNewStudentForm(prev => ({...prev, section: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer">
                                            {['A','B','C','D','E','F','G','H','I','J','CS-A','CS-B','CS-C','CS-D'].map(sec => (
                                                <option key={sec} value={sec}>Section {sec}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Year</label>
                                        <select value={newStudentForm.year} onChange={(e) => setNewStudentForm(prev => ({...prev, year: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer">
                                            <option value="1">1st Year</option>
                                            <option value="2">2nd Year</option>
                                            <option value="3">3rd Year</option>
                                            <option value="4">4th Year</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs uppercase tracking-widest font-bold text-slate-500 dark:text-slate-400 mb-2">Status</label>
                                        <select value={newStudentForm.status} onChange={(e) => setNewStudentForm(prev => ({...prev, status: e.target.value}))} className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm dark:text-white outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer">
                                            <option value="Active">Active</option>
                                            <option value="Inactive">Inactive</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-t border-slate-100 dark:border-slate-700 flex justify-end space-x-3 pt-4">
                                    <button type="button" onClick={() => setIsAddModalOpen(false)} className="px-5 py-2.5 text-sm font-bold text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">Cancel</button>
                                    <button type="submit" className="px-5 py-2.5 text-sm font-bold text-white bg-emerald-600 border border-emerald-500/50 hover:bg-emerald-700 rounded-xl transition-all shadow-lg shadow-emerald-500/30 active:scale-95">Add Record</button>
                                </div>
                            </form>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
