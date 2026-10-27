import React, { useState, useEffect } from 'react';
import { AlertTriangle, Clock, Users, FileX, RefreshCw, X, CheckCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { jsPDF } from 'jspdf';
import { panelAPI } from '../../services/api';
import { requirePanelId } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const MissedSubmissions = () => {
  const [missedData, setMissedData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [sendingRequest, setSendingRequest] = useState(false);
  const [showSuccessPopup, setShowSuccessPopup] = useState(false);
  const { semesterMap, filterRows } = useGlobalFilters();
  const filteredMissedData = filterRows(missedData);

  useEffect(() => {
    const fetchMissedSubmissions = async () => {
      try {
        const panelId = requirePanelId();
        const data = await panelAPI.getMissed(panelId);
        setMissedData(data);
      } catch (err) {
        console.error('Failed to fetch missed submissions:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMissedSubmissions();
  }, []);

  const handleRefresh = () => {
    setLoading(true);
    setError(null);
    const fetchMissedSubmissions = async () => {
      try {
        const panelId = requirePanelId();
        const data = await panelAPI.getMissed(panelId);
        setMissedData(data);
      } catch (err) {
        console.error('Failed to fetch missed submissions:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchMissedSubmissions();
  };

  const handleNotifyAdministrator = () => {
    setShowRescheduleModal(true);
  };

  const handleSelectTeam = (team) => {
    setSelectedTeam(team);
  };

  const handleSendRescheduleRequest = async () => {
    if (!selectedTeam) {
      alert('Please select a team first');
      return;
    }

    setSendingRequest(true);
    try {
      const panelId = requirePanelId();
      await panelAPI.requestReschedule(panelId, selectedTeam.team_id);

      setShowRescheduleModal(false);
      setShowSuccessPopup(true);
      setTimeout(() => setShowSuccessPopup(false), 3000);
      setSelectedTeam(null);
    } catch (err) {
      console.error('Failed to send reschedule request:', err);
      alert(err.message || 'Failed to send request. Please try again.');
    } finally {
      setSendingRequest(false);
    }
  };

  const handleDownloadReport = () => {
    try {
      const panelId = requirePanelId();
      const reportDate = new Date().toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
      const reportTime = new Date().toLocaleTimeString();

      // Create PDF
      const doc = new jsPDF();
      
      // Set document properties
      doc.setProperties({
        title: 'Missed Evaluation Submissions Report',
        subject: `Report for Panel ${panelId}`,
        author: 'Panel Portal System',
        keywords: 'missed, submissions, evaluation, report',
        creator: 'Procksi Panel Portal'
      });

      // Header
      doc.setFontSize(18);
      doc.setFont('helvetica', 'bold');
      doc.text('MISSED EVALUATION SUBMISSIONS REPORT', 105, 20, { align: 'center' });
      
      // Line separator
      doc.setLineWidth(0.5);
      doc.line(20, 25, 190, 25);

      // Report Info
      let y = 35;
      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Panel ID: ${panelId}`, 20, y);
      y += 7;
      doc.text(`Generated: ${reportDate}`, 20, y);
      y += 7;
      doc.text(`Time: ${reportTime}`, 20, y);

      // Separator line
      y += 5;
      doc.setLineWidth(0.3);
      doc.line(20, y, 190, y);

      // Summary Section
      y += 10;
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('SUMMARY', 20, y);
      
      y += 10;
      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.text(`Total Missed Submissions: ${filteredMissedData.length}`, 20, y);
      y += 7;
      doc.text(`Unique Teams Affected: ${new Set(filteredMissedData.map(item => item.team_id)).size}`, 20, y);

      // Detailed List Section
      y += 15;
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('DETAILED LIST', 20, y);
      
      y += 10;
      doc.setFontSize(10);
      
      filteredMissedData.forEach((item, index) => {
        // Check if we need a new page
        if (y > 260) {
          doc.addPage();
          y = 20;
        }
        
        doc.setFont('helvetica', 'bold');
        doc.text(`${index + 1}. Team ${item.team_id}: ${item.team_name}`, 20, y);
        y += 6;
        doc.setFont('helvetica', 'normal');
        doc.text(`   Time Slot: ${item.slot}`, 20, y);
        y += 6;
        doc.text(`   Status: ${item.status}`, 20, y);
        y += 10;
      });

      // Recommended Actions
      if (y > 220) {
        doc.addPage();
        y = 20;
      } else {
        y += 5;
      }
      
      doc.setFontSize(14);
      doc.setFont('helvetica', 'bold');
      doc.text('RECOMMENDED ACTIONS', 20, y);
      
      y += 10;
      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');
      
      const actions = [
        '1. Contact each affected team to understand the circumstances',
        '2. Schedule alternative evaluation slots if necessary',
        '3. Document any special circumstances for the record',
        '4. Report to the Chief Administrator for final decision'
      ];
      
      actions.forEach(action => {
        const lines = doc.splitTextToSize(action, 170);
        doc.text(lines, 20, y);
        y += 6 * lines.length + 2;
      });

      // Footer
      const pageCount = doc.internal.getNumberOfPages();
      for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        doc.setFontSize(8);
        doc.setFont('helvetica', 'italic');
        doc.text(
          'This report was generated automatically by the Panel Portal System.',
          105,
          285,
          { align: 'center' }
        );
        doc.text(`Page ${i} of ${pageCount}`, 105, 290, { align: 'center' });
      }

      // Save the PDF
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      doc.save(`missed_submissions_report_panel_${panelId}_${timestamp}.pdf`);

      alert('Report downloaded successfully! Check your Downloads folder.');
    } catch (err) {
      console.error('Failed to download report:', err);
      alert('Failed to generate report. Please try again.');
    }
  };

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          Failed to load missed submissions: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
            Missed Submissions
          </h2>
          <p className="text-slate-500 font-medium">
            Teams whose evaluation deadlines were missed
          </p>
        </div>

        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-rose-100 dark:bg-rose-500/20 rounded-xl">
              <FileX className="text-rose-600 dark:text-rose-400" size={24} />
            </div>
            <div data-tour="panel-missed-totals">
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {filteredMissedData.length}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">Total Missed</p>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-amber-100 dark:bg-amber-500/20 rounded-xl">
              <AlertTriangle className="text-amber-600 dark:text-amber-400" size={24} />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {filteredMissedData.filter(item => item.status === 'Missed').length}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">Action Required</p>
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-slate-100 dark:bg-slate-700 rounded-xl">
              <Users className="text-slate-600 dark:text-slate-400" size={24} />
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {new Set(filteredMissedData.map(item => item.team_id)).size}
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">Unique Teams</p>
            </div>
          </div>
        </div>
      </div>

      {/* Missed Submissions Table */}
      <div className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden">
        <div className="px-8 py-6 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">
            Missed Evaluation Details
          </h3>
        </div>

        {filteredMissedData.length === 0 ? (
          <div className="p-12 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 dark:bg-emerald-500/20 rounded-full mb-4">
              <FileX className="text-emerald-600 dark:text-emerald-400" size={32} />
            </div>
            <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2">
              No Missed Submissions
            </h4>
            <p className="text-slate-500 dark:text-slate-400">
              All evaluations have been submitted on time.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table data-tour="panel-missed-list" className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Team Information
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Time Slot
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {filteredMissedData.map((item, index) => (
                  <tr key={index} className="hover:bg-slate-50 dark:hover:bg-slate-900/30 transition-colors">
                    <td className="px-6 py-4">
                      <div>
                        <div className="text-sm font-medium text-slate-900 dark:text-slate-100">
                          {teamDisplayLabel(item.team_id, item, semesterMap)}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2 text-sm text-slate-900 dark:text-slate-100">
                        <Clock size={14} className="text-slate-400" />
                        {item.slot}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                        item.status === 'Missed'
                          ? 'bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-400'
                          : 'bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400'
                      }`}>
                        <AlertTriangle size={10} />
                        {item.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => {
                          setSelectedTeam(item);
                          setShowRescheduleModal(true);
                        }}
                        className="text-sm text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 font-medium"
                      >
                        Request Reschedule
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Alert Section */}
      {filteredMissedData.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-2xl p-6">
          <div className="flex items-start gap-4">
            <div className="p-2 bg-amber-100 dark:bg-amber-500/20 rounded-lg">
              <AlertTriangle className="text-amber-600 dark:text-amber-400" size={20} />
            </div>
            <div className="flex-1">
              <h4 className="font-semibold text-amber-800 dark:text-amber-200 mb-2">
                Action Required
              </h4>
              <p className="text-sm text-amber-700 dark:text-amber-300 mb-3">
                The following teams missed their evaluation deadlines. Please contact the administrator
                to arrange for alternative evaluation methods or document the circumstances.
              </p>
              <div className="flex gap-3">
                <button onClick={handleNotifyAdministrator} className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-colors">
                  Request Reschedule
                </button>
                <button onClick={handleDownloadReport} className="px-4 py-2 bg-white dark:bg-slate-800 border border-amber-200 dark:border-amber-500/20 text-amber-700 dark:text-amber-300 rounded-lg text-sm font-medium hover:bg-amber-100 dark:hover:bg-amber-500/10 transition-colors">
                  Download Report
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reschedule Modal */}
      <AnimatePresence>
        {showRescheduleModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => !sendingRequest && setShowRescheduleModal(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                onClick={(e) => e.stopPropagation()}
                className="bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden"
              >
                <div className="p-6 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
                  <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                    Request Reschedule
                  </h3>
                  <button
                    onClick={() => !sendingRequest && setShowRescheduleModal(false)}
                    className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                    disabled={sendingRequest}
                  >
                    <X size={20} className="text-slate-500" />
                  </button>
                </div>

                <div className="p-6 max-h-[60vh] overflow-y-auto">
                  <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
                    Select a team to request the administrator to reschedule their missed evaluation slot.
                  </p>

                  <div className="space-y-2">
                    {filteredMissedData.map((item) => (
                      <button
                        key={item.team_id}
                        onClick={() => handleSelectTeam(item)}
                        className={`w-full p-4 rounded-xl border-2 transition-all text-left ${
                          selectedTeam?.team_id === item.team_id
                            ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10'
                            : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-bold text-slate-900 dark:text-slate-100">
                              {teamDisplayLabel(item.team_id, item, semesterMap)}
                            </p>
                            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                              Missed Slot: {item.slot}
                            </p>
                          </div>
                          {selectedTeam?.team_id === item.team_id && (
                            <CheckCircle className="text-emerald-500" size={24} />
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="p-6 border-t border-slate-200 dark:border-slate-700 flex gap-3 justify-end">
                  <button
                    onClick={() => !sendingRequest && setShowRescheduleModal(false)}
                    disabled={sendingRequest}
                    className="px-4 py-2 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleSendRescheduleRequest}
                    disabled={!selectedTeam || sendingRequest}
                    className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
                  >
                    {sendingRequest ? (
                      <>
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                        Sending...
                      </>
                    ) : (
                      'Send Request'
                    )}
                  </button>
                </div>
              </motion.div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Success Popup */}
      <AnimatePresence>
        {showSuccessPopup && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
            className="fixed bottom-6 right-6 z-50 bg-emerald-600 text-white px-6 py-4 rounded-xl shadow-2xl flex items-center gap-3"
          >
            <CheckCircle size={24} />
            <div>
              <p className="font-bold">Request Sent Successfully!</p>
              <p className="text-sm text-emerald-100">Administrator has been notified</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MissedSubmissions;
