"use client";
import React, { useState } from 'react';
import { 
  Brain, 
  Briefcase, 
  ShieldCheck, 
  Database, 
  Lightbulb, 
  Search, 
  Layers,
  GraduationCap,
  Activity,
  GitMerge,
  TrendingUp
} from 'lucide-react';

const InfographicSection = ({ title, icon: Icon, children, gradient, accentColor, iconColor, isActive, onClick }) => {
  return (
    <div 
      onClick={onClick}
      className={`relative transform transition-all duration-500 ease-in-out cursor-pointer group
        ${isActive ? 'scale-100 opacity-100' : 'scale-95 opacity-90 hover:scale-98'}
      `}
    >
      {/* Dynamic Gradient Glow */}
      <div className={`absolute -inset-0.5 bg-gradient-to-r ${gradient} rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-1000 group-hover:duration-200`}></div>
      
      <div className="relative bg-white dark:bg-slate-900 rounded-xl p-6 shadow-xl border border-slate-100 dark:border-slate-800 h-full">
        <div className="flex items-center gap-4 mb-4">
          <div className={`p-3 rounded-lg bg-opacity-10 ${accentColor}`}>
            <Icon className={`w-8 h-8 ${iconColor}`} />
          </div>
          <h3 className="text-xl font-bold text-slate-800 dark:text-white">{title}</h3>
          
          <div className="ml-auto">
            {isActive ? (
               <span className="text-xs font-semibold px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500">Active</span>
            ) : (
              <span className="text-xs font-semibold px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                Click to Expand
              </span>
            )}
          </div>
        </div>
        
        <div className={`transition-all duration-500 overflow-hidden ${isActive ? 'max-h-[600px] opacity-100' : 'max-h-24 opacity-70'}`}>
          {children}
        </div>
      </div>
      
      {/* Connector Line (Hidden on mobile or for last item) */}
      <div className="hidden lg:block absolute left-1/2 -bottom-8 w-1 h-8 bg-slate-200 dark:bg-slate-700 -translate-x-1/2 z-0 last:hidden"></div>
    </div>
  );
};

const PipelineStep = ({ label, sublabel }) => (
  <div className="flex flex-col items-center text-center p-2 min-w-[80px]">
    <div className="w-3 h-3 rounded-full bg-blue-500 mb-2 shadow-sm"></div>
    <span className="text-sm font-bold text-slate-700 dark:text-slate-300 leading-tight">{label}</span>
    <span className="text-[10px] uppercase tracking-wide text-slate-500 mt-1">{sublabel}</span>
  </div>
);

