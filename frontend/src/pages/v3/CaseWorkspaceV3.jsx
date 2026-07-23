import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Send,
  Upload,
  FileText,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Lock,
  Download,
  RefreshCw,
  ChevronRight,
  ChevronLeft,
  MessageSquare,
  Briefcase,
  Scale,
  TrendingDown,
  TrendingUp,
  DollarSign,
  AlertTriangle,
  Info,
  Sparkles,
  Paperclip,
  MoreVertical,
  Eye,
  Trash2,
  Clock,
  User,
  Bot,
  Copy,
  Check,
  Filter,
  Search,
  ArrowLeft,
  Play,
  ShieldCheck,
  ExternalLink,
  Wrench,
  File,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';

// Document type configurations
const DOCUMENT_TYPES = {
  FORM_16: { label: 'Form 16', icon: FileText, color: 'blue' },
  AIS: { label: 'AIS', icon: FileText, color: 'green' },
  '26AS': { label: '26AS', icon: FileText, color: 'purple' },
  BANK_STATEMENT: { label: 'Bank Statement', icon: FileText, color: 'indigo' },
  CAPITAL_GAINS: { label: 'Capital Gains', icon: TrendingUp, color: 'emerald' },
  PREVIOUS_ITR: { label: 'Previous ITR', icon: FileText, color: 'amber' },
  OTHER: { label: 'Other Document', icon: FileText, color: 'gray' },
};

// Quick action definitions
const QUICK_ACTIONS = [
  { id: 'summarize', label: 'Summarize this client', icon: Sparkles },
  { id: 'foreign_assets', label: 'Check for foreign assets', icon: AlertTriangle },
  { id: 'deductions', label: 'Review deductions', icon: TrendingDown },
  { id: 'regime_comparison', label: 'Compare tax regimes', icon: Scale },
  { id: 'missing_info', label: 'Identify missing info', icon: AlertTriangle },
  { id: 'tax_saving', label: 'Find tax saving opportunities', icon: DollarSign },
];

// Document processing states
const DOC_STATUS = {
  PENDING: { label: 'Pending', color: 'text-gray-500', bg: 'bg-gray-100', icon: Clock },
  UPLOADING: { label: 'Uploading', color: 'text-blue-500', bg: 'bg-blue-100', icon: Upload },
  PROCESSING: { label: 'Processing', color: 'text-amber-500', bg: 'bg-amber-100', icon: Loader2 },
  PASSWORD_REQUIRED: { label: 'Password Required', color: 'text-orange-500', bg: 'bg-orange-100', icon: Lock },
  COMPLETED: { label: 'Completed', color: 'text-green-500', bg: 'bg-green-100', icon: CheckCircle2 },
  FAILED: { label: 'Failed', color: 'text-red-500', bg: 'bg-red-100', icon: AlertCircle },
};

// Always reduce an API/network error to a human string. FastAPI `detail` can be
// an object (e.g. duplicate/password errors return {message, document_id, ...});
// rendering an object as a React child throws (React error #31), so never let
// one reach state or JSX.
const errText = (err, fallback = 'Something went wrong') => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || detail.detail || JSON.stringify(detail);
  return err?.message || fallback;
};

// Empty export identity template
const emptyExportIdentity = {
  pan: '',
  first_name: '',
  middle_name: '',
  surname: '',
  date_of_birth: '',
  email: '',
  mobile: '',
  address: {
    ResidenceNo: '',
    ResidenceName: '',
    CityOrTownOrDistrict: '',
    StateCode: '',
    PinCode: '',
  },
  verification_place: '',
  verification_capacity: 'S',
};

// Suggestion prompts
const suggestions = [
  'Upload documents and I\'ll summarize what we have',
  'What income and deductions have been extracted so far?',
  'What documents are still missing for this client?',
  'Show me the tax computation breakdown',
  'Compare Old vs New tax regime for this client',
  'Check if FA Schedule is needed for foreign assets',
  'What capital gains did this client realize?',
  'Summarize the tax position and next steps',
];

