"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import React from "react";
import dynamic from "next/dynamic";

const KnowledgeGraph = dynamic(() => import("../../components/KnowledgeGraph"), {
  ssr: false,
  loading: () => <div className="p-6 text-slate-400">Loading Knowledge Graph…</div>,
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:5000";

export default function StudyPage() {
  const { data: session } = useSession();
  const [subjects, setSubjects] = useState([]);
  const [notes, setNotes] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showSubjectModal, setShowSubjectModal] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [previewNote, setPreviewNote] = useState(null);
  const [stats, setStats] = useState(null);
  const [showGraph, setShowGraph] = useState(false);
  const [graphKey, setGraphKey] = useState(0);
  const [uploadStatus, setUploadStatus] = useState(null);

  // Search states
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null);
  const [searching, setSearching] = useState(false);

  // Form states
  const [subjectForm, setSubjectForm] = useState({ name: "", description: "" });
  const [uploadForm, setUploadForm] = useState({ title: "", description: "", file: null });

  // BM25 Search
  const handleSearch = async (query) => {
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    setSearching(true);
    try {
      const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}&top_k=10`);
      const data = await response.json();
      setSearchResults(data.results);
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setSearching(false);
    }
  };

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      handleSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Helper: build headers with user email
  const authHeaders = () => {
    const headers = {};
    const email = session?.user?.email;
    if (email) headers["x-user-email"] = email;
    return headers;
  };

  // Fetch subjects
  const fetchSubjects = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/subjects`, { headers: authHeaders() });
      const data = await response.json();
      setSubjects(data.subjects || []);
    } catch (error) {
      console.error("Error fetching subjects:", error);
    }
  };

  // Fetch notes
  const fetchNotes = async (subjectId = null) => {
    try {
      const url = subjectId 
        ? `${API_BASE}/api/notes?subject_id=${subjectId}`
        : `${API_BASE}/api/notes`;
      const response = await fetch(url, { headers: authHeaders() });
      const data = await response.json();
      setNotes(data.notes || []);
    } catch (error) {
      console.error("Error fetching notes:", error);
    }
  };

  // Fetch stats
  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/study/stats`, { headers: authHeaders() });
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error("Error fetching stats:", error);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSubjects(), fetchNotes(), fetchStats()]);
      setLoading(false);
    };
    loadData();
  }, []);

  // Create subject
  const handleCreateSubject = async (e) => {
    e.preventDefault();
    try {
      const formData = new FormData();
      formData.append("name", subjectForm.name);
      formData.append("description", subjectForm.description);

      if (session?.user?.email) formData.append("email", session.user.email);

      const response = await fetch(`${API_BASE}/api/subjects`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });

      if (response.ok) {
        setSubjectForm({ name: "", description: "" });
        setShowSubjectModal(false);
        await fetchSubjects();
      }
    } catch (error) {
      console.error("Error creating subject:", error);
    }
  };

  // Upload file
  const handleUploadFile = async (e) => {
    e.preventDefault();
    if (!selectedSubject || !uploadForm.file) return;

    try {
      const formData = new FormData();
      formData.append("file", uploadForm.file);
      formData.append("subject_id", selectedSubject.id);
      formData.append("title", uploadForm.title || uploadForm.file.name);
      formData.append("description", uploadForm.description);
      if (session?.user?.email) formData.append("email", session.user.email);

      const response = await fetch(`${API_BASE}/api/notes/upload`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });

      if (response.ok) {
        const data = await response.json().catch(() => ({}));
        setUploadForm({ title: "", description: "", file: null });
        setShowUploadModal(false);
        // Inform user that extraction was queued and refresh notes/stats
        setUploadStatus((data && data.message) || "File uploaded — extraction queued");
        // bump graph key to force KnowledgeGraph to refetch when visible
        setGraphKey((k) => k + 1);
        await fetchNotes(selectedSubject.id);
        await fetchStats();
        // clear status after a few seconds
        setTimeout(() => setUploadStatus(null), 6000);
      }
    } catch (error) {
      console.error("Error uploading file:", error);
    }
  };

  // Delete note
  const handleDeleteNote = async (noteId) => {
    if (!confirm("Are you sure you want to delete this note?")) return;

    try {
      const response = await fetch(`${API_BASE}/api/notes/${noteId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });

      if (response.ok) {
        await fetchNotes(selectedSubject?.id);
        await fetchStats();
      }
    } catch (error) {
      console.error("Error deleting note:", error);
    }
  };

  // Download note
  const handleDownloadNote = (noteId) => {
    window.open(`${API_BASE}/api/notes/${noteId}/download`, "_blank");
  };

  // Preview note
  const handlePreviewNote = (note) => {
    setPreviewNote(note);
    setShowPreviewModal(true);
  };

  // Check if file can be previewed
  const canPreview = (fileType) => {
    const previewableTypes = ["PDF", "TXT", "MD", "JSON", "HTML", "CSS", "JS", "PNG", "JPG", "JPEG", "GIF", "SVG"];
    return previewableTypes.includes(fileType?.toUpperCase());
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + " " + sizes[i];
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center">
        <p className="text-white text-xl">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-0 w-[700px] h-[700px] bg-gradient-to-tl from-purple-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
      </div>

      <div className="relative z-10 p-8">
        {/* Header */}
        <header className="mb-8">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-4xl font-black bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
                Study Hub
              </h1>
              <p className="text-slate-400 mt-2">
                Welcome back, {session?.user?.name || "User"}
              </p>
            </div>
            <button
              onClick={() => setShowSubjectModal(true)}
              className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-6 py-3 rounded-lg hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 hover:scale-105 font-semibold"
            >
              + Add Subject
            </button>
          </div>

          {/* Search Bar */}
          <div className="mt-4 relative">
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search notes, subjects, tasks..."
                className="w-full bg-slate-900/80 border border-slate-700 text-white pl-12 pr-4 py-3 rounded-xl focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 placeholder-slate-500 transition-all"
              />
              {searchQuery && (
                <button
                  onClick={() => { setSearchQuery(""); setSearchResults(null); }}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Search Results Dropdown */}
            {searchResults && searchQuery && (
              <div className="absolute top-full left-0 right-0 mt-2 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl z-20 max-h-80 overflow-y-auto">
                {searching ? (
                  <p className="p-4 text-slate-400 text-center">Searching...</p>
                ) : (
                  <>
                    {(searchResults.notes?.length > 0 || searchResults.subjects?.length > 0 || searchResults.tasks?.length > 0) ? (
                      <div className="p-3 space-y-3">
                        {searchResults.subjects?.length > 0 && (
                          <div>
                            <p className="text-xs font-bold text-purple-400 uppercase tracking-wider px-2 mb-1">Subjects</p>
                            {searchResults.subjects.map((r) => {
                              const subj = subjects.find((s) => s.id === r.id);
                              return (
                                <button
                                  key={r.id}
                                  onClick={() => {
                                    const found = subjects.find((s) => s.id === r.id);
                                    if (found) { setSelectedSubject(found); fetchNotes(found.id); }
                                    setSearchQuery(""); setSearchResults(null);
                                  }}
                                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2"
                                >
                                  <span>📚</span>
                                  <span className="text-white text-sm">{subj?.name || r.id}</span>
                                  <span className="ml-auto text-xs text-slate-500">score: {r.score}</span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                        {searchResults.notes?.length > 0 && (
                          <div>
                            <p className="text-xs font-bold text-blue-400 uppercase tracking-wider px-2 mb-1">Notes</p>
                            {searchResults.notes.map((r) => {
                              const note = notes.find((n) => n.id === r.id);
                              return (
                                <button
                                  key={r.id}
                                  onClick={() => {
                                    if (note) handlePreviewNote(note);
                                    setSearchQuery(""); setSearchResults(null);
                                  }}
                                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2"
                                >
                                  <span>📄</span>
                                  <span className="text-white text-sm">{note?.title || r.id}</span>
                                  <span className="ml-auto text-xs text-slate-500">score: {r.score}</span>
                                </button>
                              );
                            })}
                          </div>
                        )}
                        {searchResults.tasks?.length > 0 && (
                          <div>
                            <p className="text-xs font-bold text-cyan-400 uppercase tracking-wider px-2 mb-1">Tasks</p>
                            {searchResults.tasks.map((r) => (
                              <div
                                key={r.id}
                                className="px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors flex items-center gap-2"
                              >
                                <span>✅</span>
                                <span className="text-white text-sm">{r.id}</span>
                                <span className="ml-auto text-xs text-slate-500">score: {r.score}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="p-4 text-slate-400 text-center">No results found</p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </header>
        {uploadStatus && (
          <div className="mb-6 max-w-3xl">
            <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-300">
              {uploadStatus}
            </div>
          </div>
        )}

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-cyan-500/20 shadow-lg">
              <p className="text-slate-400 text-sm mb-2">Total Subjects</p>
              <p className="text-3xl font-bold text-cyan-400">{stats.totalSubjects}</p>
            </div>
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-blue-500/20 shadow-lg">
              <p className="text-slate-400 text-sm mb-2">Total Notes</p>
              <p className="text-3xl font-bold text-blue-400">{stats.totalNotes}</p>
            </div>
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-purple-500/20 shadow-lg">
              <p className="text-slate-400 text-sm mb-2">Storage Used</p>
              <p className="text-3xl font-bold text-purple-400">{formatFileSize(stats.totalSize)}</p>
            </div>
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-pink-500/20 shadow-lg">
              <p className="text-slate-400 text-sm mb-2">File Types</p>
              <p className="text-3xl font-bold text-pink-400">{Object.keys(stats.fileTypes || {}).length}</p>
            </div>
          </div>
        )}

        {/* Main Content */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Subjects Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-cyan-500/20 shadow-2xl">
              <h2 className="text-xl font-bold mb-4 flex items-center">
                <span className="mr-2">📚</span>
                Subjects
              </h2>
              <div className="space-y-2 max-h-[600px] overflow-y-auto custom-scrollbar">
                <button
                  onClick={() => {
                    setSelectedSubject(null);
                    fetchNotes();
                  }}
                  className={`w-full text-left p-3 rounded-lg transition-all ${
                    !selectedSubject
                      ? "bg-cyan-500/20 border border-cyan-500/40 text-cyan-400"
                      : "bg-slate-800/50 hover:bg-slate-700/50 text-slate-300"
                  }`}
                >
                  All Notes
                </button>
                {subjects.map((subject, index) => (
                  <button
                    key={`${subject.id ?? "subject"}-${index}`}
                    onClick={() => {
                      setSelectedSubject(subject);
                      fetchNotes(subject.id);
                    }}
                    className={`w-full text-left p-3 rounded-lg transition-all ${
                      selectedSubject?.id === subject.id
                        ? "bg-cyan-500/20 border border-cyan-500/40 text-cyan-400"
                        : "bg-slate-800/50 hover:bg-slate-700/50 text-slate-300"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-medium">{subject.name}</span>
                      <span className="text-xs bg-slate-700 px-2 py-1 rounded">
                        {subject.notesCount || 0}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Notes Area */}
          <div className="lg:col-span-3">
            <div className="bg-slate-900/80 backdrop-blur-sm p-6 rounded-xl border border-purple-500/20 shadow-2xl">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-bold flex items-center">
                  <span className="mr-2">📁</span>
                  {selectedSubject ? selectedSubject.name : "All Notes"}
                </h2>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowGraph((s) => !s)}
                    className="bg-gradient-to-r from-green-400 to-teal-500 text-white px-3 py-2 rounded-lg hover:shadow-xl hover:shadow-green-400/30 transition-all duration-200 font-semibold text-sm"
                  >
                    {showGraph ? "Hide" : "View"} Knowledge Graph
                  </button>

                  {selectedSubject && (
                    <button
                      onClick={() => setShowUploadModal(true)}
                      className="bg-gradient-to-r from-purple-500 to-pink-500 text-white px-4 py-2 rounded-lg hover:shadow-xl hover:shadow-purple-500/30 transition-all duration-300 hover:scale-105 font-semibold text-sm"
                    >
                      + Upload File
                    </button>
                  )}
                </div>
              </div>

              {notes.length === 0 ? (
                <div className="text-center py-16">
                  <p className="text-slate-400 text-lg mb-4">📭 No notes yet</p>
                  <p className="text-slate-500 text-sm">
                    {selectedSubject
                      ? "Upload your first file to get started"
                      : "Select a subject or create one to begin"}
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {notes.map((note, index) => (
                    <div
                      key={`${note.id ?? "note"}-${index}`}
                      className="bg-gradient-to-br from-slate-800/80 to-slate-700/80 p-4 rounded-lg border border-purple-500/20 hover:border-purple-400/60 hover:shadow-lg hover:shadow-purple-500/10 transition-all duration-200"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex-1">
                          <p className="font-bold text-white text-sm mb-1 line-clamp-1">
                            {note.title}
                          </p>
                          <p className="text-xs text-slate-400">{note.fileType}</p>
                        </div>
                        <span className="text-2xl">
                          {note.fileType === "PDF" && "📄"}
                          {note.fileType === "DOCX" && "📝"}
                          {note.fileType === "TXT" && "📋"}
                          {!["PDF", "DOCX", "TXT"].includes(note.fileType) && "📎"}
                        </span>
                      </div>

                      {note.description && (
                        <p className="text-xs text-slate-400 mb-3 line-clamp-2">
                          {note.description}
                        </p>
                      )}

                      <div className="flex items-center justify-between text-xs text-slate-500 mb-3">
                        <span>{formatFileSize(note.fileSize)}</span>
                        <span>{formatDate(note.uploadedAt)}</span>
                      </div>

                      <div className="flex gap-2">
                        {canPreview(note.fileType) && (
                          <button
                            onClick={() => handlePreviewNote(note)}
                            className="flex-1 bg-blue-500/20 text-blue-400 py-2 rounded hover:bg-blue-500/30 transition-colors text-xs font-semibold"
                          >
                            👁️ View
                          </button>
                        )}
                        <button
                          onClick={() => handleDownloadNote(note.id)}
                          className="flex-1 bg-cyan-500/20 text-cyan-400 py-2 rounded hover:bg-cyan-500/30 transition-colors text-xs font-semibold"
                        >
                          ⬇️ Download
                        </button>
                        <button
                          onClick={() => handleDeleteNote(note.id)}
                          className="bg-red-500/20 text-red-400 px-3 py-2 rounded hover:bg-red-500/30 transition-colors text-xs font-semibold"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {showGraph && (
                <div className="mt-6">
                  {/* Lazy load KnowledgeGraph component to keep bundle small */}
                  {/* KnowledgeGraph component (client-side) */}
                  <KnowledgeGraph key={graphKey} />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Add Subject Modal */}
      {showSubjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="w-full max-w-md bg-slate-900 p-8 rounded-2xl shadow-2xl border border-cyan-500/20">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-2xl font-bold text-white">Add Subject</h3>
              <button
                onClick={() => setShowSubjectModal(false)}
                className="text-slate-400 hover:text-slate-200 text-xl"
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleCreateSubject} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">
                  Subject Name
                </label>
                <input
                  required
                  type="text"
                  value={subjectForm.name}
                  onChange={(e) =>
                    setSubjectForm({ ...subjectForm, name: e.target.value })
                  }
                  className="w-full bg-slate-800 border border-slate-700 text-white px-4 py-2 rounded-lg focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
                  placeholder="e.g., Data Structures"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">
                  Description (Optional)
                </label>
                <textarea
                  value={subjectForm.description}
                  onChange={(e) =>
                    setSubjectForm({ ...subjectForm, description: e.target.value })
                  }
                  className="w-full bg-slate-800 border border-slate-700 text-white px-4 py-2 rounded-lg focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20 resize-none"
                  rows={3}
                  placeholder="Brief description..."
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowSubjectModal(false)}
                  className="flex-1 bg-slate-800 text-slate-300 py-2 rounded-lg hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 bg-gradient-to-r from-cyan-500 to-blue-600 text-white py-2 rounded-lg hover:shadow-lg hover:shadow-cyan-500/30 transition-all"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Upload File Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div className="w-full max-w-md bg-slate-900 p-8 rounded-2xl shadow-2xl border border-purple-500/20">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-2xl font-bold text-white">Upload File</h3>
              <button
                onClick={() => setShowUploadModal(false)}
                className="text-slate-400 hover:text-slate-200 text-xl"
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleUploadFile} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">
                  File
                </label>
                <input
                  required
                  type="file"
                  onChange={(e) =>
                    setUploadForm({ ...uploadForm, file: e.target.files[0] })
                  }
                  className="w-full bg-slate-800 border border-slate-700 text-white px-4 py-2 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">
                  Title (Optional)
                </label>
                <input
                  type="text"
                  value={uploadForm.title}
                  onChange={(e) =>
                    setUploadForm({ ...uploadForm, title: e.target.value })
                  }
                  className="w-full bg-slate-800 border border-slate-700 text-white px-4 py-2 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20"
                  placeholder="Custom title..."
                />
              </div>
              <div>
                <label className="block text-sm font-bold text-slate-300 mb-2">
                  Description (Optional)
                </label>
                <textarea
                  value={uploadForm.description}
                  onChange={(e) =>
                    setUploadForm({ ...uploadForm, description: e.target.value })
                  }
                  className="w-full bg-slate-800 border border-slate-700 text-white px-4 py-2 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-500/20 resize-none"
                  rows={3}
                  placeholder="Notes about this file..."
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="flex-1 bg-slate-800 text-slate-300 py-2 rounded-lg hover:bg-slate-700 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 bg-gradient-to-r from-purple-500 to-pink-500 text-white py-2 rounded-lg hover:shadow-lg hover:shadow-purple-500/30 transition-all"
                >
                  Upload
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreviewModal && previewNote && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-6xl h-[90vh] bg-slate-900 rounded-2xl shadow-2xl border border-blue-500/20 flex flex-col">
            <div className="flex justify-between items-center p-6 border-b border-slate-700">
              <div>
                <h3 className="text-xl font-bold text-white">{previewNote.title}</h3>
                <p className="text-sm text-slate-400 mt-1">
                  {previewNote.fileType} • {formatFileSize(previewNote.fileSize)} • {formatDate(previewNote.uploadedAt)}
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => handleDownloadNote(previewNote.id)}
                  className="bg-cyan-500/20 text-cyan-400 px-4 py-2 rounded-lg hover:bg-cyan-500/30 transition-colors font-semibold"
                >
                  ⬇️ Download
                </button>
                <button
                  onClick={() => {
                    setShowPreviewModal(false);
                    setPreviewNote(null);
                  }}
                  className="text-slate-400 hover:text-slate-200 text-2xl px-3"
                >
                  ✕
                </button>
              </div>
            </div>
            
            <div className="flex-1 overflow-hidden p-6">
              {previewNote.fileType === "PDF" ? (
                <iframe
                  src={`${API_BASE}/api/notes/${previewNote.id}/preview`}
                  className="w-full h-full rounded-lg border border-slate-700"
                  title={previewNote.title}
                />
              ) : ["PNG", "JPG", "JPEG", "GIF", "SVG"].includes(previewNote.fileType?.toUpperCase()) ? (
                <div className="w-full h-full flex items-center justify-center bg-slate-800 rounded-lg">
                  <img
                    src={`${API_BASE}/api/notes/${previewNote.id}/preview`}
                    alt={previewNote.title}
                    className="max-w-full max-h-full object-contain"
                  />
                </div>
              ) : (
                <iframe
                  src={`${API_BASE}/api/notes/${previewNote.id}/preview`}
                  className="w-full h-full rounded-lg border border-slate-700 bg-white"
                  title={previewNote.title}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
