'use client'
import { useEffect, useState, useCallback } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'

function MasteryRing({ value, size = 64, label }) {
    const pct = Math.round((value || 0) * 100)
    const r = size / 2 - 6, circ = 2 * Math.PI * r, offset = circ * (1 - value)
    const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444'
    return (
        <div className="flex flex-col items-center">
            <svg width={size} height={size}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={4} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={4}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    transform={`rotate(-90 ${size / 2} ${size / 2})`} className="transition-all duration-700" />
                <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
                    fill="white" fontSize={size > 48 ? 14 : 10} fontWeight="bold">{pct}%</text>
            </svg>
            {label && <span className="text-slate-400 text-xs mt-1">{label}</span>}
        </div>
    )
}

function BloomBadge({ level }) {
    const colors = { remember: 'bg-slate-600', understand: 'bg-blue-600', apply: 'bg-cyan-600', analyze: 'bg-violet-600', evaluate: 'bg-amber-600', create: 'bg-emerald-600' }
    return <span className={`px-2 py-0.5 rounded text-xs text-white capitalize ${colors[level] || 'bg-slate-600'}`}>{level}</span>
}

export default function KnowledgeTracingPage() {
    const { data: session } = useSession()
    const [tab, setTab] = useState('overview')
    const [state, setState] = useState({ states: [], summary: {} })
    const [gaps, setGaps] = useState(null)
    const [dueReview, setDueReview] = useState([])
    const [quiz, setQuiz] = useState({ questions: [], active: false, current: 0, answers: {} })
    const [quizConcept, setQuizConcept] = useState('')
    const [loading, setLoading] = useState(true)
    const email = session?.user?.email || ''

    const fetchState = useCallback(async () => {
        try {
            setLoading(true)
            const r = await fetch(`${API}/api/knowledge-tracing/state?email=${encodeURIComponent(email)}`)
            setState(await r.json())
        } catch (e) { console.error(e) }
        finally { setLoading(false) }
    }, [email])

    useEffect(() => { fetchState() }, [fetchState])

    const fetchGaps = async () => {
        const r = await fetch(`${API}/api/knowledge-tracing/gaps?email=${encodeURIComponent(email)}`)
        setGaps(await r.json())
    }

    const fetchDueReview = async () => {
        const r = await fetch(`${API}/api/knowledge-tracing/due-review?email=${encodeURIComponent(email)}`)
        const d = await r.json()
        setDueReview(d.due_concepts || [])
    }

    const generateQuiz = async (concept) => {
        const fd = new FormData()
        fd.append('concept_name', concept)
        fd.append('num_questions', '5')
        fd.append('email', email)
        const r = await fetch(`${API}/api/quiz/generate`, { method: 'POST', body: fd })
        const d = await r.json()
        setQuiz({ questions: d.questions || [], active: true, current: 0, answers: {} })
        setQuizConcept(concept)
    }

    const submitAnswer = async (qIdx, answer) => {
        const q = quiz.questions[qIdx]
        const fd = new FormData()
        fd.append('question_id', q.id)
        fd.append('concept_name', q.concept_name || quizConcept)
        fd.append('student_answer', answer)
        fd.append('correct_answer', q.correct_answer || '')
        fd.append('bloom_level', q.bloom_level || 'understand')
        fd.append('email', email)
        const r = await fetch(`${API}/api/quiz/evaluate`, { method: 'POST', body: fd })
        const d = await r.json()
        setQuiz(prev => ({
            ...prev,
            answers: { ...prev.answers, [qIdx]: d },
        }))
    }

    const summary = state.summary || {}

    return (
        <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6">
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 left-1/2 w-[600px] h-[600px] bg-gradient-to-b from-blue-500/8 via-indigo-500/5 to-transparent rounded-full blur-3xl -translate-x-1/2" />
            </div>
            <div className="relative z-10 max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">📊 Knowledge Tracing</h1>
                        <p className="text-slate-400 mt-1">Track mastery, identify gaps, and optimize your learning</p>
                    </div>
                    <a href="/dashboard" className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition">← Dashboard</a>
                </div>

                {/* Summary Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    {[
                        { label: 'Total Concepts', value: summary.total_concepts || 0, icon: '📚' },
                        { label: 'Strong (≥80%)', value: summary.strong_concepts || 0, icon: '💪', color: 'text-emerald-400' },
                        { label: 'Weak (<50%)', value: summary.weak_concepts || 0, icon: '⚠️', color: 'text-red-400' },
                        { label: 'Mastered', value: `${summary.mastered_percentage || 0}%`, icon: '🏆', color: 'text-amber-400' },
                    ].map((c, i) => (
                        <div key={i} className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5 text-center">
                            <span className="text-2xl">{c.icon}</span>
                            <p className={`text-2xl font-bold mt-1 ${c.color || 'text-white'}`}>{c.value}</p>
                            <p className="text-slate-400 text-sm">{c.label}</p>
                        </div>
                    ))}
                </div>

                {/* Tabs */}
                <div className="flex gap-2 mb-6 flex-wrap">
                    {[
                        { id: 'overview', label: '📈 Overview' },
                        { id: 'gaps', label: '🔍 Gap Analysis', fn: fetchGaps },
                        { id: 'review', label: '🔁 Spaced Review', fn: fetchDueReview },
                        { id: 'quiz', label: '📝 Quiz' },
                    ].map(t => (
                        <button key={t.id} onClick={() => { setTab(t.id); t.fn?.() }}
                            className={`px-4 py-2 rounded-lg font-medium transition ${tab === t.id ? 'bg-gradient-to-r from-blue-500 to-indigo-500 text-white shadow-lg shadow-blue-500/25' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                            {t.label}
                        </button>
                    ))}
                </div>

                {loading ? (
                    <div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-400" /></div>
                ) : (
                    <>
                        {/* ── Overview ── */}
                        {tab === 'overview' && (
                            <div>
                                <div className="flex items-center gap-6 mb-6">
                                    <MasteryRing value={summary.overall_mastery || 0} size={100} label="Overall" />
                                    <div>
                                        <p className="text-white text-lg font-semibold">Overall Mastery</p>
                                        <p className="text-slate-400 text-sm">{summary.total_concepts} concepts tracked</p>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    {state.states.map(s => (
                                        <div key={s.concept_name} className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5 hover:border-blue-500/40 transition group">
                                            <div className="flex justify-between items-start mb-3">
                                                <div>
                                                    <h3 className="text-white font-semibold group-hover:text-blue-300 transition">{s.concept_name}</h3>
                                                    <div className="flex gap-2 mt-1">
                                                        <BloomBadge level={s.bloom_level_reached} />
                                                        {s.streak > 0 && <span className="text-xs text-amber-400">🔥 {s.streak} streak</span>}
                                                    </div>
                                                </div>
                                                <MasteryRing value={s.mastery} size={48} />
                                            </div>
                                            <div className="w-full bg-slate-700 rounded-full h-2 mb-2">
                                                <div className="h-2 rounded-full transition-all duration-500"
                                                    style={{ width: `${s.mastery * 100}%`, background: s.mastery >= 0.8 ? '#10b981' : s.mastery >= 0.5 ? '#f59e0b' : '#ef4444' }} />
                                            </div>
                                            <div className="grid grid-cols-3 gap-2 text-xs text-slate-400 mt-3">
                                                <span>Accuracy: {Math.round(s.accuracy * 100)}%</span>
                                                <span>α: {s.learning_rate?.toFixed(3)}</span>
                                                <span>λ: {s.forgetting_rate?.toFixed(3)}</span>
                                            </div>
                                            <button onClick={() => { generateQuiz(s.concept_name); setTab('quiz') }}
                                                className="mt-3 w-full text-center text-xs py-1.5 bg-blue-500/10 text-blue-300 rounded-lg hover:bg-blue-500/20 transition">📝 Quiz me</button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* ── Gap Analysis ── */}
                        {tab === 'gaps' && gaps && (
                            <div className="space-y-4">
                                <div className="bg-gradient-to-r from-orange-500/10 to-red-500/10 rounded-2xl border border-orange-500/30 p-6">
                                    <p className="text-slate-200">{gaps.message}</p>
                                </div>
                                {(gaps.gaps || []).map((g, i) => (
                                    <div key={i} className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5">
                                        <div className="flex justify-between items-start mb-3">
                                            <div>
                                                <h3 className="text-white font-semibold flex items-center gap-2">
                                                    {g.concept}
                                                    <span className={`text-xs px-2 py-0.5 rounded-full ${g.priority === 'high' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>{g.priority}</span>
                                                </h3>
                                                <p className="text-slate-400 text-sm mt-1">⏱ Est. {g.estimated_hours}h to mastery</p>
                                            </div>
                                            <MasteryRing value={g.current_mastery} size={48} />
                                        </div>
                                        {g.root_cause?.message && <p className="text-orange-200 text-sm bg-orange-500/10 rounded-lg p-3 mb-2">{g.root_cause.message}</p>}
                                        <p className="text-slate-300 text-sm">💡 {g.recommended_action}</p>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* ── Spaced Review ── */}
                        {tab === 'review' && (
                            <div className="space-y-4">
                                {dueReview.length > 0 ? dueReview.map((c, i) => (
                                    <div key={i} className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5 flex items-center justify-between">
                                        <div>
                                            <h3 className="text-white font-semibold">{c.concept}</h3>
                                            <p className="text-slate-400 text-sm">Stored: {Math.round(c.stored_mastery * 100)}% → Predicted: {Math.round(c.predicted_mastery * 100)}%</p>
                                            <p className="text-slate-500 text-xs">{c.hours_since_review}h since last review · Decayed {c.decay_percent}%</p>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <span className={`px-3 py-1 rounded-full text-xs ${c.urgency === 'high' ? 'bg-red-500/20 text-red-300' : 'bg-amber-500/20 text-amber-300'}`}>{c.urgency}</span>
                                            <button onClick={() => { generateQuiz(c.concept); setTab('quiz') }}
                                                className="px-3 py-1.5 bg-blue-500/20 text-blue-300 rounded-lg text-sm hover:bg-blue-500/30 transition">Review</button>
                                        </div>
                                    </div>
                                )) : <p className="text-slate-400 text-center py-12">✅ No concepts due for review right now!</p>}
                            </div>
                        )}

                        {/* ── Quiz ── */}
                        {tab === 'quiz' && (
                            <div>
                                {!quiz.active ? (
                                    <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-8 text-center">
                                        <span className="text-6xl mb-4 block">📝</span>
                                        <h3 className="text-xl font-bold text-white mb-2">Adaptive Quiz</h3>
                                        <p className="text-slate-400 mb-6">Select a concept from the Overview tab to start a quiz, or enter a topic below.</p>
                                        <div className="flex gap-3 max-w-md mx-auto">
                                            <input value={quizConcept} onChange={e => setQuizConcept(e.target.value)} placeholder="Enter concept name..."
                                                className="flex-1 bg-slate-900 border border-slate-600 rounded-xl px-4 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none" />
                                            <button onClick={() => generateQuiz(quizConcept)} disabled={!quizConcept.trim()}
                                                className="px-6 py-2 bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-xl disabled:opacity-50">Generate</button>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="space-y-4">
                                        <div className="flex items-center justify-between mb-2">
                                            <h3 className="text-white font-bold text-lg">Quiz: {quizConcept}</h3>
                                            <button onClick={() => setQuiz({ questions: [], active: false, current: 0, answers: {} })}
                                                className="text-slate-400 hover:text-white text-sm">✕ Close</button>
                                        </div>
                                        {quiz.questions.map((q, idx) => (
                                            <div key={q.id} className="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-5">
                                                <div className="flex justify-between items-center mb-3">
                                                    <p className="text-white font-medium">Q{idx + 1}. {q.question}</p>
                                                    <BloomBadge level={q.bloom_level} />
                                                </div>
                                                {q.options?.length > 0 ? (
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                                        {q.options.map((opt, oi) => {
                                                            const answered = quiz.answers[idx]
                                                            const letter = opt.charAt(0)
                                                            return (
                                                                <button key={oi} onClick={() => !answered && submitAnswer(idx, letter)}
                                                                    disabled={!!answered}
                                                                    className={`text-left px-4 py-2 rounded-lg border text-sm transition ${answered
                                                                        ? answered.is_correct && letter === answered.learner_state?.concept_name ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-600 bg-slate-700/50'
                                                                        : 'border-slate-600 hover:border-blue-400 hover:bg-blue-500/10 text-slate-200'}`}>
                                                                    {opt}
                                                                </button>
                                                            )
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="flex gap-2">
                                                        <input placeholder="Your answer..." id={`ans-${idx}`}
                                                            className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:border-blue-500 focus:outline-none" />
                                                        <button onClick={() => submitAnswer(idx, document.getElementById(`ans-${idx}`)?.value || '')}
                                                            disabled={!!quiz.answers[idx]}
                                                            className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm disabled:opacity-50">Submit</button>
                                                    </div>
                                                )}
                                                {quiz.answers[idx] && (
                                                    <div className={`mt-3 p-3 rounded-lg text-sm ${quiz.answers[idx].is_correct ? 'bg-emerald-500/10 text-emerald-300' : 'bg-red-500/10 text-red-300'}`}>
                                                        {quiz.answers[idx].feedback}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>
        </main>
    )
}
