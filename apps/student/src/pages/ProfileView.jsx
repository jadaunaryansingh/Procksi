import React, { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { User, Shield, Lock, CheckCircle2, AlertCircle, Camera, Loader2, Edit3, Save, X, Phone, FileText, Code } from 'lucide-react';
import { useProfile, fetchWithAuth } from '../hooks/useStudentData';
import { supabase } from '../lib/supabase';
import LoadingSkeleton from '../components/LoadingSkeleton';
import ErrorCard from '../components/ErrorCard';

export const ProfileView = () => {
    const { data: profile, loading, error, refetch } = useProfile();
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [pwdLoading, setPwdLoading] = useState(false);
    const [pwdSuccess, setPwdSuccess] = useState('');
    const [pwdError, setPwdError] = useState('');

    const fileInputRef = useRef(null);
    const [avatarUploading, setAvatarUploading] = useState(false);
    const [avatarError, setAvatarError] = useState('');

    const [isEditing, setIsEditing] = useState(false);
    const [editData, setEditData] = useState({ name: '', phone: '', bio: '', skills: '' });
    const [saveLoading, setSaveLoading] = useState(false);
    const [saveError, setSaveError] = useState('');

    const handleEditClick = () => {
        setEditData({
            name: profile?.name || '',
            phone: profile?.phone || '',
            bio: profile?.bio || '',
            skills: profile?.skills || ''
        });
        setSaveError('');
        setIsEditing(true);
    };

    const handleSaveProfile = async () => {
        try {
            setSaveLoading(true);
            setSaveError('');
            await fetchWithAuth('/api/student/me', {
                method: 'PATCH',
                body: editData
            });
            await refetch();
            setIsEditing(false);
        } catch (err) {
            setSaveError(err.message || 'Failed to update profile.');
        } finally {
            setSaveLoading(false);
        }
    };

    const handleAvatarClick = () => {
        if (!avatarUploading) {
            fileInputRef.current?.click();
        }
    };

    const handleAvatarChange = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            setAvatarError('Please select a valid image file.');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            setAvatarError('Image size must be under 5 MB.');
            return;
        }

        setAvatarUploading(true);
        setAvatarError('');

        try {
            const { data: { session } } = await supabase.auth.getSession();
            const userId = session?.user?.id || 'unknown';
            const ext = file.name.split('.').pop();
            const filePath = `avatars/${userId}/${Date.now()}.${ext}`;
            const bucket = 'PMS';

            const { error: uploadError } = await supabase.storage
                .from(bucket)
                .upload(filePath, file, { upsert: true });

            if (uploadError) throw uploadError;

            const { data: urlData } = supabase.storage.from(bucket).getPublicUrl(filePath);
            const publicUrl = urlData?.publicUrl;

            if (!publicUrl) throw new Error('Failed to get public URL');

            // Call backend API to update avatar
            await fetchWithAuth('/api/student/avatar', {
                method: 'PATCH',
                body: { avatar_url: publicUrl }
            });

            // Refetch profile to update topbar and view
            await refetch();
        } catch (err) {
            setAvatarError(err.message || 'Failed to upload image.');
        } finally {
            setAvatarUploading(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }
    };

    if (loading) {
        return (
            <div className="max-w-5xl mx-auto space-y-6">
                <LoadingSkeleton lines={6} />
            </div>
        );
    }

    if (error) {
        return <ErrorCard message={error} onRetry={refetch} />;
    }

    const handlePasswordChange = async (e) => {
        e.preventDefault();
        setPwdError('');
        setPwdSuccess('');

        if (newPassword.length < 6) {
            setPwdError('Password must be at least 6 characters long.');
            return;
        }

        if (newPassword !== confirmPassword) {
            setPwdError('Passwords do not match.');
            return;
        }

        setPwdLoading(true);
        try {
            const { error: authErr } = await supabase.auth.updateUser({
                password: newPassword
            });
            if (authErr) {
                setPwdError(authErr.message);
            } else {
                setPwdSuccess('Password changed successfully!');
                setNewPassword('');
                setConfirmPassword('');
            }
        } catch {
            setPwdError('An unexpected error occurred. Please try again.');
        } finally {
            setPwdLoading(false);
        }
    };

    const studentName = profile?.name || 'Student';
    const avatarUrl = profile?.avatar_url || `https://ui-avatars.com/api/?name=${encodeURIComponent(studentName)}&background=random`;
    const isTeamLeader = profile?.team_membership?.role === 'LEADER';
    const teamName = profile?.team?.name || 'No Team Assigned';

    return (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-5xl mx-auto space-y-6">
            <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 border border-slate-200 dark:border-slate-700/50 shadow-sm relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-32 bg-gradient-to-r from-indigo-500 to-purple-600"></div>
                <div className="relative mt-12 flex flex-col sm:flex-row items-center sm:items-end gap-6">
                    <div 
                        onClick={handleAvatarClick}
                        className="w-32 h-32 rounded-full border-4 border-white dark:border-slate-800 overflow-hidden bg-slate-100 shrink-0 shadow-lg relative group cursor-pointer"
                    >
                        <img src={avatarUrl} alt="Profile" className="w-full h-full object-cover" />
                        <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                            {avatarUploading ? (
                                <Loader2 className="w-8 h-8 text-white animate-spin" />
                            ) : (
                                <Camera className="w-8 h-8 text-white" />
                            )}
                        </div>
                    </div>
                    <input 
                        type="file"
                        ref={fileInputRef}
                        accept="image/*"
                        onChange={handleAvatarChange}
                        className="hidden"
                    />

                    <div className="flex-1 text-center sm:text-left mb-2 w-full">
                        <div className="flex flex-col sm:flex-row items-center sm:items-start justify-between gap-4">
                            <div className="flex-1">
                                {isEditing ? (
                                    <input 
                                        type="text" 
                                        value={editData.name} 
                                        onChange={(e) => setEditData({...editData, name: e.target.value})}
                                        className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-2 w-full outline-none focus:ring-2 focus:ring-indigo-500"
                                        placeholder="Your Name"
                                    />
                                ) : (
                                    <h1 className="text-3xl font-bold text-slate-900 dark:text-white">{studentName}</h1>
                                )}
                                <p className="text-slate-500 dark:text-slate-400 flex items-center justify-center sm:justify-start mt-1">
                                    <User className="w-4 h-4 mr-1.5" /> Student
                                </p>
                            </div>
                            
                            {!isEditing ? (
                                <button
                                    onClick={handleEditClick}
                                    className="flex items-center px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-colors font-semibold text-sm border border-slate-200 dark:border-slate-600/50"
                                >
                                    <Edit3 className="w-4 h-4 mr-2" /> Edit Profile
                                </button>
                            ) : (
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setIsEditing(false)}
                                        disabled={saveLoading}
                                        className="flex items-center px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl transition-colors font-semibold text-sm border border-slate-200 dark:border-slate-600/50 disabled:opacity-50"
                                    >
                                        <X className="w-4 h-4 mr-1" /> Cancel
                                    </button>
                                    <button
                                        onClick={handleSaveProfile}
                                        disabled={saveLoading}
                                        className="flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl transition-colors font-semibold text-sm disabled:opacity-50 shadow-sm"
                                    >
                                        {saveLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                                        Save
                                    </button>
                                </div>
                            )}
                        </div>
                        {saveError && (
                            <p className="text-xs font-semibold text-rose-500 mt-2 flex items-center justify-center sm:justify-start gap-1">
                                <AlertCircle className="w-3.5 h-3.5" />
                                {saveError}
                            </p>
                        )}
                        {avatarError && (
                            <p className="text-xs font-semibold text-rose-500 mt-2 flex items-center justify-center sm:justify-start gap-1">
                                <AlertCircle className="w-3.5 h-3.5 animate-bounce" />
                                {avatarError}
                            </p>
                        )}
                        {avatarUploading && (
                            <p className="text-xs font-semibold text-indigo-500 mt-2 flex items-center justify-center sm:justify-start gap-1">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Updating profile photo...
                            </p>
                        )}
                    </div>
                </div>

                {isEditing ? (
                    <div className="mt-8 space-y-4 max-w-2xl">
                        <div className="space-y-1">
                            <label className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center"><Phone className="w-3.5 h-3.5 mr-1" /> Phone Number</label>
                            <input 
                                type="text"
                                value={editData.phone}
                                onChange={e => setEditData({...editData, phone: e.target.value})}
                                placeholder="+1 234 567 890"
                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-sm font-medium text-slate-800 dark:text-white"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center"><FileText className="w-3.5 h-3.5 mr-1" /> Bio / About Me</label>
                            <textarea 
                                value={editData.bio}
                                onChange={e => setEditData({...editData, bio: e.target.value})}
                                placeholder="Tell us about yourself..."
                                rows={3}
                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-sm font-medium text-slate-800 dark:text-white resize-none"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center"><Code className="w-3.5 h-3.5 mr-1" /> Skills</label>
                            <input 
                                type="text"
                                value={editData.skills}
                                onChange={e => setEditData({...editData, skills: e.target.value})}
                                placeholder="e.g. React, Python, Machine Learning"
                                className="w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl outline-none focus:ring-2 focus:ring-indigo-500 text-sm font-medium text-slate-800 dark:text-white"
                            />
                        </div>
                    </div>
                ) : (
                    <div className="mt-8">
                        {(profile?.phone || profile?.bio || profile?.skills) && (
                            <div className="mb-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                                {profile?.phone && (
                                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 flex items-center"><Phone className="w-3.5 h-3.5 mr-1" /> Phone</p>
                                        <p className="font-medium text-slate-800 dark:text-slate-200">{profile.phone}</p>
                                    </div>
                                )}
                                {profile?.skills && (
                                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 flex items-center"><Code className="w-3.5 h-3.5 mr-1" /> Skills</p>
                                        <div className="flex flex-wrap gap-2 mt-2">
                                            {profile.skills.split(',').map((skill, idx) => (
                                                <span key={idx} className="px-2.5 py-1 bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400 rounded-lg text-xs font-bold">
                                                    {skill.trim()}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {profile?.bio && (
                                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50 md:col-span-2">
                                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1 flex items-center"><FileText className="w-3.5 h-3.5 mr-1" /> Bio</p>
                                        <p className="font-medium text-slate-800 dark:text-slate-200 text-sm">{profile.bio}</p>
                                    </div>
                                )}
                            </div>
                        )}
                        <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 mb-4 border-b border-slate-100 dark:border-slate-700 pb-2">Academic Details</h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Email Address</p>
                                <p className="font-medium text-slate-800 dark:text-slate-200">{profile?.email}</p>
                            </div>
                            <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                                <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Student Roll Number</p>
                                <p className="font-medium text-slate-800 dark:text-slate-200">{profile?.roll_number}</p>
                            </div>
                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Academic Year / Branch</p>
                        <p className="font-medium text-slate-800 dark:text-slate-200">Year {profile?.year} · {profile?.branch} (Sec {profile?.section})</p>
                    </div>
                    <div className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-700/50">
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Current Team</p>
                        <p className="font-medium text-slate-800 dark:text-slate-200">{teamName} {isTeamLeader ? '(Leader)' : '(Member)'}</p>
                    </div>
                    </div>
                    </div>
                )}
            </div>

            {/* Change Password Card */}
            <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 border border-slate-200 dark:border-slate-700/50 shadow-sm">
                <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 flex items-center mb-6">
                    <Shield className="w-5 h-5 mr-2 text-indigo-500" /> Account Security
                </h3>

                <form onSubmit={handlePasswordChange} className="space-y-4 max-w-md">
                    {pwdError && (
                        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 p-3.5 rounded-xl text-sm font-semibold flex items-center">
                            <AlertCircle className="w-5 h-5 mr-2" />
                            {pwdError}
                        </div>
                    )}
                    {pwdSuccess && (
                        <div className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 p-3.5 rounded-xl text-sm font-semibold flex items-center">
                            <CheckCircle2 className="w-5 h-5 mr-2" />
                            {pwdSuccess}
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">New Password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-400" />
                            <input
                                type="password"
                                placeholder="••••••••"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                required
                                disabled={pwdLoading}
                                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none text-slate-700 dark:text-slate-200"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Confirm New Password</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-400" />
                            <input
                                type="password"
                                placeholder="••••••••"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                required
                                disabled={pwdLoading}
                                className="w-full pl-10 pr-4 py-2.5 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none text-slate-700 dark:text-slate-200"
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={pwdLoading}
                        className="bg-slate-900 dark:bg-indigo-600 hover:bg-slate-800 dark:hover:bg-indigo-700 text-white px-6 py-2.5 rounded-xl text-sm font-semibold transition-all active:scale-95 shadow-sm disabled:opacity-50"
                    >
                        {pwdLoading ? 'Updating...' : 'Update Password'}
                    </button>
                </form>
            </div>
        </motion.div>
    );
};

export default ProfileView;
