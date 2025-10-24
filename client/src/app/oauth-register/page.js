'use client';

import { useState, useEffect } from 'react';
import { useSession, signIn } from 'next-auth/react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

const API_BASE =
  process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, '') ||
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') ||
  'http://localhost:5000';

export default function OAuthRegisterPage() {
  const { data: session, status } = useSession();
  const router = useRouter();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [careerGoal, setCareerGoal] = useState('');
  const [careerOther, setCareerOther] = useState('');
  const [weaknesses, setWeaknesses] = useState([]);
  const [weaknessesOther, setWeaknessesOther] = useState('');
  const [challenges, setChallenges] = useState([]);
  const [challengesOther, setChallengesOther] = useState('');
  const [helpOptions, setHelpOptions] = useState([]);
  const [helpOther, setHelpOther] = useState('');
  const [resumeFile, setResumeFile] = useState(null);
  const [branch, setBranch] = useState('');
  const [year, setYear] = useState('');
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (session?.user) {
      setName(session.user.name || '');
      setEmail(session.user.email || '');
    }
  }, [session]);

  // If the OAuth session exists and the user is already registered in our DB,
  // automatically create the server-side session (via oauth-register) and
  // redirect to dashboard. This avoids showing the onboarding form to users
  // who already completed onboarding previously.
  useEffect(() => {
    let mounted = true;
    const tryAutoLogin = async () => {
      if (!session?.user || !session.user.email) return;
      try {
        const check = await fetch(`${API_BASE}/api/auth/exists?email=${encodeURIComponent(session.user.email)}`);
        if (!mounted) return;
        if (check.ok) {
          const data = await check.json();
          if (data?.exists) {
            // user exists in DB — perform minimal oauth-register POST to create server session
            const form = new FormData();
            form.append('name', session.user.name || '');
            form.append('email', session.user.email || '');
            form.append('branch', branch || '');
            form.append('year', year || '');
            form.append('career_goal', '');

            const res = await fetch(`${API_BASE}/api/auth/oauth-register`, {
              method: 'POST',
              body: form,
              credentials: 'include',
            });
            if (res.ok) {
              router.push('/dashboard');
            } else {
              // Log and surface server validation errors (422) so it's easier to debug
              let txt = '';
              try {
                const j = await res.json();
                txt = JSON.stringify(j);
                setError(j?.detail || j?.message || 'OAuth login failed');
              } catch (e) {
                txt = await res.text().catch(() => String(res.status));
                setError('OAuth login failed');
              }
              console.error('oauth-register failed', res.status, txt);
            }
          }
        }
      } catch (e) {
        // ignore network errors — user can still fill the form manually
      }
    };

    tryAutoLogin();
    return () => {
      mounted = false;
    };
  }, [session]);

  // helper to toggle values in an array (for checkbox groups)
  const toggleArray = (arrSetter, arr, value) => {
    if (arr.includes(value)) {
      arrSetter(arr.filter((x) => x !== value));
    } else {
      arrSetter([...arr, value]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const form = new FormData();
      form.append('name', name);
      form.append('email', email);
  form.append('branch', branch || '');
  form.append('year', year || '');
  const chosenCareer = careerGoal === 'Other' ? careerOther : careerGoal;
  form.append('career_goal', chosenCareer || '');
  form.append('weaknesses', JSON.stringify(weaknesses.concat(weaknessesOther ? [weaknessesOther] : [])));
  form.append('challenges', JSON.stringify(challenges.concat(challengesOther ? [challengesOther] : [])));
  form.append('wants_help', JSON.stringify(helpOptions.concat(helpOther ? [helpOther] : [])));
      if (resumeFile) form.append('resume', resumeFile);

      const res = await fetch(`${API_BASE}/api/auth/oauth-register`, {
        method: 'POST',
        body: form,
      });

      if (res.ok) {
        // Redirect to dashboard
        setFieldErrors({});
        router.push('/dashboard');
      } else {
        const data = await res.json().catch(() => null);
        if (Array.isArray(data)) {
          const map = {};
          data.forEach((err) => {
            const loc = Array.isArray(err.loc) ? err.loc : [err.loc];
            const key = loc[loc.length - 1];
            map[key] = map[key] ? map[key] + '; ' + (err.msg || JSON.stringify(err)) : (err.msg || JSON.stringify(err));
          });
          setFieldErrors(map);
          setError('Please correct the highlighted fields.');
        } else if (data && Array.isArray(data.detail)) {
          const map = {};
          data.detail.forEach((err) => {
            const loc = Array.isArray(err.loc) ? err.loc : [err.loc];
            const key = loc[loc.length - 1];
            map[key] = map[key] ? map[key] + '; ' + (err.msg || JSON.stringify(err)) : (err.msg || JSON.stringify(err));
          });
          setFieldErrors(map);
          setError('Please correct the highlighted fields.');
        } else {
          setError(data?.detail || data?.message || 'Registration failed.');
        }
      }
    } catch (err) {
      setError('Unable to reach the server. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (status === 'loading') {
    return <div className="min-h-screen flex items-center justify-center">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md p-8 space-y-6 bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-2xl shadow-2xl"
      >
        <div className="text-center">
          <h1 className="text-3xl font-bold text-cyan-400">Complete Your Profile</h1>
          <p className="mt-2 text-slate-400">Finish your TrackEneer profile to get tailored recommendations</p>
        </div>

        {error && (
          <p className="text-center text-red-400 bg-red-500/10 p-2 rounded-md">
            {typeof error === 'string'
              ? error
              : Array.isArray(error)
              ? error.map((it) => (typeof it === 'string' ? it : JSON.stringify(it))).join('; ')
              : typeof error === 'object'
              ? (error.detail
                  ? (typeof error.detail === 'string' ? error.detail : Array.isArray(error.detail) ? error.detail.map((d) => d.msg || JSON.stringify(d)).join('; ') : JSON.stringify(error.detail))
                  : error.message || JSON.stringify(error))
              : String(error)}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-sm font-medium text-slate-300">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
            {fieldErrors.name && <p className="text-xs text-red-400 mt-1">{fieldErrors.name}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Branch</label>
            <input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="e.g. CSE" className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700" />
            {fieldErrors.branch && <p className="text-xs text-red-400 mt-1">{fieldErrors.branch}</p>}
          </div>
          <div>
            <label className="text-sm font-medium text-slate-300">Year</label>
            <input value={year} onChange={(e) => setYear(e.target.value)} placeholder="e.g. 3rd" className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700" />
            {fieldErrors.year && <p className="text-xs text-red-400 mt-1">{fieldErrors.year}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            />
            {fieldErrors.email && <p className="text-xs text-red-400 mt-1">{fieldErrors.email}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Career Goal</label>
            <select
              value={careerGoal}
              onChange={(e) => setCareerGoal(e.target.value)}
              className="w-full mt-1 p-3 bg-slate-900 rounded-md border border-slate-700 focus:outline-none focus:ring-2 focus:ring-cyan-500"
            >
              <option value="">Select one</option>
              <option>Become a Cybersecurity Expert</option>
              <option>Blockchain Developer / Architect</option>
              <option>AI & ML Researcher</option>
              <option>IoT Engineer / Innovator</option>
              <option>Data Scientist</option>
              <option>Cloud & DevOps Specialist</option>
              <option>Full Stack Developer</option>
              <option>Tech Entrepreneur / Founder</option>
              <option>Academic Researcher / Professor</option>
              <option value="Other">Other</option>
            </select>
            {careerGoal === 'Other' && (
              <input value={careerOther} onChange={(e) => setCareerOther(e.target.value)} placeholder="Other: specify" className="w-full mt-2 p-2 bg-slate-800 rounded-md border border-slate-700" />
            )}
            {fieldErrors.careerGoal && <p className="text-xs text-red-400 mt-1">{fieldErrors.careerGoal}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Weaknesses (choose any)</label>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {['Time management','Public speaking','Consistency / focus','Handling pressure or failure','Technical depth','Confidence in interviews','Communication skills','Networking'].map((w) => (
                <label key={w} className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={weaknesses.includes(w)} onChange={() => toggleArray(setWeaknesses, weaknesses, w)} className="w-4 h-4" />
                  <span className="text-slate-300">{w}</span>
                </label>
              ))}
            </div>
            <input value={weaknessesOther} onChange={(e) => setWeaknessesOther(e.target.value)} placeholder="Other weakness (optional)" className="w-full mt-2 p-2 bg-slate-800 rounded-md border border-slate-700" />
            {fieldErrors.weaknesses && <p className="text-xs text-red-400 mt-1">{fieldErrors.weaknesses}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Challenges (choose any)</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
              {['Lack of proper guidance or mentorship','Difficulty finding good learning resources','Balancing academics and projects','Financial or technical limitations','Self-doubt or motivation issues','Team collaboration challenges'].map((c) => (
                <label key={c} className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={challenges.includes(c)} onChange={() => toggleArray(setChallenges, challenges, c)} className="w-4 h-4" />
                  <span className="text-slate-300">{c}</span>
                </label>
              ))}
            </div>
            <input value={challengesOther} onChange={(e) => setChallengesOther(e.target.value)} placeholder="Other challenge (optional)" className="w-full mt-2 p-2 bg-slate-800 rounded-md border border-slate-700" />
            {fieldErrors.challenges && <p className="text-xs text-red-400 mt-1">{fieldErrors.challenges}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">I want help / mentorship (choose any)</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
              {['Resume review & LinkedIn optimization','Interview preparation','Technical skill development (AI / Blockchain / IoT / Cybersecurity)','Career planning & specialization guidance','Research paper or project mentoring','Networking & industry exposure','Time management & productivity','Personal branding & communication','Mental resilience & motivation'].map((h) => (
                <label key={h} className="inline-flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={helpOptions.includes(h)} onChange={() => toggleArray(setHelpOptions, helpOptions, h)} className="w-4 h-4" />
                  <span className="text-slate-300">{h}</span>
                </label>
              ))}
            </div>
            <input value={helpOther} onChange={(e) => setHelpOther(e.target.value)} placeholder="Other help (optional)" className="w-full mt-2 p-2 bg-slate-800 rounded-md border border-slate-700" />
            {fieldErrors.wantsHelp && <p className="text-xs text-red-400 mt-1">{fieldErrors.wantsHelp}</p>}
          </div>

          <div>
            <label className="text-sm font-medium text-slate-300">Upload Resume (optional)</label>
            <input type="file" accept=".pdf,.doc,.docx" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} className="w-full mt-1 text-sm text-slate-300" />
            {fieldErrors.resume && <p className="text-xs text-red-400 mt-1">{fieldErrors.resume}</p>}
          </div>

          <div className="flex justify-between items-center">
            <Link href="/dashboard" className="text-sm text-slate-400 hover:underline">Skip for now</Link>
            <button type="submit" disabled={submitting} className="font-bold py-2 px-4 bg-cyan-500 hover:bg-cyan-400 text-slate-900 rounded-lg transition-colors">
              {submitting ? 'Saving…' : 'Save & Continue'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}
