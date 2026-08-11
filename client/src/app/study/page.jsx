'use client'
import { useEffect, useState, useRef, useCallback } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_STUDY_API?.replace(/\/$/, '') || process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'

const DIFF_COLORS = { easy: '#10b981', medium: '#f59e0b', hard: '#ef4444' }
const REL_COLORS = { PREREQUISITE_OF: '#f97316', PART_OF: '#8b5cf6', RELATED_TO: '#06b6d4', LEADS_TO: '#22c55e' }
const CAT_COLORS = {
    topic: '#3b82f6', subtopic: '#8b5cf6', skill: '#06b6d4', theorem: '#f59e0b',
    algorithm: '#ef4444', definition: '#10b981', formula: '#ec4899', default: '#64748b'
}

function MasteryBadge({ v }) {
    const pct = Math.round((v || 0) * 100)
    const color = pct >= 80 ? 'from-emerald-500 to-green-400' : pct >= 50 ? 'from-amber-500 to-yellow-400' : 'from-red-500 to-rose-400'
    return <span className={`px-3 py-1 rounded-full text-xs font-bold bg-gradient-to-r ${color} text-white shadow-lg shadow-${color.split('-')[1]}-500/30`}>{pct}%</span>
}

// Enhanced concept card for preview
function ConceptCard({ node, index }) {
    const getWeightPercentage = () => node.weight ? Math.round(node.weight * 100) : 0
    const getDifficultyEmoji = () => {
        const diffMap = { easy: '🟢', medium: '🟡', hard: '🔴' }
        return diffMap[node.difficulty] || '🔵'
    }
    
    return (
        <div className="group bg-gradient-to-br from-slate-700/60 via-slate-800/40 to-slate-900/50 rounded-xl p-4 border border-slate-600/40 hover:border-cyan-500/60 transition-all duration-300 hover:shadow-lg hover:shadow-cyan-500/20 hover:-translate-y-1 cursor-pointer">
            <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                        <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-cyan-500/20 text-cyan-300 group-hover:bg-cyan-500/30">#{index + 1}</span>
                        <div className="w-1 h-1 rounded-full bg-gradient-to-r from-cyan-400 to-blue-400 group-hover:shadow-lg group-hover:shadow-cyan-500/50"></div>
                    </div>
                    <h4 className="text-sm font-semibold text-white line-clamp-2 group-hover:text-cyan-100 transition">{node.name}</h4>
                </div>
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
                <span className="px-2 py-0.5 rounded-lg text-xs font-medium bg-slate-700/60 text-slate-300 inline-flex items-center gap-1" style={{ borderLeft: `3px solid ${DIFF_COLORS[node.difficulty] || '#3b82f6'}` }}>
                    {getDifficultyEmoji()} {node.difficulty}
                </span>
                <span className="px-2 py-0.5 rounded-lg text-xs font-medium text-slate-300 bg-gradient-to-r from-purple-500/20 to-blue-500/20">{node.category || 'topic'}</span>
            </div>
            {node.weight && (
                <div className="relative h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                    <div className="absolute top-0 left-0 h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all duration-500" style={{width: `${getWeightPercentage()}%`}}></div>
                </div>
            )}
            <p className="text-xs text-slate-400 mt-2">{getWeightPercentage()}% relevance</p>
        </div>
    )
}

