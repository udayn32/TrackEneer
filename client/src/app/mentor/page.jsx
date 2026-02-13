'use client'
import { useState, useRef, useEffect } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'

const MODES = [
    { id: 'socratic', icon: '🤔', label: 'Socratic', desc: 'Guide through questions' },
    { id: 'explain', icon: '📖', label: 'Explain', desc: 'Detailed explanation' },
    { id: 'quiz', icon: '📝', label: 'Quiz', desc: 'Test your knowledge' },
    { id: 'connect', icon: '🔗', label: 'Connect', desc: 'Relate concepts' },
    { id: 'plan', icon: '📋', label: 'Plan', desc: 'Study plan' },
]

function MarkdownLite({ text }) {
    if (!text) return null
    const lines = text.split('\n')
    return (
        <div className="space-y-1 text-slate-200 text-sm leading-relaxed">
            {lines.map((line, i) => {
                if (line.startsWith('## ')) return <h3 key={i} className="text-lg font-bold text-white mt-3">{line.slice(3)}</h3>
                if (line.startsWith('### ')) return <h4 key={i} className="text-base font-semibold text-cyan-300 mt-2">{line.slice(4)}</h4>
                if (line.startsWith('**') && line.endsWith('**')) return <p key={i} className="font-bold text-white">{line.slice(2, -2)}</p>
                if (line.startsWith('- ')) return <p key={i} className="pl-4 before:content-['•'] before:mr-2 before:text-cyan-400">{line.slice(2)}</p>
                if (line.startsWith('> ')) return <blockquote key={i} className="border-l-2 border-cyan-500 pl-3 italic text-slate-300">{line.slice(2)}</blockquote>
                if (line.trim() === '') return <div key={i} className="h-2" />
                const formatted = line
                    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>')
                    .replace(/\*(.+?)\*/g, '<em>$1</em>')
                    .replace(/`(.+?)`/g, '<code class="bg-slate-700 px-1 rounded text-cyan-300 text-xs">$1</code>')
                return <p key={i} dangerouslySetInnerHTML={{ __html: formatted }} />
            })}
        </div>
    )
}

