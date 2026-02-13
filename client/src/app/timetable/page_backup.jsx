"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:5000";

export default function TimetablePage() {
  const { data: session } = useSession();
  const [activeTab, setActiveTab] = useState("universal");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  
  // Document upload states
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [calendarFile, setCalendarFile] = useState(null);
  const [examFile, setExamFile] = useState(null);
  const [uploadResults, setUploadResults] = useState(null);
  
  // Universal extraction states
  const [universalFile, setUniversalFile] = useState(null);
  const [universalResults, setUniversalResults] = useState(null);
  const [extracting, setExtracting] = useState(false);
  
  // Document status
  const [docStatus, setDocStatus] = useState(null);
  
  // Constraints state
  const [constraints, setConstraints] = useState(null);
  
  // Generated timetable
  const [timetable, setTimetable] = useState(null);
  
  // Preferences
  const [preferences, setPreferences] = useState({
    study_start_hour: 8,
    study_end_hour: 20,
    max_daily_hours: 6,
    days_ahead: 14
  });

  // Manual subjects for testing without PDF
  const [manualSubjects, setManualSubjects] = useState([
    { name: "Data Structures", difficulty: "hard", weekly_target_hours: 8, priority: 9 },
    { name: "Database Systems", difficulty: "medium", weekly_target_hours: 5, priority: 7 },
    { name: "Operating Systems", difficulty: "hard", weekly_target_hours: 6, priority: 8 }
  ]);
  
  const [manualExams, setManualExams] = useState([
    { subject: "Data Structures", date: "2026-02-01" },
    { subject: "Database Systems", date: "2026-02-05" }
  ]);

  const userEmail = session?.user?.email || "demo@trackeneer.local";

  // Fetch document status on load
  useEffect(() => {
    fetchDocumentStatus();
  }, []);

  const fetchDocumentStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents/status?email=${userEmail}`);
      if (res.ok) {
        const data = await res.json();
        setDocStatus(data);
      }
    } catch (err) {
      console.log("Backend not available yet - this is normal if server isn't running");
      setDocStatus(null);
    }
  };

  const showMessage = (text, type = "info") => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 5000);
  };

  // Upload single document
  const uploadDocument = async (file, type) => {
    if (!file) {
      showMessage(`Please select a ${type} file`, "error");
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("email", userEmail);

    try {
      const endpoint = type === "syllabus" 
        ? "/api/documents/upload/syllabus"
        : type === "calendar"
        ? "/api/documents/upload/calendar"
        : "/api/documents/upload/exam-timetable";

      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      
      if (res.ok) {
        showMessage(`${type} uploaded successfully!`, "success");
        setUploadResults(prev => ({ ...prev, [type]: data }));
        fetchDocumentStatus();
      } else {
        showMessage(data.detail || "Upload failed", "error");
      }
    } catch (err) {
      showMessage(`Error uploading ${type}: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  // Upload all documents at once
  const uploadAllDocuments = async () => {
    if (!syllabusFile && !calendarFile && !examFile) {
      showMessage("Please select at least one file", "error");
      return;
    }

    setLoading(true);
    const formData = new FormData();
    if (syllabusFile) formData.append("syllabus", syllabusFile);
    if (calendarFile) formData.append("calendar", calendarFile);
    if (examFile) formData.append("exam_timetable", examFile);
    formData.append("email", userEmail);

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload/all`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      
      if (res.ok) {
        showMessage("Documents uploaded successfully!", "success");
        // Normalize keys: backend uses underscore, frontend expects hyphen for consistency
        const normalized = {
          syllabus: data.results?.syllabus || null,
          calendar: data.results?.calendar || null,
          "exam-timetable": data.results?.exam_timetable || data.results?.["exam-timetable"] || null
        };
        setUploadResults(normalized);
        fetchDocumentStatus();
      } else {
        showMessage(data.detail || "Upload failed", "error");
      }
    } catch (err) {
      showMessage(`Error uploading: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  // Fetch constraints
  const fetchConstraints = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/timetable/constraints?email=${userEmail}`);
      const data = await res.json();
      setConstraints(data.constraints);
      if (data.constraints) {
        showMessage("Constraints loaded!", "success");
        setActiveTab("constraints");
      } else {
        showMessage("No constraints found. Upload documents first.", "info");
      }
    } catch (err) {
      showMessage(`Error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  // Generate timetable from uploaded documents
  const generateTimetable = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/timetable/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: userEmail, preferences })
      });

      const data = await res.json();
      
      if (res.ok) {
        setTimetable(data);
        showMessage(`Timetable generated! ${data.total_slots} study slots created.`, "success");
        setActiveTab("timetable");
      } else {
        showMessage(data.detail || "Generation failed", "error");
      }
    } catch (err) {
      showMessage(`Error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  // Generate timetable from manual input (no PDF needed)
  const generateManualTimetable = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/timetable/generate-manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subjects: manualSubjects,
          exams: manualExams,
          holidays: ["2026-01-26"],
          preferences
        })
      });

      const data = await res.json();
      
      if (res.ok) {
        setTimetable(data);
        showMessage(`Timetable generated! ${data.total_slots} study slots.`, "success");
        setActiveTab("timetable");
      } else {
        showMessage(data.detail || "Generation failed", "error");
      }
    } catch (err) {
      showMessage(`Error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  // Universal PDF extraction - auto-detects document type
  const extractUniversalPDF = async () => {
    if (!universalFile) {
      showMessage("Please select a PDF file", "error");
      return;
    }

    setExtracting(true);
    const formData = new FormData();
    formData.append("file", universalFile);
    formData.append("email", userEmail);

    try {
      const res = await fetch(`${API_BASE}/api/documents/extract`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      
      if (res.ok) {
        setUniversalResults(data);
        showMessage(`✅ ${data.document_type?.toUpperCase()} detected! Extracted using ${data.extraction_method}`, "success");
      } else {
        showMessage(data.detail || "Extraction failed", "error");
      }
    } catch (err) {
      showMessage(`Error extracting PDF: ${err.message}`, "error");
    } finally {
      setExtracting(false);
    }
  };

  // Add manual subject
  const addManualSubject = () => {
    setManualSubjects([...manualSubjects, { 
      name: "", 
      difficulty: "medium", 
      weekly_target_hours: 4, 
      priority: 5 
    }]);
  };

  const updateManualSubject = (index, field, value) => {
    const updated = [...manualSubjects];
    updated[index][field] = value;
    setManualSubjects(updated);
  };

  const removeManualSubject = (index) => {
    setManualSubjects(manualSubjects.filter((_, i) => i !== index));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            📅 pdf extractor&Generator
          </h1>
          <p className="text-gray-400 mt-2">
            Upload your syllabus, academic calendar, and exam timetable to extract and load it.
          </p>
        </div>

        {/* Message Alert */}
        {message && (
          <div className={`mb-4 p-4 rounded-lg ${
            message.type === "success" ? "bg-green-500/20 border border-green-500 text-green-300" :
            message.type === "error" ? "bg-red-500/20 border border-red-500 text-red-300" :
            "bg-blue-500/20 border border-blue-500 text-blue-300"
          }`}>
            {message.text}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {["universal", "upload", "manual", "constraints", "timetable"].map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg capitalize transition ${
                activeTab === tab 
                  ? "bg-blue-600 text-white" 
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
            >
              {tab === "universal" ? "🤖 AI Extract" :
               tab === "upload" ? "📤 Upload PDFs" : 
               tab === "manual" ? "✏️ Manual Input" :
               tab === "constraints" ? "📋 Constraints" : "📅 Timetable"}
            </button>
          ))}
        </div>

        {/* Document Status Card */}
        {docStatus && (
          <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
            <h3 className="font-semibold mb-2">Document Status</h3>
            <div className="flex gap-4 flex-wrap text-sm">
              <span className={docStatus.syllabus_uploaded ? "text-green-400" : "text-gray-500"}>
                {docStatus.syllabus_uploaded ? "✅" : "⬜"} Syllabus
              </span>
              <span className={docStatus.calendar_uploaded ? "text-green-400" : "text-gray-500"}>
                {docStatus.calendar_uploaded ? "✅" : "⬜"} Calendar
              </span>
              <span className={docStatus.exam_timetable_uploaded ? "text-green-400" : "text-gray-500"}>
                {docStatus.exam_timetable_uploaded ? "✅" : "⬜"} Exam Timetable
              </span>
              {docStatus.summary && (
                <span className="text-blue-400 ml-4">
                  📊 {docStatus.summary.subjects_count} subjects, {docStatus.summary.exams_count} exams
                </span>
              )}
            </div>
          </div>
        )}

        {/* Universal AI Extract Tab */}
        {activeTab === "universal" && (
          <div className="space-y-6">
            {/* AI Extraction Card */}
            <div className="p-6 bg-gradient-to-br from-purple-900/30 to-blue-900/30 rounded-xl border border-purple-500/30">
              <div className="flex items-center gap-3 mb-4">
                <span className="text-4xl">🤖</span>
                <div>
                  <h2 className="text-xl font-bold text-purple-300">Hybrid AI Document Extractor</h2>
                  <p className="text-gray-400 text-sm">Drop ANY PDF - auto-detects type using Camelot + pdfplumber (FREE) with Gemini AI for JSON conversion</p>
                </div>
              </div>
              
              <div className="flex items-center gap-4 mb-4">
                <div className="flex-1">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => setUniversalFile(e.target.files[0])}
                    className="w-full text-sm text-gray-400 file:mr-4 file:py-3 file:px-6 file:rounded-lg file:border-0 file:bg-purple-600 file:text-white file:cursor-pointer file:font-semibold hover:file:bg-purple-700"
                  />
                </div>
                <button
                  onClick={extractUniversalPDF}
                  disabled={extracting || !universalFile}
                  className="px-8 py-3 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 disabled:from-gray-600 disabled:to-gray-600 rounded-lg font-bold transition flex items-center gap-2"
                >
                  {extracting ? (
                    <>
                      <span className="animate-spin">⏳</span> Extracting...
                    </>
                  ) : (
                    <>🚀 Extract Document</>
                  )}
                </button>
              </div>
              
              {universalFile && (
                <div className="text-sm text-gray-400 flex items-center gap-2">
                  <span>📄</span> Selected: <span className="text-white">{universalFile.name}</span>
                </div>
              )}

              <div className="mt-2 text-xs text-gray-500">
                Scanned PDFs use OCR automatically and may take longer.
              </div>
              
              {/* Extraction Pipeline */}
              <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <div className="p-3 bg-gray-800/50 rounded-lg text-center border border-green-500/30">
                  <span className="text-xl block mb-1">📊</span>
                  <span className="text-green-400 font-semibold">Camelot</span>
                  <p className="text-xs text-gray-500">Tables</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center border border-blue-500/30">
                  <span className="text-xl block mb-1">📝</span>
                  <span className="text-blue-400 font-semibold">pdfplumber</span>
                  <p className="text-xs text-gray-500">Text + Layout</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center border border-yellow-500/30">
                  <span className="text-xl block mb-1">🔍</span>
                  <span className="text-yellow-400 font-semibold">OCR Fallback</span>
                  <p className="text-xs text-gray-500">Scanned PDFs</p>
                </div>
                <div className="p-3 bg-gray-800/50 rounded-lg text-center border border-purple-500/30">
                  <span className="text-xl block mb-1">🤖</span>
                  <span className="text-purple-400 font-semibold">Gemini AI</span>
                  <p className="text-xs text-gray-500">JSON Convert</p>
                </div>
              </div>
            </div>

            {/* Universal Extraction Results */}
            {universalResults && (
              <div className="space-y-4">
                {/* Detection Result */}
                <div className="p-4 bg-gray-800 rounded-lg border border-green-500/50">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <span className="text-3xl">
                        {universalResults.document_type === 'syllabus' ? '📚' : 
                         universalResults.document_type === 'calendar' ? '📅' : '📝'}
                      </span>
                      <div>
                        <h3 className="font-bold text-green-400 text-lg">
                          Detected: {universalResults.document_type?.toUpperCase()}
                        </h3>
                        <p className="text-sm text-gray-400">
                          Method: <span className="text-blue-400">{universalResults.extraction_method}</span>
                        </p>
                      </div>
                    </div>
                    <span className="px-3 py-1 bg-green-600/30 text-green-300 rounded-full text-sm font-semibold">
                      ✅ Auto-detected
                    </span>
                  </div>
                  
                  {/* Extraction Stats */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                    {universalResults.quality_score !== undefined && (
                      <div className="p-2 bg-gray-700/50 rounded text-center">
                        <span className="block text-xl font-bold text-green-400">{Math.round(universalResults.quality_score)}</span>
                        <span className="text-xs text-gray-400">chars/page</span>
                      </div>
                    )}
                    <div className="p-2 bg-gray-700/50 rounded text-center">
                      <span className="block text-xl font-bold text-blue-400">{universalResults.tables?.length || 0}</span>
                      <span className="text-xs text-gray-400">tables found</span>
                    </div>
                    <div className="p-2 bg-gray-700/50 rounded text-center">
                      <span className="block text-xl font-bold text-purple-400">{universalResults.subjects?.length || 0}</span>
                      <span className="text-xs text-gray-400">courses</span>
                    </div>
                    <div className="p-2 bg-gray-700/50 rounded text-center">
                      <span className="block text-xl font-bold text-yellow-400">{universalResults.events?.length || 0}</span>
                      <span className="text-xs text-gray-400">events</span>
                    </div>
                    <div className="p-2 bg-gray-700/50 rounded text-center">
                      <span className="block text-xl font-bold text-pink-400">{universalResults.exams?.length || 0}</span>
                      <span className="text-xs text-gray-400">exams</span>
                    </div>
                  </div>

                  {/* Syllabus Totals Summary */}
                  {universalResults.document_type === 'syllabus' && universalResults.subjects?.length > 0 && (
                    <div className="mt-4 p-3 bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-lg border border-purple-500/30">
                      <h4 className="text-sm font-semibold text-purple-300 mb-2">📊 Syllabus Summary</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div className="text-center">
                          <span className="block text-lg font-bold text-purple-400">
                            {universalResults.subjects.length}
                          </span>
                          <span className="text-xs text-gray-400">Total Courses</span>
                        </div>
                        <div className="text-center">
                          <span className="block text-lg font-bold text-blue-400">
                            {universalResults.subjects.reduce((sum, s) => sum + (s.modules_count || s.modules?.length || 0), 0)}
                          </span>
                          <span className="text-xs text-gray-400">Total Modules</span>
                        </div>
                        <div className="text-center">
                          <span className="block text-lg font-bold text-green-400">
                            {universalResults.subjects.reduce((sum, s) => sum + (s.total_hours || s.estimated_hours || 0), 0)}h
                          </span>
                          <span className="text-xs text-gray-400">Total Hours</span>
                        </div>
                        <div className="text-center">
                          <span className="block text-lg font-bold text-yellow-400">
                            {universalResults.subjects.reduce((sum, s) => sum + (s.topics?.length || 0), 0)}
                          </span>
                          <span className="text-xs text-gray-400">Total Topics</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Subjects Table (for syllabus) */}
                {universalResults.subjects && universalResults.subjects.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-blue-500/30">
                    <h3 className="font-semibold mb-4 text-blue-400 flex items-center gap-2">
                      <span>📚</span> Extracted Courses ({universalResults.subjects.length})
                    </h3>
                    
                    {universalResults.subjects.map((subj, idx) => (
                      <div key={idx} className="mb-4 p-4 bg-gray-700/30 rounded-lg">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <h4 className="font-bold text-lg">{subj.name}</h4>
                            {subj.code && <span className="text-xs text-gray-400 mr-2">Code: {subj.code}</span>}
                            {(subj.modules_count || subj.modules?.length > 0) && (
                              <span className="text-xs text-purple-400">
                                • {subj.modules_count || subj.modules?.length} modules
                              </span>
                            )}
                          </div>
                          <div className="flex gap-2">
                            <span className={`px-2 py-1 rounded text-xs ${
                              subj.difficulty === 'hard' ? 'bg-red-600/30 text-red-300' :
                              subj.difficulty === 'easy' ? 'bg-green-600/30 text-green-300' :
                              'bg-yellow-600/30 text-yellow-300'
                            }`}>
                              {subj.difficulty || 'medium'}
                            </span>
                            <span className="px-2 py-1 bg-blue-600/30 text-blue-300 rounded text-xs">
                              {subj.total_hours || subj.estimated_hours || 0}h
                            </span>
                            {subj.priority && (
                              <span className="px-2 py-1 bg-orange-600/30 text-orange-300 rounded text-xs">
                                P{subj.priority}
                              </span>
                            )}
                          </div>
                        </div>
                        
                        {/* Modules */}
                        {subj.modules && subj.modules.length > 0 && (
                          <div className="mb-3">
                            <h5 className="text-sm font-semibold text-purple-400 mb-2">📘 Modules ({subj.modules.length})</h5>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {subj.modules.slice(0, 8).map((mod, mIdx) => (
                                <div key={mIdx} className="flex items-start gap-2 text-sm text-gray-300">
                                  <span className="text-purple-500 mt-0.5">•</span>
                                  <span>{typeof mod === 'string' ? mod : mod.module_title || mod.name || JSON.stringify(mod)}</span>
                                </div>
                              ))}
                            </div>
                            {subj.modules.length > 8 && (
                              <p className="text-xs text-gray-500 mt-2">...and {subj.modules.length - 8} more modules</p>
                            )}
                          </div>
                        )}
                        
                        {/* Topics/Objectives */}
                        {subj.topics && subj.topics.length > 0 && (
                          <div>
                            <h5 className="text-sm font-semibold text-green-400 mb-2">🎯 Topics & Objectives ({subj.topics.length})</h5>
                            <div className="flex flex-wrap gap-2">
                              {subj.topics.slice(0, 10).map((topic, tIdx) => (
                                <span key={tIdx} className="px-2 py-1 bg-green-900/30 text-green-300 rounded text-xs">
                                  {typeof topic === 'string' ? topic.substring(0, 60) : topic}
                                  {typeof topic === 'string' && topic.length > 60 && '...'}
                                </span>
                              ))}
                              {subj.topics.length > 10 && (
                                <span className="px-2 py-1 bg-gray-700 text-gray-400 rounded text-xs">
                                  +{subj.topics.length - 10} more
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Events Table (for calendar) */}
                {universalResults.events && universalResults.events.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-green-500/30">
                    <h3 className="font-semibold mb-4 text-green-400 flex items-center gap-2">
                      <span>📅</span> Extracted Events ({universalResults.events.length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-left">
                            <th className="py-2 px-3 text-gray-400">#</th>
                            <th className="py-2 px-3 text-gray-400">Event Name</th>
                            <th className="py-2 px-3 text-gray-400">Date</th>
                            <th className="py-2 px-3 text-gray-400">Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {universalResults.events.map((event, idx) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-3 px-3 text-gray-500">{idx + 1}</td>
                              <td className="py-3 px-3 font-medium">{event.name || event.event || event}</td>
                              <td className="py-3 px-3 text-green-400">{event.date || '-'}</td>
                              <td className="py-3 px-3">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  event.type === 'holiday' ? 'bg-red-600/30 text-red-300' :
                                  event.type === 'exam' ? 'bg-purple-600/30 text-purple-300' :
                                  'bg-blue-600/30 text-blue-300'
                                }`}>
                                  {event.type || 'event'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Exams Table (for exam timetable) */}
                {universalResults.exams && universalResults.exams.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-purple-500/30">
                    <h3 className="font-semibold mb-4 text-purple-400 flex items-center gap-2">
                      <span>📝</span> Extracted Exams ({universalResults.exams.length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-left">
                            <th className="py-2 px-3 text-gray-400">#</th>
                            <th className="py-2 px-3 text-gray-400">Subject</th>
                            <th className="py-2 px-3 text-gray-400">Date</th>
                            <th className="py-2 px-3 text-gray-400">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {universalResults.exams.map((exam, idx) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-3 px-3 text-gray-500">{idx + 1}</td>
                              <td className="py-3 px-3 font-medium">{exam.subject || exam.name || exam}</td>
                              <td className="py-3 px-3 text-purple-400">{exam.date || '-'}</td>
                              <td className="py-3 px-3 text-gray-400">{exam.time || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Raw Text Preview */}
                {(universalResults.raw_text || universalResults.raw_text_preview) && (
                  <details className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <summary className="cursor-pointer font-semibold text-gray-400 hover:text-white">
                      📄 View Raw Extracted Text
                    </summary>
                    <pre className="mt-4 p-4 bg-gray-900 rounded-lg text-xs text-gray-300 overflow-x-auto max-h-64 whitespace-pre-wrap">
                      {(universalResults.raw_text || universalResults.raw_text_preview || '').substring(0, 3000)}
                      {(universalResults.raw_text || universalResults.raw_text_preview || '').length > 3000 && '...'}
                    </pre>
                  </details>
                )}

                {/* Tables Preview */}
                {universalResults.tables && universalResults.tables.length > 0 && (
                  <details className="p-4 bg-gray-800 rounded-lg border border-blue-500/30">
                    <summary className="cursor-pointer font-semibold text-blue-400 hover:text-blue-300">
                      📊 View Extracted Tables ({universalResults.tables.length})
                    </summary>
                    <div className="mt-4 space-y-4">
                      {universalResults.tables.slice(0, 5).map((table, idx) => (
                        <div key={idx} className="p-3 bg-gray-900 rounded-lg">
                          <h5 className="text-sm font-semibold text-gray-400 mb-2">Table {idx + 1}</h5>
                          <pre className="text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap max-h-32">
                            {typeof table === 'string' ? table.substring(0, 500) : JSON.stringify(table, null, 2).substring(0, 500)}
                            {(typeof table === 'string' ? table.length : JSON.stringify(table).length) > 500 && '...'}
                          </pre>
                        </div>
                      ))}
                      {universalResults.tables.length > 5 && (
                        <p className="text-sm text-gray-500">...and {universalResults.tables.length - 5} more tables</p>
                      )}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        )}

        {/* Upload Tab */}
        {activeTab === "upload" && (
          <div className="space-y-6">
            {/* Individual Uploads */}
            <div className="grid md:grid-cols-3 gap-4">
              {/* Syllabus Upload */}
              <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                <h3 className="font-semibold mb-3">📚 Syllabus PDF</h3>
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setSyllabusFile(e.target.files[0])}
                  className="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-blue-600 file:text-white file:cursor-pointer"
                />
                {syllabusFile && <p className="text-xs text-gray-400 mt-2">{syllabusFile.name}</p>}
                <button
                  onClick={() => uploadDocument(syllabusFile, "syllabus")}
                  disabled={loading || !syllabusFile}
                  className="mt-3 w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg transition"
                >
                  Upload Syllabus
                </button>
              </div>

              {/* Calendar Upload */}
              <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                <h3 className="font-semibold mb-3">📅 Academic Calendar</h3>
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setCalendarFile(e.target.files[0])}
                  className="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-green-600 file:text-white file:cursor-pointer"
                />
                {calendarFile && <p className="text-xs text-gray-400 mt-2">{calendarFile.name}</p>}
                <button
                  onClick={() => uploadDocument(calendarFile, "calendar")}
                  disabled={loading || !calendarFile}
                  className="mt-3 w-full py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 rounded-lg transition"
                >
                  Upload Calendar
                </button>
              </div>

              {/* Exam Timetable Upload */}
              <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                <h3 className="font-semibold mb-3">📝 Exam Timetable</h3>
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setExamFile(e.target.files[0])}
                  className="w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-purple-600 file:text-white file:cursor-pointer"
                />
                {examFile && <p className="text-xs text-gray-400 mt-2">{examFile.name}</p>}
                <button
                  onClick={() => uploadDocument(examFile, "exam-timetable")}
                  disabled={loading || !examFile}
                  className="mt-3 w-full py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 rounded-lg transition"
                >
                  Upload Exam Table
                </button>
              </div>
            </div>

            {/* Upload All Button */}
            <div className="flex gap-4">
              <button
                onClick={uploadAllDocuments}
                disabled={loading || (!syllabusFile && !calendarFile && !examFile)}
                className="px-6 py-3 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 disabled:from-gray-600 disabled:to-gray-600 rounded-lg font-semibold transition"
              >
                {loading ? "⏳ Uploading..." : "📤 Upload All Documents"}
              </button>
              
              <button
                onClick={fetchConstraints}
                disabled={loading}
                className="px-6 py-3 bg-gray-700 hover:bg-gray-600 rounded-lg transition"
              >
                📋 View Constraints
              </button>
              
              <button
                onClick={generateTimetable}
                disabled={loading || !docStatus?.ready_for_generation}
                className="px-6 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-600 rounded-lg font-semibold transition"
              >
                {loading ? "⏳ Generating..." : "🚀 Generate Timetable"}
              </button>
            </div>

            {/* Upload Results - Display as Tables */}
            {uploadResults && (
              <div className="space-y-4">
                {/* Syllabus Results - handle both uploadResults.syllabus.subjects and uploadResults.subjects */}
                {((uploadResults.syllabus?.subjects && uploadResults.syllabus.subjects.length > 0) ||
                  (uploadResults.subjects && uploadResults.subjects.length > 0)) && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-4 text-blue-400">
                      📚 Extracted Courses ({(uploadResults.syllabus?.subjects || uploadResults.subjects).length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-left">
                            <th className="py-2 px-3 text-gray-400">Course Name</th>
                            <th className="py-2 px-3 text-gray-400">Hours</th>
                            <th className="py-2 px-3 text-gray-400">Difficulty</th>
                            <th className="py-2 px-3 text-gray-400">Priority</th>
                            <th className="py-2 px-3 text-gray-400">Weekly Target</th>
                            <th className="py-2 px-3 text-gray-400">Modules</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(uploadResults.syllabus?.subjects || uploadResults.subjects).map((subj, idx) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-3 px-3 font-medium">{subj.name}</td>
                              <td className="py-3 px-3">{subj.estimated_hours}h</td>
                              <td className="py-3 px-3">
                                <span className={`px-2 py-1 rounded text-xs ${
                                  subj.difficulty === 'hard' ? 'bg-red-600/30 text-red-300' :
                                  subj.difficulty === 'easy' ? 'bg-green-600/30 text-green-300' :
                                  'bg-yellow-600/30 text-yellow-300'
                                }`}>
                                  {subj.difficulty}
                                </span>
                              </td>
                              <td className="py-3 px-3">
                                <span className="text-blue-400">{subj.priority}/10</span>
                              </td>
                              <td className="py-3 px-3">{subj.weekly_target_hours}h/week</td>
                              <td className="py-3 px-3 text-gray-400">
                                {subj.topics?.filter(t => t.startsWith('📘')).length || 0} modules
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    
                    {/* Summary Stats */}
                    <div className="mt-4 pt-4 border-t border-gray-700 flex gap-6 text-sm">
                      <span className="text-gray-400">
                        Total Hours: <span className="text-white font-semibold">
                          {(uploadResults.syllabus?.subjects || uploadResults.subjects).reduce((sum, s) => sum + (s.estimated_hours || 0), 0)}h
                        </span>
                      </span>
                      <span className="text-gray-400">
                        Total Modules: <span className="text-white font-semibold">
                          {(uploadResults.syllabus?.subjects || uploadResults.subjects).reduce((sum, s) => 
                            sum + (s.topics?.filter(t => t.startsWith('📘')).length || 0), 0
                          )}
                        </span>
                      </span>
                    </div>
                  </div>
                )}

                {/* Expandable Module Details */}
                {((uploadResults.syllabus?.subjects && uploadResults.syllabus.subjects.length > 0) ||
                  (uploadResults.subjects && uploadResults.subjects.length > 0)) && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-4 text-purple-400">📖 Module Details</h3>
                    <div className="space-y-4">
                      {(uploadResults.syllabus?.subjects || uploadResults.subjects).map((subj, idx) => (
                        <details key={idx} className="bg-gray-700/30 rounded-lg">
                          <summary className="p-3 cursor-pointer hover:bg-gray-700/50 rounded-lg font-medium">
                            {subj.name} - {subj.topics?.filter(t => t.startsWith('📘')).length || 0} modules
                          </summary>
                          <div className="px-4 pb-4">
                            <table className="w-full text-sm mt-2">
                              <thead>
                                <tr className="border-b border-gray-600 text-left">
                                  <th className="py-2 px-2 text-gray-400 w-1/4">Module</th>
                                  <th className="py-2 px-2 text-gray-400">Topics</th>
                                </tr>
                              </thead>
                              <tbody>
                                {subj.topics?.filter(t => t.startsWith('📘')).map((module, mIdx) => {
                                  // Find topics for this module (topics between this 📘 and next 📘)
                                  const moduleIdx = subj.topics.indexOf(module);
                                  const nextModuleIdx = subj.topics.findIndex((t, i) => i > moduleIdx && t.startsWith('📘'));
                                  const endIdx = nextModuleIdx === -1 ? subj.topics.length : nextModuleIdx;
                                  const moduleTopics = subj.topics.slice(moduleIdx + 1, endIdx).filter(t => t.includes('•'));
                                  
                                  return (
                                    <tr key={mIdx} className="border-b border-gray-600/30">
                                      <td className="py-2 px-2 align-top font-medium text-blue-300">
                                        {module.replace('📘 ', '')}
                                      </td>
                                      <td className="py-2 px-2 text-gray-300 text-xs">
                                        {moduleTopics.map((topic, tIdx) => (
                                          <div key={tIdx} className="mb-1">
                                            {topic.trim().substring(0, 100)}{topic.length > 100 ? '...' : ''}
                                          </div>
                                        ))}
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        </details>
                      ))}
                    </div>
                  </div>
                )}

                {/* Calendar Results */}
                {uploadResults.calendar?.events && uploadResults.calendar.events.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-4 text-green-400">
                      📅 Academic Events ({uploadResults.calendar.events.length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-left">
                            <th className="py-2 px-3 text-gray-400">Date</th>
                            <th className="py-2 px-3 text-gray-400">Event</th>
                            <th className="py-2 px-3 text-gray-400">Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {uploadResults.calendar.events.map((event, idx) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-2 px-3">{event.date}</td>
                              <td className="py-2 px-3">{event.name}</td>
                              <td className="py-2 px-3">
                                {event.is_holiday ? (
                                  <span className="px-2 py-1 bg-red-600/30 text-red-300 rounded text-xs">Holiday</span>
                                ) : event.is_exam ? (
                                  <span className="px-2 py-1 bg-purple-600/30 text-purple-300 rounded text-xs">Exam</span>
                                ) : (
                                  <span className="px-2 py-1 bg-blue-600/30 text-blue-300 rounded text-xs">Event</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Exam Timetable Results */}
                {(uploadResults["exam-timetable"]?.exams || uploadResults.exam_timetable?.exams) && 
                 (uploadResults["exam-timetable"]?.exams?.length > 0 || uploadResults.exam_timetable?.exams?.length > 0) && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-4 text-orange-400">
                      📝 Exam Schedule ({(uploadResults["exam-timetable"]?.exams || uploadResults.exam_timetable?.exams).length})
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-gray-700 text-left">
                            <th className="py-2 px-3 text-gray-400">Date</th>
                            <th className="py-2 px-3 text-gray-400">Time</th>
                            <th className="py-2 px-3 text-gray-400">Subject</th>
                            <th className="py-2 px-3 text-gray-400">Venue</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(uploadResults["exam-timetable"]?.exams || uploadResults.exam_timetable?.exams).map((exam, idx) => (
                            <tr key={idx} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                              <td className="py-2 px-3 font-medium">{exam.date}</td>
                              <td className="py-2 px-3">{exam.start_time} - {exam.end_time}</td>
                              <td className="py-2 px-3">{exam.subject}</td>
                              <td className="py-2 px-3 text-gray-400">{exam.venue || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* If no structured data, show raw JSON */}
                {!uploadResults.syllabus?.subjects && 
                 !uploadResults.subjects &&
                 !uploadResults.calendar?.events && 
                 !uploadResults["exam-timetable"]?.exams &&
                 !uploadResults.exam_timetable?.exams && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-2">Raw Response</h3>
                    <pre className="text-xs text-gray-300 overflow-auto max-h-60">
                      {JSON.stringify(uploadResults, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Manual Input Tab */}
        {activeTab === "manual" && (
          <div className="space-y-6">
            <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
              <h3 className="font-semibold mb-4">✏️ Manual Subject Entry (No PDF Required)</h3>
              
              {/* Subjects */}
              <div className="space-y-3 mb-4">
                {manualSubjects.map((subj, idx) => (
                  <div key={idx} className="flex gap-2 items-center flex-wrap">
                    <input
                      type="text"
                      placeholder="Subject name"
                      value={subj.name}
                      onChange={(e) => updateManualSubject(idx, "name", e.target.value)}
                      className="flex-1 min-w-[150px] px-3 py-2 bg-gray-700 rounded-lg border border-gray-600 focus:border-blue-500 outline-none"
                    />
                    <select
                      value={subj.difficulty}
                      onChange={(e) => updateManualSubject(idx, "difficulty", e.target.value)}
                      className="px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                    >
                      <option value="easy">Easy</option>
                      <option value="medium">Medium</option>
                      <option value="hard">Hard</option>
                    </select>
                    <input
                      type="number"
                      placeholder="Hrs/week"
                      value={subj.weekly_target_hours}
                      onChange={(e) => updateManualSubject(idx, "weekly_target_hours", parseInt(e.target.value) || 0)}
                      className="w-20 px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                    />
                    <input
                      type="number"
                      placeholder="Priority"
                      min="1" max="10"
                      value={subj.priority}
                      onChange={(e) => updateManualSubject(idx, "priority", parseInt(e.target.value) || 5)}
                      className="w-20 px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                    />
                    <button
                      onClick={() => removeManualSubject(idx)}
                      className="px-3 py-2 bg-red-600 hover:bg-red-700 rounded-lg"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
              
              <button
                onClick={addManualSubject}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg"
              >
                + Add Subject
              </button>
            </div>

            {/* Preferences */}
            <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
              <h3 className="font-semibold mb-4">⚙️ Preferences</h3>
              <div className="grid md:grid-cols-4 gap-4">
                <div>
                  <label className="text-sm text-gray-400">Start Hour</label>
                  <input
                    type="number"
                    value={preferences.study_start_hour}
                    onChange={(e) => setPreferences({...preferences, study_start_hour: parseInt(e.target.value)})}
                    className="w-full px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400">End Hour</label>
                  <input
                    type="number"
                    value={preferences.study_end_hour}
                    onChange={(e) => setPreferences({...preferences, study_end_hour: parseInt(e.target.value)})}
                    className="w-full px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400">Max Daily Hours</label>
                  <input
                    type="number"
                    value={preferences.max_daily_hours}
                    onChange={(e) => setPreferences({...preferences, max_daily_hours: parseInt(e.target.value)})}
                    className="w-full px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                  />
                </div>
                <div>
                  <label className="text-sm text-gray-400">Days Ahead</label>
                  <input
                    type="number"
                    value={preferences.days_ahead}
                    onChange={(e) => setPreferences({...preferences, days_ahead: parseInt(e.target.value)})}
                    className="w-full px-3 py-2 bg-gray-700 rounded-lg border border-gray-600"
                  />
                </div>
              </div>
            </div>

            <button
              onClick={generateManualTimetable}
              disabled={loading || manualSubjects.length === 0}
              className="px-6 py-3 bg-gradient-to-r from-green-600 to-blue-600 hover:from-green-700 hover:to-blue-700 disabled:from-gray-600 disabled:to-gray-600 rounded-lg font-semibold transition"
            >
              {loading ? "⏳ Generating..." : "🚀 Generate Timetable"}
            </button>
          </div>
        )}

        {/* Constraints Tab */}
        {activeTab === "constraints" && (
          <div className="space-y-4">
            {constraints ? (
              <>
                {/* Subjects */}
                <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                  <h3 className="font-semibold mb-3">📚 Subjects ({constraints.subjects?.length || 0})</h3>
                  <div className="grid md:grid-cols-2 gap-3">
                    {constraints.subjects?.map((s, i) => (
                      <div key={i} className="p-3 bg-gray-700 rounded-lg">
                        <div className="font-medium">{s.name}</div>
                        <div className="text-sm text-gray-400">
                          Difficulty: <span className={
                            s.difficulty === "hard" ? "text-red-400" :
                            s.difficulty === "easy" ? "text-green-400" : "text-yellow-400"
                          }>{s.difficulty}</span> | 
                          Hours: {s.estimated_hours}h | 
                          Weekly: {s.weekly_target_hours}h
                        </div>
                        {s.topics?.length > 0 && (
                          <div className="text-xs text-gray-500 mt-1">
                            Topics: {s.topics.slice(0, 3).join(", ")}...
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Events */}
                {constraints.academic_events?.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-3">📅 Events ({constraints.academic_events.length})</h3>
                    <div className="space-y-2">
                      {constraints.academic_events.slice(0, 10).map((e, i) => (
                        <div key={i} className="flex justify-between items-center p-2 bg-gray-700 rounded">
                          <span>{e.name}</span>
                          <span className="text-sm text-gray-400">{e.date}</span>
                          {e.is_holiday && <span className="text-xs bg-red-600 px-2 py-1 rounded">Holiday</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Exams */}
                {constraints.exams?.length > 0 && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-3">📝 Exams ({constraints.exams.length})</h3>
                    <div className="space-y-2">
                      {constraints.exams.map((e, i) => (
                        <div key={i} className="flex justify-between items-center p-2 bg-gray-700 rounded">
                          <span>{e.subject}</span>
                          <span className="text-sm text-gray-400">{e.date} {e.start_time || ""}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <button
                  onClick={generateTimetable}
                  disabled={loading}
                  className="px-6 py-3 bg-green-600 hover:bg-green-700 rounded-lg font-semibold transition"
                >
                  {loading ? "⏳ Generating..." : "🚀 Generate Timetable from Constraints"}
                </button>
              </>
            ) : (
              <div className="text-center py-10 text-gray-400">
                <p>No constraints loaded. Upload documents or use manual input first.</p>
                <button
                  onClick={fetchConstraints}
                  className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg"
                >
                  🔄 Load Constraints
                </button>
              </div>
            )}
          </div>
        )}

        {/* Timetable Tab */}
        {activeTab === "timetable" && (
          <div className="space-y-4">
            {timetable ? (
              <>
                {/* Stats */}
                <div className="grid md:grid-cols-4 gap-4">
                  <div className="p-4 bg-gradient-to-br from-blue-600 to-blue-800 rounded-lg">
                    <div className="text-2xl font-bold">{timetable.total_slots}</div>
                    <div className="text-sm text-blue-200">Total Study Slots</div>
                  </div>
                  <div className="p-4 bg-gradient-to-br from-green-600 to-green-800 rounded-lg">
                    <div className="text-2xl font-bold">{timetable.total_hours}h</div>
                    <div className="text-sm text-green-200">Total Hours</div>
                  </div>
                  <div className="p-4 bg-gradient-to-br from-purple-600 to-purple-800 rounded-lg">
                    <div className="text-2xl font-bold">{timetable.days_covered}</div>
                    <div className="text-sm text-purple-200">Days Covered</div>
                  </div>
                  <div className="p-4 bg-gradient-to-br from-orange-600 to-orange-800 rounded-lg">
                    <div className="text-2xl font-bold">{Object.keys(timetable.subject_distribution || {}).length}</div>
                    <div className="text-sm text-orange-200">Subjects</div>
                  </div>
                </div>

                {/* Subject Distribution */}
                {timetable.subject_distribution && (
                  <div className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                    <h3 className="font-semibold mb-3">📊 Hours per Subject</h3>
                    <div className="flex flex-wrap gap-3">
                      {Object.entries(timetable.subject_distribution).map(([subj, hours]) => (
                        <div key={subj} className="px-4 py-2 bg-gray-700 rounded-lg">
                          <span className="font-medium">{subj}</span>
                          <span className="ml-2 text-blue-400">{hours}h</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Schedule by Day */}
                <div className="space-y-4">
                  {timetable.schedule?.map((day, i) => (
                    <div key={i} className="p-4 bg-gray-800 rounded-lg border border-gray-700">
                      <h3 className="font-semibold mb-3 text-blue-400">
                        📆 {day.day}, {day.date}
                      </h3>
                      <div className="grid md:grid-cols-3 lg:grid-cols-4 gap-2">
                        {day.slots?.map((slot, j) => (
                          <div 
                            key={j} 
                            className={`p-3 rounded-lg ${
                              slot.difficulty === "hard" ? "bg-red-900/30 border border-red-700" :
                              slot.difficulty === "easy" ? "bg-green-900/30 border border-green-700" :
                              "bg-yellow-900/30 border border-yellow-700"
                            }`}
                          >
                            <div className="text-xs text-gray-400">{slot.start_time} - {slot.end_time}</div>
                            <div className="font-medium">{slot.subject}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="text-center py-10 text-gray-400">
                <p>No timetable generated yet.</p>
                <p className="text-sm mt-2">Upload documents or use manual input to generate a study schedule.</p>
              </div>
            )}
          </div>
        )}

        {/* Loading Overlay */}
        {loading && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="p-6 bg-gray-800 rounded-lg text-center">
              <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
              <p>Processing...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
