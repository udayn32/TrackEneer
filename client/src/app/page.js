// app/page.tsx
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-200 overflow-x-hidden relative">
      {/* Advanced Background Effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        {/* Animated gradient mesh */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950"></div>
        
        {/* Large animated orbs */}
        <div className="absolute top-0 left-0 w-[800px] h-[800px] bg-gradient-to-br from-cyan-500/20 via-blue-500/10 to-transparent rounded-full blur-3xl animate-pulse" style={{animationDuration: '4s'}}></div>
        <div className="absolute bottom-0 right-0 w-[900px] h-[900px] bg-gradient-to-tl from-purple-500/20 via-blue-500/10 to-transparent rounded-full blur-3xl animate-pulse" style={{animationDuration: '6s', animationDelay: '1s'}}></div>
        <div className="absolute top-1/3 right-1/4 w-[600px] h-[600px] bg-gradient-to-br from-pink-500/10 via-cyan-500/10 to-transparent rounded-full blur-3xl animate-pulse" style={{animationDuration: '5s', animationDelay: '2s'}}></div>
        
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:64px_64px]"></div>
        
        {/* Radial gradient overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(15,23,42,0.8)_100%)]"></div>
      </div>

      {/* Navbar */}
      <nav className="flex justify-between items-center px-8 py-5 bg-slate-950/60 backdrop-blur-xl border-b border-slate-800/50 sticky top-0 z-50 shadow-xl">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-lg flex items-center justify-center shadow-lg">
            <span className="text-white font-black text-xl">T</span>
          </div>
          <span className="text-2xl font-black text-cyan-400">TrackEneer</span>
        </div>
        <div className="hidden md:flex space-x-8 items-center">
          <a href="#features" className="text-base font-medium text-slate-300 hover:text-cyan-400 transition-colors">Features</a>
          <a href="#how-it-works" className="text-base font-medium text-slate-300 hover:text-cyan-400 transition-colors">How It Works</a>
        </div>
        <div className="flex space-x-4 items-center">
          <a href="/login" className="text-base font-medium text-slate-300 hover:text-cyan-400 transition-colors">Login</a>
          <a href="/register" className="bg-gradient-to-r from-cyan-400 to-blue-500 text-white font-bold px-6 py-2.5 rounded-full hover:shadow-xl hover:shadow-cyan-500/30 transition-all duration-300 hover:scale-105">Sign Up</a>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative text-center px-6 py-20 md:py-32 overflow-hidden">
        <div className="relative z-10">
          <h1 className="text-5xl md:text-7xl font-black mb-6 leading-tight">
            <span className="block text-cyan-400 text-6xl md:text-8xl mb-4">TrackEneer</span>
            <span className="block text-slate-300 text-3xl md:text-4xl font-normal mb-2">Your Engineering Career</span>
            <span className="block text-white text-4xl md:text-6xl font-black">Transformation Hub</span>
          </h1>
          
          <p className="text-lg md:text-xl text-slate-400 max-w-3xl mx-auto mb-12 leading-relaxed font-normal mt-8">
            Empowering students to excel in academics and placements with comprehensive resources and companion for study.
          </p>
          
          <div className="flex justify-center items-center">
            <a href="/register" className="group relative inline-flex items-center justify-center px-10 py-5 text-xl font-bold text-white bg-gradient-to-r from-cyan-400 to-blue-500 rounded-full shadow-2xl shadow-cyan-500/50 hover:shadow-cyan-500/70 transition-all duration-300 hover:scale-105">
              <span className="mr-2">🚀</span>
              Start Your Journey
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-6 py-20 max-w-7xl mx-auto relative">
         <div className="text-center mb-16">
            <h2 className="text-4xl md:text-5xl font-black text-white mb-4">
              Everything You Need to <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">Succeed</span>
            </h2>
            <p className="text-slate-400 text-lg mt-3 max-w-2xl mx-auto font-medium">From your first project to your final placement — we've got you covered.</p>
         </div>
         
         <div className="grid md:grid-cols-3 gap-8">
            {[
                { 
                  icon: "📊", 
                  title: "Project Dashboard", 
                  desc: "Organize your projects, assign tasks, and track your team's progress with AI-powered insights.",
                  color: "from-cyan-500/20 to-blue-500/20",
                  borderColor: "hover:border-cyan-400"
                },
                { 
                  icon: "📚", 
                  title: "Smart Study Planner", 
                  desc: "Upload syllabus, break down topics, and follow AI-recommended personalized study schedules.",
                  color: "from-purple-500/20 to-pink-500/20",
                  borderColor: "hover:border-purple-400"
                },
                { 
                  icon: "🎯", 
                  title: "Placement Insights", 
                  desc: "Explore company profiles, get alumni tips, and strategically target your dream job.",
                  color: "from-orange-500/20 to-amber-500/20",
                  borderColor: "hover:border-orange-400"
                },
            ].map((f, i) => (
                <div 
                  key={i} 
                  className={`group relative bg-gradient-to-br ${f.color} backdrop-blur-sm border border-slate-700/50 p-8 rounded-2xl ${f.borderColor} transition-all duration-300 hover:scale-105 hover:shadow-2xl cursor-pointer`}
                >
                    <div className="text-5xl mb-6 group-hover:scale-110 transition-transform duration-300">{f.icon}</div>
                    <h3 className="text-2xl font-black mb-4 text-white group-hover:text-cyan-400 transition-colors">{f.title}</h3>
                    <p className="text-slate-400 leading-relaxed font-medium">{f.desc}</p>
                    
                    {/* Decorative gradient orb */}
                    <div className="absolute -top-20 -right-20 w-40 h-40 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                </div>
            ))}
         </div>

         {/* Additional Features Grid */}
         <div className="grid md:grid-cols-2 gap-6 mt-16">
            {[
              { icon: "🔔", title: "Smart Notifications", desc: "Never miss a deadline with intelligent reminders" },
              { icon: "📈", title: "Progress Analytics", desc: "Track your growth with detailed performance metrics" },
              { icon: "🤝", title: "Team Collaboration", desc: "Work seamlessly with your project teammates" },
              { icon: "🎓", title: "AI Recommendations", desc: "Get personalized task suggestions based on your goals" },
            ].map((feature, i) => (
              <div key={i} className="flex items-start gap-4 p-6 bg-slate-900/30 backdrop-blur-sm border border-slate-800 rounded-xl hover:border-cyan-500/50 transition-all duration-300 hover:scale-102">
                <div className="text-3xl flex-shrink-0">{feature.icon}</div>
                <div>
                  <h4 className="text-lg font-bold text-white mb-1">{feature.title}</h4>
                  <p className="text-slate-400 text-sm font-medium">{feature.desc}</p>
                </div>
              </div>
            ))}
         </div>
      </section>

      {/* CTA Section */}
      <section className="px-6 py-20 max-w-5xl mx-auto text-center">
        <div className="relative bg-gradient-to-br from-cyan-500/10 via-blue-500/10 to-purple-500/10 backdrop-blur-sm border border-cyan-500/30 rounded-3xl p-12 md:p-16 overflow-hidden">
          {/* Background decoration */}
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/5 to-purple-500/5 rounded-3xl"></div>
          <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/10 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-purple-500/10 rounded-full blur-3xl"></div>
          
          <div className="relative z-10">
            <h2 className="text-4xl md:text-5xl font-black text-white mb-6">
              Smart <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">Study Scheduling</span> Made Easy
            </h2>
            <p className="text-xl text-slate-300 mb-8 max-w-3xl mx-auto font-medium leading-relaxed">
              Take control of your academic journey with intelligent study planning. Our AI-powered scheduler helps you organize tasks, set priorities, and manage deadlines effortlessly. From exam preparation to project tracking, stay on top of everything that matters.
            </p>
            <div className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto text-left">
              <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-xl p-5">
                <div className="text-3xl mb-3">📅</div>
                <h3 className="text-lg font-bold text-white mb-2">Automated Scheduling</h3>
                <p className="text-sm text-slate-400">AI creates optimal study plans based on your syllabus and deadlines</p>
              </div>
              <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-xl p-5">
                <div className="text-3xl mb-3">⏰</div>
                <h3 className="text-lg font-bold text-white mb-2">Smart Reminders</h3>
                <p className="text-sm text-slate-400">Never miss important tasks with real-time notifications</p>
              </div>
              <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-xl p-5">
                <div className="text-3xl mb-3">📊</div>
                <h3 className="text-lg font-bold text-white mb-2">Progress Tracking</h3>
                <p className="text-sm text-slate-400">Monitor your study patterns and optimize productivity</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="text-center px-6 py-12 border-t border-slate-800/50 mt-12 bg-slate-950/50 relative">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-center justify-center space-x-3 mb-6">
            <div className="w-8 h-8 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-black">T</span>
            </div>
            <span className="text-xl font-black bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">TrackEneer</span>
          </div>
          <p className="text-slate-400 text-sm mb-6 font-medium">Empowering engineering students to achieve their dreams.</p>
          
          {/* Team Credits */}
          <div className="mb-8">
            <div className="flex flex-wrap justify-center gap-x-8 gap-y-3">
              {[
                "Himanshu Pandey",
                "Kulsum Khan",
                "Bhanavi Pandey",
                "Uday Naik"
              ].map((name, i) => (
                <span key={i} className="text-lg font-black bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent hover:from-cyan-300 hover:to-blue-300 transition-all duration-200 hover:scale-105">
                  {name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </footer>
    </main>
  );
}