export default function MentorPage() {
    const { data: session } = useSession()
    const [messages, setMessages] = useState([])
    const [input, setInput] = useState('')
    const [mode, setMode] = useState('socratic')
    const [sessionId, setSessionId] = useState('')
    const [loading, setLoading] = useState(false)
    const [recommendations, setRecs] = useState(null)
    const [showRecs, setShowRecs] = useState(false)
    const scrollRef = useRef(null)
    const email = session?.user?.email || ''

    useEffect(() => { scrollRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

    const sendMessage = async () => {
        if (!input.trim() || loading) return
        const userMsg = { role: 'user', content: input, ts: Date.now() }
        setMessages(prev => [...prev, userMsg])
        setInput('')
        setLoading(true)
        try {
            const fd = new FormData()
            fd.append('message', input)
            fd.append('mode', mode)
            fd.append('session_id', sessionId)
            fd.append('email', email)
            const r = await fetch(`${API}/api/mentor/chat`, { method: 'POST', body: fd })
            const d = await r.json()
            if (d.session_id) setSessionId(d.session_id)
            setMessages(prev => [...prev, {
                role: 'mentor', content: d.answer || 'No response', ts: Date.now(),
                citations: d.citations, confidence: d.confidence, mode: d.mode,
                discussed: d.discussed_concepts, prerequisites: d.prerequisites,
            }])
        } catch (e) {
            setMessages(prev => [...prev, { role: 'mentor', content: '⚠️ Failed to get response. Please try again.', ts: Date.now() }])
        }
        finally { setLoading(false) }
    }

    const fetchRecs = async () => {
        try {
            const r = await fetch(`${API}/api/mentor/recommendations?email=${encodeURIComponent(email)}`)
            setRecs(await r.json())
            setShowRecs(true)
        } catch (e) { console.error(e) }
    }

    const clearChat = () => { setMessages([]); setSessionId('') }

    return (
        <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex flex-col">
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-gradient-to-bl from-emerald-500/8 via-cyan-500/5 to-transparent rounded-full blur-3xl" />
                <div className="absolute bottom-0 left-0 w-[500px] h-[500px] bg-gradient-to-tr from-violet-500/8 via-purple-500/5 to-transparent rounded-full blur-3xl" />
            </div>

            {/* Header */}
            <header className="relative z-10 border-b border-slate-700/50 bg-slate-900/80 backdrop-blur-md px-6 py-4">
                <div className="max-w-5xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <span className="text-3xl">🎓</span>
                        <div>
                            <h1 className="text-xl font-bold text-white">AI Study Mentor</h1>
                            <p className="text-slate-400 text-xs">Socratic tutoring powered by your Knowledge Graph</p>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={fetchRecs} className="px-3 py-1.5 bg-emerald-500/20 text-emerald-300 rounded-lg text-sm hover:bg-emerald-500/30 transition">💡 Recommendations</button>
                        <button onClick={clearChat} className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg text-sm hover:bg-slate-600 transition">🗑️ Clear</button>
                        <a href="/dashboard" className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg text-sm hover:bg-slate-600 transition">← Back</a>
                    </div>
                </div>
            </header>

            {/* Mode Selector */}
            <div className="relative z-10 border-b border-slate-700/50 bg-slate-900/40 px-6 py-2">
                <div className="max-w-5xl mx-auto flex gap-2 overflow-x-auto">
                    {MODES.map(m => (
                        <button key={m.id} onClick={() => setMode(m.id)}
                            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm whitespace-nowrap transition ${mode === m.id ? 'bg-gradient-to-r from-cyan-500 to-blue-500 text-white shadow-lg shadow-cyan-500/20' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                            <span>{m.icon}</span><span className="font-medium">{m.label}</span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 overflow-y-auto px-6 py-4 relative z-10">
                <div className="max-w-5xl mx-auto space-y-4">
                    {messages.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-[50vh] text-center">
                            <span className="text-7xl mb-4">🎓</span>
                            <h2 className="text-2xl font-bold text-white mb-2">Welcome to your AI Study Mentor</h2>
                            <p className="text-slate-400 max-w-md">Ask me anything about your courses. I'll use your Knowledge Graph to provide grounded, contextual answers.</p>
                            <div className="flex gap-3 mt-6 flex-wrap justify-center">
                                {['Explain recursion', 'Quiz me on data structures', 'Create a study plan', 'How does SQL relate to databases?'].map(q => (
                                    <button key={q} onClick={() => { setInput(q); setTimeout(sendMessage, 100) }}
                                        className="px-4 py-2 bg-slate-800 border border-slate-600 rounded-full text-sm text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 transition">{q}</button>
                                ))}
                            </div>
                        </div>
                    )}

                    {messages.map((msg, i) => (
                        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[80%] rounded-2xl px-5 py-3 ${msg.role === 'user'
                                ? 'bg-gradient-to-r from-cyan-500 to-blue-500 text-white'
                                : 'bg-slate-800/80 backdrop-blur-sm border border-slate-700/50'}`}>
                                {msg.role === 'mentor' && msg.mode && (
                                    <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-700/50">
                                        <span className="text-xs text-slate-400">Mode: {MODES.find(m => m.id === msg.mode)?.label || msg.mode}</span>
                                        {msg.confidence != null && (
                                            <span className={`text-xs px-2 py-0.5 rounded-full ${msg.confidence > 0.6 ? 'bg-emerald-500/20 text-emerald-300' : msg.confidence > 0.3 ? 'bg-amber-500/20 text-amber-300' : 'bg-red-500/20 text-red-300'}`}>
                                                {Math.round(msg.confidence * 100)}% confidence
                                            </span>
                                        )}
                                    </div>
                                )}
                                {msg.role === 'user' ? <p className="text-sm">{msg.content}</p> : <MarkdownLite text={msg.content} />}
                                {msg.citations?.length > 0 && (
                                    <div className="mt-3 pt-2 border-t border-slate-700/50">
                                        <p className="text-xs text-slate-500 mb-1">📎 Sources:</p>
                                        {msg.citations.map((c, j) => (
                                            <span key={j} className="inline-block text-xs bg-slate-700/50 text-slate-300 px-2 py-0.5 rounded mr-1 mb-1">{c.source}</span>
                                        ))}
                                    </div>
                                )}
                                {msg.discussed?.length > 0 && (
                                    <div className="mt-2 flex flex-wrap gap-1">
                                        {msg.discussed.map((c, j) => (
                                            <span key={j} className="text-xs bg-cyan-500/10 text-cyan-300 px-2 py-0.5 rounded-full">{c}</span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}

                    {loading && (
                        <div className="flex justify-start">
                            <div className="bg-slate-800/80 rounded-2xl px-5 py-3 border border-slate-700/50">
                                <div className="flex gap-1"><span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" /><span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} /><span className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} /></div>
                            </div>
                        </div>
                    )}
                    <div ref={scrollRef} />
                </div>
            </div>

            {/* Input Bar */}
            <div className="relative z-10 border-t border-slate-700/50 bg-slate-900/80 backdrop-blur-md px-6 py-4">
                <div className="max-w-5xl mx-auto flex gap-3">
                    <input value={input} onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && sendMessage()}
                        placeholder={`Ask your ${MODES.find(m => m.id === mode)?.label || ''} mentor...`}
                        className="flex-1 bg-slate-800 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none" />
                    <button onClick={sendMessage} disabled={loading || !input.trim()}
                        className="px-6 py-3 bg-gradient-to-r from-cyan-500 to-blue-500 text-white rounded-xl font-semibold disabled:opacity-50 hover:shadow-lg hover:shadow-cyan-500/25 transition">
                        {loading ? '...' : '🚀 Send'}
                    </button>
                </div>
            </div>

            {/* Recommendations Modal */}
            {showRecs && recommendations && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-6" onClick={() => setShowRecs(false)}>
                    <div className="bg-slate-800 rounded-2xl border border-slate-600 p-8 max-w-lg w-full shadow-2xl max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xl font-bold text-white">💡 Study Recommendations</h2>
                            <button onClick={() => setShowRecs(false)} className="text-slate-400 hover:text-white">✕</button>
                        </div>
                        <p className="text-slate-300 mb-4">{recommendations.message}</p>
                        <div className="space-y-3">
                            {(recommendations.recommendations || []).map((r, i) => (
                                <div key={i} className="bg-slate-700/50 rounded-lg p-4">
                                    <div className="flex justify-between items-center mb-1">
                                        <p className="text-white font-medium">{r.concept}</p>
                                        <span className={`text-xs px-2 py-0.5 rounded-full ${r.priority === 'high' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>{r.priority}</span>
                                    </div>
                                    <div className="w-full bg-slate-600 rounded-full h-2 mb-2">
                                        <div className="bg-gradient-to-r from-cyan-400 to-blue-500 h-2 rounded-full transition-all" style={{ width: `${(r.current_mastery || 0) * 100}%` }} />
                                    </div>
                                    <p className="text-slate-400 text-xs">{r.action}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </main>
    )
}
