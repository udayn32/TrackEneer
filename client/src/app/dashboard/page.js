'use client'

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, "") || "http://localhost:5000";
const DASHBOARD_REFRESH_MS = 30000;

// Fallback quotes for when API is unavailable
const FALLBACK_QUOTES = [
  { content: "The beautiful thing about learning is that no one can take it away from you.", author: "B.B. King" },
  { content: "Success is the sum of small efforts, repeated day in and day out.", author: "Robert Collier" },
  { content: "The only way to do great work is to love what you do.", author: "Steve Jobs" },
  { content: "Believe you can and you're halfway there.", author: "Theodore Roosevelt" },
  { content: "The expert in anything was once a beginner.", author: "Helen Hayes" },
  { content: "Don't wish it were easier; wish you were better.", author: "Jim Rohn" },
  { content: "Small daily improvements over time lead to stunning results.", author: "Robin Sharma" },
  { content: "The best time to plant a tree was 20 years ago. The second best time is now.", author: "Chinese Proverb" },
  { content: "Discipline is the bridge between goals and accomplishment.", author: "Jim Rohn" },
  { content: "Everything you've ever wanted is on the other side of fear.", author: "George Addair" },
];

const PRIORITY_LABELS = {
  high: "high",
  medium: "medium",
  low: "low",
};

function cleanTaskTitle(title) {
  if (!title) return "Untitled task";
  return String(title).replace(/\s+/g, " ").replace(/^study:\s*/i, "").trim();
}

function cleanFileTitle(title) {
  if (!title) return "Untitled file";
  let value = String(title).trim();
  value = value.replace(/^[a-f0-9]{8}-[a-f0-9-]{20,}_/i, "");
  value = value.replace(/^demo\s+/i, "");
  value = value.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return value || "Untitled file";
}

