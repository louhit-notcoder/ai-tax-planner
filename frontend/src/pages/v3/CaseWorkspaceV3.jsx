import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Send, FileText, Bot, User, X, CheckCircle2, AlertCircle, Loader2, Download, RefreshCw, Paperclip, Calculator, File, Lock, Sparkles, ExternalLink } from 'lucide-react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// Reduce API errors to human-readable strings
const errText = (err, fallback = 'Something went wrong') => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') return detail.message || detail.detail || JSON.stringify(detail);
  return err?.message || fallback;
};

// Format file size for display
const formatFileSize = (bytes) => {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// Format currency in INR
const formatINR = (amount) => {
  if (amount === undefined || amount === null) return '-';
  const num = typeof amount === 'number' ? amount : parseFloat(amount) || 0;
  return `₹${num.toLocaleString('en-IN')}`;
};

// Simple markdown-like formatter for messages
const formatText = (text) => {
  if (!text) return '';
  if (typeof text !== 'string') text = JSON.stringify(text);
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code class="bg-slate-100 px-1 rounded text-sm">$1</code>')
    .replace(/\n/g, '<br/>');
};

export default function CaseWorkspaceV3() {
  const { id } = useParams();
  const navigate = useNavigate();

  // Core state
  const [caseData, setCaseData] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [facts, setFacts] = useState([]);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');

  // Chat state
  const [chatInput, setChatInput] = useState('');
  const [chatBusy, setChatBusy] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState([]);
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // UI state
  const [rightPanelTab, setRightPanelTab] = useState('computation');
  const [isDragging, setIsDragging] = useState(false);
  const [processingStatus, setProcessingStatus] = useState(null);
  const [passwordModal, setPasswordModal] = useState({ open: false, docId: null, filename: '', password: '' });

  // Load all case data
  const load = useCallback(async () => {
    setError('');
    try {
      const [caseRes, docsRes, factsRes] = await Promise.all([
        api.get(`/cases/${id}`),
        api.get(`/cases/${id}/documents`),
        api.get(`/cases/${id}/facts`),
      ]);
      setCaseData(caseRes.data);
      setDocuments(docsRes.data);
      setFacts(factsRes.data);
    } catch (err) {
      setError(errText(err, 'Failed to load case'));
    }
  }, [id]);

  // Load chat history
  const loadChatHistory = useCallback(async () => {
    try {
      const { data } = await api.get(`/cases/${id}/assistant/messages`);
      if (data && data.length > 0) {
        setMessages(data.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          documents: m.documents || [],
          timestamp: m.created_at,
        })));
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

  // ========== FILE HANDLING ==========

  const handleFileSelect = (files) => {
    if (!files || files.length === 0) return;
    const newFiles = Array.from(files).map((file) => ({
      id: `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: file.name,
      size: file.size,
      type: file.type,
      file,
    }));
    setAttachedFiles((prev) => [...prev, ...newFiles]);
  };

  const removeAttachedFile = (fileId) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files);
    }
  };

  // ========== UPLOAD & PROCESS FILES ==========

  const uploadAndProcessFiles = async (files) => {
    const results = [];

    for (const uploadFile of files) {
      try {
        setProcessingStatus({
          type: 'uploading',
          message: `Uploading ${uploadFile.name}...`,
          fileName: uploadFile.name,
        });

        const formData = new FormData();
        formData.append('file', uploadFile.file);
        formData.append('case_id', id);

        const { data: uploadResult } = await api.post('/documents/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });

        // Check if password is required
        if (uploadResult.status === 'password_required') {
          setPasswordModal({
            open: true,
            docId: uploadResult.document_id,
            filename: uploadFile.name,
            password: '',
          });
          return { success: false, passwordRequired: true, docId: uploadResult.document_id };
        }

        setProcessingStatus({
          type: 'processing',
          message: `Processing ${uploadFile.name}...`,
          fileName: uploadFile.name,
        });

        await api.post(`/documents/${uploadResult.document_id}/process`);

        results.push({
          id: uploadResult.document_id,
          name: uploadFile.name,
          success: true,
        });

      } catch (err) {
        console.error('[Upload] Error:', err);
        results.push({
          id: null,
          name: uploadFile.name,
          success: false,
          error: errText(err),
        });
      }
    }

    return { success: true, results };
  };

  const handlePasswordSubmit = async () => {
    if (!passwordModal.docId || !passwordModal.password.trim()) return;

    try {
      setProcessingStatus({
        type: 'processing',
        message: `Processing ${passwordModal.filename}...`,
        fileName: passwordModal.filename,
      });

      await api.post(`/documents/${passwordModal.docId}/process`, {
        password: passwordModal.password,
      });

      // Refresh data
      await load();

      setPasswordModal({ open: false, docId: null, filename: '', password: '' });
      setProcessingStatus(null);

      addSystemMessage(`${passwordModal.filename} processed successfully.`);
    } catch (err) {
      addSystemMessage(`Failed to process ${passwordModal.filename}: ${errText(err)}`);
      setPasswordModal({ open: false, docId: null, filename: '', password: '' });
      setProcessingStatus(null);
    }
  };

  // ========== CHAT HANDLER ==========

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

  const sendChat = async () => {
    const text = chatInput.trim();
    const filesToUpload = [...attachedFiles];

    // If no text and no files, do nothing
    if (!text && filesToUpload.length === 0) return;
    if (chatBusy) return;

    setChatBusy(true);
    setChatInput('');
    setAttachedFiles([]);

    // Add user message
    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text || (filesToUpload.length > 0 ? 'Uploaded files' : ''),
      files: filesToUpload.map((f) => f.name),
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      // If there are files attached, upload them first
      if (filesToUpload.length > 0) {
        const uploadResult = await uploadAndProcessFiles(filesToUpload);

        if (uploadResult.passwordRequired) {
          setChatBusy(false);
          return;
        }

        if (uploadResult.success) {
          const successfulFiles = uploadResult.results.filter((r) => r.success);
          const failedFiles = uploadResult.results.filter((r) => !r.success);

          if (successfulFiles.length > 0) {
            addSystemMessage(`Processed ${successfulFiles.length} file(s): ${successfulFiles.map((f) => f.name).join(', ')}`);
          }
          if (failedFiles.length > 0) {
            addSystemMessage(`Failed to process: ${failedFiles.map((f) => f.name).join(', ')}`);
          }

          // Refresh data after uploads
          await load();
        }

        setProcessingStatus(null);
      }

      // Now send the chat message
      if (text) {
        const { data } = await api.post(`/cases/${id}/assistant/chat`, { message: text });

        const assistantMsg = {
          id: data.id || `assistant-${Date.now()}`,
          role: 'assistant',
          content: typeof data.content === 'string' ? data.content : JSON.stringify(data.content),
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);

        // Refresh data if needed
        await load();
      }
    } catch (err) {
      console.error('[Chat] Error:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'system',
          content: `Error: ${errText(err)}`,
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setChatBusy(false);
      setProcessingStatus(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  };

  // Initial suggestions
  const suggestions = [
    'Summarize the documents I have',
    'What income has been extracted?',
    'What documents are still missing?',
    'Show me the tax computation',
    'Compare old vs new tax regime',
    'Check for foreign assets',
    'What are the next steps?',
  ];

  if (!caseData && error) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-600 mb-4">{error}</p>
          <Button onClick={() => load()}>Try Again</Button>
        </div>
      </div>
    );
  }

  if (!caseData) {
    return (
      <div className="h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400 mx-auto mb-4" />
          <p className="text-slate-500">Loading case...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      {/* ========== HEADER ========== */}
      <header className="bg-white border-b px-6 py-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/dashboard')} className="text-slate-600">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-green-500 to-emerald-600 rounded-xl flex items-center justify-center">
              <FileText className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-900">{caseData.client_name}</h1>
              <p className="text-xs text-slate-500">
                {caseData.tax_period} · {caseData.selected_regime} Regime
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { load(); loadChatHistory(); }}
            className="text-slate-500"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
          <span className="px-2.5 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-full">
            {documents.length} docs
          </span>
        </div>
      </header>

      {/* ========== MAIN CONTENT ========== */}
      <div className="flex-1 flex overflow-hidden">
        {/* ========== LEFT - CHAT PANEL ========== */}
        <section
          className={`flex-1 flex flex-col bg-white border-r ${isDragging ? 'ring-2 ring-green-400 ring-inset bg-green-50' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Chat Header */}
          <div className="border-b px-4 py-3 flex items-center gap-2 bg-slate-50 flex-shrink-0">
            <Bot className="h-5 w-5 text-blue-600" />
            <span className="font-medium text-sm">Tax Assistant</span>
            {chatBusy && (
              <span className="text-xs text-slate-400 animate-pulse ml-2">Thinking...</span>
            )}
          </div>

          {/* Chat Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="text-center py-10">
                <Bot className="h-12 w-12 mx-auto text-slate-300 mb-4" />
                <p className="text-slate-500 mb-6 text-sm">
                  Ask me about this client's tax return or upload documents.
                </p>
                <div className="grid grid-cols-2 gap-2 max-w-lg mx-auto">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => setChatInput(s)}
                      className="text-left text-xs p-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 hover:border-green-400 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}

            {/* Processing Status */}
            {processingStatus && (
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm flex items-center gap-3">
                <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                <span className="text-blue-700">{processingStatus.message}</span>
              </div>
            )}

            {/* Thinking Indicator */}
            {chatBusy && !processingStatus && (
              <div className="flex items-center gap-2 text-slate-500 text-sm">
                <Bot className="h-4 w-4" />
                <span className="animate-pulse">Thinking...</span>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* ========== INPUT AREA ========== */}
          <div className="border-t p-4 bg-white flex-shrink-0">
            {/* Attached Files Pills */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {attachedFiles.map((f) => (
                  <div
                    key={f.id}
                    className="flex items-center gap-2 px-3 py-1.5 bg-slate-100 rounded-full text-xs"
                  >
                    <Paperclip className="h-3 w-3 text-slate-500" />
                    <span className="text-slate-700 max-w-32 truncate">{f.name}</span>
                    <span className="text-slate-400">{formatFileSize(f.size)}</span>
                    <button
                      onClick={() => removeAttachedFile(f.id)}
                      className="ml-1 hover:bg-slate-200 rounded-full p-0.5 transition-colors"
                    >
                      <X className="h-3 w-3 text-slate-500" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Input Row */}
            <div className="flex items-end gap-3">
              {/* Paperclip Button */}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex-shrink-0 p-2.5 rounded-lg hover:bg-slate-100 transition-colors text-slate-500"
                title="Attach files"
              >
                <Paperclip className="h-5 w-5" />
              </button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.csv,.xlsx,.xls,.txt"
                onChange={(e) => handleFileSelect(e.target.files)}
              />

              {/* Textarea */}
              <div className="flex-1 relative">
                <textarea
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask about this client's tax return..."
                  className="w-full resize-none rounded-xl border border-slate-200 px-4 py-3 pr-12 text-sm focus:outline-none focus:ring-2 focus:ring-green-400 focus:border-transparent"
                  rows={chatInput.includes('\n') ? 3 : 1}
                />
                <Button
                  onClick={sendChat}
                  disabled={chatBusy || (!chatInput.trim() && attachedFiles.length === 0)}
                  className="absolute right-2 bottom-2 h-8 w-8 p-0 rounded-lg bg-green-500 hover:bg-green-600"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <p className="text-[11px] text-slate-400 mt-2 ml-11">
              Press Enter to send · I can analyze Form 16, AIS, 26AS, bank statements
            </p>
          </div>
        </section>

        {/* ========== RIGHT - PANEL ========== */}
        <section className="w-[480px] flex flex-col overflow-hidden bg-slate-50 flex-shrink-0">
          <Tabs value={rightPanelTab} onValueChange={setRightPanelTab} className="flex-1 flex flex-col">
            <TabsList className="w-full justify-start rounded-none border-b bg-white px-4 flex-shrink-0">
              <TabsTrigger value="computation">Computation</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="facts">Facts</TabsTrigger>
            </TabsList>

            {/* ========== COMPUTATION TAB ========== */}
            <TabsContent value="computation" className="flex-1 overflow-y-auto p-4">
              <ComputationTab caseData={caseData} documents={documents} />
            </TabsContent>

            {/* ========== DOCUMENTS TAB ========== */}
            <TabsContent value="documents" className="flex-1 overflow-y-auto p-4">
              <DocumentsTab documents={documents} caseId={id} />
            </TabsContent>

            {/* ========== FACTS TAB ========== */}
            <TabsContent value="facts" className="flex-1 overflow-y-auto p-4">
              <FactsTab facts={facts} />
            </TabsContent>
          </Tabs>
        </section>
      </div>

      {/* ========== PASSWORD MODAL ========== */}
      {passwordModal.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
                <Lock className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <h3 className="font-semibold">Password Required</h3>
                <p className="text-sm text-slate-500 truncate max-w-48">{passwordModal.filename}</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 mb-4">
              This PDF is password-protected. Enter the password to decrypt and process it.
            </p>
            <input
              type="password"
              placeholder="Enter password"
              value={passwordModal.password}
              onChange={(e) => setPasswordModal({ ...passwordModal, password: e.target.value })}
              className="w-full px-4 py-2.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-green-400 mb-4"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handlePasswordSubmit()}
            />
            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={() => setPasswordModal({ open: false, docId: null, filename: '', password: '' })}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                onClick={handlePasswordSubmit}
                disabled={!passwordModal.password.trim()}
                className="flex-1 bg-orange-500 hover:bg-orange-600"
              >
                Process
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ========== MESSAGE BUBBLE ==========

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const content = typeof message.content === 'string' ? message.content : JSON.stringify(message.content);

  if (isSystem) {
    return (
      <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm">
        <div dangerouslySetInnerHTML={{ __html: formatText(content) }} />
        {message.files && message.files.length > 0 && (
          <p className="text-xs text-amber-600 mt-2">
            Files: {message.files.join(', ')}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${
          isUser ? 'bg-blue-500 text-white' : 'bg-slate-100 text-slate-600'
        }`}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Message Content */}
      <div className={`flex-1 max-w-[85%] ${isUser ? 'text-right' : ''}`}>
        <div
          className={`inline-block rounded-2xl px-4 py-3 text-sm text-left ${
            isUser
              ? 'bg-blue-500 text-white rounded-tr-sm'
              : 'bg-slate-100 text-slate-800 rounded-tl-sm'
          }`}
        >
          <div dangerouslySetInnerHTML={{ __html: formatText(content) }} />
        </div>

        {/* Files indicator */}
        {message.files && message.files.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1 justify-start">
            {message.files.map((filename, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 text-xs bg-slate-100 rounded px-2 py-1 text-slate-600"
              >
                <Paperclip className="h-3 w-3" />
                {filename}
              </span>
            ))}
          </div>
        )}

        {/* Timestamp */}
        {message.timestamp && (
          <p className="text-[11px] text-slate-400 mt-1">
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </p>
        )}
      </div>
    </div>
  );
}

// ========== COMPUTATION TAB ==========

function ComputationTab({ caseData, documents }) {
  const [busy, setBusy] = useState(false);
  const [computation, setComputation] = useState(null);
  const [latest, setLatest] = useState(null);

  const runComputation = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/cases/${caseData.id}/computations`, {
        selected_regime: caseData.selected_regime || 'NEW',
      });
      setLatest(data);
      setComputation(data.result);
    } catch (err) {
      console.error('[Computation] Error:', err);
    } finally {
      setBusy(false);
    }
  };

  const downloadJson = () => {
    if (!computation) return;
    const blob = new Blob([JSON.stringify(computation, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `computation-${caseData.client_name || caseData.id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Use existing computation if available
  const activeComputation = computation || caseData?.latest_computation?.result;
  const activeLatest = latest || caseData?.latest_computation;

  if (!activeComputation) {
    return (
      <div className="text-center py-12">
        <Calculator className="h-12 w-12 mx-auto text-slate-300 mb-4" />
        <p className="text-slate-500 mb-4 text-sm">No computation yet.</p>
        <Button onClick={runComputation} disabled={busy} size="sm">
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Computing...
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4 mr-2" />
              Run Computation
            </>
          )}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Tax Computation</h3>
          {activeLatest?.created_at && (
            <p className="text-xs text-slate-500">
              {new Date(activeLatest.created_at).toLocaleDateString()}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={downloadJson}>
            <Download className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={runComputation} disabled={busy}>
            <RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Regime Banner */}
      <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="font-semibold text-green-800">
              {activeComputation.selected_regime === 'NEW' ? 'New' : 'Old'} Tax Regime
            </span>
            {activeComputation.recommended_regime &&
              activeComputation.recommended_regime !== activeComputation.selected_regime && (
                <p className="text-xs text-green-700 mt-1">
                  Recommended: <strong>{activeComputation.recommended_regime === 'NEW' ? 'New' : 'Old'} Regime</strong>
                </p>
              )}
          </div>
          {activeComputation.total_tax_liability !== undefined && (
            <div className="text-right">
              <p className="text-xs text-green-600">Total Tax</p>
              <p className="text-xl font-bold text-green-700">
                {formatINR(activeComputation.total_tax_liability)}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Computation Details */}
      {activeComputation.selected_result && (
        <div className="bg-white rounded-xl border divide-y divide-slate-100">
          <ComputationLine
            label="Gross Total Income"
            value={activeComputation.selected_result.gross_total_income}
          />
          {activeComputation.selected_result.deductions > 0 && (
            <ComputationLine
              label="Deductions"
              value={activeComputation.selected_result.deductions}
              green
            />
          )}
          <ComputationLine
            label="Total Taxable Income"
            value={activeComputation.selected_result.total_income}
            bold
          />
          <div className="px-4 py-3">
            <div className="flex justify-between font-semibold">
              <span className="text-slate-700">Tax Liability</span>
              <span className="text-slate-900">{formatINR(activeComputation.selected_result.total_tax_liability)}</span>
            </div>
          </div>
          {activeComputation.selected_result.tax_paid > 0 && (
            <ComputationLine
              label="Tax Paid (TDS/Advance)"
              value={activeComputation.selected_result.tax_paid}
            />
          )}
          <ComputationLine
            label={activeComputation.selected_result.payable > 0 ? 'Tax Payable' : 'Refund Due'}
            value={
              activeComputation.selected_result.payable > 0
                ? activeComputation.selected_result.payable
                : activeComputation.selected_result.refund
            }
            bold
            green={activeComputation.selected_result.refund > 0}
          />
        </div>
      )}

      {/* Regime Comparison */}
      {activeComputation.old_regime_result && activeComputation.new_regime_result && (
        <div className="bg-white rounded-xl border p-4">
          <h4 className="text-xs font-medium text-slate-500 mb-3">Regime Comparison</h4>
          <div className="grid grid-cols-2 gap-3">
            <div className="text-center p-3 bg-slate-50 rounded-lg">
              <p className="text-xs text-slate-500">Old Regime</p>
              <p className="text-lg font-bold text-red-600">
                {formatINR(activeComputation.old_regime_result.total_tax_liability)}
              </p>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
              <p className="text-xs text-slate-500">New Regime</p>
              <p className="text-lg font-bold text-green-600">
                {formatINR(activeComputation.new_regime_result.total_tax_liability)}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Warnings */}
      {activeComputation.warnings?.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-medium text-orange-600">Warnings</h4>
          {activeComputation.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-orange-700 bg-orange-50 border border-orange-200 rounded-lg p-3">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
              <span>{typeof w === 'string' ? w : JSON.stringify(w)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ComputationLine({ label, value, bold, green, red }) {
  const numValue = typeof value === 'number' ? value : parseFloat(value) || 0;

  return (
    <div className="px-4 py-3 flex justify-between">
      <span className={`text-sm ${bold ? 'font-semibold text-slate-700' : 'text-slate-600'}`}>
        {label}
      </span>
      <span className={`text-sm ${bold ? 'font-semibold' : ''} ${
        green ? 'text-green-600' : red ? 'text-red-600' : 'text-slate-900'
      }`}>
        {green && numValue > 0 ? '-' : ''}{formatINR(numValue)}
      </span>
    </div>
  );
}

// ========== DOCUMENTS TAB ==========

function DocumentsTab({ documents, caseId }) {
  const [selectedDoc, setSelectedDoc] = useState(null);

  const openDocument = async (doc) => {
    setSelectedDoc(doc);
    try {
      const { data } = await api.get(`/documents/${doc.id}/content`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(data);
      window.open(url, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      console.error('[Document] Error opening:', err);
    }
  };

  if (documents.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText className="h-12 w-12 mx-auto text-slate-300 mb-4" />
        <p className="text-slate-500 text-sm">No documents uploaded yet.</p>
        <p className="text-xs text-slate-400 mt-1">Upload documents in the chat panel.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => (
        <div
          key={doc.id}
          onClick={() => openDocument(doc)}
          className="flex items-center gap-3 p-3 rounded-xl border bg-white hover:bg-slate-50 cursor-pointer transition-colors"
        >
          <FileText className="h-5 w-5 text-slate-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{doc.filename}</p>
            <p className="text-xs text-slate-500">
              {doc.document_type || 'Document'} · {formatFileSize(doc.file_size)}
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
            {doc.state === 'PROCESSED' ? 'Done' : doc.state || 'Ready'}
          </span>
          <ExternalLink className="h-4 w-4 text-slate-400" />
        </div>
      ))}
    </div>
  );
}

// ========== FACTS TAB ==========

function FactsTab({ facts }) {
  if (!facts || facts.length === 0) {
    return (
      <div className="text-center py-12">
        <File className="h-12 w-12 mx-auto text-slate-300 mb-4" />
        <p className="text-slate-500 text-sm">No facts extracted yet.</p>
        <p className="text-xs text-slate-400 mt-1">Upload documents to extract facts.</p>
      </div>
    );
  }

  // Group facts by category
  const groupedFacts = facts.reduce((acc, fact) => {
    const category = fact.category || 'General';
    if (!acc[category]) acc[category] = [];
    acc[category].push(fact);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {Object.entries(groupedFacts).map(([category, categoryFacts]) => (
        <div key={category}>
          <h4 className="text-xs font-medium text-slate-500 mb-2 uppercase tracking-wide">
            {category}
          </h4>
          <div className="space-y-1">
            {categoryFacts.map((fact, i) => (
              <div key={fact.id || i} className="p-3 bg-white rounded-lg border text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="font-mono text-xs text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                      {fact.field_code}
                    </span>
                    <p className="text-slate-700 mt-1">
                      {typeof fact.value === 'object' ? JSON.stringify(fact.value) : fact.value}
                    </p>
                  </div>
                  {fact.confidence && (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${
                        fact.confidence > 0.95
                          ? 'bg-green-100 text-green-700'
                          : fact.confidence > 0.85
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {Math.round(fact.confidence * 100)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