export default function CaseWorkspaceV3() {
  const { id } = useParams();
  const navigate = useNavigate();

  // Case data state
  const [caseData, setCaseData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [facts, setFacts] = useState([]);
  const [latest, setLatest] = useState(null);
  const [missing, setMissing] = useState([]);
  const [reconciliation, setReconciliation] = useState([]);
  const [exportsList, setExportsList] = useState([]);
  const [audit, setAudit] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [identity, setIdentity] = useState(emptyExportIdentity);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  // Chat state
  const [messages, setMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const chatEndRef = useRef(null);
  const chatContainerRef = useRef(null);

  // Document upload state
  const [uploadQueue, setUploadQueue] = useState([]);
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const [passwordModal, setPasswordModal] = useState({ open: false, docId: null, filename: '' });
  const [password, setPassword] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  // UI state
  const [activeTab, setActiveTab] = useState('chat');
  const [copiedMessageId, setCopiedMessageId] = useState(null);
  const [showDocumentQueue, setShowDocumentQueue] = useState(false);
  const [documentFilter, setDocumentFilter] = useState('all');
  const [selectedDocDetail, setSelectedDocDetail] = useState(null);

  const computation = latest?.result || caseData?.latest_computation || null;

  // Load case data
  const load = useCallback(async () => {
    setError('');
    try {
      const [
        caseRes,
        docsRes,
        candsRes,
        factsRes,
        missRes,
        reconRes,
        exportsRes,
        auditRes,
      ] = await Promise.all([
        api.get(`/cases/${id}`),
        api.get(`/cases/${id}/documents`),
        api.get(`/cases/${id}/candidate-facts`),
        api.get(`/cases/${id}/facts`),
        api.get(`/cases/${id}/missing-items`),
        api.get(`/cases/${id}/reconciliation`),
        api.get(`/cases/${id}/exports`),
        api.get(`/cases/${id}/audit-events`),
      ]);
      setCaseData(caseRes.data);
      setDocuments(docsRes.data);
      setCandidates(candsRes.data);
      setFacts(factsRes.data);
      setMissing(missRes.data);
      setReconciliation(reconRes.data);
      setExportsList(exportsRes.data);
      setAudit(auditRes.data);
    } catch (err) {
      setError(errText(err, 'Failed to load case'));
    }
  }, [id]);

  // Load chat history
  const loadChatHistory = useCallback(async () => {
    try {
      const { data } = await api.get(`/cases/${id}/assistant/messages`);
      if (data && data.length > 0) {
        setMessages(
          data.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            documents: m.documents || [],
            facts_extracted: m.facts_extracted || [],
            timestamp: m.created_at,
          }))
        );
      }
    } catch (err) {
      console.error('[Chat] Failed to load history:', err);
    }
  }, [id]);

  useEffect(() => {
    load();
    loadChatHistory();
  }, [load, loadChatHistory]);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Action helper
  const act = (label, fn) => {
    setBusy(label);
    return fn().finally(() => setBusy(''));
  };

  // Review candidate fact
  const review = (candidate, decision) =>
    act(`candidate-${candidate.id}`, () =>
      api.post(`/candidate-facts/${candidate.id}/review`, {
        decision,
        justification: `${decision} after reviewing source evidence.`,
      })
    );

  // Compute taxes
  const compute = () =>
    act('compute', () =>
      api.post(`/cases/${id}/computations`, { selected_regime: caseData?.selected_regime || 'NEW' })
    );

  // Approve computation
  const approveComputation = () => {
    if (!latest?.id) return;
    return act('approve-computation', () =>
      api.post(`/computations/${latest.id}/review`, {
        decision: 'APPROVE',
        justification: 'Final computation reviewed by CA.',
      })
    );
  };

  // Show document evidence
  const showDocument = async (document) => {
    setSelectedDocument(document);
    const { data } = await api.get(`/documents/${document.id}/evidence`);
    setEvidence(data);
  };

  // Open document in new tab
  const openDocument = async () => {
    if (!selectedDocument) return;
    const { data } = await api.get(`/documents/${selectedDocument.id}/content`, {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(data);
    window.open(url, '_blank', 'noopener,noreferrer');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  // Resolve missing item
  const resolveMissing = (item) =>
    act(`missing-${item.id}`, () => api.post(`/missing-items/${item.id}/resolve`));

  // Resolve reconciliation
  const resolveReconciliation = (item) =>
    act(`reconcile-${item.id}`, () =>
      api.post(`/reconciliation/${item.id}/resolve`, {
        accepted_fact_id: item.accepted_fact_id,
        status: 'RESOLVED',
        resolution_note: 'Difference reviewed.',
      })
    );

  // Download computation JSON
  const downloadComputationJson = () => {
    if (!computation) return;
    const blob = new Blob([JSON.stringify(computation, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `computation-${caseData?.client_name || id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // ========== DOCUMENT UPLOAD HANDLERS ==========

  const handleFileSelect = async (files) => {
    if (!files || files.length === 0) return;

    const newFiles = Array.from(files).map((file) => ({
      id: `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      file,
      name: file.name,
      size: file.size,
      type: file.type,
      status: 'PENDING',
      progress: 0,
      summary: null,
      error: null,
      doc_id: null,
    }));

    setUploadQueue((prev) => [...prev, ...newFiles]);
    setShowUploadPanel(true);

    // Process files sequentially
    for (const uploadFile of newFiles) {
      await processFile(uploadFile);
    }

    // After the whole batch, ask the assistant for ONE consolidated summary.
    await requestConsolidatedSummary(newFiles);
  };

  const requestConsolidatedSummary = async (files) => {
    // Only ask for summary if at least one file was successfully processed
    const successfulFiles = (files || []).filter(f => f.status === 'COMPLETED');
    if (successfulFiles.length === 0) {
      addSystemMessage("No documents were processed successfully. Please try uploading again.");
      setShowUploadPanel(false);
      return;
    }

    const names = (files || []).map((f) => f.name).filter(Boolean).join(', ');
    setChatBusy(true);
    setMessages((prev) => [
      ...prev,
      { id: `sum-req-${Date.now()}`, role: 'user', content: `Uploaded: ${names || 'documents'}. Give me one consolidated summary.`, timestamp: new Date().toISOString() },
    ]);
    try {
      const { data } = await api.post(`/cases/${id}/assistant/chat`, {
        message:
          `I've uploaded these documents: ${names}. Process everything together and give me ONE consolidated summary of the client's situation. Flag any mismatches across sources and any verifications needed (including Schedule FA / foreign assets and USD conversion), and list what is still missing or worth asking the client.`,
      });
      setMessages((prev) => [
        ...prev,
        { id: data.id || `assistant-${Date.now()}`, role: 'assistant', content: typeof data.content === 'string' ? data.content : JSON.stringify(data.content), timestamp: new Date().toISOString() },
      ]);
      load();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: `sum-err-${Date.now()}`, role: 'assistant', content: `Couldn't generate the summary: ${errText(err, 'please try again.')}`, timestamp: new Date().toISOString() },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  const processFile = async (uploadItem) => {
    // Update status to uploading
    updateUploadItem(uploadItem.id, { status: 'UPLOADING', progress: 10 });

    try {
      // Create form data
      const formData = new FormData();
      formData.append('file', uploadItem.file);
      formData.append('case_id', id);

      // Update progress
      updateUploadItem(uploadItem.id, { progress: 30 });

      // Upload the file
      const { data: uploadResult } = await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const percent = Math.round((progressEvent.loaded * 50) / progressEvent.total);
          updateUploadItem(uploadItem.id, { progress: 10 + percent });
        },
      });

      // Check if password is required
      if (uploadResult.status === 'password_required') {
        updateUploadItem(uploadItem.id, {
          status: 'PASSWORD_REQUIRED',
          progress: 50,
          doc_id: uploadResult.document_id,
        });
        setPasswordModal({
          open: true,
          docId: uploadResult.document_id,
          filename: uploadItem.name,
        });
        return;
      }

      // Process the document
      updateUploadItem(uploadItem.id, { status: 'PROCESSING', progress: 60 });

      const { data: processResult } = await api.post(`/documents/${uploadResult.document_id}/process`);

      // Complete
      updateUploadItem(uploadItem.id, {
        status: 'COMPLETED',
        progress: 100,
        summary:
          processResult.summary ||
          `Extracted ${processResult.facts_count || 0} facts from ${uploadItem.name}`,
        doc_id: uploadResult.document_id,
      });

      // Per-document progress is shown in the upload queue, not the chat.
      // One consolidated summary is posted after the whole batch (see handleFiles).

      // Refresh documents list
      const { data: docsRes } = await api.get(`/cases/${id}/documents`);
      setDocuments(docsRes);

      // Trigger computation refresh
      load();
    } catch (err) {
      console.error('[Upload] Error:', err);
      const errorMsg = errText(err, 'Upload failed');
      updateUploadItem(uploadItem.id, {
        status: 'FAILED',
        progress: 0,
        error: errorMsg,
      });
      addSystemMessage(`Failed to process **${uploadItem.name}**: ${errorMsg}`);
    }
  };

  const handlePasswordSubmit = async () => {
    if (!passwordModal.docId || !password.trim()) return;

    const uploadItem = uploadQueue.find((u) => u.doc_id === passwordModal.docId);
    if (!uploadItem) return;

    try {
      // Submit password and process
      const { data: processResult } = await api.post(
        `/documents/${passwordModal.docId}/process`,
        {
          password: password,
        }
      );

      updateUploadItem(uploadItem.id, {
        status: 'COMPLETED',
        progress: 100,
        summary: processResult.summary || `Processed ${uploadItem.name} with password`,
      });

      addSystemMessage(`**${uploadItem.name}** processed successfully with provided password.`);

      // Refresh
      const { data: docsRes } = await api.get(`/cases/${id}/documents`);
      setDocuments(docsRes);
      load();
    } catch (err) {
      const errorMsg = errText(err, 'Invalid password or processing failed');
      updateUploadItem(uploadItem.id, {
        status: 'FAILED',
        error: errorMsg,
      });
      addSystemMessage(`**${uploadItem.name}**: ${errorMsg}`);
    } finally {
      setPasswordModal({ open: false, docId: null, filename: '' });
      setPassword('');
    }
  };

  const updateUploadItem = (itemId, updates) => {
    setUploadQueue((prev) =>
      prev.map((item) => (item.id === itemId ? { ...item, ...updates } : item))
    );
  };

  const removeUploadItem = (itemId) => {
    setUploadQueue((prev) => prev.filter((item) => item.id !== itemId));
  };

  const addSystemMessage = (content) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `system-${Date.now()}`,
        role: 'system',
        content,
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  // ========== CHAT HANDLER ==========

  const sendChat = async () => {
    const text = chatInput.trim();
    if (!text || chatBusy) return;
    setChatInput('');
    setChatBusy(true);

    // Add user message immediately
    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const { data } = await api.post(`/cases/${id}/assistant/chat`, { message: text });

      // Add assistant response
      const assistantContent = typeof data.content === 'string' ? data.content : JSON.stringify(data.content);
      setMessages((prev) => [
        ...prev,
        {
          id: data.id || `assistant-${Date.now()}`,
          role: 'assistant',
          content: assistantContent,
          documents: data.documents || [],
          facts_extracted: data.facts_extracted || [],
          computation_update: data.computation_update || null,
          timestamp: new Date().toISOString(),
        },
      ]);

      // Refresh case data if computation was updated
      if (data.computation_update) {
        load();
      }
    } catch (err) {
      console.error('[Chat] Error:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: `I encountered an issue processing your request. ${
            errText(err, 'Please try again.')
          }`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  // ========== DRAG & DROP ==========

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files);
    }
  };

  // Handle quick action
  const handleQuickAction = (actionText) => {
    setChatInput(actionText);
  };

  // Copy message to clipboard
  const handleCopyMessage = async (messageId, content) => {
    await navigator.clipboard.writeText(content);
    setCopiedMessageId(messageId);
    setTimeout(() => setCopiedMessageId(null), 2000);
  };

  // Format file size
  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Filter documents
  const filteredDocuments = documents.filter((doc) => {
    if (documentFilter === 'all') return true;
    return doc.document_type?.toLowerCase() === documentFilter.toLowerCase();
  });

  if (!caseData) {
    return (
      <div className="p-10 text-center">
        <div className="animate-pulse">Loading case...</div>
        {error && <div className="text-red-500 mt-2">{String(error)}</div>}
      </div>
    );
  }

  // ========== RENDER ==========

  return (
    <div className="h-screen bg-slate-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="h-4 w-4 mr-1" />
              Back
            </Button>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl flex items-center justify-center">
                <Briefcase className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gray-900">
                  {caseData.client_name}
                </h1>
                <p className="text-sm text-gray-500">
                  {caseData.tax_period} · {caseData.selected_regime} Regime ·{' '}
                  {caseData.assessment_year}
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                load();
                loadChatHistory();
              }}
            >
              <RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
            </Button>
            <span
              className={`text-xs px-2 py-1 rounded ${
                caseData.status === 'ACTIVE'
                  ? 'bg-green-100 text-green-700'
                  : 'bg-slate-100 text-slate-600'
              }`}
            >
              {caseData.status}
            </span>
            <span className="px-3 py-1 bg-green-100 text-green-700 text-sm font-medium rounded-full">
              {documents.length} Documents
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT - Chat Panel */}
        <section
          className={`flex-1 flex flex-col bg-white border-r ${
            isDragging ? 'ring-2 ring-green-400 ring-inset' : ''
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Chat Header */}
          <div className="border-b px-4 py-3 flex items-center justify-between bg-slate-50">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-blue-600" />
              <span className="font-medium">AI Tax Assistant</span>
              {chatBusy && (
                <span className="text-xs text-slate-400 animate-pulse">Thinking...</span>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowUploadPanel(!showUploadPanel)}
            >
              <Upload className="h-4 w-4 mr-1" />
              Documents ({documents.length})
            </Button>
          </div>

          {/* Upload Panel */}
          {showUploadPanel && (
            <div className="border-b bg-blue-50 p-3 max-h-56 overflow-y-auto">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-blue-800">Document Upload Queue</span>
                <span className="text-xs text-blue-600">{uploadQueue.length} file(s)</span>
              </div>
              {uploadQueue.length === 0 ? (
                <div className="text-sm text-blue-600 text-center py-6 border-2 border-dashed border-blue-200 rounded-lg">
                  <Upload className="h-8 w-8 mx-auto mb-2 text-blue-400" />
                  <p>Drop files here or click the upload button below</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {uploadQueue.map((item) => {
                    const StatusConfig = DOC_STATUS[item.status] || DOC_STATUS.PENDING;
                    const StatusIcon = StatusConfig.icon;
                    return (
                      <div
                        key={item.id}
                        className="flex items-center gap-3 bg-white rounded-lg p-3 text-sm shadow-sm"
                      >
                        <File className="h-5 w-5 text-slate-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-gray-900 truncate">{item.name}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs ${StatusConfig.color}`}>
                              {StatusConfig.label}
                            </span>
                            {item.status === 'UPLOADING' && (
                              <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden max-w-20">
                                <div
                                  className="h-full bg-blue-500 transition-all"
                                  style={{ width: `${item.progress}%` }}
                                />
                              </div>
                            )}
                            {item.summary && (
                              <span className="text-xs text-gray-500 truncate">
                                {item.summary}
                              </span>
                            )}
                            {item.error && (
                              <span className="text-xs text-red-500 truncate">{String(item.error)}</span>
                            )}
                          </div>
                        </div>
                        <StatusIcon
                          className={`w-4 h-4 ${StatusConfig.color} flex-shrink-0 ${
                            item.status === 'PROCESSING' || item.status === 'UPLOADING'
                              ? 'animate-spin'
                              : ''
                          }`}
                        />
                        {item.status !== 'PROCESSING' && item.status !== 'UPLOADING' && (
                          <button
                            onClick={() => removeUploadItem(item.id)}
                            className="p-1 hover:bg-gray-100 rounded transition-colors"
                          >
                            <Trash2 className="h-4 w-4 text-gray-400" />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Chat Messages */}
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center py-8">
                <Bot className="h-12 w-12 mx-auto text-slate-300 mb-4" />
                <p className="text-slate-500 mb-4">
                  Upload documents or ask me anything about this client's tax return.
                </p>
                <div className="space-y-2 text-left">
                  <p className="text-xs text-slate-400 uppercase tracking-wide mb-3">
                    Try asking:
                  </p>
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => setChatInput(s)}
                      className="block w-full text-left text-sm rounded-lg border bg-white px-3 py-2 hover:bg-blue-50 hover:border-blue-300 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <ChatMessage
                key={m.id}
                message={m}
                onCopy={handleCopyMessage}
                copiedId={copiedMessageId}
              />
            ))}
            {chatBusy && (
              <div className="flex items-center gap-2 text-slate-500">
                <Bot className="h-5 w-5" />
                <span className="animate-pulse">Analyzing...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Actions (shown when there are messages) */}
          {messages.length > 0 && (
            <div className="px-4 pb-2">
              <p className="text-xs text-gray-400 mb-2">Quick Actions</p>
              <div className="flex flex-wrap gap-2">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.id}
                    onClick={() => handleQuickAction(action.label)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-gray-200 hover:border-green-500 hover:bg-green-50 rounded-lg text-xs text-gray-600 transition-colors"
                  >
                    <action.icon className="w-3.5 h-3.5 text-green-600" />
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat Input */}
          <div className="border-t p-3 bg-white">
            <div className="flex items-end gap-2">
              <div className="flex-1 relative">
                <textarea
                  className="w-full resize-none rounded-xl border border-slate-200 px-4 py-3 pr-20 text-sm focus:outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent"
                  rows={chatInput.includes('\n') ? 3 : 1}
                  value={chatInput}
                  placeholder="Ask about this client's return, or drop files anywhere to upload..."
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                />
                <input
                  type="file"
                  ref={fileInputRef}
                  className="hidden"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png,.csv,.xlsx,.xls,.txt"
                  onChange={(e) => handleFileSelect(e.target.files)}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute right-12 bottom-3.5 text-slate-400 hover:text-blue-500 transition-colors"
                  title="Upload documents"
                >
                  <Upload className="h-5 w-5" />
                </button>
              </div>
              <Button
                onClick={sendChat}
                disabled={chatBusy || !chatInput.trim()}
                className="h-11 w-11 rounded-xl bg-green-500 hover:bg-green-600"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Press Enter to send · Shift+Enter for new line · I can read Form 16, AIS, 26AS, bank
              statements, and more
            </p>
          </div>
        </section>

        {/* RIGHT - Computation & Review */}
        <section className="w-[480px] flex flex-col overflow-hidden bg-slate-50">
          <Tabs defaultValue="computation" className="flex-1 flex flex-col">
            <TabsList className="w-full justify-start rounded-none border-b bg-white px-4">
              <TabsTrigger value="computation">Computation</TabsTrigger>
              <TabsTrigger value="documents">
                Documents ({documents.length})
              </TabsTrigger>
              <TabsTrigger value="facts">
                Facts ({facts.length + candidates.length})
              </TabsTrigger>
              <TabsTrigger value="review">Review</TabsTrigger>
            </TabsList>

            <TabsContent value="computation" className="flex-1 overflow-y-auto p-4">
              <ComputationPanel
                computation={computation}
                latest={latest}
                caseData={caseData}
                onCompute={compute}
                onApprove={approveComputation}
                busy={busy}
                onDownloadJson={downloadComputationJson}
              />
            </TabsContent>

            <TabsContent value="documents" className="flex-1 overflow-y-auto p-4">
              {/* Document Filters */}
              <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-2">
                {['all', 'FORM_16', 'AIS', '26AS', 'BANK_STATEMENT'].map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setDocumentFilter(filter)}
                    className={`px-3 py-1.5 text-xs rounded-lg whitespace-nowrap transition-colors ${
                      documentFilter === filter
                        ? 'bg-green-100 text-green-700 font-medium'
                        : 'bg-white text-gray-600 hover:bg-gray-100 border border-gray-200'
                    }`}
                  >
                    {filter === 'all' ? 'All' : DOCUMENT_TYPES[filter]?.label || filter}
                  </button>
                ))}
              </div>
              <DocumentsPanel
                documents={filteredDocuments}
                onShow={showDocument}
                selected={selectedDocument}
                onOpenDetail={(doc) => setSelectedDocDetail(doc)}
              />
            </TabsContent>

            <TabsContent value="facts" className="flex-1 overflow-y-auto p-4">
              <FactsPanel
                candidates={candidates}
                facts={facts}
                onReview={review}
                busy={busy}
              />
            </TabsContent>

            <TabsContent value="review" className="flex-1 overflow-y-auto p-4 space-y-4">
              <MissingItemsPanel missing={missing} onResolve={resolveMissing} />
              <ReconciliationPanel
                reconciliation={reconciliation}
                onResolve={resolveReconciliation}
              />
              <ExportPanel
                exports={exportsList}
                caseData={caseData}
                onExport={downloadComputationJson}
                identity={identity}
                setIdentity={setIdentity}
              />
            </TabsContent>
          </Tabs>
        </section>
      </div>

      {/* Password Modal */}
      {passwordModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-orange-100 rounded-xl flex items-center justify-center">
                <Lock className="h-6 w-6 text-orange-600" />
              </div>
              <div>
                <h3 className="font-semibold text-lg">Password Required</h3>
                <p className="text-sm text-gray-500 truncate max-w-64">{passwordModal.filename}</p>
              </div>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              This PDF is password-protected. Please enter the password to decrypt and process it.
            </p>
            <form onSubmit={(e) => { e.preventDefault(); handlePasswordSubmit(); }}>
              <Input
                type="password"
                placeholder="Enter document password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mb-4"
                autoFocus
              />
              <div className="flex gap-3">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setPasswordModal({ open: false, docId: null, filename: '' });
                    setPassword('');
                  }}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={!password.trim()} className="flex-1 bg-orange-500 hover:bg-orange-600">
                  Decrypt & Process
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Document Detail Modal */}
      {selectedDocDetail && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] overflow-hidden">
            <div className="p-6 border-b border-gray-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="h-6 w-6 text-gray-400" />
                  <div>
                    <h3 className="text-lg font-semibold">{selectedDocDetail.filename}</h3>
                    <p className="text-sm text-gray-500">
                      {selectedDocDetail.document_type} · {selectedDocDetail.state}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={openDocument}>
                    <ExternalLink className="h-4 w-4 mr-1" />
                    Open
                  </Button>
                  <button
                    onClick={() => setSelectedDocDetail(null)}
                    className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <X className="h-5 w-5 text-gray-500" />
                  </button>
                </div>
              </div>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {evidence.length > 0 ? (
                <div className="space-y-4">
                  <h4 className="font-medium text-gray-900 flex items-center gap-2">
                    <Eye className="w-4 h-4" />
                    Extracted Evidence
                  </h4>
                  <div className="space-y-3">
                    {evidence.map((item, index) => (
                      <div key={index} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-900">{item.field_code}</span>
                            {item.confidence && (
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ${
                                  item.confidence > 0.95
                                    ? 'bg-green-100 text-green-700'
                                    : item.confidence > 0.85
                                    ? 'bg-yellow-100 text-yellow-700'
                                    : 'bg-gray-100 text-gray-600'
                                }`}
                              >
                                {Math.round(item.confidence * 100)}%
                              </span>
                            )}
                          </div>
                          <p className="text-gray-700 mt-1">{String(item.value)}</p>
                          {item.source && (
                            <p className="text-xs text-gray-400 mt-1">Source: {item.source}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-gray-500 text-center py-8">
                  No evidence extracted from this document yet.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ========== SUB-COMPONENTS ==========

function ChatMessage({ message, onCopy, copiedId }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const content = typeof message.content === 'string' ? message.content : JSON.stringify(message.content);

  if (isSystem) {
    return (
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm">
        <div dangerouslySetInnerHTML={{ __html: formatMarkdown(content) }} />
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600'
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div className={`flex-1 max-w-[85%] ${isUser ? 'text-right' : ''}`}>
        <div
          className={`inline-block rounded-2xl px-4 py-3 text-sm ${
            isUser ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-800'
          } ${isUser ? 'rounded-tr-sm' : 'rounded-tl-sm'}`}
        >
          <div dangerouslySetInnerHTML={{ __html: formatMarkdown(content) }} />
        </div>
        {message.documents?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.documents.map((doc) => (
              <span key={doc.id} className="text-xs bg-slate-200 rounded px-2 py-1">
                {doc.filename}
              </span>
            ))}
          </div>
        )}
        {message.computation_update && (
          <div className="mt-2 text-xs text-green-600 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Computation updated based on this conversation
          </div>
        )}
        {message.timestamp && (
          <p className="text-xs text-gray-400 mt-1">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </p>
        )}
        {!isUser && (
          <button
            onClick={() => onCopy(message.id, content)}
            className="mt-1 p-1 hover:bg-gray-100 rounded transition-colors"
          >
            {copiedId === message.id ? (
              <Check className="h-3 w-3 text-green-500" />
            ) : (
              <Copy className="h-3 w-3 text-gray-400" />
            )}
          </button>
        )}
      </div>
    </div>
  );
}

function formatMarkdown(text) {
  if (!text) return '';
  if (typeof text !== 'string') text = JSON.stringify(text);
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br/>');
}

function ComputationPanel({
  computation,
  latest,
  caseData,
  onCompute,
  onApprove,
  busy,
  onDownloadJson,
}) {
  if (!computation) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <p className="text-slate-500 mb-4">No computation yet. Run the tax engine to calculate.</p>
          <Button onClick={onCompute} disabled={busy === 'compute'}>
            <Play className="h-4 w-4 mr-2" />
            Run Computation
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Tax Computation</h3>
          <p className="text-xs text-slate-500">
            {latest?.created_at ? new Date(latest.created_at).toLocaleString() : 'N/A'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onDownloadJson}>
            <Download className="h-4 w-4 mr-1" />
            JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onCompute}
            disabled={busy === 'compute'}
          >
            <RefreshCw
              className={`h-4 w-4 mr-1 ${busy === 'compute' ? 'animate-spin' : ''}`}
            />
            Recompute
          </Button>
          {latest?.status === 'COMPLETE' && latest?.review_decision !== 'APPROVED' && (
            <Button size="sm" onClick={onApprove} disabled={busy?.startsWith('approve')}>
              <ShieldCheck className="h-4 w-4 mr-1" />
              Approve
            </Button>
          )}
        </div>
      </div>

      {computation.selected_regime && (
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-semibold text-green-800">
                {computation.selected_regime === 'NEW' ? 'New' : 'Old'} Tax Regime
              </span>
              {computation.recommended_regime &&
                computation.recommended_regime !== computation.selected_regime && (
                  <p className="text-sm text-green-700 mt-1">
                    AI recommends:{' '}
                    <strong>
                      {computation.recommended_regime === 'NEW' ? 'New' : 'Old'} Regime
                    </strong>
                  </p>
                )}
            </div>
            {computation.total_tax_liability !== undefined && (
              <div className="text-right">
                <p className="text-xs text-green-600">Total Tax</p>
                <p className="text-lg font-bold text-green-700">
                  ₹{computation.total_tax_liability?.toLocaleString('en-IN')}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {computation.selected_result && (
        <Card>
          <CardContent className="p-4 space-y-3">
            <ComputationRow
              label="Gross Total Income"
              value={computation.selected_result.gross_total_income}
            />
            {computation.selected_result.deductions > 0 && (
              <ComputationRow
                label="Deductions"
                value={computation.selected_result.deductions}
                isDeduction
              />
            )}
            <ComputationRow
              label="Total Taxable Income"
              value={computation.selected_result.total_income}
              isHighlight
            />
            <div className="border-t border-gray-200 pt-2">
              <ComputationRow
                label="Tax Liability"
                value={computation.selected_result.total_tax_liability}
                isHighlight
              />
            </div>
            {computation.selected_result.tax_paid > 0 && (
              <ComputationRow
                label="Tax Paid (TDS/Advance)"
                value={computation.selected_result.tax_paid}
              />
            )}
            <ComputationRow
              label={
                computation.selected_result.payable > 0 ? 'Tax Payable' : 'Refund Due'
              }
              value={
                computation.selected_result.payable > 0
                  ? computation.selected_result.payable
                  : computation.selected_result.refund
              }
              isHighlight
              isRefund={computation.selected_result.refund > 0}
            />
          </CardContent>
        </Card>
      )}

      {/* Regime Comparison (if available) */}
      {computation.old_regime_result && computation.new_regime_result && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Regime Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-3 bg-white rounded-lg border">
                <p className="text-xs text-gray-500">Old Regime</p>
                <p className="text-lg font-bold text-red-600">
                  ₹{computation.old_regime_result.total_tax_liability?.toLocaleString('en-IN')}
                </p>
              </div>
              <div className="text-center p-3 bg-white rounded-lg border border-green-200">
                <p className="text-xs text-gray-500">New Regime</p>
                <p className="text-lg font-bold text-green-600">
                  ₹{computation.new_regime_result.total_tax_liability?.toLocaleString('en-IN')}
                </p>
              </div>
            </div>
            {computation.recommended_regime && (
              <p className="text-xs text-center text-green-700 mt-2">
                Recommended:{' '}
                <strong>
                  {computation.recommended_regime === 'NEW' ? 'New' : 'Old'} Regime
                </strong>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {computation.warnings?.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-orange-600">Warnings</h4>
          {computation.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-sm text-orange-700 bg-orange-50 border border-orange-200 rounded-lg p-3"
            >
              <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <span>{typeof w === 'string' ? w : JSON.stringify(w)}</span>
            </div>
          ))}
        </div>
      )}

      {computation.blockers?.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-red-600">Blockers</h4>
          {computation.blockers.map((b, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3"
            >
              <X className="h-4 w-4 mt-0.5 flex-shrink-0" />
              <span>{typeof b === 'string' ? b : JSON.stringify(b)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ComputationRow({ label, value, isHighlight, isRefund, isDeduction }) {
  const numValue = typeof value === 'number' ? value : parseFloat(value) || 0;

  return (
    <div className={`flex justify-between ${isHighlight ? 'font-semibold' : ''}`}>
      <span className={isDeduction ? 'text-green-600' : 'text-slate-600'}>{label}</span>
      <span
        className={
          isRefund
            ? 'text-green-600'
            : isDeduction
            ? 'text-green-600'
            : isHighlight
            ? 'text-slate-900'
            : 'text-slate-800'
        }
      >
        {isDeduction && numValue > 0 ? '-' : ''}₹{numValue.toLocaleString('en-IN')}
      </span>
    </div>
  );
}

function DocumentsPanel({ documents, onShow, selected, onOpenDetail }) {
  if (documents.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <FileText className="h-12 w-12 mx-auto text-slate-300 mb-3" />
        <p className="font-medium">No documents uploaded yet</p>
        <p className="text-sm mt-1">Upload documents using the chat panel to begin.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
            selected?.id === doc.id
              ? 'border-blue-400 bg-blue-50'
              : 'bg-white hover:bg-slate-50 hover:border-gray-300'
          }`}
          onClick={() => {
            onShow(doc);
            onOpenDetail(doc);
          }}
        >
          <FileText className="h-5 w-5 text-slate-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{doc.filename}</p>
            <p className="text-xs text-slate-500">
              {doc.document_type} · {formatDocSize(doc.file_size)}
            </p>
          </div>
          <span
            className={`text-xs px-2 py-0.5 rounded ${
              doc.state === 'PROCESSED'
                ? 'bg-green-100 text-green-700'
                : doc.state === 'PENDING'
                ? 'bg-yellow-100 text-yellow-700'
                : doc.state === 'FAILED'
                ? 'bg-red-100 text-red-700'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            {doc.state}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatDocSize(size) {
  if (!size) return '';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function FactsPanel({ candidates, facts, onReview, busy }) {
  return (
    <div className="space-y-4">
      {candidates.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h4 className="text-sm font-medium">Pending Review</h4>
            <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
              {candidates.length}
            </span>
          </div>
          <div className="space-y-2">
            {candidates.map((c) => (
              <div key={c.id} className="p-3 border rounded-xl bg-white shadow-sm">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-slate-800">{c.field_code}</p>
                    <p className="text-xs text-slate-500 mt-1">
                      Value: {typeof c.value === 'object' ? JSON.stringify(c.value) : c.value}
                    </p>
                    {c.confidence && (
                      <p className="text-xs text-gray-400 mt-1">
                        Confidence: {Math.round(c.confidence * 100)}%
                      </p>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-green-200 text-green-600 hover:bg-green-50"
                      onClick={() => onReview(c, 'ACCEPT')}
                      disabled={busy === `candidate-${c.id}`}
                    >
                      <CheckCircle2 className="h-3 w-3 mr-1" />
                      Accept
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-red-200 text-red-600 hover:bg-red-50"
                      onClick={() => onReview(c, 'REJECT')}
                      disabled={busy === `candidate-${c.id}`}
                    >
                      <X className="h-3 w-3 mr-1" />
                      Reject
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {facts.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <h4 className="text-sm font-medium text-slate-600">Accepted Facts</h4>
            <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">
              {facts.length}
            </span>
          </div>
          <div className="space-y-1 bg-white rounded-xl border divide-y divide-slate-100">
            {facts.map((f) => (
              <div key={f.id} className="p-2.5 text-sm">
                <span className="font-mono text-xs text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                  {f.field_code}
                </span>
                <span className="ml-2 text-slate-700">
                  {typeof f.value === 'object' ? JSON.stringify(f.value) : f.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {candidates.length === 0 && facts.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          <Wrench className="h-12 w-12 mx-auto text-slate-300 mb-3" />
          <p className="font-medium">No facts extracted yet</p>
          <p className="text-sm mt-1">Upload documents to begin extracting facts.</p>
        </div>
      )}
    </div>
  );
}

function MissingItemsPanel({ missing, onResolve }) {
  if (missing.length === 0) {
    return (
      <div className="text-center py-6 text-slate-500 text-sm bg-green-50 rounded-xl border border-green-200">
        <CheckCircle2 className="h-8 w-8 mx-auto text-green-500 mb-2" />
        <p>No missing items</p>
        <p className="text-xs text-green-600 mt-1">All required information is available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-medium">Missing Information</h4>
        <span className="px-2 py-0.5 bg-amber-100 text-amber-700 text-xs rounded-full">
          {missing.length}
        </span>
      </div>
      {missing.map((item) => (
        <div
          key={item.id}
          className="flex items-center justify-between p-3 border rounded-xl bg-white"
        >
          <div>
            <p className="text-sm font-medium">{item.field_code || item.description}</p>
            <p className="text-xs text-slate-500">
              {item.importance || 'Required'}
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={() => onResolve(item)}>
            Mark Resolved
          </Button>
        </div>
      ))}
    </div>
  );
}

function ReconciliationPanel({ reconciliation, onResolve }) {
  if (reconciliation.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">Reconciliation Needed</h4>
      {reconciliation.map((item) => (
        <div key={item.id} className="p-3 border rounded-xl bg-white">
          <p className="text-sm font-medium">{item.field_code}</p>
          <div className="flex items-center gap-2 mt-2 text-xs">
            <span className="px-2 py-1 bg-slate-100 rounded">Candidate: {item.candidate_value}</span>
            <ChevronRight className="h-3 w-3 text-slate-400" />
            <span className="px-2 py-1 bg-green-100 rounded text-green-700">
              Accepted: {item.accepted_value}
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="mt-2"
            onClick={() => onResolve(item)}
          >
            Accept Difference
          </Button>
        </div>
      ))}
    </div>
  );
}

function ExportPanel({ exports: exportsList, caseData, onExport, identity, setIdentity }) {
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium mb-2">ITR Export</h4>
        {caseData?.latest_computation?.form_eligibility?.recommended_form ? (
          <p className="text-sm text-slate-600 mb-2">
            Recommended form:{' '}
            <strong>
              {caseData.latest_computation.form_eligibility.recommended_form}
            </strong>
          </p>
        ) : null}
        <Button variant="outline" size="sm" onClick={onExport}>
          <Download className="h-4 w-4 mr-1" />
          Download Computation JSON
        </Button>
      </div>

      <div className="border-t pt-4">
        <h4 className="text-sm font-medium mb-2">Export Identity</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <Input
            placeholder="PAN"
            value={identity.pan}
            onChange={(e) => setIdentity({ ...identity, pan: e.target.value })}
          />
          <Input
            placeholder="First Name"
            value={identity.first_name}
            onChange={(e) => setIdentity({ ...identity, first_name: e.target.value })}
          />
          <Input
            placeholder="Middle Name"
            value={identity.middle_name}
            onChange={(e) => setIdentity({ ...identity, middle_name: e.target.value })}
          />
          <Input
            placeholder="Surname"
            value={identity.surname}
            onChange={(e) => setIdentity({ ...identity, surname: e.target.value })}
          />
          <Input
            placeholder="Date of Birth"
            type="date"
            value={identity.date_of_birth}
            onChange={(e) => setIdentity({ ...identity, date_of_birth: e.target.value })}
            className="col-span-2"
          />
        </div>
      </div>
    </div>
  );
}