/* ================================================================
   STUDY PAGE - INTEGRATED NOTES UPLOAD + CONCEPT PREVIEW
================================================================ */
export default function StudyPage() {
    const { data: session } = useSession()
    const [uploadFile, setUploadFile] = useState(null)
    const [uploading, setUploading] = useState(false)
    const [buildText, setBuildText] = useState('')
    const [building, setBuilding] = useState(false)
    const [recentConcepts, setRecentConcepts] = useState([])
    const [successMessage, setSuccessMessage] = useState('')
    const [documents, setDocuments] = useState([])
    const [showNotesViewer, setShowNotesViewer] = useState(false)
    const [notes, setNotes] = useState([])
    const [selectedNote, setSelectedNote] = useState(null)
    const [notesLoading, setNotesLoading] = useState(false)
    const [fileOperationStatus, setFileOperationStatus] = useState(null) // Track download/preview status
    const email = session?.user?.email || ''
    const MAX_CONCEPTS = 15

    // Fetch documents and update recent concepts
    const fetchDocuments = useCallback(async () => {
        if (!email) return
        try {
            const r = await fetch(`${API}/api/knowledge-graph/documents?email=${encodeURIComponent(email)}`)
            if (!r.ok) throw new Error('Failed to fetch docs')
            const d = await r.json()
            setDocuments(d.documents || [])

            // Get concepts from the most recent document
            if (d.documents && d.documents.length > 0) {
                const latestDoc = d.documents[0].document
                const graphRes = await fetch(`${API}/api/knowledge-graph?email=${encodeURIComponent(email)}&source_document=${encodeURIComponent(latestDoc)}`)
                const graphData = await graphRes.json()
                const sorted = (graphData.nodes || [])
                    .sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
                    .slice(0, MAX_CONCEPTS)
                setRecentConcepts(sorted)
            }
        } catch (e) {
            console.error("fetchDocuments error:", e)
            setDocuments([])
        }
    }, [email])

    // Fetch user's notes
    const fetchNotes = useCallback(async () => {
        if (!email) return
        setNotesLoading(true)
        try {
            const r = await fetch(`${API}/api/notes/recent?limit=20&email=${encodeURIComponent(email)}`)
            if (!r.ok) throw new Error('Failed to fetch notes')
            const d = await r.json()
            setNotes(d.notes || [])
        } catch (e) {
            console.error("fetchNotes error:", e)
            setNotes([])
        } finally {
            setNotesLoading(false)
        }
    }, [email])

    useEffect(() => { fetchDocuments() }, [fetchDocuments])
    useEffect(() => { fetchNotes() }, [fetchNotes])

    const handleUpload = async () => {
        if (!uploadFile) return
        setUploading(true)
        setSuccessMessage('')
        try {
            const fd = new FormData()
            fd.append('file', uploadFile)
            fd.append('email', email)
            const uploadRes = await fetch(`${API}/api/notes/upload-simple`, { method: 'POST', body: fd })
            const result = await uploadRes.json()
            
            if (!uploadRes.ok) {
                throw new Error(result.detail || 'Upload failed')
            }

            setSuccessMessage(`✅ File uploaded successfully! "${uploadFile.name}" is now in your Study Notes.`)
            setTimeout(() => {
                fetchNotes()
                setSuccessMessage('')
            }, 2000)
            setUploadFile(null)
        } catch (e) {
            console.error(e)
            setSuccessMessage(`❌ Upload failed: ${e.message}`)
        }
        finally { setUploading(false) }
    }

    const handleBuildText = async () => {
        if (!buildText.trim()) return
        setBuilding(true)
        setSuccessMessage('')
        try {
            const fd = new FormData()
            fd.append('text', buildText)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            const buildRes = await fetch(`${API}/api/knowledge-graph/build`, { method: 'POST', body: fd })
            await buildRes.json().catch(() => ({}))

            setSuccessMessage('✅ Concepts extracted! Refreshing preview...')
            setTimeout(() => {
                fetchDocuments()
                setSuccessMessage('')
            }, 2000)
            setBuildText('')
        } catch (e) {
            console.error(e)
            setSuccessMessage('❌ Extraction failed. Please try again.')
        }
        finally { setBuilding(false) }
    }

    return (
        <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6 relative overflow-hidden">
            {/* Animated background elements */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 left-0 w-[500px] h-[500px] bg-gradient-to-br from-violet-500/10 via-purple-500/5 to-transparent rounded-full blur-3xl animate-pulse" />
                <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-gradient-to-tl from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl animate-pulse animation-delay-2000" />
                <div className="absolute top-1/2 left-1/3 w-[400px] h-[400px] bg-gradient-to-tr from-blue-500/8 via-cyan-500/5 to-transparent rounded-full blur-3xl animate-pulse animation-delay-4000" />
            </div>

            <div className="relative z-10 max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-8 animate-fade-in">
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h1 className="text-5xl font-bold text-white flex items-center gap-3 mb-1">
                                <span className="text-6xl">📚</span>
                                <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">Smart Study Hub</span>
                            </h1>
                            <p className="text-slate-300 text-lg max-w-2xl">Transform your notes into interactive knowledge graphs with AI-powered concept extraction</p>
                        </div>
                        <div className="flex gap-3 flex-wrap justify-end">
                            <button onClick={() => setShowNotesViewer(true)} className="px-5 py-2.5 bg-orange-500/80 hover:bg-orange-600/80 text-white rounded-lg hover:shadow-lg hover:shadow-orange-500/30 transition-all duration-300 flex items-center gap-2 font-medium border border-orange-600/50">
                                📖 Notes ({notes.length})
                            </button>
                            <a href="/knowledge-tracing" className="px-5 py-2.5 bg-gradient-to-r from-rose-500 to-red-500 hover:from-rose-600 hover:to-red-600 text-white rounded-lg hover:shadow-xl hover:shadow-rose-500/30 transition-all duration-300 flex items-center gap-2 font-medium">
                                Mastery Tracker
                            </a>
                            <a href="/dashboard" className="px-5 py-2.5 bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 rounded-lg hover:shadow-lg transition-all duration-300 flex items-center gap-2 font-medium border border-slate-700/50">
                                ← Dashboard
                            </a>
                            <a href="/knowledge-graph" className="px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 text-white rounded-lg hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 flex items-center gap-2 font-medium">
                                View Graph →
                            </a>
                        </div>
                    </div>
                </div>

                {/* Success Message */}
                {successMessage && (
                    <div className="mb-6 p-5 bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10 border border-cyan-500/50 rounded-xl text-cyan-200 animate-in slide-in-from-top-2 duration-300 flex items-center gap-3 shadow-lg shadow-cyan-500/10">
                        <span className="text-xl flex-shrink-0">✨</span>
                        <span className="font-medium">{successMessage}</span>
                    </div>
                )}

                {/* Main Grid */}
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mb-8">
                    {/* Left: Upload Section */}
                    <div className="space-y-6 animate-fade-in animation-delay-100">
                        {/* Upload File Card */}
                        <div className="group bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-slate-900/60 backdrop-blur-xl rounded-2xl border border-slate-700/50 hover:border-cyan-500/40 p-8 transition-all duration-300 hover:shadow-xl hover:shadow-cyan-500/10 hover:-translate-y-1">
                            <div className="flex items-center gap-3 mb-3">
                                <span className="text-3xl">📄</span>
                                <h2 className="text-2xl font-bold text-white">Upload Notes</h2>
                            </div>
                            <p className="text-slate-400 text-sm mb-6">PDF, DOCX, or TXT files — Perfect for lectures, textbooks, and notes</p>

                            <label className="block border-3 border-dashed border-slate-600 group-hover:border-cyan-500/50 rounded-xl p-8 text-center cursor-pointer hover:bg-slate-800/50 transition-all duration-300 relative overflow-hidden">
                                <input type="file" accept=".pdf,.txt,.docx" className="hidden" onChange={e => setUploadFile(e.target.files?.[0] || null)} />
                                <div className="relative z-10">
                                    <span className="text-6xl block mb-3 group-hover:scale-110 transition-transform duration-300 inline-block">📁</span>
                                    <span className="text-slate-300 font-semibold text-lg block">{uploadFile ? uploadFile.name : 'Click to upload or drag & drop'}</span>
                                    <p className="text-xs text-slate-500 mt-2">PDF, DOCX, or TXT — Max 50MB</p>
                                </div>
                            </label>

                            <button onClick={handleUpload} disabled={!uploadFile || uploading}
                                className="mt-6 w-full py-4 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 text-white rounded-xl font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 transform hover:scale-105 disabled:hover:scale-100 active:scale-95">
                                {uploading ? (
                                    <span className="flex items-center justify-center gap-3">
                                        <span className="animate-spin rounded-full h-5 w-5 border-3 border-white border-t-transparent"></span>
                                        <span>Processing…</span>
                                    </span>
                                ) : '🚀 Upload & Extract'}
                            </button>
                        </div>

                        {/* Text Input Card */}
                        <div className="group bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-slate-900/60 backdrop-blur-xl rounded-2xl border border-slate-700/50 hover:border-purple-500/40 p-8 transition-all duration-300 hover:shadow-xl hover:shadow-purple-500/10 hover:-translate-y-1">
                            <div className="flex items-center gap-3 mb-3">
                                <span className="text-3xl">✍️</span>
                                <h2 className="text-2xl font-bold text-white">Or Paste Text</h2>
                            </div>
                            <p className="text-slate-400 text-sm mb-4">Paste lecture notes, syllabus, or any educational content directly</p>

                            <textarea value={buildText} onChange={e => setBuildText(e.target.value)} rows={6}
                                placeholder="Paste your content here to instantly build a knowledge graph..."
                                className="w-full bg-slate-900/50 border border-slate-600 hover:border-purple-500/30 focus:border-purple-500/60 rounded-xl p-4 text-slate-200 placeholder-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500/20 transition-all duration-300 font-medium" />

                            <button onClick={handleBuildText} disabled={!buildText.trim() || building}
                                className="mt-4 w-full py-4 bg-gradient-to-r from-violet-500 to-purple-500 hover:from-violet-600 hover:to-purple-600 text-white rounded-xl font-semibold disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-xl hover:shadow-purple-500/30 transition-all duration-300 transform hover:scale-105 disabled:hover:scale-100 active:scale-95">
                                {building ? (
                                    <span className="flex items-center justify-center gap-3">
                                        <span className="animate-spin rounded-full h-5 w-5 border-3 border-white border-t-transparent"></span>
                                        <span>Extracting…</span>
                                    </span>
                                ) : '🧠 Extract Concepts'}
                            </button>
                        </div>
                    </div>

                    {/* Right: Concept Preview Section */}
                    <div className="group bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-slate-900/60 backdrop-blur-xl rounded-2xl border border-slate-700/50 hover:border-blue-500/40 p-8 transition-all duration-300 hover:shadow-xl hover:shadow-blue-500/10 animate-fade-in animation-delay-200 flex flex-col">
                        <div className="flex items-center justify-between mb-6 pb-6 border-b border-slate-700/50">
                            <div>
                                <h2 className="text-2xl font-bold text-white flex items-center gap-2 mb-1">
                                    <span>🧠</span>
                                    Top Concepts
                                </h2>
                                <p className="text-slate-400 text-sm">{recentConcepts.length} of {documents.length > 0 ? documents[0].concept_count : 0} extracted</p>
                            </div>
                            {recentConcepts.length > 0 && (
                                <div className="text-right bg-gradient-to-br from-cyan-500/20 to-blue-500/20 rounded-lg px-4 py-3 border border-cyan-500/30">
                                    <p className="text-3xl font-bold bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">{recentConcepts.length}</p>
                                    <p className="text-xs text-slate-400 font-medium">shown</p>
                                </div>
                            )}
                        </div>

                        {recentConcepts.length > 0 ? (
                            <>
                                {/* Concept Cards Grid */}
                                <div className="grid grid-cols-2 gap-4 mb-6 flex-1 max-h-[600px] overflow-y-auto pr-2 custom-scrollbar">
                                    {recentConcepts.map((node, idx) => (
                                        <ConceptCard key={node.id || node.name} node={node} index={idx} />
                                    ))}
                                </div>

                                {/* Stats */}
                                <div className="grid grid-cols-2 gap-4 pt-6 border-t border-slate-700">
                                    <div className="bg-gradient-to-br from-emerald-500/10 to-emerald-600/5 rounded-lg p-4 border border-emerald-500/20">
                                        <p className="text-xs text-slate-400 font-medium mb-1">Avg. Difficulty</p>
                                        <div className="flex items-end gap-2">
                                            <p className="text-2xl font-bold text-emerald-400">
                                                {recentConcepts.length > 0
                                                    ? (recentConcepts.reduce((a, b) => a + (['easy', 'medium', 'hard'].indexOf(b.difficulty) || 1), 0) / recentConcepts.length).toFixed(1)
                                                    : 'N/A'}
                                            </p>
                                            <p className="text-xs text-slate-500">/2</p>
                                        </div>
                                    </div>
                                    <div className="bg-gradient-to-br from-cyan-500/10 to-blue-600/5 rounded-lg p-4 border border-cyan-500/20">
                                        <p className="text-xs text-slate-400 font-medium mb-1">Coverage</p>
                                        <p className="text-2xl font-bold text-cyan-400">
                                            {documents.length > 0 ? Math.round((recentConcepts.length / (documents[0].concept_count || 1)) * 100) : 0}%
                                        </p>
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                                <span className="text-7xl mb-4 opacity-50">📊</span>
                                <p className="text-lg font-semibold text-slate-300 mb-2">No concepts extracted yet</p>
                                <p className="text-sm text-slate-500">Upload a document or paste text to start building your knowledge graph</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Recent Documents Section */}
                {documents.length > 1 && (
                    <div className="group bg-gradient-to-br from-slate-800/60 via-slate-800/50 to-slate-900/50 backdrop-blur-xl rounded-2xl border border-slate-700/50 hover:border-slate-600/80 p-8 transition-all duration-300 hover:shadow-xl hover:shadow-slate-900/20 animate-fade-in animation-delay-300">
                        <h3 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
                            <span>📚</span>
                            Recent Uploads
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {documents.slice(0, 6).map((doc, idx) => (
                                <div key={idx} className="group/doc bg-gradient-to-br from-slate-700/40 to-slate-800/40 rounded-lg p-5 border border-slate-600/30 hover:border-slate-500/60 transition-all duration-300 hover:shadow-lg hover:bg-slate-700/50 cursor-pointer hover:-translate-y-0.5">
                                    <p className="font-semibold text-white text-sm truncate mb-2 group-hover/doc:text-cyan-300 transition">{doc.document}</p>
                                    <div className="flex items-center justify-between">
                                        <p className="text-xs text-slate-400">{doc.concept_count} concepts</p>
                                        <span className="text-xs px-2 py-1 rounded bg-slate-700/50 text-slate-300">📖</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Notes Viewer Modal */}
                {showNotesViewer && (
                    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-end transition-all duration-300 animate-in">
                        <div className="w-full h-[85vh] bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 border-t border-slate-700/50 rounded-t-3xl shadow-2xl animate-in slide-in-from-bottom-5 duration-300 flex flex-col overflow-hidden">
                            {/* Notes Header */}
                            <div className="bg-gradient-to-r from-slate-800/80 to-slate-900/80 backdrop-blur-xl p-6 border-b border-slate-700/50 flex items-center justify-between">
                                <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                                    <span>📖</span>
                                    Your Study Notes
                                </h2>
                                <button onClick={() => setShowNotesViewer(false)} className="text-slate-400 hover:text-white transition text-2xl">✕</button>
                            </div>

                            {/* Notes Content */}
                            <div className="flex-1 overflow-hidden flex">
                                {/* Notes List */}
                                <div className="w-80 border-r border-slate-700/50 overflow-y-auto custom-scrollbar bg-slate-900/30">
                                    {notesLoading ? (
                                        <div className="flex items-center justify-center h-full">
                                            <div className="animate-spin rounded-full h-8 w-8 border-2 border-cyan-400 border-t-transparent"></div>
                                        </div>
                                    ) : notes.length === 0 ? (
                                        <div className="flex flex-col items-center justify-center h-full text-slate-400 p-4">
                                            <span className="text-5xl mb-3">📝</span>
                                            <p className="text-center">No notes yet. Upload documents to get started!</p>
                                        </div>
                                    ) : (
                                        <div className="p-4 space-y-3">
                                            {notes.map((note, idx) => (
                                                <button key={idx} onClick={() => setSelectedNote(note)} className={`w-full text-left p-4 rounded-lg border transition-all duration-200 group/note ${selectedNote?.id === note.id ? 'bg-gradient-to-r from-cyan-500/20 to-blue-500/20 border-cyan-500/50 shadow-lg shadow-cyan-500/10' : 'bg-slate-700/30 border-slate-600/30 hover:border-slate-500/50 hover:bg-slate-700/40'}`}>
                                                    <p className="font-semibold text-white text-sm truncate group-hover/note:text-cyan-300 transition">{note.title || note.filename}</p>
                                                    <p className="text-xs text-slate-400 mt-1">{new Date(note.uploadedAt).toLocaleDateString()}</p>
                                                    <p className="text-xs text-slate-500 mt-1">{Math.round(note.fileSize / 1024)} KB</p>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Note Preview */}
                                <div className="flex-1 overflow-y-auto custom-scrollbar bg-slate-800/20 p-6">
                                    {selectedNote ? (
                                        <div className="animate-fade-in">
                                            <div className="bg-gradient-to-br from-slate-800/50 to-slate-900/50 rounded-xl border border-slate-700/50 p-6 mb-4">
                                                <h3 className="text-2xl font-bold text-white mb-2">{selectedNote.title || selectedNote.filename}</h3>
                                                <div className="flex flex-wrap gap-3 text-sm text-slate-400">
                                                    <span className="flex items-center gap-1">📅 {new Date(selectedNote.uploadedAt).toLocaleDateString()}</span>
                                                    <span className="flex items-center gap-1">💾 {Math.round(selectedNote.fileSize / 1024)} KB</span>
                                                    <span className="flex items-center gap-1">📄 {selectedNote.fileType}</span>
                                                </div>
                                                {selectedNote.description && (
                                                    <p className="text-slate-300 mt-3">{selectedNote.description}</p>
                                                )}
                                            </div>
                                            <div className="flex gap-3">
                                                <button onClick={async () => {
                                                    setFileOperationStatus({ type: 'download', status: 'loading' });
                                                    try {
                                                        const response = await fetch(`${API}/api/notes/${selectedNote.id}/download?email=${encodeURIComponent(email)}`);
                                                        if (!response.ok) {
                                                            const error = await response.json().catch(() => ({ detail: 'Download failed' }));
                                                            setFileOperationStatus({ type: 'download', status: 'error', message: error.detail });
                                                            return;
                                                        }
                                                        const blob = await response.blob();
                                                        const url = window.URL.createObjectURL(blob);
                                                        const a = document.createElement('a');
                                                        a.href = url;
                                                        a.download = selectedNote.filename || 'note';
                                                        document.body.appendChild(a);
                                                        a.click();
                                                        window.URL.revokeObjectURL(url);
                                                        document.body.removeChild(a);
                                                        setFileOperationStatus({ type: 'download', status: 'success' });
                                                        setTimeout(() => setFileOperationStatus(null), 2000);
                                                    } catch (e) {
                                                        setFileOperationStatus({ type: 'download', status: 'error', message: e.message });
                                                    }
                                                }} disabled={fileOperationStatus?.type === 'download' && fileOperationStatus?.status === 'loading'} className="flex-1 py-3 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-semibold transition-all duration-300 flex items-center justify-center gap-2 hover:shadow-lg hover:shadow-cyan-500/30">
                                                    {fileOperationStatus?.type === 'download' && fileOperationStatus?.status === 'loading' ? (
                                                        <><span className="animate-spin text-lg">⏳</span> Downloading...</>
                                                    ) : fileOperationStatus?.type === 'download' && fileOperationStatus?.status === 'success' ? (
                                                        <><span className="text-xl">✅</span> Downloaded</>
                                                    ) : (
                                                        <><span className="text-lg">⬇️</span> Download</>
                                                    )}
                                                </button>
                                                <button onClick={async () => {
                                                    setFileOperationStatus({ type: 'preview', status: 'loading' });
                                                    try {
                                                        const response = await fetch(`${API}/api/notes/${selectedNote.id}/preview?email=${encodeURIComponent(email)}`);
                                                        if (!response.ok) {
                                                            const error = await response.json().catch(() => ({ detail: 'Preview failed' }));
                                                            setFileOperationStatus({ type: 'preview', status: 'error', message: error.detail });
                                                            return;
                                                        }
                                                        const blob = await response.blob();
                                                        const url = window.URL.createObjectURL(blob);
                                                        window.open(url, '_blank');
                                                        setFileOperationStatus({ type: 'preview', status: 'success' });
                                                        setTimeout(() => setFileOperationStatus(null), 2000);
                                                    } catch (e) {
                                                        setFileOperationStatus({ type: 'preview', status: 'error', message: e.message });
                                                    }
                                                }} disabled={fileOperationStatus?.type === 'preview' && fileOperationStatus?.status === 'loading'} className="flex-1 py-3 bg-slate-700/50 hover:bg-slate-700/70 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-semibold transition-all duration-300 flex items-center justify-center gap-2 border border-slate-600/50">
                                                    {fileOperationStatus?.type === 'preview' && fileOperationStatus?.status === 'loading' ? (
                                                        <><span className="animate-spin text-lg">⏳</span> Opening...</>
                                                    ) : fileOperationStatus?.type === 'preview' && fileOperationStatus?.status === 'success' ? (
                                                        <><span className="text-xl">✅</span> Opened</>
                                                    ) : (
                                                        <><span className="text-lg">👁️</span> Preview</>
                                                    )}
                                                </button>
                                            </div>
                                            {/* Error message display */}
                                            {fileOperationStatus?.status === 'error' && (
                                                <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                                                    <p className="text-red-300 text-sm"><span className="font-bold">Error:</span> {fileOperationStatus.message}</p>
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="flex flex-col items-center justify-center h-full text-slate-400">
                                            <span className="text-6xl mb-3 opacity-50">👈</span>
                                            <p className="text-lg">Select a note to view details</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>

            <style jsx>{`
                .custom-scrollbar::-webkit-scrollbar {
                    width: 6px;
                }
                .custom-scrollbar::-webkit-scrollbar-track {
                    background: rgba(51, 65, 85, 0.2);
                    border-radius: 10px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb {
                    background: rgba(139, 92, 246, 0.6);
                    border-radius: 10px;
                }
                .custom-scrollbar::-webkit-scrollbar-thumb:hover {
                    background: rgba(139, 92, 246, 0.8);
                }
                
                @keyframes fade-in {
                    from {
                        opacity: 0;
                        transform: translateY(10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
                
                @keyframes slide-in-from-top {
                    from {
                        opacity: 0;
                        transform: translateY(-10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }
                
                .animate-fade-in {
                    animation: fade-in 0.6s ease-out forwards;
                    opacity: 0;
                }
                
                .animation-delay-100 {
                    animation-delay: 0.1s;
                }
                
                .animation-delay-200 {
                    animation-delay: 0.2s;
                }
                
                .animation-delay-300 {
                    animation-delay: 0.3s;
                }
                
                .animation-delay-2000 {
                    animation-delay: 2s;
                }
                
                .animation-delay-4000 {
                    animation-delay: 4s;
                }
            `}</style>
        </main>
    )
}