// Header Component
const Header = () => {
  const { data: session } = useSession();
  const [quote, setQuote] = useState(FALLBACK_QUOTES[0]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const saved = sessionStorage.getItem('dashboardQuote');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed?.content) {
          setQuote(parsed);
          return;
        }
      } catch (err) {
        // ignore malformed storage; fall through to fetch
      }
    }

    const fetchQuote = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/quote`);
        if (!response.ok) throw new Error("Failed to fetch quote");
        const data = await response.json();

        const newQuote = {
          content: data.content || data.quote || data.text,
          author: data.author || "Unknown",
        };

        setQuote(newQuote);
        sessionStorage.setItem('dashboardQuote', JSON.stringify(newQuote));
      } catch (err) {
        console.error("Error fetching quote:", err);
        const fallbackQuote = FALLBACK_QUOTES[Math.floor(Math.random() * FALLBACK_QUOTES.length)];
        setQuote(fallbackQuote);
        sessionStorage.setItem('dashboardQuote', JSON.stringify(fallbackQuote));
      }
    };

    fetchQuote();
  }, []);

  return (
    <header className="bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500 text-white p-6 rounded-xl flex flex-col md:flex-row items-center justify-between gap-4 shadow-2xl shadow-cyan-500/20">

      {/* Left side: Welcome */}
      <div className="flex items-center gap-4">
        <h1 className="text-3xl font-bold">Welcome, {session?.user?.name || 'User'}</h1>
      </div>

      {/* Middle: Quote */}
      <div className="text-center flex-1">
        <p className="text-xl md:text-2xl italic font-serif">
          "{quote.content}"
        </p>
        {quote.author && (
          <p className="text-sm mt-2 text-white/80 font-medium">— {quote.author}</p>
        )}
      </div>

      {/* Right side: Avatar and Logout */}
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center text-2xl">
          👤
        </div>
        <a href="/api/auth/signout" className="bg-white text-blue-500 font-bold py-2 px-4 rounded-full hover:bg-slate-100 transition-all duration-300 hover:scale-105">
          Logout
        </a>
      </div>

    </header>
  );
};

// Next Task Component
const NextTask = () => {
  const { data: session } = useSession();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const email = session?.user?.email || "";

  useEffect(() => {
    const fetchNextTasks = async () => {
      try {
        const query = email ? `?email=${encodeURIComponent(email)}` : "";
        const response = await fetch(`${API_BASE}/api/upcoming-deadlines${query}`);
        if (!response.ok) throw new Error("Failed to fetch tasks");
        const data = await response.json();

        // Get deadlines array and take first 3 tasks
        const deadlines = Array.isArray(data.deadlines) ? data.deadlines : [];
        setTasks(deadlines.slice(0, 3));
      } catch (err) {
        console.error("Error fetching next tasks:", err);
        setTasks([]);
      } finally {
        setLoading(false);
      }
    };

    fetchNextTasks();
    const intervalId = setInterval(fetchNextTasks, DASHBOARD_REFRESH_MS);
    return () => clearInterval(intervalId);
  }, [email]);

  const formatDueDate = (dueDate) => {
    if (!dueDate) return "";
    const date = new Date(dueDate);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);

    const dateStr = date.toDateString();
    const todayStr = today.toDateString();
    const tomorrowStr = tomorrow.toDateString();

    if (dateStr === todayStr) return "Today";
    if (dateStr === tomorrowStr) return "Tomorrow";

    const diffTime = date - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays > 0 && diffDays <= 7) return `in ${diffDays} days`;

    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className='bg-gradient-to-br from-slate-800 via-slate-700 to-slate-800 p-6 rounded-xl shadow-2xl border border-cyan-500/20 w-full'>
      <h2 className="text-2xl font-bold mb-4 text-white flex items-center">
        <span className="mr-2">📋</span>
        Next Tasks
      </h2>

      {/* Tasks List */}
      <div className="bg-slate-900/50 backdrop-blur-sm rounded-lg p-4 mb-6 space-y-3 min-h-[200px] border border-cyan-500/10">
        {loading ? (
          <p className="text-lg text-slate-400 text-center py-8">Loading...</p>
        ) : tasks.length > 0 ? (
          tasks.map((task, index) => (
            <div key={index} className="bg-gradient-to-r from-slate-800/80 to-slate-700/80 rounded-xl p-4 shadow-lg border border-cyan-500/20 hover:border-cyan-400/35 hover:shadow-cyan-500/15 transition-all duration-300">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-lg font-bold leading-snug text-white break-words">
                    {cleanTaskTitle(task.title)}
                  </h3>
                  <p className="text-sm text-slate-400 mt-2">
                    {task.dueDate && `Due: ${formatDueDate(task.dueDate)}`}
                  </p>
                </div>
                {task.priority && (
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap capitalize shrink-0 ${task.priority === 'High' ? 'bg-gradient-to-r from-red-500 to-pink-500 text-white' :
                      task.priority === 'Medium' ? 'bg-gradient-to-r from-yellow-500 to-orange-500 text-white' :
                        'bg-gradient-to-r from-green-500 to-emerald-500 text-white'
                    }`}>
                    {PRIORITY_LABELS[String(task.priority || '').toLowerCase()] || String(task.priority).toLowerCase()}
                  </span>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-8">
            <p className="text-xl font-bold text-white">No Tasks Pending</p>
            <p className="text-sm text-slate-400 mt-2">Add tasks to your schedule</p>
          </div>
        )}
      </div>

      <a href="/schedule" className="block w-full bg-gradient-to-r from-cyan-400 to-blue-500 text-white py-3 rounded-lg hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 text-center font-semibold">
        Go to Schedule →
      </a>
    </div>
  );
};

