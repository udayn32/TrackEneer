'use client';

import { useState, useEffect } from 'react';
import { useSession } from 'next-auth/react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:5000';

export default function PlacementPage() {
  const { data: session } = useSession();
  const [companyName, setCompanyName] = useState('');
  const [website, setWebsite] = useState('');
  const [loading, setLoading] = useState(false);
  const [companyData, setCompanyData] = useState(null);
  const [error, setError] = useState('');
  const [alumni, setAlumni] = useState([]);

  // Load alumni data on component mount
  useEffect(() => {
    fetchAlumni();
  }, []);

  const fetchAlumni = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/placement/alumni`);
      const data = await response.json();
      setAlumni(data.alumni || []);
    } catch (err) {
      console.error('Failed to load alumni data:', err);
    }
  };

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!companyName.trim()) {
      setError('Please enter a company name');
      return;
    }

    setLoading(true);
    setError('');
    setCompanyData(null);

    try {
      const formData = new FormData();
      formData.append('company_name', companyName);
      if (website.trim()) {
        formData.append('website', website);
      }

      const response = await fetch(`${API_BASE}/api/placement/generate`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMessage = errorData.detail || 'Failed to generate company information';
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setCompanyData(data);
      setError('');
    } catch (err) {
      setError(err.message || 'Failed to generate company information');
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatContent = (content) => {
    if (!content) return null;
    
    // Function to parse inline markdown bold and render as React elements
    const parseMarkdown = (text) => {
      // Split by ** to find bold sections
      const parts = text.split(/(\*\*.*?\*\*)/g);
      
      return parts.map((part, i) => {
        // Check if this part is bold (wrapped in **)
        if (part.startsWith('**') && part.endsWith('**')) {
          const boldText = part.slice(2, -2); // Remove ** from both ends
          return <strong key={i} className="font-bold text-white">{boldText}</strong>;
        }
        return <span key={i}>{part}</span>;
      });
    };
    
    return content.split('\n').map((line, idx) => {
      line = line.trim();
      if (!line) return <br key={idx} />;
      
      // Bold headers (lines ending with :)
      if (line.endsWith(':') && !line.startsWith('-')) {
        const cleanLine = line.replace(/\*\*/g, '');
        return <h3 key={idx} className="font-bold text-lg text-cyan-400 mt-4 mb-2">{cleanLine}</h3>;
      }
      
      // Bullet points
      if (line.startsWith('-')) {
        const bulletText = line.substring(1).trim();
        return (
          <li key={idx} className="ml-4 mb-2 text-slate-300">
            {parseMarkdown(bulletText)}
          </li>
        );
      }
      
      // Regular paragraphs
      return (
        <p key={idx} className="mb-2 text-slate-300">
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
            <h1 className="text-3xl font-bold">Placement Research</h1>
            <p className="text-sm text-white/80 mt-1">Smart Placement</p>
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
        {/* Search Form */}
        <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-cyan-500/20 shadow-lg mb-8">
          <h2 className="text-2xl font-bold mb-4 text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
            Research Company
          </h2>
          <form onSubmit={handleGenerate} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Company Name *
              </label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="e.g., TCS, Accenture, Google"
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:border-cyan-500 text-white placeholder-slate-500"
                disabled={loading}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Company Website (Optional)
              </label>
              <input
                type="text"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="e.g., https://www.tcs.com"
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:border-cyan-500 text-white placeholder-slate-500"
                disabled={loading}
              />
            </div>
            {error && (
              <div className="bg-red-500/20 border border-red-500/50 rounded-lg p-3 text-red-300">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 disabled:from-slate-700 disabled:to-slate-700 text-white font-medium py-3 px-6 rounded-lg transition-all duration-200 shadow-lg disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generating with AI...
                </span>
              ) : (
                '🔍 Generate Company Report'
              )}
            </button>
          </form>
        </div>

        {/* Company Information Display */}
        {companyData && (
          <div className="space-y-6">
            {/* Company Header with Score */}
            <div className="bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-purple-500/10 backdrop-blur-sm rounded-xl p-6 border border-cyan-500/30 shadow-lg">
              <div className="flex justify-between items-start">
                <div>
                  <h2 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-400">
                    {companyData.company_name}
                  </h2>
                  {companyData.website && (
                    <a
                      href={companyData.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-cyan-400 hover:text-cyan-300 text-sm mt-1 inline-block"
                    >
                      🔗 {companyData.website}
                    </a>
                  )}
                  {companyData.cached && (
                    <span className="ml-3 text-xs bg-purple-500/20 border border-purple-500/50 px-2 py-1 rounded">
                      Cached Data
                    </span>
                  )}
                </div>
                {companyData.score_info && (
                  <div className="bg-slate-900/80 rounded-xl p-4 border border-cyan-500/30 min-w-[120px] text-center">
                    <div className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">
                      {companyData.score_info.score}
                    </div>
                    <div className="text-xs text-slate-400 mt-1">Overall Score</div>
                    <div className="flex justify-center mt-2">
                      {[...Array(10)].map((_, i) => (
                        <span
                          key={i}
                          className={`text-xs ${
                            i < Math.round(companyData.score_info.score)
                              ? 'text-cyan-400'
                              : 'text-slate-700'
                          }`}
                        >
                          ★
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Score Details */}
              {companyData.score_info && (
                <div className="grid md:grid-cols-2 gap-4 mt-6">
                  {/* Strengths */}
                  <div className="bg-slate-900/50 rounded-lg p-4 border border-green-500/20">
                    <h4 className="font-bold text-green-400 mb-3 flex items-center gap-2">
                      <span>✅</span> Key Strengths
                    </h4>
                    <ul className="space-y-2">
                      {companyData.score_info.strengths?.map((strength, idx) => (
                        <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                          <span className="text-green-400 mt-1">•</span>
                          <span>{strength}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Considerations */}
                  <div className="bg-slate-900/50 rounded-lg p-4 border border-yellow-500/20">
                    <h4 className="font-bold text-yellow-400 mb-3 flex items-center gap-2">
                      <span>⚠️</span> Considerations
                    </h4>
                    <ul className="space-y-2">
                      {companyData.score_info.considerations?.map((consideration, idx) => (
                        <li key={idx} className="text-sm text-slate-300 flex items-start gap-2">
                          <span className="text-yellow-400 mt-1">•</span>
                          <span>{consideration}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Recommendation */}
              {companyData.score_info?.recommendation && (
                <div className="mt-4 bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                  <p className="text-blue-300 text-center italic">
                    💡 {companyData.score_info.recommendation}
                  </p>
                </div>
              )}
            </div>

            {/* Three Column Layout */}
            <div className="grid lg:grid-cols-3 gap-6">
              {/* Vision & Mission */}
              <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-cyan-500/20 shadow-lg">
                <h3 className="text-xl font-bold text-cyan-400 mb-4 flex items-center gap-2">
                  <span>🎯</span> Vision & Mission
                </h3>
                <div className="text-sm space-y-2">
                  {formatContent(companyData.sections?.vision_mission)}
                </div>
              </div>

              {/* Placement Process */}
              <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-purple-500/20 shadow-lg">
                <h3 className="text-xl font-bold text-purple-400 mb-4 flex items-center gap-2">
                  <span>📋</span> Placement Process
                </h3>
                <div className="text-sm space-y-2">
                  {formatContent(companyData.sections?.placement_process)}
                </div>
              </div>

              {/* Company Review */}
              <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-blue-500/20 shadow-lg">
                <h3 className="text-xl font-bold text-blue-400 mb-4 flex items-center gap-2">
                  <span>⭐</span> Company Review
                </h3>
                <div className="text-sm space-y-2">
                  {formatContent(companyData.sections?.company_review)}
                </div>
              </div>
            </div>

            {/* Alumni Section */}
            <div className="bg-slate-900/80 backdrop-blur-sm rounded-xl p-6 border border-orange-500/20 shadow-lg">
              <h3 className="text-xl font-bold text-orange-400 mb-4 flex items-center gap-2">
                <span>👥</span> Alumni Placements
              </h3>
              <div className="grid md:grid-cols-3 gap-4">
                {alumni.map((person, idx) => (
                  <div
                    key={idx}
                    className="bg-slate-800/50 rounded-lg p-4 border border-slate-700 hover:border-orange-500/50 transition-all duration-200"
                  >
                    <div className="flex items-center gap-3 mb-3">
                      <div className="text-3xl">{person.avatar}</div>
                      <div>
                        <h4 className="font-bold text-white">{person.name}</h4>
                        <p className="text-xs text-slate-400">Batch {person.batch}</p>
                      </div>
                    </div>
                    <div className="space-y-1 text-sm">
                      <p className="text-slate-300">
                        <span className="text-slate-500">Company:</span> {person.company}
                      </p>
                      <p className="text-slate-300">
                        <span className="text-slate-500">Role:</span> {person.role}
                      </p>
                      <p className="text-green-400 font-bold">
                        <span className="text-slate-500">Package:</span> {person.package}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!companyData && !loading && (
          <div className="bg-slate-900/50 backdrop-blur-sm rounded-xl p-12 border border-slate-700 text-center">
            <div className="text-6xl mb-4">🏢</div>
            <h3 className="text-2xl font-bold text-slate-300 mb-2">
              Research Any Company
            </h3>
            <p className="text-slate-400 mb-6 max-w-md mx-auto">
              Enter a company name above to get smart insights about their vision, mission,
              placement process, and reviews from a student perspective.
            </p>
            <div className="flex justify-center gap-4 flex-wrap">
              <button
                onClick={() => setCompanyName('TCS')}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm border border-slate-600"
              >
                Try: TCS
              </button>
              <button
                onClick={() => setCompanyName('Accenture')}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm border border-slate-600"
              >
                Try: Accenture
              </button>
              <button
                onClick={() => setCompanyName('Infosys')}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm border border-slate-600"
              >
                Try: Infosys
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
