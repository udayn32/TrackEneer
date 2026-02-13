'use client'
import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'

const API = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') || 'http://localhost:5000'

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

function SkillBar({ skill, readiness, domain, category }) {
    const pct = Math.round((readiness || 0) * 100)
    const barColor = pct >= 70 ? 'from-emerald-500 to-green-400' : pct >= 40 ? 'from-amber-500 to-yellow-400' : 'from-red-500 to-rose-400'
    return (
        <div className="flex items-center gap-3 group">
            <span className="w-36 text-sm text-slate-300 truncate group-hover:text-white transition">{skill}</span>
            <div className="flex-1 bg-slate-700 rounded-full h-2.5">
                <div className={`h-2.5 rounded-full bg-gradient-to-r ${barColor} transition-all duration-700`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs text-slate-400 w-10 text-right">{pct}%</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${category === 'technical' ? 'bg-blue-500/20 text-blue-300' : 'bg-violet-500/20 text-violet-300'}`}>{category}</span>
        </div>
    )
}

export default function CareerPage() {
    const { data: session } = useSession()
    const [tab, setTab] = useState('readiness')
    const [roles, setRoles] = useState([])
    const [selectedRole, setSelectedRole] = useState('software_engineer')
    const [prediction, setPrediction] = useState(null)
    const [skillProfile, setSkillProfile] = useState(null)
    const [loading, setLoading] = useState(false)
    const [form, setForm] = useState({ cgpa: 7.0, internship: 0, projects: 0, practice: 0 })
    const [resumeText, setResumeText] = useState('')
    const [resumeResult, setResumeResult] = useState(null)
    const email = session?.user?.email || ''

    useEffect(() => {
        fetch(`${API}/api/career/roles`).then(r => r.json()).then(d => setRoles(d.roles || [])).catch(() => { })
    }, [])

    const fetchProfile = async () => {
        setLoading(true)
        try {
            const r = await fetch(`${API}/api/career/skill-profile?email=${encodeURIComponent(email)}`)
            setSkillProfile(await r.json())
        } catch (e) { console.error(e) }
        finally { setLoading(false) }
    }

    const predict = async () => {
        setLoading(true)
        try {
            const fd = new FormData()
            fd.append('target_role', selectedRole)
            fd.append('cgpa', form.cgpa)
            fd.append('internship_months', form.internship)
            fd.append('projects_count', form.projects)
            fd.append('practice_score', form.practice)
            fd.append('email', email)
            const r = await fetch(`${API}/api/career/predict-readiness`, { method: 'POST', body: fd })
            setPrediction(await r.json())
        } catch (e) { console.error(e) }
        finally { setLoading(false) }
    }

    const analyzeResume = async () => {
        if (!resumeText.trim()) return
        setLoading(true)
        try {
            const fd = new FormData()
            fd.append('resume_text', resumeText)
            fd.append('target_role', selectedRole)
            fd.append('email', email)
            const r = await fetch(`${API}/api/career/analyze-resume`, { method: 'POST', body: fd })
            setResumeResult(await r.json())
        } catch (e) { console.error(e) }
        finally { setLoading(false) }
    }

    const readinessColor = (p) => p >= 0.8 ? '#10b981' : p >= 0.6 ? '#06b6d4' : p >= 0.4 ? '#f59e0b' : '#ef4444'

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
                        <p className="text-slate-400 mt-1">Map your skills to industry roles and predict placement readiness</p>
                    </div>
                    <a href="/dashboard" className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition">← Dashboard</a>
                </div>

                {/* Tabs */}
                <div className="flex gap-2 mb-6 flex-wrap">
                    {[
                        { id: 'readiness', label: '🎯 Readiness', fn: predict },
                        { id: 'skills', label: '🛠️ Skill Profile', fn: fetchProfile },
                        { id: 'resume', label: '📄 Resume Check' },
                    ].map(t => (
                        <button key={t.id} onClick={() => { setTab(t.id); t.fn?.() }}
                            className={`px-4 py-2 rounded-lg font-medium transition ${tab === t.id ? 'bg-gradient-to-r from-cyan-500 to-emerald-500 text-white shadow-lg shadow-cyan-500/20' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                            {t.label}
                        </button>
                    ))}
                </div>

                {loading && <div className="flex justify-center py-16"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-cyan-400" /></div>}

                {!loading && (
                    <>
                        {/* ── Readiness ── */}
                        {tab === 'readiness' && (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                {/* Input */}
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold mb-4">Your Profile</h3>
                                    <div className="space-y-4">
                                        <div>
                                            <label className="text-slate-400 text-sm">Target Role</label>
                                            <select value={selectedRole} onChange={e => setSelectedRole(e.target.value)}
                                                className="w-full mt-1 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none">
                                                {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
                                            </select>
                                        </div>
                                        {[
                                            { key: 'cgpa', label: 'CGPA (out of 10)', step: 0.1, max: 10 },
                                            { key: 'internship', label: 'Internship (months)', step: 1, max: 24 },
                                            { key: 'projects', label: 'Projects', step: 1, max: 20 },
                                            { key: 'practice', label: 'Practice Score (%)', step: 5, max: 100 },
                                        ].map(f => (
                                            <div key={f.key}>
                                                <label className="text-slate-400 text-sm">{f.label}</label>
                                                <input type="number" step={f.step} max={f.max} min={0}
                                                    value={form[f.key]} onChange={e => setForm(prev => ({ ...prev, [f.key]: parseFloat(e.target.value) || 0 }))}
                                                    className="w-full mt-1 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:border-cyan-500 focus:outline-none" />
                                            </div>
                                        ))}
                                        <button onClick={predict}
                                            className="w-full py-3 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-semibold hover:shadow-lg hover:shadow-cyan-500/25 transition">
                                            🔮 Predict Readiness
                                        </button>
                                    </div>
                                </div>

                                {/* Result */}
                                <div className="lg:col-span-2 space-y-6">
                                    {prediction && (
                                        <>
                                            <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6 flex items-center gap-8">
                                                <RadialGauge value={prediction.probability || 0} size={140} label={prediction.target_role}
                                                    color={readinessColor(prediction.probability)} />
                                                <div>
                                                    <h3 className="text-2xl font-bold text-white">{prediction.readiness_level}</h3>
                                                    <p className="text-slate-400 mt-1">{prediction.percentage}% placement probability for {prediction.target_role}</p>
                                                </div>
                                            </div>

                                            {/* Feature Contributions */}
                                            <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                                <h3 className="text-white font-bold mb-4">📊 XAI: What's driving your score?</h3>
                                                <div className="space-y-3">
                                                    {(prediction.contributions || []).map((c, i) => (
                                                        <div key={i} className="flex items-center gap-3">
                                                            <span className="w-40 text-sm text-slate-300 truncate">{c.feature}</span>
                                                            <div className="flex-1 flex items-center gap-2">
                                                                <div className="flex-1 bg-slate-700 rounded-full h-3 relative overflow-hidden">
                                                                    <div className={`absolute top-0 h-3 rounded-full transition-all duration-700 ${c.direction === 'positive' ? 'bg-gradient-to-r from-emerald-500 to-green-400 left-1/2' : 'bg-gradient-to-l from-red-500 to-rose-400 right-1/2'}`}
                                                                        style={{ width: `${Math.min(c.magnitude * 200, 50)}%` }} />
                                                                    <div className="absolute left-1/2 top-0 w-0.5 h-3 bg-slate-500" />
                                                                </div>
                                                            </div>
                                                            <span className={`text-xs font-mono w-16 text-right ${c.direction === 'positive' ? 'text-emerald-400' : 'text-red-400'}`}>
                                                                {c.direction === 'positive' ? '+' : '-'}{Math.round(c.magnitude * 100)}%
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>

                                            {/* Missing Skills */}
                                            {prediction.missing_skills?.length > 0 && (
                                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                                    <h3 className="text-white font-bold mb-4">⚠️ Missing Skills</h3>
                                                    <div className="flex flex-wrap gap-2">
                                                        {prediction.missing_skills.map((s, i) => (
                                                            <span key={i} className={`px-3 py-1.5 rounded-full text-sm ${s.importance === 'required' ? 'bg-red-500/20 text-red-300 border border-red-500/30' : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'}`}>
                                                                {s.skill} <span className="text-xs opacity-60">({s.importance})</span>
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Recommendations */}
                                            {prediction.recommendations?.length > 0 && (
                                                <div className="bg-gradient-to-r from-cyan-500/10 to-emerald-500/10 rounded-2xl border border-cyan-500/30 p-6">
                                                    <h3 className="text-cyan-300 font-bold mb-3">💡 Recommendations</h3>
                                                    <div className="space-y-2">
                                                        {prediction.recommendations.map((r, i) => <p key={i} className="text-slate-200 text-sm">{r}</p>)}
                                                    </div>
                                                </div>
                                            )}
                                        </>
                                    )}
                                    {!prediction && (
                                        <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-12 text-center">
                                            <span className="text-6xl block mb-4">🎯</span>
                                            <p className="text-slate-300 text-lg">Fill in your profile and click Predict to see your placement readiness</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* ── Skill Profile ── */}
                        {tab === 'skills' && skillProfile && (
                            <div className="space-y-6">
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-center">
                                        <p className="text-3xl font-bold text-cyan-400">{skillProfile.total_skills_mapped || 0}</p>
                                        <p className="text-slate-400 text-sm">Skills Mapped</p>
                                    </div>
                                    <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-center">
                                        <p className="text-3xl font-bold text-emerald-400">{Math.round((skillProfile.avg_readiness || 0) * 100)}%</p>
                                        <p className="text-slate-400 text-sm">Avg Readiness</p>
                                    </div>
                                    <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-center">
                                        <p className="text-3xl font-bold text-blue-400">{(skillProfile.technical_skills || []).length}</p>
                                        <p className="text-slate-400 text-sm">Technical</p>
                                    </div>
                                    <div className="bg-slate-800/60 rounded-xl border border-slate-700/50 p-5 text-center">
                                        <p className="text-3xl font-bold text-violet-400">{(skillProfile.soft_skills || []).length}</p>
                                        <p className="text-slate-400 text-sm">Soft Skills</p>
                                    </div>
                                </div>
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold mb-4">🛠️ Your Industry Skills</h3>
                                    <div className="space-y-2">
                                        {(skillProfile.skills || []).slice(0, 20).map((s, i) => (
                                            <SkillBar key={i} skill={s.skill} readiness={s.readiness} domain={s.domain} category={s.category} />
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* ── Resume ── */}
                        {tab === 'resume' && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                <div className="bg-slate-800/60 backdrop-blur-sm rounded-2xl border border-slate-700/50 p-6">
                                    <h3 className="text-white font-bold mb-4">📄 Paste Your Resume</h3>
                                    <select value={selectedRole} onChange={e => setSelectedRole(e.target.value)}
                                        className="w-full mb-3 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:border-cyan-500 focus:outline-none">
                                        {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
                                    </select>
                                    <textarea value={resumeText} onChange={e => setResumeText(e.target.value)} rows={14}
                                        placeholder="Paste your resume text here..."
                                        className="w-full bg-slate-900/50 border border-slate-600 rounded-xl p-4 text-slate-200 placeholder-slate-500 resize-none focus:border-cyan-500 focus:outline-none text-sm" />
                                    <button onClick={analyzeResume} disabled={!resumeText.trim()}
                                        className="mt-4 w-full py-3 bg-gradient-to-r from-cyan-500 to-emerald-500 text-white rounded-xl font-semibold disabled:opacity-50 hover:shadow-lg transition">
                                        🔍 Analyze Resume
                                    </button>
                                </div>
                                <div>
                                    {resumeResult?.analysis ? (
                                        <div className="space-y-4">
                                            <div className="bg-slate-800/60 rounded-2xl border border-slate-700/50 p-6 text-center">
                                                <RadialGauge value={(resumeResult.analysis.overall_match_percentage || 0) / 100} size={120}
                                                    label={resumeResult.target_role} color={readinessColor((resumeResult.analysis.overall_match_percentage || 0) / 100)} />
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
                                            <p className="text-slate-400">Paste your resume and select a target role to get AI-powered analysis</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </main>
    )
}
