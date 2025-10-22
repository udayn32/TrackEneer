'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';

const API_BASE = 'http://localhost:5004';

export default function InsightsPage() {
  const { data: session } = useSession();
  const [selectedYear, setSelectedYear] = useState('');
  const [selectedBranch, setSelectedBranch] = useState('');
  const [loading, setLoading] = useState(false);
  const [insightsData, setInsightsData] = useState(null);
  const [error, setError] = useState('');
  const [years, setYears] = useState([]);
  const [branches, setBranches] = useState([]);

  // Load years and branches on component mount
  useEffect(() => {
    fetchYearsAndBranches();
  }, []);

  const fetchYearsAndBranches = async () => {
    try {
      const [yearsRes, branchesRes] = await Promise.all([
        fetch(`${API_BASE}/api/insights/years`),
        fetch(`${API_BASE}/api/insights/branches`)
      ]);
      
      const yearsData = await yearsRes.json();
      const branchesData = await branchesRes.json();
      
      setYears(yearsData.years || []);
      setBranches(branchesData.branches || []);
    } catch (err) {
      console.error('Failed to load years/branches:', err);
    }
  };

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!selectedYear) {
      setError('Please select your year');
      return;
    }

    setLoading(true);
    setError('');
    setInsightsData(null);

    try {
      const formData = new FormData();
      formData.append('year', selectedYear);
      if (selectedBranch) {
        formData.append('branch', selectedBranch);
      }

      const response = await fetch(`${API_BASE}/api/insights/generate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage = errorData.detail || 'Failed to generate insights';
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setInsightsData(data);
      setError('');
    } catch (err) {
      setError(err.message || 'Failed to generate insights');
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatContent = (content) => {
    if (!content) return null;
    
    const parseMarkdown = (text) => {
      const parts = text.split(/(\*\*.*?\*\*)/g);
      return parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          const boldText = part.slice(2, -2);
          return <strong key={i} className="font-bold text-white">{boldText}</strong>;
        }
        return <span key={i}>{part}</span>;
      });
    };
    
    return content.split('\n').map((line, idx) => {
      line = line.trim();
      if (!line) return <br key={idx} />;
      
      // Section headers (all caps or ending with :)
      if ((line === line.toUpperCase() && line.length > 3) || (line.endsWith(':') && !line.startsWith('-') && !line.match(/^\d/))) {
        const cleanLine = line.replace(/\*\*/g, '').replace(/:$/, '');
        return <h3 key={idx} className="font-bold text-xl text-cyan-400 mt-6 mb-3">{cleanLine}</h3>;
      }
      
      // Numbered lists
      if (line.match(/^\d+\./)) {
        return (
          <li key={idx} className="ml-6 mb-2 text-slate-300 list-decimal">
            {parseMarkdown(line.replace(/^\d+\.\s*/, ''))}
          </li>
        );
      }
      
      // Bullet points
      if (line.startsWith('-') || line.startsWith('•')) {
        const bulletText = line.substring(1).trim();
        return (
          <li key={idx} className="ml-4 mb-2 text-slate-300">
            {parseMarkdown(bulletText)}
          </li>
        );
      }
      
      // Regular paragraphs
      return (
        <p key={idx} className="mb-3 text-slate-300 leading-relaxed">
          {parseMarkdown(line)}
        </p>
      );
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Animated Background */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 -left-48 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 -right-48 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse delay-1000"></div>
      </div>

      {/* Header */}
      <div className="relative z-10 bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-600 p-6 shadow-lg">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold">Student Insights</h1>
            <p className="text-sm text-white/80 mt-1">Smart Prep Guide</p>
          </div>
          {session?.user ? (
            <div className="flex items-center gap-3">
              <span className="text-sm">{session.user.name || 'User'}</span>
              {session.user.image ? (
                <img
                  src={session.user.image}
                  alt="Profile"
                  className="w-10 h-10 rounded-full border-2 border-white/50"
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(session.user.name || 'User')}&background=0D8ABC&color=fff`;
                  }}
                />
              ) : (
                <div className="w-10 h-10 rounded-full border-2 border-white/50 bg-cyan-600 flex items-center justify-center text-white font-bold">
                  {(session.user.name || 'U').charAt(0).toUpperCase()}
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <span className="text-sm">Guest User</span>
              <div className="w-10 h-10 rounded-full border-2 border-white/50 bg-purple-600 flex items-center justify-center text-white font-bold">
                G
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="relative z-10 max-w-7xl mx-auto p-6 mt-6">
        {/* Selection Form */}
        <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-cyan-500/20 shadow-lg mb-8">
          <h2 className="text-2xl font-bold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
            Get Personalized Guidance
          </h2>
          <form onSubmit={handleGenerate} className="space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              {/* Year Selection */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Select Your Year *
                </label>
                <select
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:border-cyan-500 text-white"
                  disabled={loading}
                >
                  <option value="">-- Select Year --</option>
                  {years.map((year) => (
                    <option key={year.code} value={year.code}>
                      {year.full_name} ({year.code})
                    </option>
                  ))}
                </select>
                {selectedYear && (
                  <p className="text-xs text-slate-400 mt-1">
                    Focus: {years.find(y => y.code === selectedYear)?.focus}
                  </p>
                )}
              </div>

              {/* Branch Selection */}
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Select Your Branch (Optional)
                </label>
                <select
                  value={selectedBranch}
                  onChange={(e) => setSelectedBranch(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:border-cyan-500 text-white"
                  disabled={loading}
                >
                  <option value="">-- All Branches --</option>
                  {branches.map((branch) => (
                    <option key={branch.code} value={branch.code}>
                      {branch.full_name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {error && (
              <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-300">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !selectedYear}
              className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 disabled:from-slate-700 disabled:to-slate-700 text-white font-medium py-3 px-6 rounded-lg transition-all duration-200 shadow-lg disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generating Insights...
                </span>
              ) : (
                '✨ Generate My Preparation Guide'
              )}
            </button>
          </form>
        </div>

        {/* Insights Display */}
        {insightsData && (
          <div className="space-y-6">
            {/* Header Card */}
            <div className="bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10 backdrop-blur-sm rounded-xl p-6 border border-cyan-500/30 shadow-lg">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-400">
                    {insightsData.year_full_name}
                  </h2>
                  <p className="text-cyan-400 text-lg mt-1">{insightsData.branch}</p>
                  {insightsData.cached && (
                    <span className="text-xs bg-purple-500/20 border border-purple-500/50 px-2 py-1 rounded mt-2 inline-block">
                      Cached Data
                    </span>
                  )}
                </div>
                <div className="bg-slate-900/80 rounded-xl p-4 border border-cyan-500/30 min-w-[120px] text-center">
                  <div className="text-4xl">🎓</div>
                  <div className="text-xs text-slate-400 mt-2">Personalized<br />Guide</div>
                </div>
              </div>
            </div>

            {/* Content Card */}
            <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-8 border border-slate-700 shadow-lg">
              <div className="prose prose-invert max-w-none">
                {formatContent(insightsData.content)}
              </div>
            </div>

            {/* Action Card */}
            <div className="bg-gradient-to-r from-green-500/10 to-blue-500/10 backdrop-blur-sm rounded-xl p-6 border border-green-500/30 shadow-lg">
              <div className="flex items-center gap-4">
                <div className="text-4xl">💡</div>
                <div className="flex-1">
                  <h3 className="text-lg font-bold text-green-400 mb-1">Ready to Excel?</h3>
                  <p className="text-slate-300 text-sm">
                    Follow this guide consistently and track your progress. Success comes from dedication and smart work!
                  </p>
                </div>
                <button
                  onClick={() => {
                    setInsightsData(null);
                    setSelectedYear('');
                    setSelectedBranch('');
                  }}
                  className="px-4 py-2 bg-green-500/20 hover:bg-green-500/30 border border-green-500/50 rounded-lg text-sm transition-all"
                >
                  Generate Again
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!insightsData && !loading && (
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-12 border border-slate-700 text-center">
            <div className="text-6xl mb-4">💡</div>
            <h3 className="text-2xl font-bold text-slate-300 mb-2">
              Personalized Learning Path
            </h3>
            <p className="text-slate-400 mb-6 max-w-md mx-auto">
              Select your year and branch to get smart guidance on what to study,
              skills to develop, and how to prepare for your future.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-2xl mx-auto">
              {years.map((year) => (
                <button
                  key={year.code}
                  onClick={() => setSelectedYear(year.code)}
                  className="p-4 bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-600 hover:border-cyan-500 transition-all"
                >
                  <div className="text-2xl mb-2">
                    {year.code === 'FE' ? '🌱' : year.code === 'SE' ? '🚀' : year.code === 'TE' ? '⚡' : '🎯'}
                  </div>
                  <div className="text-sm font-bold">{year.code}</div>
                  <div className="text-xs text-slate-400">{year.focus}</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
