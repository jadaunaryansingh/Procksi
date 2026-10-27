import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ShieldCheck, FileCheck, Clock, User, Lock, Download, Share, CheckCircle2, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { jsPDF } from 'jspdf';
import { evaluationAPI } from '../../services/api';
import { requirePanelId } from '../../services/session';
import { useGlobalFilters } from '../../context/useGlobalFilters';
import { teamDisplayLabel } from '../../lib/globalFilters';

const SecureSubmissionReceipt = () => {
  const { teamId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const resolvedTeamId = teamId || searchParams.get('team');

  const [receiptData, setReceiptData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const { semesterMap } = useGlobalFilters();

  const fetchReceipt = async () => {
    if (!resolvedTeamId) {
      setError('Missing team id in route.');
      setLoading(false);
      return;
    }

    try {
      const panelId = requirePanelId();
      const data = await evaluationAPI.getSubmissionReceipt(resolvedTeamId, panelId);
      setReceiptData(data);
      setError(null);
      return data;
    } catch (err) {
      console.error('Failed to fetch receipt data:', err);
      setError(err.message || 'Failed to fetch receipt data');
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReceipt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTeamId]);

  const handleVerifyReceipt = async () => {
    setVerifying(true);
    try {
      const latest = await fetchReceipt();
      alert(latest?.verified ? 'Receipt is verified.' : 'Receipt is not verified yet.');
    } catch (err) {
      console.error('Verification failed:', err);
      alert('Verification failed. Please try again later.');
    } finally {
      setVerifying(false);
    }
  };

  const handleDownloadReceipt = () => {
    if (!receiptData) {
      return;
    }

    try {
      const doc = new jsPDF();
      
      // Set document properties
      doc.setProperties({
        title: 'Evaluation Submission Receipt',
        subject: `Receipt for Team ${receiptData.team_id}`,
        author: 'Panel Portal System',
        keywords: 'evaluation, receipt, submission',
        creator: 'Procksi Panel Portal'
      });

      // Header
      doc.setFontSize(20);
      doc.setFont('helvetica', 'bold');
      doc.text('EVALUATION SUBMISSION RECEIPT', 105, 20, { align: 'center' });
      
      // Line separator
      doc.setLineWidth(0.5);
      doc.line(20, 25, 190, 25);

      // Receipt Information
      let y = 40;
      doc.setFontSize(12);
      doc.setFont('helvetica', 'bold');
      doc.text('Receipt Information:', 20, y);
      
      y += 10;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(11);
      doc.text(`Receipt ID: ${receiptData.receipt_id}`, 20, y);
      y += 7;
      doc.text(`Panel ID: ${receiptData.panel_id}`, 20, y);
      y += 7;
      doc.text(`Team ID: ${receiptData.team_id}`, 20, y);
      y += 7;
      doc.text(`Team Name: ${receiptData.team_name}`, 20, y);
      y += 7;
      doc.text(`Project: ${receiptData.project_title || 'N/A'}`, 20, y);

      // Submission Details
      y += 15;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(12);
      doc.text('Submission Details:', 20, y);
      
      y += 10;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(11);
      doc.text(`Total Score: ${receiptData.total_score}`, 20, y);
      y += 7;
      doc.text(`Submission Time: ${receiptData.submitted_at}`, 20, y);

      // Security Information
      y += 15;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(12);
      doc.text('Security Information:', 20, y);
      
      y += 10;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(11);
      doc.text(`Digital Signature: ${receiptData.digital_signature || 'Unavailable'}`, 20, y);
      y += 7;
      doc.text(`Blockchain Hash: ${receiptData.blockchain_hash || 'Unavailable'}`, 20, y);
      y += 7;
      const verificationStatus = receiptData.verified ? 'Verified ✓' : 'Pending';
      doc.text(`Verification Status: ${verificationStatus}`, 20, y);

      // Remarks
      y += 15;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(12);
      doc.text('Remarks:', 20, y);
      
      y += 10;
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(10);
      const remarks = receiptData.remarks || 'No remarks provided';
      const remarksLines = doc.splitTextToSize(remarks, 170);
      doc.text(remarksLines, 20, y);

      // Footer
      const pageHeight = doc.internal.pageSize.height;
      doc.setFontSize(8);
      doc.setFont('helvetica', 'italic');
      doc.text('This is a computer-generated document. No signature is required.', 105, pageHeight - 15, { align: 'center' });
      doc.text(`Generated on: ${new Date().toLocaleString()}`, 105, pageHeight - 10, { align: 'center' });

      // Save the PDF
      doc.save(`evaluation_receipt_${receiptData.team_id}_${Date.now()}.pdf`);
    } catch (err) {
      console.error('Failed to generate PDF:', err);
      alert('Failed to generate PDF receipt. Please try again.');
    }
  };

  const handleShareReceipt = async () => {
    if (!receiptData) {
      return;
    }

    if (navigator.share) {
      try {
        await navigator.share({
          title: 'Evaluation Submission Receipt',
          text: `Evaluation for Team ${receiptData.team_id} has been submitted. Receipt ID: ${receiptData.receipt_id}`,
          url: window.location.href
        });
      } catch (err) {
        console.log('Share cancelled or failed:', err);
      }
    } else {
      const shareText = `Evaluation for Team ${receiptData.team_id} submitted. Receipt ID: ${receiptData.receipt_id}`;
      await navigator.clipboard.writeText(shareText);
      alert('Receipt details copied to clipboard!');
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-600 dark:text-red-400 px-4 py-3 rounded-xl">
          Failed to load submission receipt: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-3xl font-black text-slate-900 dark:text-slate-100 mb-2">
            Secure Submission Receipt
          </h2>
          <p className="text-slate-500 font-medium">
            Immutable proof of submitted evaluation from backend records
          </p>
        </div>

        <div className="flex items-center gap-2 px-4 py-2 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/20 rounded-lg">
          <ShieldCheck className="text-emerald-600 dark:text-emerald-400" size={20} />
          <span className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
            {receiptData?.verified ? 'Verified' : 'Pending'}
          </span>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-slate-700/50 shadow-sm overflow-hidden"
      >
        <div className="bg-gradient-to-r from-emerald-50 to-emerald-100 dark:from-emerald-500/10 dark:to-emerald-500/20 px-8 py-6 border-b border-emerald-200 dark:border-emerald-500/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-emerald-600 dark:bg-emerald-500 rounded-xl">
                <FileCheck className="text-white" size={24} />
              </div>
              <div>
                <h3 className="text-xl font-bold text-emerald-900 dark:text-emerald-100">
                  Evaluation Submitted Successfully
                </h3>
                <p className="text-emerald-700 dark:text-emerald-300 text-sm">
                  Retrieved from the evaluation database
                </p>
              </div>
            </div>

            <div className="text-right">
              <div className="text-2xl font-mono font-bold text-emerald-900 dark:text-emerald-100">
                {receiptData?.receipt_id}
              </div>
              <div className="text-xs text-emerald-700 dark:text-emerald-300 uppercase tracking-wider">
                Receipt ID
              </div>
            </div>
          </div>
        </div>

        <div className="p-8 space-y-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <User size={16} />
                Submission Details
              </h4>
              <div className="space-y-3">
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Panel ID</span>
                  <span className="font-mono font-bold text-slate-900 dark:text-slate-100">{receiptData?.panel_id}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Team</span>
                  <span className="font-bold text-slate-900 dark:text-slate-100">{teamDisplayLabel(receiptData?.team_id, receiptData, semesterMap)}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Project</span>
                  <span className="font-bold text-slate-900 dark:text-slate-100">{receiptData?.project_title || 'N/A'}</span>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <Clock size={16} />
                Timestamp Information
              </h4>
              <div className="space-y-3">
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Submitted At</span>
                  <span className="font-mono text-sm text-slate-900 dark:text-slate-100">
                    {receiptData?.submitted_at ? new Date(receiptData.submitted_at).toLocaleString() : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Total Score</span>
                  <span className="font-bold text-emerald-600 dark:text-emerald-400">{receiptData?.total_score}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700">
                  <span className="text-sm text-slate-500 dark:text-slate-400">Status</span>
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 size={14} />
                    Locked
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-slate-50 dark:bg-slate-900/50 rounded-xl p-6 border border-slate-200 dark:border-slate-700">
            <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
              <Lock size={16} />
              Security & Verification
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider">Digital Signature</span>
                <div className="font-mono text-xs text-slate-700 dark:text-slate-300 mt-1 break-all">
                  {receiptData?.digital_signature || 'Unavailable'}
                </div>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider">Blockchain Hash</span>
                <div className="font-mono text-xs text-slate-700 dark:text-slate-300 mt-1 break-all">
                  {receiptData?.blockchain_hash || 'Unavailable'}
                </div>
              </div>
            </div>
          </div>

          {receiptData?.remarks && (
            <div>
              <h4 className="font-semibold text-slate-900 dark:text-slate-100 mb-4">Evaluator Remarks</h4>
              <div className="p-4 bg-slate-50 dark:bg-slate-900/30 rounded-lg">
                <p className="text-sm text-slate-700 dark:text-slate-300 italic">"{receiptData.remarks}"</p>
              </div>
            </div>
          )}
        </div>

        <div className="px-8 py-6 bg-slate-50 dark:bg-slate-900/30 border-t border-slate-200 dark:border-slate-700">
          <div className="flex flex-wrap gap-3 justify-between">
            <div className="flex gap-3">
              <button
                onClick={handleVerifyReceipt}
                disabled={verifying}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-400 text-white rounded-lg font-medium transition-colors"
              >
                {verifying ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    Verifying...
                  </>
                ) : (
                  <>
                    <ShieldCheck size={16} />
                    Verify Receipt
                  </>
                )}
              </button>

              <button
                onClick={handleDownloadReceipt}
                className="flex items-center gap-2 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors"
              >
                <Download size={16} />
                Download
              </button>

              <button
                onClick={handleShareReceipt}
                className="flex items-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 rounded-lg font-medium hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
              >
                <Share size={16} />
                Share
              </button>
            </div>

            <button
              onClick={() => navigate('/panel')}
              className="px-4 py-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 font-medium transition-colors"
            >
              Back to Dashboard
            </button>
          </div>
        </div>
      </motion.div>

      <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-xl p-6">
        <div className="flex items-start gap-4">
          <div className="p-2 bg-amber-100 dark:bg-amber-500/20 rounded-lg">
            <AlertCircle className="text-amber-600 dark:text-amber-400" size={20} />
          </div>
          <div>
            <h4 className="font-semibold text-amber-800 dark:text-amber-200 mb-2">
              Security Notice
            </h4>
            <p className="text-sm text-amber-700 dark:text-amber-300">
              This receipt is generated from immutable backend submission records. Any mismatch during verification indicates tampering and should be reported to the administrator.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SecureSubmissionReceipt;
