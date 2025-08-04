'use client'

import { useSession, signOut } from "next-auth/react";
import { motion } from 'framer-motion';
import { 
    LayoutDashboard, 
    BookOpen, 
    Target, 
    Bot, 
    Calendar, 
    LogOut,
    Briefcase,
    Lightbulb,
    FileText
} from 'lucide-react';

// Reusable Card Component (JavaScript version)
const DashboardCard = ({ title, icon, children, className }) => (
    <motion.div 
        className={`bg-slate-800 p-6 rounded-xl shadow-lg ${className}`}
        variants={{
            hidden: { y: 20, opacity: 0 },
            visible: { y: 0, opacity: 1 }
        }}
    >
        <div className="flex items-center mb-4">
            {icon}
            <h3 className="text-xl font-bold ml-3 text-slate-100">{title}</h3>
        </div>
        <div>{children}</div>
    </motion.div>
);

export default function DashboardPage() {
    const { data: session } = useSession();

    const containerVariants = {
        hidden: { opacity: 0 },
        visible: {
            opacity: 1,
            transition: {
                staggerChildren: 0.1
            }
        }
    };
    
    return (
        <div className="flex h-screen bg-slate-900 text-slate-300">
            {/* Sidebar */}
            <aside className="w-64 bg-slate-950 p-6 flex flex-col justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-cyan-400 mb-10">TrackEneer</h1>
                    <nav className="space-y-2">
                        {[
                            { icon: <LayoutDashboard />, label: 'Dashboard' },
                            { icon: <BookOpen />, label: 'Study Planner' },
                            { icon: <Target />, label: 'Placement Insights' },
                            { icon: <Bot />, label: 'AI Assistant' },
                        ].map(item => (
                            <a key={item.label} href="#" className="flex items-center p-3 text-slate-300 hover:bg-slate-800 rounded-lg transition-colors">
                                {item.icon}
                                <span className="ml-4 font-semibold">{item.label}</span>
                            </a>
                        ))}
                    </nav>
                </div>
                <button onClick={() => signOut()} className="flex items-center p-3 w-full text-red-400 hover:bg-red-900/50 rounded-lg transition-colors">
                    <LogOut />
                    <span className="ml-4 font-semibold">Sign Out</span>
                </button>
            </aside>

            {/* Main Content */}
            <main className="flex-1 p-8 overflow-y-auto">
                {/* Welcome Header */}
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h2 className="text-3xl font-bold text-white">Welcome back, {session?.user?.name?.split(' ')[0]}!</h2>
                    <p className="text-slate-400 mt-1">Here's your snapshot for Saturday, August 2, 2025.</p>
                </motion.div>

                {/* Dashboard Grid */}
                <motion.div 
                    className="mt-8 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                    variants={containerVariants}
                    initial="hidden"
                    animate="visible"
                >
                    <DashboardCard title="Project Overview" icon={<Briefcase className="text-cyan-400" />} className="lg:col-span-2">
                        <p>Your 'AI Chatbot' project is 75% complete. Next milestone: User authentication.</p>
                        <div className="w-full bg-slate-700 rounded-full h-2.5 mt-3">
                            <div className="bg-cyan-400 h-2.5 rounded-full" style={{ width: '75%' }}></div>
                        </div>
                    </DashboardCard>
                    
                    <DashboardCard title="AI Assistant" icon={<Bot className="text-cyan-400" />}>
                        <p>Your personal AI mentor is ready to help. Ask about study plans, resume tips, or complex topics.</p>
                        <button className="mt-3 w-full bg-cyan-500/10 border border-cyan-500 text-cyan-400 font-bold py-2 px-4 rounded-lg hover:bg-cyan-500/20">Chat Now</button>
                    </DashboardCard>

                    <DashboardCard title="Study Planner" icon={<BookOpen className="text-cyan-400" />}>
                         <p>You have 3 study sessions and 1 project deadline this week. Stay focused!</p>
                        <a href="#" className="mt-3 inline-block text-cyan-400 font-semibold hover:underline">View Full Schedule &rarr;</a>
                    </DashboardCard>

                    <DashboardCard title="Placement Insights" icon={<Lightbulb className="text-cyan-400" />}>
                        <p>New insight: "Demand for 'Cloud Architecture' skills is up 15% this month."</p>
                        <a href="#" className="mt-3 inline-block text-cyan-400 font-semibold hover:underline">Explore Insights &rarr;</a>
                    </DashboardCard>
                    
                    <DashboardCard title="Daily Schedule" icon={<Calendar className="text-cyan-400" />}>
                       <ul className="space-y-2">
                           <li className="flex items-start"><span className="font-bold w-20">10 AM:</span><span>Data Structures Lecture</span></li>
                           <li className="flex items-start"><span className="font-bold w-20">2 PM:</span><span>Study Block: Aptitude</span></li>
                           <li className="flex items-start"><span className="font-bold w-20">7 PM:</span><span>Project Team Sync</span></li>
                       </ul>
                    </DashboardCard>
                </motion.div>
                
                {/* Footer */}
                <footer className="text-center mt-10 text-slate-500 text-sm">
                    TrackEneer &copy; 2025
                </footer>
            </main>
        </div>
    );
}