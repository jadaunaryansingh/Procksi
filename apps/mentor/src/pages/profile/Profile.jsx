import React, { useState, useEffect } from 'react';
import { User, Mail, FileText, Save, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';

const Profile = () => {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    profileInfo: ''
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);
  const [validationErrors, setValidationErrors] = useState({});

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const response = await api.get('/me');
        const data = response.data?.user || response.data || {};
        setFormData({
          name: data.name || '',
          email: data.email || '',
          profileInfo: data.profileInfo || data.bio || ''
        });
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to load profile data.');
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear validation error when user types
    if (validationErrors[name]) {
      setValidationErrors(prev => ({ ...prev, [name]: null }));
    }
    setSuccess(false);
  };

  const validateForm = () => {
    const errors = {};
    if (!formData.name.trim()) errors.name = 'Name is required';
    if (!formData.email.trim()) {
      errors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      errors.email = 'Email address is invalid';
    }
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateForm()) return;
    
    setSaving(true);
    setError(null);
    setSuccess(false);
    
    try {
      await api.patch('/me', formData);
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to update profile.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center items-center min-h-[400px]"><Loader2 className="w-10 h-10 animate-spin text-indigo-500" /></div>;
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="mb-8 mt-2">
        <h2 className="text-2xl font-black text-slate-900 dark:text-slate-100 flex items-center gap-3">
           <User className="text-indigo-600 dark:text-indigo-400" /> My Profile
        </h2>
        <p className="text-sm font-medium text-slate-500 mt-1">Manage your personal information and preferences.</p>
      </div>

      {error && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/30 text-rose-600 dark:text-rose-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm animate-in fade-in">
          <AlertCircle className="w-5 h-5 mr-3 shrink-0" />
          {error}
        </div>
      )}

      {success && (
        <div className="bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 text-emerald-600 dark:text-emerald-400 px-4 py-3 rounded-xl text-sm font-bold flex items-center shadow-sm animate-in fade-in">
          <CheckCircle2 className="w-5 h-5 mr-3 shrink-0" />
          Profile updated successfully.
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700/50 overflow-hidden shadow-sm">
        <div className="p-8 space-y-6">
          
          {/* Name Field */}
          <div>
            <label className="flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">
              <User size={16} className="text-slate-400" /> Full Name
            </label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              disabled={saving}
              className={`w-full bg-slate-50 dark:bg-slate-900 border ${validationErrors.name ? 'border-rose-300 focus:ring-rose-500' : 'border-slate-200 dark:border-slate-700 focus:ring-indigo-500'} rounded-xl px-4 py-3 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 shadow-sm transition-shadow disabled:opacity-50`}
              placeholder="Enter your full name"
            />
            {validationErrors.name && <p className="text-rose-500 text-xs font-semibold mt-1.5">{validationErrors.name}</p>}
          </div>

          {/* Email Field */}
          <div>
            <label className="flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">
              <Mail size={16} className="text-slate-400" /> Email Address
            </label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              disabled={saving}
              className={`w-full bg-slate-50 dark:bg-slate-900 border ${validationErrors.email ? 'border-rose-300 focus:ring-rose-500' : 'border-slate-200 dark:border-slate-700 focus:ring-indigo-500'} rounded-xl px-4 py-3 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 shadow-sm transition-shadow disabled:opacity-50`}
              placeholder="Enter your email address"
            />
            {validationErrors.email && <p className="text-rose-500 text-xs font-semibold mt-1.5">{validationErrors.email}</p>}
          </div>

          {/* Profile Information Field */}
          <div>
            <label className="flex items-center gap-2 text-sm font-bold text-slate-700 dark:text-slate-300 mb-2">
              <FileText size={16} className="text-slate-400" /> Profile Information
            </label>
            <textarea
              name="profileInfo"
              value={formData.profileInfo}
              onChange={handleChange}
              disabled={saving}
              rows={5}
              className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-sm transition-shadow resize-none disabled:opacity-50"
              placeholder="Tell us about your expertise and background..."
            />
          </div>

        </div>

        {/* Footer actions */}
        <div className="bg-slate-50 dark:bg-slate-900/50 border-t border-slate-200 dark:border-slate-800 p-6 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-8 py-3 rounded-xl font-bold transition-all shadow-md active:scale-95 disabled:opacity-50 disabled:active:scale-100 w-full sm:w-auto"
          >
            {saving ? <><Loader2 size={18} className="animate-spin" /> Saving...</> : <><Save size={18} /> Save Changes</>}
          </button>
        </div>
      </form>
    </div>
  );
};

export default Profile;