const App = () => {
  const [activeSection, setActiveSection] = useState('foundation');

  const sections = [
    {
      id: 'foundation',
      title: '1. The Semantic Backbone',
      icon: Database,
      gradient: 'from-blue-500 to-cyan-500',
      accentColor: 'bg-blue-500',
      iconColor: 'text-blue-500',
      content: (
        <div className="space-y-4 pt-2">
          <p className="text-slate-600 dark:text-slate-300">
            Automated conversion of unstructured data (PDFs, Notes) into a structured <strong>Educational Knowledge Graph (EduKG)</strong>.
          </p>
          <div className="bg-slate-50 dark:bg-slate-800 p-4 rounded-lg border border-slate-200 dark:border-slate-700 overflow-x-auto">
            <h4 className="font-semibold text-xs text-slate-500 uppercase mb-3 tracking-wider">Construction Pipeline</h4>
            <div className="flex justify-between items-start gap-4 min-w-[400px] relative">
              {/* Connector line behind dots */}
              <div className="absolute top-[5px] left-4 right-4 h-0.5 bg-slate-200 dark:bg-slate-600 -z-10"></div>
              
              <PipelineStep label="Input" sublabel="PDF/OCR" />
              <PipelineStep label="Segment" sublabel="Hierarchical" />
              <PipelineStep label="Extract" sublabel="SqueezeBERT" />
              <PipelineStep label="Enrich" sublabel="Wiki/DBpedia" />
              <PipelineStep label="Graph" sublabel="Neo4j" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded border border-blue-100 dark:border-blue-800 text-blue-800 dark:text-blue-300">
              <strong>Key Tech:</strong> SIFRank, SqueezeBERT
            </div>
            <div className="bg-cyan-50 dark:bg-cyan-900/20 p-3 rounded border border-cyan-100 dark:border-cyan-800 text-cyan-800 dark:text-cyan-300">
              <strong>Outcome:</strong> Maps prerequisites (e.g., Recursion → Merge Sort).
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'engine',
      title: '2. The Cognitive Engine',
      icon: Brain,
      gradient: 'from-purple-500 to-pink-500',
      accentColor: 'bg-purple-500',
      iconColor: 'text-purple-500',
      content: (
        <div className="space-y-4 pt-2">
          <p className="text-slate-600 dark:text-slate-300">
            Moving beyond simple search to <strong>GraphRAG</strong> (Retrieval-Augmented Generation) and Socratic Mentorship.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 bg-white dark:bg-slate-800 p-4 rounded shadow-sm border border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-2 mb-2 text-purple-600">
                <GitMerge size={18} />
                <span className="font-bold text-sm">GraphRAG</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">Traverses the Knowledge Graph to find multi-hop answers (e.g., relating React 'State' to JS 'Variables').</p>
            </div>
            <div className="flex-1 bg-white dark:bg-slate-800 p-4 rounded shadow-sm border border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-2 mb-2 text-pink-600">
                <Lightbulb size={18} />
                <span className="font-bold text-sm">Socratic AI</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">Uses Chain-of-Thought (CoT) prompts to guide students with questions rather than giving answers.</p>
            </div>
          </div>
          <div className="flex items-start gap-3 text-xs text-red-600 bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-100 dark:border-red-800">
            <ShieldCheck size={16} className="mt-0.5 shrink-0" />
            <span><strong>Guardrails:</strong> Hallucination mitigation via source citation & confidence thresholding to ensure academic integrity.</span>
          </div>
        </div>
      )
    },
    {
      id: 'learner',
      title: '3. The Learner Model',
      icon: Activity,
      gradient: 'from-emerald-500 to-teal-500',
      accentColor: 'bg-emerald-500',
      iconColor: 'text-emerald-500',
      content: (
        <div className="space-y-4 pt-2">
          <p className="text-slate-600 dark:text-slate-300">
            Deep Knowledge Tracing (DKT) tracks mastery over time, replacing simple "Pass/Fail" metrics.
          </p>
          
          <div className="bg-slate-800 text-white p-5 rounded-lg font-mono text-xs relative overflow-hidden shadow-inner">
             <div className="absolute top-0 right-0 p-4 opacity-10"><Activity size={64} /></div>
             <p className="mb-3 border-b border-slate-700 pb-2"><span className="text-emerald-400 font-bold">Model:</span> PSI-KT (Predictive, Scalable, Interpretable)</p>
             <p className="mb-3"><span className="text-blue-400 font-bold">Input:</span> Interaction History + Time Decay</p>
             <p><span className="text-pink-400 font-bold">Output:</span> Mastery Probability & Forgetting Curve</p>
          </div>

          <div className="bg-yellow-50 dark:bg-yellow-900/20 p-3 rounded-lg border border-yellow-200 dark:border-yellow-700">
            <h4 className="font-bold text-yellow-800 dark:text-yellow-400 text-sm mb-1 flex items-center gap-2">
              <Search size={14}/> Automated Gap Analysis
            </h4>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              If a student fails "Neural Networks", the system traces back the graph to find the root cause (e.g., weak "Linear Algebra") and recommends remedial content.
            </p>
          </div>
        </div>
      )
    },
    {
      id: 'career',
      title: '4. Career Readiness',
      icon: Briefcase,
      gradient: 'from-orange-500 to-red-500',
      accentColor: 'bg-orange-500',
      iconColor: 'text-orange-500',
      content: (
        <div className="space-y-4 pt-2">
          <p className="text-slate-600 dark:text-slate-300">
            Bridging the Academic-Industry divide via the <strong>"Placify" Architecture</strong>.
          </p>
          
          <div className="relative pl-6 border-l-2 border-orange-300 dark:border-orange-700 space-y-4">
             <div>
               <h4 className="font-bold text-sm text-slate-800 dark:text-white">Syllabus2Skill Pipeline</h4>
               <p className="text-xs text-slate-500">Maps academic terms (e.g., "Relational Algebra") to industry skills (e.g., "SQL") using ESCO/O*NET taxonomies.</p>
             </div>
             <div>
               <h4 className="font-bold text-sm text-slate-800 dark:text-white">Predictive Placement</h4>
               <p className="text-xs text-slate-500">Uses Random Forest/XGBoost to predict placement probability based on CGPA, Skills, and Projects.</p>
             </div>
             <div>
               <h4 className="font-bold text-sm text-slate-800 dark:text-white">Explainable AI (XAI)</h4>
               <p className="text-xs text-slate-500">Uses SHAP values to tell students <em>why</em> they aren't ready (e.g., "Low internship experience").</p>
             </div>
          </div>
        </div>
      )
    }
  ];

  return (
    <div className="w-full min-h-screen bg-slate-50 dark:bg-slate-950 font-sans text-slate-900 dark:text-slate-100">
      
      {/* Header */}
      <header className="bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-50 shadow-sm">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-2 rounded-lg text-white shadow-lg shadow-blue-500/30">
              <GraduationCap size={24} />
            </div>
            <div>
              <h1 className="text-xl font-bold leading-tight">Cognitive Learning Ecosystem</h1>
              <p className="text-xs text-slate-500 font-medium">AI-Powered Precision Education Framework</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-12">
        
        {/* Intro Section */}
        <div className="mb-12 text-center">
          <h2 className="text-3xl font-extrabold mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-purple-600">
            Solving the "2 Sigma Problem" at Scale
          </h2>
          <p className="text-lg text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
            Traditional Learning Management Systems are static. This architecture proposes a dynamic, intelligent agent that acts as a 
            <span className="text-blue-600 font-bold mx-1">Socratic Tutor</span>, 
            <span className="text-emerald-600 font-bold mx-1">Progress Tracker</span>, and 
            <span className="text-orange-600 font-bold mx-1">Career Coach</span>.
          </p>
        </div>

        {/* Interactive Flow */}
        <div className="relative space-y-8 lg:space-y-12 pl-4 lg:pl-0">
          {/* Vertical Guide Line for mobile */}
          <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-slate-200 dark:bg-slate-800 lg:hidden"></div>

          {sections.map((section) => (
            <InfographicSection 
              key={section.id}
              {...section}
              isActive={activeSection === section.id}
              onClick={() => setActiveSection(section.id)}
            />
          ))}
        </div>

        {/* Summary Footer */}
        <div className="mt-16 grid md:grid-cols-3 gap-6 border-t border-slate-200 dark:border-slate-800 pt-8">
          <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-blue-600">
               <Layers size={20} />
               <h3 className="font-bold">Tech Stack</h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">Neo4j (Graph), Pinecone (Vector), LangChain (Orchestrator), GPT-4o (Reasoning), FastAPI.</p>
          </div>
          <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-emerald-600">
               <ShieldCheck size={20} />
               <h3 className="font-bold">Ethics</h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">FERPA/GDPR compliance, IEEE P2863 AI Governance, Bias Auditing, and Data Anonymization.</p>
          </div>
          <div className="p-5 rounded-xl bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-purple-600">
               <TrendingUp size={20} />
               <h3 className="font-bold">Goal</h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">To transform passive content consumption into active, personalized, career-aligned cognitive growth.</p>
          </div>
        </div>

      </main>
    </div>
  );
};

export default App;