// Recent Files Component
const RecentFiles = () => {
  const { data: session } = useSession();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const email = session?.user?.email || "";

  useEffect(() => {
    const fetchRecentFiles = async () => {
      try {
        const emailQuery = email ? `&email=${encodeURIComponent(email)}` : "";
        const [notesResponse, docsResponse] = await Promise.all([
          fetch(`${API_BASE}/api/notes/recent?limit=3${emailQuery}`),
          fetch(`${API_BASE}/api/knowledge-graph/documents?email=${encodeURIComponent(email)}`),
        ]);

        const notesData = notesResponse.ok ? await notesResponse.json() : { notes: [] };
        const docsData = docsResponse.ok ? await docsResponse.json() : { documents: [] };

        const noteItems = Array.isArray(notesData.notes)
          ? notesData.notes.map((note) => ({
              id: note.id || note.filename || note.title,
              title: cleanFileTitle(note.title || note.filename || "Untitled note"),
              icon: "📝",
              meta: note.fileType || "Note",
            }))
          : [];

        const docItems = Array.isArray(docsData.documents)
          ? docsData.documents.slice(0, 3).map((doc) => ({
              id: doc.document,
              title: cleanFileTitle(doc.document || "Knowledge graph document"),
              icon: "🧠",
              meta: `${doc.concept_count || 0} concepts`,
            }))
          : [];

        const merged = [...noteItems, ...docItems].slice(0, 3);
        setFiles(merged);
      } catch (err) {
        console.error("Error fetching recent files:", err);
        setFiles([]);
      } finally {
        setLoading(false);
      }
    };

    fetchRecentFiles();
    const intervalId = setInterval(fetchRecentFiles, DASHBOARD_REFRESH_MS);
    return () => clearInterval(intervalId);
  }, [email]);

  return (
    <div className='bg-gradient-to-br from-slate-800 via-slate-700 to-slate-800 p-6 rounded-xl shadow-2xl border border-purple-500/20 w-full'>
      <h2 className="text-2xl font-bold mb-4 text-white flex items-center">
        <span className="mr-2">📁</span>
        Recent Files
      </h2>

      <div className="bg-slate-900/50 backdrop-blur-sm rounded-lg p-4 mb-6 border border-purple-500/10">
        {loading ? (
          <p className="text-lg text-slate-400 text-center py-8">Loading...</p>
        ) : files.length > 0 ? (
          <ul className='space-y-3'>
            {files.map((file) => (
              <li key={file.id} className='bg-gradient-to-r from-slate-800/80 to-slate-700/80 p-4 rounded-xl text-white font-medium border border-purple-500/20 hover:border-purple-400/30 transition-all duration-300 flex items-center justify-between gap-3'>
                <div className="flex items-center min-w-0 flex-1">
                  <span className="mr-3 text-xl shrink-0">{file.icon}</span>
                  <span className="truncate pr-3">{file.title}</span>
                </div>
                <span className="text-xs text-slate-400 whitespace-nowrap shrink-0">{file.meta}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-center py-8">
            <p className="text-xl font-bold text-white">No Recent Files</p>
            <p className="text-sm text-slate-400 mt-2">Upload notes in Study to see them here</p>
          </div>
        )}
      </div>

      <a href="/study" className="block w-full bg-gradient-to-r from-purple-500 to-pink-500 text-white py-3 rounded-lg hover:shadow-xl hover:shadow-purple-500/30 transition-all duration-300 text-center font-semibold">
        Go to Study →
      </a>
    </div>
  );
};

// Quick Access Modules Component
const QuickAccessModules = () => {
  const modules = [
    {
      name: 'Schedule',
      icon: '📅',
      description: 'Manage your tasks and deadlines',
      link: '/schedule',
      gradient: 'from-cyan-500 to-blue-500',
      hoverShadow: 'hover:shadow-cyan-500/30'
    },
    {
      name: 'Study',
      icon: '📚',
      description: 'Access notes and study materials',
      link: '/study',
      gradient: 'from-purple-500 to-pink-500',
      hoverShadow: 'hover:shadow-purple-500/30'
    },
    {
      name: 'Insights',
      icon: '🎓',
      description: 'Socratic tutoring powered by your notes',
      link: '/mentor',
      gradient: 'from-amber-500 to-orange-500',
      hoverShadow: 'hover:shadow-amber-500/30'
    },
    {
      name: 'Placement',
      icon: '🚀',
      description: 'Skill mapping & placement prediction',
      link: '/career',
      gradient: 'from-teal-500 to-cyan-500',
      hoverShadow: 'hover:shadow-teal-500/30'
    }
  ];

  return (
    <div className='bg-gradient-to-br from-slate-800 via-slate-700 to-slate-800 p-6 rounded-xl shadow-2xl border border-cyan-500/20 w-full'>
      <h2 className="text-2xl font-bold mb-4 text-white flex items-center">
        <span className="mr-2">🚀</span>
        Quick Access
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {modules.map((module, index) => (
          <a
            key={index}
            href={module.link}
            className={`bg-gradient-to-r ${module.gradient} p-6 rounded-xl shadow-lg hover:shadow-xl ${module.hoverShadow} transition-all duration-300 hover:scale-105 border border-white/10`}
          >
            <div className="flex items-center gap-4 mb-3">
              <span className="text-4xl">{module.icon}</span>
              <h3 className="text-2xl font-bold text-white">{module.name}</h3>
            </div>
            <p className="text-white/90 text-sm">{module.description}</p>
          </a>
        ))}
      </div>
    </div>
  );
};

// Main Dashboard Component
export default function DashboardPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-8 relative">
      {/* Background effects similar to landing page */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-0 w-[700px] h-[700px] bg-gradient-to-tl from-purple-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
      </div>

      <div className="relative z-10">
        <Header />

        {/* Quick Access Modules */}
        <div className="mt-8">
          <QuickAccessModules />
        </div>

        {/* Tasks and Files */}
        <div className="mt-8 flex gap-8 flex-col lg:flex-row">
          <NextTask />
          <RecentFiles />
        </div>
      </div>
    </main>
  );
}
