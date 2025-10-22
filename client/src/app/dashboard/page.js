'use client'

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, "") || "http://localhost:5000";

// Header Component
const Header = () => {
  const { data: session } = useSession();
  
  return (
    <header className="bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500 text-white p-6 rounded-xl flex flex-col md:flex-row items-center justify-between gap-4 shadow-2xl shadow-cyan-500/20">
      
      {/* Left side: Welcome */}
      <div className="flex items-center gap-4">
        <h1 className="text-3xl font-bold">Welcome, {session?.user?.name || 'User'}</h1>
      </div>

      {/* Middle: Quote */}
      <div className="text-center flex-1">
        <p className="text-xl md:text-2xl italic font-serif">
          Push harder than yesterday, if you want a different tomorrow
        </p>
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
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchNextTasks = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/upcoming-deadlines`);
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
  }, []);

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
            <div key={index} className="bg-gradient-to-r from-slate-800/80 to-slate-700/80 rounded-lg p-4 shadow-lg border border-cyan-500/20 hover:border-cyan-400/40 hover:shadow-cyan-500/20 transition-all duration-300">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <h3 className="text-lg font-bold text-white">{task.title || 'Untitled Task'}</h3>
                  <p className="text-sm text-slate-400 mt-1">
                    {task.dueDate && `📅 Due: ${formatDueDate(task.dueDate)}`}
                  </p>
                </div>
                {task.priority && (
                  <span className={`px-3 py-1 rounded-full text-xs font-semibold whitespace-nowrap ${
                    task.priority === 'High' ? 'bg-gradient-to-r from-red-500 to-pink-500 text-white' :
                    task.priority === 'Medium' ? 'bg-gradient-to-r from-yellow-500 to-orange-500 text-white' :
                    'bg-gradient-to-r from-green-500 to-emerald-500 text-white'
                  }`}>
                    {task.priority}
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
      
      <a href="/schedule" className="block w-full bg-gradient-to-r from-cyan-400 to-blue-500 text-white py-3 rounded-lg hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 hover:scale-105 text-center font-semibold">
        Go to Schedule →
      </a>
    </div>
  );
};

// Recent Files Component
const RecentFiles = () => {
  return (
    <div className='bg-gradient-to-br from-slate-800 via-slate-700 to-slate-800 p-6 rounded-xl shadow-2xl border border-purple-500/20 w-full'>
      <h2 className="text-2xl font-bold mb-4 text-white flex items-center">
        <span className="mr-2">📁</span>
        Recent Files
      </h2>
      
      <div className="bg-slate-900/50 backdrop-blur-sm rounded-lg p-4 mb-6 border border-purple-500/10">
        <ul className='space-y-3'>
          <li className='bg-gradient-to-r from-slate-800/80 to-slate-700/80 p-4 rounded-lg text-white font-medium border border-purple-500/20 hover:border-purple-400/40 hover:shadow-lg hover:shadow-purple-500/20 transition-all duration-300 flex items-center'>
            <span className="mr-3 text-xl">📝</span>
            DSA Notes
          </li>
          <li className='bg-gradient-to-r from-slate-800/80 to-slate-700/80 p-4 rounded-lg text-white font-medium border border-purple-500/20 hover:border-purple-400/40 hover:shadow-lg hover:shadow-purple-500/20 transition-all duration-300 flex items-center'>
            <span className="mr-3 text-xl">📚</span>
            Lecture 1 - CN
          </li>
          <li className='bg-gradient-to-r from-slate-800/80 to-slate-700/80 p-4 rounded-lg text-white font-medium border border-purple-500/20 hover:border-purple-400/40 hover:shadow-lg hover:shadow-purple-500/20 transition-all duration-300 flex items-center'>
            <span className="mr-3 text-xl">📄</span>
            Data mining QB
          </li>
        </ul>
      </div>
      
      <a href="/study" className="w-full bg-gradient-to-r from-purple-500 to-pink-500 text-white py-3 rounded-lg hover:shadow-xl hover:shadow-purple-500/30 transition-all duration-300 hover:scale-105 font-semibold">
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
      name: 'Placement',
      icon: '🏢',
      description: 'Research companies and prepare',
      link: '/placement',
      gradient: 'from-blue-500 to-indigo-600',
      hoverShadow: 'hover:shadow-blue-500/30'
    },
    {
      name: 'Insights',
      icon: '💡',
      description: 'Get personalized guidance',
      link: '/insights',
      gradient: 'from-emerald-500 to-teal-500',
      hoverShadow: 'hover:shadow-emerald-500/30'
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