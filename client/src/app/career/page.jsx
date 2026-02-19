'use client'
import { useEffect, useState, useRef, useCallback } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'
const APTITUDE_API = 'https://aptitude-gold.vercel.app/Random'
const TOTAL_QUESTIONS = 20
const TEST_DURATION = 20 * 60 // 20 minutes in seconds

function RadialGauge({ value, size = 120, label, color = '#06b6d4' }) {
    const pct = Math.round((value || 0) * 100)
    const r = size / 2 - 8, circ = 2 * Math.PI * r, offset = circ * (1 - value)
    return (
        <div className="flex flex-col items-center">
            <svg width={size} height={size}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e293b" strokeWidth={6} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={6}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
                    transform={`rotate(-90 ${size / 2} ${size / 2})`} className="transition-all duration-1000" />
                <text x="50%" y="46%" dominantBaseline="central" textAnchor="middle" fill="white" fontSize={size > 80 ? 22 : 14} fontWeight="bold">{pct}%</text>
                <text x="50%" y="62%" dominantBaseline="central" textAnchor="middle" fill="#94a3b8" fontSize={10}>ready</text>
            </svg>
            {label && <span className="text-slate-300 text-sm mt-1 font-medium">{label}</span>}
        </div>
    )
}

// ─── Timer Display ───
function TimerDisplay({ seconds }) {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    const urgent = seconds <= 120
    return (
        <div className={`flex items-center gap-2 px-4 py-2 rounded-xl font-mono text-lg font-bold border ${
            urgent
                ? 'bg-red-500/15 border-red-500/40 text-red-300 animate-pulse'
                : 'bg-slate-800/80 border-slate-600 text-cyan-300'
        }`}>
            ⏱️ {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
        </div>
    )
}

export default function CareerPage() {
    const { data: session } = useSession()
    const [tab, setTab] = useState('resume')

    // ── Resume state ──
    const [roles, setRoles] = useState([])
    const [selectedRole, setSelectedRole] = useState('software_engineer')
    const [loading, setLoading] = useState(false)
    const [resumeFile, setResumeFile] = useState(null)
    const [resumeResult, setResumeResult] = useState(null)
    const [resumeError, setResumeError] = useState(null)
    const email = session?.user?.email || ''

    // ── Aptitude Test state ──
    const [testPhase, setTestPhase] = useState('idle') // idle | loading | active | finished
    const [questions, setQuestions] = useState([])
    const [currentQ, setCurrentQ] = useState(0)
    const [answers, setAnswers] = useState({}) // { index: selectedOption }
    const [timeLeft, setTimeLeft] = useState(TEST_DURATION)
    const [testResult, setTestResult] = useState(null)
    const [fetchError, setFetchError] = useState(null)
    const timerRef = useRef(null)

    // ── Latest Trends state ──
    const [trendsLoading, setTrendsLoading] = useState(false)
    const [trendsData, setTrendsData] = useState(null)
    const [trendsError, setTrendsError] = useState(null)
    const [trendsFetched, setTrendsFetched] = useState(false)

    useEffect(() => {
        fetch(`${API}/api/career/roles`).then(r => r.json()).then(d => setRoles(d.roles || [])).catch(() => { })
    }, [])

    // ── Auto-fetch trends when switching to tab with resume data ──
    useEffect(() => {
        if (tab === 'trends' && !trendsFetched && resumeResult?.analysis) {
            fetchTrends()
        }
    }, [tab])

    // ── Timer effect ──
    useEffect(() => {
        if (testPhase === 'active' && timeLeft > 0) {
            timerRef.current = setInterval(() => {
                setTimeLeft(prev => {
                    if (prev <= 1) {
                        clearInterval(timerRef.current)
                        return 0
                    }
                    return prev - 1
                })
            }, 1000)
            return () => clearInterval(timerRef.current)
        }
        if (testPhase === 'active' && timeLeft === 0) {
            submitTest()
        }
    }, [testPhase, timeLeft === 0])

    // ── Resume handlers ──
    const analyzeResume = async () => {
        if (!resumeFile) return
        setLoading(true)
        setResumeError(null)
        setResumeResult(null)
        try {
            const fd = new FormData()
            fd.append('target_role', selectedRole)
            fd.append('email', email)
            fd.append('file', resumeFile)
            const url = `${API}/api/career/analyze-resume-pdf`
            const r = await fetch(url, { method: 'POST', body: fd })
            if (!r.ok) {
                const err = await r.json().catch(() => ({}))
                setResumeError(err.detail || `Server error (${r.status})`)
                return
            }
            const data = await r.json()
            if (data.status === 'error') {
                setResumeError(data.message || 'Analysis failed.')
            } else {
                setResumeResult(data)
            }
        } catch (e) {
            setResumeError('Could not reach the server. Make sure the backend is running.')
        } finally { setLoading(false) }
    }

    // ── Trends handler ──
    const fetchTrends = async () => {
        setTrendsLoading(true)
        setTrendsError(null)
        try {
            const skills = [
                ...(resumeResult?.analysis?.matched_skills || []),
                ...(resumeResult?.analysis?.missing_required || []).slice(0, 3),
            ]
            const fd = new FormData()
            skills.forEach(s => fd.append('skills', s))
            fd.append('role', selectedRole)
            const r = await fetch(`${API}/api/career/trends`, { method: 'POST', body: fd })
            if (!r.ok) {
                const err = await r.json().catch(() => ({}))
                setTrendsError(err.detail || `Server error (${r.status})`)
                return
            }
            const data = await r.json()
            setTrendsData(data)
            setTrendsFetched(true)
        } catch (e) {
            setTrendsError('Could not fetch trends. Make sure the backend is running.')
        } finally {
            setTrendsLoading(false)
        }
    }

    // ── Aptitude Test handlers ──
    const startTest = async () => {
        setTestPhase('loading')
        setFetchError(null)
        setAnswers({})
        setCurrentQ(0)
        setTestResult(null)
        setTimeLeft(TEST_DURATION)
        try {
            const fetches = Array.from({ length: TOTAL_QUESTIONS }, () =>
                fetch(APTITUDE_API).then(r => {
                    if (!r.ok) throw new Error(`API error ${r.status}`)
                    return r.json()
                })
            )
            const results = await Promise.all(fetches)
            // Deduplicate by question text, fetch more if needed
            const seen = new Set()
            const unique = []
            for (const q of results) {
                if (!seen.has(q.question)) {
                    seen.add(q.question)
                    unique.push(q)
                }
            }
            if (unique.length < TOTAL_QUESTIONS) {
                // fetch extras if duplicates removed some
                const extra = TOTAL_QUESTIONS - unique.length
                const moreFetches = Array.from({ length: extra + 5 }, () =>
                    fetch(APTITUDE_API).then(r => r.json()).catch(() => null)
                )
                const moreResults = await Promise.all(moreFetches)
                for (const q of moreResults) {
                    if (q && !seen.has(q.question)) {
                        seen.add(q.question)
                        unique.push(q)
                    }
                    if (unique.length >= TOTAL_QUESTIONS) break
                }
            }
            setQuestions(unique.slice(0, TOTAL_QUESTIONS))
            setTestPhase('active')
        } catch (e) {
            setFetchError('Failed to load questions. Check your internet connection and try again.')
            setTestPhase('idle')
        }
    }

    const selectAnswer = (qIndex, option) => {
        if (testPhase !== 'active') return
        setAnswers(prev => ({ ...prev, [qIndex]: option }))
    }

    const submitTest = useCallback(() => {
        clearInterval(timerRef.current)
        let correct = 0, incorrect = 0, skipped = 0
        const details = questions.map((q, i) => {
            const selected = answers[i]
            if (!selected) { skipped++; return { ...q, selected: null, isCorrect: false } }
            const isCorrect = selected === q.answer
            if (isCorrect) correct++; else incorrect++
            return { ...q, selected, isCorrect }
        })
        setTestResult({ correct, incorrect, skipped, total: questions.length, details, timeTaken: TEST_DURATION - timeLeft })
        setTestPhase('finished')
    }, [questions, answers, timeLeft])

    const resetTest = () => {
        setTestPhase('idle')
        setQuestions([])
        setAnswers({})
        setCurrentQ(0)
        setTestResult(null)
        setTimeLeft(TEST_DURATION)
        setFetchError(null)
    }

    const readinessColor = (p) => p >= 0.8 ? '#10b981' : p >= 0.6 ? '#06b6d4' : p >= 0.4 ? '#f59e0b' : '#ef4444'
    const scoreColor = (pct) => pct >= 80 ? 'text-emerald-400' : pct >= 60 ? 'text-cyan-400' : pct >= 40 ? 'text-amber-400' : 'text-red-400'

    return (
        <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-6">
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-0 right-1/4 w-[500px] h-[500px] bg-gradient-to-b from-cyan-500/8 via-blue-500/5 to-transparent rounded-full blur-3xl" />
                <div className="absolute bottom-0 left-1/4 w-[500px] h-[500px] bg-gradient-to-t from-emerald-500/8 via-green-500/5 to-transparent rounded-full blur-3xl" />
            </div>
            <div className="relative z-10 max-w-7xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h1 className="text-3xl font-bold text-white flex items-center gap-3">🚀 Career Readiness</h1>
                        <p className="text-slate-400 mt-1">AI Resume Analysis & Aptitude Testing</p>
                    </div>
                    <a href="/dashboard" className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition">← Dashboard</a>
                </div>

                {/* Tabs */}
                <div className="flex gap-2 mb-6">
                    {[
                        { id: 'resume', label: '📄 Resume Analysis' },
                        { id: 'aptitude', label: '🧠 Aptitude Test' },
                        { id: 'trends', label: '🔥 Latest Trends' },
                    ].map(t => (
                        <button key={t.id} onClick={() => setTab(t.id)}
                            className={`px-5 py-2.5 rounded-xl font-medium transition ${
                                tab === t.id
                                    ? 'bg-gradient-to-r from-cyan-500 to-emerald-500 text-white shadow-lg shadow-cyan-500/20'
                                    : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700'
                            }`}>
                            {t.label}
                        </button>
                    ))}
                </div>

                {/* ════════════════════ RESUME TAB ════════════════════ */}
                {tab === 'resume' && (
                    <>
                        {loading && <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-400" /></div>}
                        {!loading && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold mb-4">Upload Resume</h3>
                                    <div className="mb-4">
                                        <label className="text-slate-400 text-sm mb-1 block">Target Role</label>
                                        <select value={selectedRole} onChange={e => setSelectedRole(e.target.value)}
                                            className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:border-cyan-500 focus:outline-none">
                                            {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
                                        </select>
                                    </div>
                                    <label className="flex flex-col items-center justify-center w-full h-48 border-2 border-dashed border-slate-600 rounded-xl cursor-pointer hover:border-cyan-500 transition bg-slate-900/50">
                                        <span className="text-4xl mb-2">📎</span>
                                        {resumeFile ? (
                                            <>
                                                <span className="text-cyan-300 font-medium text-sm">{resumeFile.name}</span>
                                                <span className="text-slate-500 text-xs mt-1">{(resumeFile.size / 1024).toFixed(1)} KB — click to change</span>
                                            </>
                                        ) : (
                                            <>
                                                <span className="text-slate-300 text-sm font-medium">Click to upload PDF</span>
                                                <span className="text-slate-500 text-xs mt-1">Only .pdf files are supported</span>
                                            </>
                                        )}
                                        <input type="file" accept=".pdf" className="hidden"
                                            onChange={e => setResumeFile(e.target.files?.[0] || null)} />
                                    </label>
                                    <button onClick={analyzeResume} disabled={!resumeFile}
                                        className="mt-4 w-full py-3 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-semibold disabled:opacity-50 hover:shadow-lg transition">
                                        🔍 Analyze Resume
                                    </button>
                                </div>
                                <div>
                                    {resumeError && (
                                        <div className="bg-red-500/10 border border-red-500/40 rounded-2xl p-5 flex gap-3 items-start mb-4">
                                            <span className="text-2xl">❌</span>
                                            <div>
                                                <p className="text-red-300 font-semibold">Analysis Failed</p>
                                                <p className="text-red-400 text-sm mt-1">{resumeError}</p>
                                            </div>
                                        </div>
                                    )}
                                    {resumeResult?.analysis ? (
                                        <div className="space-y-4">
                                            <div className="bg-slate-800/60 rounded-2xl border border-emerald-500/40 p-6 text-center relative overflow-hidden">
                                                <div className="absolute top-3 right-3 bg-emerald-500/20 text-emerald-300 text-xs font-semibold px-2 py-1 rounded-full border border-emerald-500/30">✓ Analysis complete</div>
                                                <RadialGauge value={(resumeResult.analysis.overall_match_percentage || 0) / 100} size={120}
                                                    label={resumeResult.target_role} color={readinessColor((resumeResult.analysis.overall_match_percentage || 0) / 100)} />
                                                {resumeResult.extracted_chars && (
                                                    <p className="text-slate-500 text-xs mt-2">{resumeResult.extracted_chars.toLocaleString()} characters extracted from PDF</p>
                                                )}
                                            </div>
                                            {resumeResult.analysis.strengths?.length > 0 && (
                                                <div className="bg-emerald-500/10 rounded-xl border border-emerald-500/30 p-4">
                                                    <h4 className="text-emerald-300 font-semibold mb-2">✅ Strengths</h4>
                                                    {resumeResult.analysis.strengths.map((s, i) => <p key={i} className="text-slate-200 text-sm">• {s}</p>)}
                                                </div>
                                            )}
                                            {resumeResult.analysis.improvements?.length > 0 && (
                                                <div className="bg-amber-500/10 rounded-xl border border-amber-500/30 p-4">
                                                    <h4 className="text-amber-300 font-semibold mb-2">📈 Improvements</h4>
                                                    {resumeResult.analysis.improvements.map((s, i) => <p key={i} className="text-slate-200 text-sm">• {s}</p>)}
                                                </div>
                                            )}
                                            {resumeResult.analysis.interview_tips?.length > 0 && (
                                                <div className="bg-blue-500/10 rounded-xl border border-blue-500/30 p-4">
                                                    <h4 className="text-blue-300 font-semibold mb-2">💡 Interview Tips</h4>
                                                    {resumeResult.analysis.interview_tips.map((s, i) => <p key={i} className="text-slate-200 text-sm">• {s}</p>)}
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="bg-slate-800/60 rounded-2xl border border-slate-700/50 p-12 text-center h-full flex flex-col items-center justify-center">
                                            <span className="text-6xl mb-4">📄</span>
                                            <p className="text-slate-400">Upload your PDF resume and select a target role to get AI-powered analysis</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </>
                )}

                {/* ════════════════════ APTITUDE TEST TAB ════════════════════ */}
                {tab === 'aptitude' && (
                    <>
                        {/* ── Idle: Start screen ── */}
                        {testPhase === 'idle' && (
                            <div className="max-w-2xl mx-auto">
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-8 text-center">
                                    <span className="text-7xl block mb-5">🧠</span>
                                    <h2 className="text-2xl font-bold text-white mb-3">Aptitude Test</h2>
                                    <p className="text-slate-400 mb-6 leading-relaxed">
                                        Challenge yourself with <span className="text-cyan-300 font-semibold">{TOTAL_QUESTIONS} random aptitude questions</span> covering
                                        logical reasoning, quantitative analysis, and verbal ability.
                                        You have <span className="text-amber-300 font-semibold">20 minutes</span> to complete the test.
                                    </p>
                                    <div className="grid grid-cols-3 gap-4 mb-8">
                                        <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/50">
                                            <p className="text-2xl font-bold text-cyan-400">{TOTAL_QUESTIONS}</p>
                                            <p className="text-slate-500 text-xs mt-1">Questions</p>
                                        </div>
                                        <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/50">
                                            <p className="text-2xl font-bold text-amber-400">20:00</p>
                                            <p className="text-slate-500 text-xs mt-1">Time Limit</p>
                                        </div>
                                        <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-700/50">
                                            <p className="text-2xl font-bold text-emerald-400">4</p>
                                            <p className="text-slate-500 text-xs mt-1">Options Each</p>
                                        </div>
                                    </div>
                                    {fetchError && (
                                        <div className="bg-red-500/10 border border-red-500/40 rounded-xl p-4 mb-4 text-red-300 text-sm">
                                            ❌ {fetchError}
                                        </div>
                                    )}
                                    <button onClick={startTest}
                                        className="px-8 py-3.5 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-bold text-lg hover:shadow-lg hover:shadow-cyan-500/25 transition transform hover:scale-[1.02]">
                                        🚀 Start Test
                                    </button>
                                </div>
                            </div>
                        )}

                        {/* ── Loading questions ── */}
                        {testPhase === 'loading' && (
                            <div className="flex flex-col items-center justify-center py-20">
                                <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-400 mb-6" />
                                <p className="text-slate-300 text-lg font-medium">Loading {TOTAL_QUESTIONS} questions...</p>
                                <p className="text-slate-500 text-sm mt-1">Fetching from aptitude API</p>
                            </div>
                        )}

                        {/* ── Active: Test in progress ── */}
                        {testPhase === 'active' && questions.length > 0 && (
                            <div className="max-w-4xl mx-auto">
                                {/* Top bar: Timer + Progress */}
                                <div className="flex items-center justify-between mb-5">
                                    <div className="flex items-center gap-3">
                                        <span className="text-slate-400 text-sm font-medium">
                                            Question <span className="text-white font-bold">{currentQ + 1}</span> / {questions.length}
                                        </span>
                                        <div className="w-48 bg-slate-700 rounded-full h-2">
                                            <div className="h-2 rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-300"
                                                style={{ width: `${((currentQ + 1) / questions.length) * 100}%` }} />
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-3">
                                        <span className="text-slate-500 text-xs">
                                            {Object.keys(answers).length}/{questions.length} answered
                                        </span>
                                        <TimerDisplay seconds={timeLeft} />
                                    </div>
                                </div>

                                {/* Question Card */}
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-8 mb-5">
                                    <p className="text-white text-lg font-medium leading-relaxed mb-6">
                                        <span className="text-cyan-400 font-bold mr-2">Q{currentQ + 1}.</span>
                                        {questions[currentQ].question}
                                    </p>
                                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                        {questions[currentQ].options.map((opt, i) => {
                                            const isSelected = answers[currentQ] === opt
                                            return (
                                                <button key={i} onClick={() => selectAnswer(currentQ, opt)}
                                                    className={`text-left px-5 py-4 rounded-xl border-2 transition-all duration-200 ${
                                                        isSelected
                                                            ? 'border-cyan-500 bg-cyan-500/15 text-white shadow-lg shadow-cyan-500/10'
                                                            : 'border-slate-600 bg-slate-900/50 text-slate-300 hover:border-slate-500 hover:bg-slate-800'
                                                    }`}>
                                                    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold mr-3 ${
                                                        isSelected ? 'bg-cyan-500 text-white' : 'bg-slate-700 text-slate-400'
                                                    }`}>
                                                        {String.fromCharCode(65 + i)}
                                                    </span>
                                                    {opt}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>

                                {/* Navigation + Question Grid */}
                                <div className="flex flex-col sm:flex-row gap-4">
                                    {/* Nav buttons */}
                                    <div className="flex gap-3 flex-1">
                                        <button onClick={() => setCurrentQ(p => Math.max(0, p - 1))} disabled={currentQ === 0}
                                            className="px-5 py-2.5 bg-slate-800 text-slate-300 rounded-xl hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed transition font-medium">
                                            ← Previous
                                        </button>
                                        {currentQ < questions.length - 1 ? (
                                            <button onClick={() => setCurrentQ(p => Math.min(questions.length - 1, p + 1))}
                                                className="px-5 py-2.5 bg-slate-800 text-slate-300 rounded-xl hover:bg-slate-700 transition font-medium">
                                                Next →
                                            </button>
                                        ) : (
                                            <button onClick={submitTest}
                                                className="px-6 py-2.5 bg-gradient-to-r from-emerald-500 to-green-500 text-white rounded-xl font-bold hover:shadow-lg hover:shadow-emerald-500/25 transition">
                                                ✅ Submit Test
                                            </button>
                                        )}
                                    </div>
                                    {/* Submit anytime */}
                                    {currentQ < questions.length - 1 && (
                                        <button onClick={submitTest}
                                            className="px-5 py-2.5 bg-red-500/20 text-red-300 border border-red-500/30 rounded-xl hover:bg-red-500/30 transition text-sm font-medium">
                                            End Test Early
                                        </button>
                                    )}
                                </div>

                                {/* Question number grid */}
                                <div className="mt-5 bg-slate-800/40 rounded-2xl border border-slate-700/50 p-4">
                                    <p className="text-slate-500 text-xs mb-3 font-medium uppercase tracking-wide">Question Navigator</p>
                                    <div className="flex flex-wrap gap-2">
                                        {questions.map((_, i) => {
                                            const isActive = currentQ === i
                                            const isAnswered = answers[i] !== undefined
                                            return (
                                                <button key={i} onClick={() => setCurrentQ(i)}
                                                    className={`w-9 h-9 rounded-lg text-sm font-bold transition-all ${
                                                        isActive
                                                            ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/30 scale-110'
                                                            : isAnswered
                                                                ? 'bg-emerald-500/25 text-emerald-300 border border-emerald-500/30'
                                                                : 'bg-slate-700/50 text-slate-400 hover:bg-slate-600'
                                                    }`}>
                                                    {i + 1}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* ── Finished: Results ── */}
                        {testPhase === 'finished' && testResult && (
                            <div className="max-w-4xl mx-auto">
                                {/* Score Summary */}
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-8 mb-6">
                                    <div className="text-center mb-6">
                                        <span className="text-6xl block mb-3">
                                            {testResult.correct / testResult.total >= 0.8 ? '🏆' : testResult.correct / testResult.total >= 0.5 ? '👍' : '📚'}
                                        </span>
                                        <h2 className="text-2xl font-bold text-white">Test Complete!</h2>
                                        <p className="text-slate-400 mt-1">
                                            Time taken: {Math.floor(testResult.timeTaken / 60)}m {testResult.timeTaken % 60}s
                                        </p>
                                    </div>
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                                        <div className="bg-slate-900/60 rounded-xl p-4 text-center border border-slate-700/50">
                                            <p className={`text-3xl font-bold ${scoreColor(Math.round(testResult.correct / testResult.total * 100))}`}>
                                                {Math.round(testResult.correct / testResult.total * 100)}%
                                            </p>
                                            <p className="text-slate-500 text-xs mt-1">Score</p>
                                        </div>
                                        <div className="bg-slate-900/60 rounded-xl p-4 text-center border border-emerald-500/20">
                                            <p className="text-3xl font-bold text-emerald-400">{testResult.correct}</p>
                                            <p className="text-slate-500 text-xs mt-1">Correct</p>
                                        </div>
                                        <div className="bg-slate-900/60 rounded-xl p-4 text-center border border-red-500/20">
                                            <p className="text-3xl font-bold text-red-400">{testResult.incorrect}</p>
                                            <p className="text-slate-500 text-xs mt-1">Incorrect</p>
                                        </div>
                                        <div className="bg-slate-900/60 rounded-xl p-4 text-center border border-slate-600/50">
                                            <p className="text-3xl font-bold text-slate-400">{testResult.skipped}</p>
                                            <p className="text-slate-500 text-xs mt-1">Skipped</p>
                                        </div>
                                    </div>
                                    <div className="flex justify-center gap-3">
                                        <button onClick={resetTest}
                                            className="px-6 py-3 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-bold hover:shadow-lg transition">
                                            🔄 Retake Test
                                        </button>
                                        <button onClick={() => setTab('resume')}
                                            className="px-6 py-3 bg-slate-700 text-slate-300 rounded-xl font-medium hover:bg-slate-600 transition">
                                            📄 Back to Resume
                                        </button>
                                    </div>
                                </div>

                                {/* Detailed Review */}
                                <div className="bg-slate-800/40 rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold mb-4 text-lg">📋 Detailed Review</h3>
                                    <div className="space-y-4">
                                        {testResult.details.map((q, i) => {
                                            const wasSkipped = !q.selected
                                            return (
                                                <div key={i} className={`rounded-xl border p-5 ${
                                                    wasSkipped
                                                        ? 'bg-slate-800/40 border-slate-600/50'
                                                        : q.isCorrect
                                                            ? 'bg-emerald-500/5 border-emerald-500/30'
                                                            : 'bg-red-500/5 border-red-500/30'
                                                }`}>
                                                    <div className="flex items-start gap-3 mb-3">
                                                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold flex-shrink-0 ${
                                                            wasSkipped
                                                                ? 'bg-slate-700 text-slate-400'
                                                                : q.isCorrect
                                                                    ? 'bg-emerald-500/20 text-emerald-300'
                                                                    : 'bg-red-500/20 text-red-300'
                                                        }`}>
                                                            {wasSkipped ? '–' : q.isCorrect ? '✓' : '✗'}
                                                        </span>
                                                        <p className="text-white text-sm font-medium leading-relaxed">{q.question}</p>
                                                    </div>
                                                    <div className="ml-11 space-y-1.5">
                                                        {wasSkipped ? (
                                                            <p className="text-slate-500 text-sm italic">Skipped</p>
                                                        ) : !q.isCorrect && (
                                                            <p className="text-red-400 text-sm">
                                                                Your answer: <span className="font-medium">{q.selected}</span>
                                                            </p>
                                                        )}
                                                        <p className="text-emerald-400 text-sm">
                                                            Correct answer: <span className="font-medium">{q.answer}</span>
                                                        </p>
                                                        {q.explanation && (
                                                            <p className="text-slate-400 text-xs mt-2 leading-relaxed bg-slate-900/50 rounded-lg px-3 py-2">
                                                                💡 {q.explanation}
                                                            </p>
                                                        )}
                                                    </div>
                                                </div>
                                            )
                                        })}
                                    </div>
                                </div>
                            </div>
                        )}
                    </>
                )}

                {/* ════════════════════ LATEST TRENDS TAB ════════════════════ */}
                {tab === 'trends' && (
                    <>
                        {/* Prompt to upload resume first if no data */}
                        {!resumeResult?.analysis && !trendsData && (
                            <div className="max-w-2xl mx-auto">
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-8 text-center">
                                    <span className="text-7xl block mb-5">🔍</span>
                                    <h2 className="text-2xl font-bold text-white mb-3">Latest Trends & Resources</h2>
                                    <p className="text-slate-400 mb-6 leading-relaxed">
                                        Upload and analyze your resume first to get <span className="text-cyan-300 font-semibold">personalized trends</span> based on your skills and target role.
                                        We&apos;ll search for the latest news, blogs, videos, and interview tips tailored to your profile.
                                    </p>
                                    <button onClick={() => setTab('resume')}
                                        className="px-6 py-3 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-bold hover:shadow-lg transition">
                                        📄 Go to Resume Analysis
                                    </button>
                                    <div className="mt-4 border-t border-slate-700 pt-4">
                                        <p className="text-slate-500 text-sm mb-3">Or fetch general trends for your selected role:</p>
                                        <button onClick={fetchTrends} disabled={trendsLoading}
                                            className="px-5 py-2.5 bg-slate-700 text-slate-300 rounded-xl font-medium hover:bg-slate-600 disabled:opacity-50 transition">
                                            {trendsLoading ? '⏳ Searching...' : '🔥 Fetch Trends Without Resume'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Loading state */}
                        {trendsLoading && (
                            <div className="flex flex-col items-center justify-center py-20">
                                <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-cyan-400 mb-6" />
                                <p className="text-slate-300 text-lg font-medium">Searching latest trends...</p>
                                <p className="text-slate-500 text-sm mt-1">Fetching news, articles & videos via Brave Search</p>
                            </div>
                        )}

                        {/* Error */}
                        {trendsError && (
                            <div className="max-w-2xl mx-auto bg-red-500/10 border border-red-500/40 rounded-2xl p-5 flex gap-3 items-start mb-4">
                                <span className="text-2xl">❌</span>
                                <div>
                                    <p className="text-red-300 font-semibold">Failed to Fetch Trends</p>
                                    <p className="text-red-400 text-sm mt-1">{trendsError}</p>
                                </div>
                            </div>
                        )}

                        {/* Trends results */}
                        {!trendsLoading && trendsData && (
                            <div className="space-y-6">
                                {/* Header bar */}
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h2 className="text-xl font-bold text-white flex items-center gap-2">
                                            🔥 Trends for <span className="text-cyan-300">{trendsData.role}</span>
                                        </h2>
                                        {trendsData.skills_searched?.length > 0 && (
                                            <div className="flex flex-wrap gap-1.5 mt-2">
                                                {trendsData.skills_searched.map((s, i) => (
                                                    <span key={i} className="px-2 py-0.5 bg-cyan-500/15 text-cyan-300 text-xs rounded-full border border-cyan-500/30">{s}</span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                    <button onClick={() => { setTrendsFetched(false); fetchTrends() }}
                                        className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition text-sm font-medium">
                                        🔄 Refresh
                                    </button>
                                </div>

                                {/* Skill News Section */}
                                {trendsData.sections?.skill_news?.length > 0 && (
                                    <div>
                                        <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                            <span className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center text-sm">📰</span>
                                            Latest News in Your Domain
                                        </h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                            {trendsData.sections.skill_news.map((item, i) => (
                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                    className="group bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-blue-500/40 transition-all hover:shadow-lg hover:shadow-blue-500/5">
                                                    {item.thumbnail && (
                                                        <img src={item.thumbnail} alt="" className="w-full h-32 object-cover rounded-lg mb-3 opacity-80 group-hover:opacity-100 transition" />
                                                    )}
                                                    <h4 className="text-white text-sm font-semibold line-clamp-2 group-hover:text-blue-300 transition">{item.title}</h4>
                                                    <p className="text-slate-400 text-xs mt-2 line-clamp-2">{item.description}</p>
                                                    <div className="flex items-center justify-between mt-3">
                                                        <span className="text-blue-400 text-xs font-medium px-2 py-0.5 bg-blue-500/10 rounded-full">News</span>
                                                        {item.age && <span className="text-slate-500 text-xs">{item.age}</span>}
                                                    </div>
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Career Articles Section */}
                                {trendsData.sections?.career_articles?.length > 0 && (
                                    <div>
                                        <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                            <span className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center text-sm">📚</span>
                                            Career &amp; Technology Articles
                                        </h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                            {trendsData.sections.career_articles.map((item, i) => (
                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                    className="group bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-emerald-500/40 transition-all hover:shadow-lg hover:shadow-emerald-500/5">
                                                    {item.thumbnail && (
                                                        <img src={item.thumbnail} alt="" className="w-full h-32 object-cover rounded-lg mb-3 opacity-80 group-hover:opacity-100 transition" />
                                                    )}
                                                    <h4 className="text-white text-sm font-semibold line-clamp-2 group-hover:text-emerald-300 transition">{item.title}</h4>
                                                    <p className="text-slate-400 text-xs mt-2 line-clamp-2">{item.description}</p>
                                                    <div className="flex items-center justify-between mt-3">
                                                        <span className="text-emerald-400 text-xs font-medium px-2 py-0.5 bg-emerald-500/10 rounded-full">Article</span>
                                                        {item.age && <span className="text-slate-500 text-xs">{item.age}</span>}
                                                    </div>
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Interview Tips Section */}
                                {trendsData.sections?.interview_tips?.length > 0 && (
                                    <div>
                                        <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                            <span className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center text-sm">💡</span>
                                            Interview Tips &amp; Preparation
                                        </h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                            {trendsData.sections.interview_tips.map((item, i) => (
                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                    className="group bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-amber-500/40 transition-all hover:shadow-lg hover:shadow-amber-500/5">
                                                    {item.thumbnail && (
                                                        <img src={item.thumbnail} alt="" className="w-full h-32 object-cover rounded-lg mb-3 opacity-80 group-hover:opacity-100 transition" />
                                                    )}
                                                    <h4 className="text-white text-sm font-semibold line-clamp-2 group-hover:text-amber-300 transition">{item.title}</h4>
                                                    <p className="text-slate-400 text-xs mt-2 line-clamp-2">{item.description}</p>
                                                    <div className="flex items-center justify-between mt-3">
                                                        <span className="text-amber-400 text-xs font-medium px-2 py-0.5 bg-amber-500/10 rounded-full">Interview Tip</span>
                                                        {item.age && <span className="text-slate-500 text-xs">{item.age}</span>}
                                                    </div>
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Videos Section */}
                                {trendsData.sections?.videos?.length > 0 && (
                                    <div>
                                        <h3 className="text-white font-bold mb-3 flex items-center gap-2">
                                            <span className="w-8 h-8 rounded-lg bg-red-500/20 flex items-center justify-center text-sm">🎥</span>
                                            Videos &amp; Tutorials
                                        </h3>
                                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                            {trendsData.sections.videos.map((item, i) => (
                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                    className="group bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-700/50 p-4 hover:border-red-500/40 transition-all hover:shadow-lg hover:shadow-red-500/5">
                                                    <div className="relative">
                                                        {item.thumbnail ? (
                                                            <img src={item.thumbnail} alt="" className="w-full h-36 object-cover rounded-lg mb-3 opacity-80 group-hover:opacity-100 transition" />
                                                        ) : (
                                                            <div className="w-full h-36 bg-slate-700/50 rounded-lg mb-3 flex items-center justify-center">
                                                                <span className="text-4xl">▶️</span>
                                                            </div>
                                                        )}
                                                        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                                                            <span className="w-12 h-12 bg-red-500/80 rounded-full flex items-center justify-center text-white text-xl shadow-lg">▶</span>
                                                        </div>
                                                    </div>
                                                    <h4 className="text-white text-sm font-semibold line-clamp-2 group-hover:text-red-300 transition">{item.title}</h4>
                                                    <p className="text-slate-400 text-xs mt-2 line-clamp-2">{item.description}</p>
                                                    <div className="flex items-center justify-between mt-3">
                                                        <span className="text-red-400 text-xs font-medium px-2 py-0.5 bg-red-500/10 rounded-full">Video</span>
                                                        {item.age && <span className="text-slate-500 text-xs">{item.age}</span>}
                                                    </div>
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Empty state */}
                                {!trendsData.sections?.skill_news?.length && !trendsData.sections?.career_articles?.length && !trendsData.sections?.interview_tips?.length && !trendsData.sections?.videos?.length && (
                                    <div className="bg-slate-800/60 rounded-2xl border border-slate-700/50 p-12 text-center">
                                        <span className="text-6xl mb-4 block">🤷</span>
                                        <p className="text-slate-400">No results found. Try analyzing your resume first for personalized results.</p>
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
