// app/page.tsx
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-slate-800 text-slate-200">
      {/* Navbar */}
      <nav className="flex justify-between items-center px-6 py-4 bg-slate-950/70 backdrop-blur-lg border-b border-slate-800 sticky top-0 z-10">
        <div className="text-2xl font-bold text-cyan-400">TrackEneer</div>
        <div className="space-x-4 flex items-center">
          <a href="/login" className="text-sm font-medium text-slate-300 hover:text-cyan-400 transition">Login</a>
          <a href="/register" className="bg-cyan-500 text-slate-900 font-bold px-4 py-2 rounded-md hover:bg-cyan-400 transition">Sign Up</a>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="text-center px-6 py-24 md:py-32">
        <h1 className="text-4xl md:text-6xl font-extrabold mb-6 text-white bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text ">
          Track Your Engineering Journey, Smarter
        </h1>
        <p className="text-lg text-slate-300 max-w-3xl mx-auto mb-10">
          Projects, Study Plans, Scheduling & Placements — All in one AI-powered dashboard.
        </p>
        <a href="/register" className="inline-block bg-white text-slate-900 text-lg font-bold px-8 py-3 rounded-full shadow-lg hover:bg-slate-200 transition-transform hover:scale-105">
          Get Started for Free
        </a>
      </section>

      {/* Features */}
      <section className="px-6 py-16 max-w-7xl mx-auto">
         <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-white">Everything You Need to Succeed</h2>
            <p className="text-slate-400 mt-2">From your first project to your final placement.</p>
         </div>
         <div className="grid md:grid-cols-3 gap-8">
            {[
                { title: "Project Dashboard", desc: "Organize your projects, assign tasks, and track your team’s progress." },
                { title: "Smart Study Planner", desc: "Upload syllabus, break down topics, and follow AI-recommended schedules." },
                { title: "Placement Insights", desc: "Explore company profiles, get alumni tips, and target your dream job." },
            ].map((f, i) => (
                <div 
                  key={i} 
                  className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 p-8 rounded-xl hover:border-cyan-400 transition-colors"
                >
                    <h3 className="text-xl font-semibold mb-3 text-white">{f.title}</h3>
                    <p className="text-slate-400">{f.desc}</p>
                </div>
            ))}
         </div>
      </section>

      {/* Footer */}
      <footer className="text-center text-sm text-slate-400 py-8 border-t border-slate-800 mt-12">
        © {new Date().getFullYear()} TrackEneer.
      </footer>
    </main>
  );
}