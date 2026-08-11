"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

const API_BASE = process.env.NEXT_PUBLIC_SCHEDULER_API?.replace(/\/$/, "") || "http://localhost:5000";

/**
 * TimetableComponent - An AI-powered study schedule generator with document extraction
 * 
 * @component
 * @description
 * A comprehensive React component that manages the entire workflow for generating optimized study schedules.
 * It handles:
 * 1. **Syllabus Management**: Upload and extract course/subject information from PDF files using OCR + AI
 * 2. **Exam Timetable Extraction**: Parse exam dates, times, and venues from timetable PDFs
 * 3. **Schedule Generation**: Use NSGA-II (multi-objective genetic algorithm) to create an optimized 2-month study plan
 * 4. **Calendar Integration**: Save generated schedules to user's calendar
 * 5. **Knowledge Graph Integration**: Store timetables in the system's knowledge graph for future reference
 * 
 * @state
 * - `loading` - Shows loading state during file uploads
 * - `message` - Toast notification system (info/success/error)
 * - `syllabusFile`, `examTimetableFile` - Currently selected PDF files
 * - `extractedCourses`, `extractedExams` - Parsed data from uploaded documents
 * - `dragActive` - Tracks drag-and-drop state
 * - `activeTab` - Controls which tab is displayed (syllabus/exams/schedule)
 * - `studySchedule` - Generated 2-month study plan with daily sessions and tasks
 * - `generatingSchedule`, `saving`, `addingToSystem` - Loading states for async operations
 * 
 * @features
 * - **Drag & Drop Upload**: Intuitive file upload experience
 * - **AI Document Parsing**: Extracts structured data from unstructured PDFs
 * - **Multi-Objective Optimization**: NSGA-II algorithm balances multiple study goals
 * - **Intelligent Task Breakdown**: Splits each study session into typed tasks (learn/practice/review/notes)
 * - **Priority-Based Scheduling**: High-priority exams get more study time
 * - **Weekend Awareness**: Considers weekends differently in scheduling
 * - **User Privacy**: Files are processed temporarily and deleted after extraction
 * 
 * @requires useSession from next-auth (for email identification)
 * @requires API_BASE environment variable for backend communication
 * 
 * @returns {JSX.Element} Three-tab interface with upload, extraction, and schedule display areas
 */
export const TimetableComponent = () => {
    const { data: session } = useSession();
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<{ text: string; type: "info" | "success" | "error" } | null>(null);
    const [syllabusFile, setSyllabusFile] = useState<File | null>(null);
    const [extractedCourses, setExtractedCourses] = useState<any[]>([]);
    const [examTimetableFile, setExamTimetableFile] = useState<File | null>(null);
    const [extractedExams, setExtractedExams] = useState<any[]>([]);
    const [dragActive, setDragActive] = useState(false);
    const [activeTab, setActiveTab] = useState("syllabus");
    const [scheduleOptions, setScheduleOptions] = useState<any[]>([]);  // All NSGA-II Pareto plans
    const [selectedPlanIndex, setSelectedPlanIndex] = useState(0);       // Which plan the user selected
    const [studySchedule, setStudySchedule] = useState<any | null>(null);
    const [generatingSchedule, setGeneratingSchedule] = useState(false);
    const [saving, setSaving] = useState(false);
    const [addingToSystem, setAddingToSystem] = useState(false);

    const userEmail = session?.user?.email || "demo@trackeneer.local";

    // Fetch previously extracted courses on load
    useEffect(() => {
        fetchExtractedCourses();
    }, [userEmail]);

    const fetchExtractedCourses = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/documents/status?email=${userEmail}`);
            if (res.ok) {
                const data = await res.json();
                if (data.syllabus?.subjects) {
                    setExtractedCourses(data.syllabus.subjects);
                }
                if (data.exam_timetable?.exams) {
                    setExtractedExams(data.exam_timetable.exams);
                }
            }
        } catch (err) {
            console.log("Backend not available");
        }
    };

    const showMessage = (text: string, type: "info" | "success" | "error" = "info") => {
        setMessage({ text, type });
        setTimeout(() => setMessage(null), 6000);
    };

    const uploadExamTimetable = async () => {
        if (!examTimetableFile) {
            showMessage("Please select an exam timetable PDF", "error");
            return;
        }

        setLoading(true);
        showMessage("Uploading and extracting exam timetable with OCR + AI...", "info");

        const formData = new FormData();
        // Corrected parameter name to match backend: exam_timetable
        formData.append("exam_timetable", examTimetableFile);
        formData.append("email", userEmail);

        try {
            const res = await fetch(`${API_BASE}/api/documents/upload/all`, {
                method: "POST",
                body: formData
            });

            const data = await res.json();

            if (res.ok) {
                const results = data.results?.exam_timetable;
                if (results && !results.error) {
                    showMessage(`✅ Exam timetable extracted! Found ${results.exams_count || 0} exams.`, "success");
                    setExtractedExams(results.exams || []);
                    setExamTimetableFile(null);
                } else {
                    showMessage(results?.error || "Upload failed", "error");
                }
            } else {
                showMessage(data.detail || "Upload failed", "error");
            }
        } catch (err: any) {
            showMessage(`Error: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    };

    const uploadSyllabus = async () => {
        if (!syllabusFile) {
            showMessage("Please select a syllabus PDF", "error");
            return;
        }
        setLoading(true);
        showMessage("Uploading and extracting syllabus...", "info");

        const formData = new FormData();
        formData.append("syllabus", syllabusFile);
        formData.append("email", userEmail);

        try {
            const res = await fetch(`${API_BASE}/api/documents/upload/all`, {
                method: "POST",
                body: formData
            });
            const data = await res.json();

            if (res.ok) {
                const results = data.results?.syllabus;
                if (results && !results.error) {
                    showMessage(`✅ Syllabus extracted! Found ${results.subjects_count || 0} subjects.`, "success");
                    setExtractedCourses(results.subjects || []);
                    setSyllabusFile(null);
                } else {
                    showMessage(results?.error || "Upload failed", "error");
                }
            } else {
                showMessage(data.detail || "Upload failed", "error");
            }
        } catch (err: any) {
            showMessage(`Error: ${err.message}`, "error");
        } finally {
            setLoading(false);
        }
    };

    const generateStudySchedule = async () => {
        if (extractedExams.length === 0) {
            showMessage("Please upload an exam timetable first", "error");
            return;
        }

        setGeneratingSchedule(true);
        showMessage("🧬 Running NSGA-II optimization on server... This may take a moment.", "info");

        try {
            const response = await fetch(`${API_BASE}/api/study/generate`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ exams: extractedExams, email: userEmail }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Failed to generate schedule");
            }

            const result = await response.json();

            // NSGA-II returns { schedules: [ {id, label, schedule, objectives, ...}, ... ] }
            const rawSchedules = result.schedules || (result.schedule ? [{ id: 'default', label: 'Study Plan', schedule: result.schedule }] : []);

            if (!rawSchedules.length) {
                throw new Error("No schedules returned from the optimizer");
            }

            const parseDaySchedule = (day: any) => ({
                date: new Date(day.date),
                dateLabel: day.date_label,
                isWeekend: day.is_weekend,
                sessions: (day.sessions || []).map((sess: any) => ({
                    subject: sess.subject,
                    hours: sess.hours,
                    startTime: sess.start_time,
                    endTime: sess.end_time,
                    priority: sess.priority,
                    daysUntilExam: sess.days_until_exam,
                    tasks: (sess.tasks || []).map((t: any) => ({
                        task: t.task,
                        duration: t.duration,
                        type: t.type
                    }))
                }))
            });

            const parsedOptions = rawSchedules.map((opt: any) => ({
                id: opt.id,
                label: opt.label,
                objectives: opt.objectives || {},
                numDays: opt.num_days,
                numSubjects: opt.num_subjects,
                days: (opt.schedule || []).map(parseDaySchedule)
            }));

            setScheduleOptions(parsedOptions);
            setSelectedPlanIndex(0);
            setStudySchedule(parsedOptions[0].days);
            showMessage(`✅ ${parsedOptions.length} optimized plans generated (${parsedOptions[0].days.length} days each)!`, "success");
            setActiveTab("schedule");

        } catch (err: any) {
            console.error("Schedule generation error:", err);
            showMessage(`Error generating schedule: ${err.message}`, "error");
        } finally {
            setGeneratingSchedule(false);
        }
    };

    const saveScheduleToCalendar = async () => {
        if (!studySchedule || studySchedule.length === 0) return;
        setSaving(true);
        showMessage("Saving schedule to your calendar...", "info");

        try {
            const formattedSchedule = studySchedule.map((day: any) => ({
                date: day.date instanceof Date ? day.date.toISOString().split('T')[0] : day.date,
                sessions: day.sessions.map((s: any) => ({
                    subject: s.subject,
                    start_time: s.startTime,
                    end_time: s.endTime,
                    priority: s.priority,
                    tasks: s.tasks
                }))
            }));

            const res = await fetch(`${API_BASE}/api/study/save`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    schedule: formattedSchedule,
                    email: userEmail
                })
            });

            const data = await res.json();

            if (res.ok) {
                showMessage(`✅ ${data.message}`, "success");
            } else {
                throw new Error(data.detail || "Failed to save");
            }
        } catch (err: any) {
            showMessage(`Error saving schedule: ${err.message}`, "error");
        } finally {
            setSaving(false);
        }
    };

    const addToKnowledgeGraph = async () => {
        if (!studySchedule || studySchedule.length === 0) return;
        setAddingToSystem(true);
        showMessage("Adding timetable to knowledge graph...", "info");

        try {
            const formattedSchedule = studySchedule.map((day: any) => ({
                date: day.date instanceof Date ? day.date.toISOString().split('T')[0] : day.date,
                sessions: day.sessions.map((s: any) => ({
                    subject: s.subject,
                    start_time: s.startTime,
                    end_time: s.endTime,
                    hours: s.hours,
                    priority: s.priority,
                    days_until_exam: s.daysUntilExam,
                    tasks: s.tasks
                }))
            }));

            const res = await fetch(`${API_BASE}/api/study/add-to-knowledge-graph`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    schedule: formattedSchedule,
                    email: userEmail,
                    name: `NSGA-II Timetable (${new Date().toLocaleDateString()})`
                })
            });

            const data = await res.json();

            if (res.ok) {
                showMessage(
                    `\u2705 Added to system! ${data.totalSessions} sessions, ${data.totalHours}h across ${data.subjects?.length || 0} subjects linked to knowledge graph.`,
                    "success"
                );
            } else {
                throw new Error(data.detail || "Failed to add to knowledge graph");
            }
        } catch (err: any) {
            showMessage(`Error: ${err.message}`, "error");
        } finally {
            setAddingToSystem(false);
        }
    };

    const handleDrag = (e: any) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e: any) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const file = e.dataTransfer.files[0];
            if (file.type === "application/pdf") {
                if (activeTab === "syllabus") setSyllabusFile(file);
                else setExamTimetableFile(file);
            } else {
                showMessage("Please upload a PDF file", "error");
            }
        }
    };

    const handleFileSelect = (e: any) => {
        if (e.target.files && e.target.files[0]) {
            if (activeTab === "syllabus") setSyllabusFile(e.target.files[0]);
            else setExamTimetableFile(e.target.files[0]);
        }
    };

    const getDifficultyColor = (difficulty: string) => {
        switch (difficulty) {
            case "hard": return "text-red-400 bg-red-500/20 border-red-500/30";
            case "medium": return "text-yellow-400 bg-yellow-500/20 border-yellow-500/30";
            case "easy": return "text-green-400 bg-green-500/20 border-green-500/30";
            default: return "text-slate-400 bg-slate-500/20 border-slate-500/30";
        }
    };

    const getTaskTypeColor = (type: string) => {
        switch (type) {
            case "learn": return "bg-blue-500/20 text-blue-300 border-blue-500/30";
            case "practice": return "bg-green-500/20 text-green-300 border-green-500/30";
            case "review": return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
            case "notes": return "bg-purple-500/20 text-purple-300 border-purple-500/30";
            default: return "bg-slate-500/20 text-slate-300 border-slate-500/30";
        }
    };

    const getPriorityBadge = (priority: string) => {
        switch (priority) {
            case "high": return "🔴 URGENT";
            case "medium": return "🟡 Soon";
            default: return "🟢 Normal";
        }
    };

    const safeDateFromISO = (isoDate: string) => {
        if (!isoDate) return null;
        const match = isoDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (!match) return null;
        const [_, y, m, d] = match;
        const dateObj = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
        return isNaN(dateObj.getTime()) ? null : dateObj;
    };

    const normalizedExams = extractedExams.map((exam) => {
        const dateObj = safeDateFromISO(exam.date);
        return {
            ...exam,
            dateLabel: dateObj ? dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "TBA",
            dayName: dateObj ? dateObj.toLocaleDateString("en-US", { weekday: "long" }) : "TBA",
            timeLabel: exam.start_time ? `${exam.start_time} - ${exam.end_time || '?'}` : "TBA"
        };
    });

    return (
        <div className="space-y-6">
            <div className="flex space-x-4 border-b border-slate-700/50 pb-2">
                <button
                    onClick={() => setActiveTab("syllabus")}
                    className={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === "syllabus" ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40" : "text-slate-400 hover:text-white"}`}
                >
                    📚 Syllabus
                </button>
                <button
                    onClick={() => setActiveTab("exams")}
                    className={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === "exams" ? "bg-purple-500/20 text-purple-400 border border-purple-500/40" : "text-slate-400 hover:text-white"}`}
                >
                    📝 Exam Timetable
                </button>
                <button
                    onClick={() => setActiveTab("schedule")}
                    className={`px-4 py-2 text-sm font-bold rounded-lg transition-all ${activeTab === "schedule" ? "bg-green-500/20 text-green-400 border border-green-500/40" : "text-slate-400 hover:text-white"}`}
                >
                    🧬 Study Schedule
                </button>
            </div>

            {message && (
                <div className={`p-4 rounded-lg border text-sm font-bold flex items-center justify-between ${message.type === "success" ? "bg-green-500/20 text-green-400 border-green-500/40" :
                    message.type === "error" ? "bg-red-500/20 text-red-400 border-red-500/40" :
                        "bg-blue-500/20 text-blue-400 border-blue-500/40"
                    }`}>
                    <span>{message.text}</span>
                    <button onClick={() => setMessage(null)} className="ml-4 hover:opacity-75">✕</button>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                <div className="space-y-4">
                    {activeTab === "schedule" ? (
                        <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-green-500/20 shadow-2xl">
                            <h2 className="text-xl font-bold mb-4 flex items-center gap-2 text-white">
                                <span className="text-2xl">🧬</span>
                                NSGA-II Study Schedule Generator
                            </h2>
                            <p className="text-slate-400 text-sm mb-6">
                                Generate an optimized 2-month study schedule using multi-objective optimization.
                            </p>

                            {extractedExams.length === 0 ? (
                                <div className="text-center py-8 text-slate-500">
                                    <p className="text-4xl mb-2">📅</p>
                                    <p>Upload an exam timetable first to generate a study schedule</p>
                                </div>
                            ) : (
                                <div className="flex flex-col gap-4">
                                    <button
                                        onClick={generateStudySchedule}
                                        disabled={generatingSchedule}
                                        className={`w-full px-6 py-4 rounded-lg font-bold transition-all ${generatingSchedule
                                            ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                                            : "bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white shadow-lg hover:shadow-green-500/25"
                                            }`}
                                    >
                                        {generatingSchedule ? "⚙️ Running NSGA-II..." : "🧬 Generate Optimized Schedule"}
                                    </button>
                                    <p className="text-center text-slate-400 text-xs">
                                        Based on {extractedExams.length} extracted exams
                                    </p>

                                    {/* Plan selector tabs (shown when multiple NSGA-II solutions exist) */}
                                    {scheduleOptions.length > 1 && (
                                        <div className="space-y-2">
                                            <p className="text-xs text-slate-400 font-semibold">Choose a plan:</p>
                                            <div className="grid grid-cols-1 gap-2">
                                                {scheduleOptions.map((opt, idx) => (
                                                    <button
                                                        key={opt.id}
                                                        onClick={() => {
                                                            setSelectedPlanIndex(idx);
                                                            setStudySchedule(opt.days);
                                                        }}
                                                        className={`w-full text-left px-4 py-3 rounded-lg border text-sm font-medium transition-all ${
                                                            idx === selectedPlanIndex
                                                                ? "border-green-500/50 bg-green-500/10 text-green-400"
                                                                : "border-slate-700 bg-slate-800/50 text-slate-300 hover:border-slate-500"
                                                        }`}
                                                    >
                                                        <div className="flex items-center justify-between">
                                                            <span>{idx === 0 ? "⚖️" : idx === 1 ? "😌" : "🎯"} {opt.label}</span>
                                                            {idx === selectedPlanIndex && <span className="text-green-400 text-xs">✓ Selected</span>}
                                                        </div>
                                                        {opt.objectives && (
                                                            <div className="flex gap-3 mt-1 text-[10px] text-slate-500">
                                                                <span>Cramming: {opt.objectives.cramming?.toFixed(2) ?? '—'}</span>
                                                                <span>Switching: {opt.objectives.switching?.toFixed(2) ?? '—'}</span>
                                                                <span>Revision: {opt.objectives.revision?.toFixed(2) ?? '—'}</span>
                                                            </div>
                                                        )}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {studySchedule && studySchedule.length > 0 && (
                                        <div className="space-y-2">
                                            <button
                                                onClick={saveScheduleToCalendar}
                                                disabled={saving}
                                                className={`w-full px-4 py-3 rounded-lg font-bold text-sm transition-all ${saving
                                                    ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                                                    : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20"
                                                    }`}
                                            >
                                                {saving ? "Saving..." : "💾 Save Tasks to Calendar"}
                                            </button>
                                            <button
                                                onClick={addToKnowledgeGraph}
                                                disabled={addingToSystem}
                                                className={`w-full px-4 py-3 rounded-lg font-bold text-sm transition-all ${addingToSystem
                                                    ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                                                    : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-lg shadow-purple-500/20"
                                                    }`}
                                            >
                                                {addingToSystem ? "⏳ Adding..." : "🧠 Add to System"}
                                            </button>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    ) : (
                        <>
                            <h3 className="text-xl font-bold text-white flex items-center">
                                <span className="mr-2">{activeTab === "syllabus" ? "📤 Upload Syllabus" : "📤 Upload Timetable"}</span>
                            </h3>

                            <div
                                className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${dragActive ? "border-cyan-400 bg-cyan-500/10" : "border-slate-700 bg-slate-800/40 hover:bg-slate-800/60"}`}
                                onDragEnter={handleDrag}
                                onDragLeave={handleDrag}
                                onDragOver={handleDrag}
                                onDrop={handleDrop}
                            >
                                <input
                                    type="file"
                                    id="file-upload"
                                    className="hidden"
                                    accept="application/pdf"
                                    onChange={handleFileSelect}
                                />

                                <div className="flex flex-col items-center justify-center space-y-3">
                                    <span className="text-4xl">📄</span>
                                    <div>
                                        <p className="text-slate-300 font-medium">
                                            {activeTab === "syllabus"
                                                ? (syllabusFile ? `Selected: ${syllabusFile.name}` : "Drag & drop syllabus PDF here")
                                                : (examTimetableFile ? `Selected: ${examTimetableFile.name}` : "Drag & drop timetable PDF here")
                                            }
                                        </p>
                                        <p className="text-slate-500 text-xs mt-1">or click to browse</p>
                                    </div>

                                    <button
                                        onClick={() => document.getElementById("file-upload")?.click()}
                                        className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm text-white font-bold transition-colors"
                                    >
                                        Browse Files
                                    </button>

                                    {(syllabusFile || examTimetableFile) && (
                                        <button
                                            onClick={activeTab === "syllabus" ? uploadSyllabus : uploadExamTimetable}
                                            disabled={loading}
                                            className={`w-full mt-4 px-4 py-3 rounded-lg font-bold text-white shadow-lg transition-all ${loading ? "bg-slate-600 cursor-wait" : "bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 hover:scale-105"
                                                }`}
                                        >
                                            {loading ? "Processing..." : `🚀 Extract ${activeTab === "syllabus" ? "Syllabus" : "Timetable"}`}
                                        </button>
                                    )}
                                </div>
                            </div>

                            <div className="bg-slate-900/50 p-4 rounded-lg border border-slate-700/50 text-xs text-slate-400">
                                <p className="font-bold text-slate-300 mb-1">ℹ️ Privacy & Security</p>
                                <p>Your documents are processed securely using AI to extract dates and topics.</p>
                                <p>Files are parsed temporarily and then deleted. Only extracted data is saved.</p>
                            </div>
                        </>
                    )}
                </div>

                <div className="space-y-4">
                    <h3 className="text-xl font-bold text-white flex items-center">
                        <span className="mr-2">
                            {activeTab === "syllabus" ? "📋 Extracted Subjects" :
                                activeTab === "exams" ? "📅 Exam Schedule" : "📆 Generated Plan"}
                        </span>
                    </h3>

                    <div className="bg-slate-900/40 rounded-xl border border-slate-700/50 p-1 min-h-[400px] max-h-[600px] overflow-y-auto custom-scrollbar">
                        {activeTab === "syllabus" ? (
                            extractedCourses.length > 0 ? (
                                <div className="grid gap-3 p-3">
                                    {extractedCourses.map((subject, idx) => (
                                        <div key={idx} className="bg-slate-800/60 p-4 rounded-lg border border-slate-700 hover:border-cyan-500/30 transition-all">
                                            <div className="flex justify-between items-start mb-2">
                                                <h4 className="font-bold text-white text-sm">{subject.name}</h4>
                                                <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${getDifficultyColor(subject.difficulty)}`}>
                                                    {subject.difficulty}
                                                </span>
                                            </div>
                                            <div className="flex gap-4 text-xs text-slate-400 mb-2">
                                                <span>⏱️ {subject.estimated_hours}h total</span>
                                                <span>🎯 {subject.weekly_target_hours}h/week</span>
                                            </div>
                                            {subject.topics && subject.topics.length > 0 && (
                                                <div className="mt-2 text-xs text-slate-500">
                                                    <p className="font-semibold mb-1">Topics:</p>
                                                    <ul className="list-disc list-inside space-y-0.5">
                                                        {subject.topics.slice(0, 3).map((t: string, i: number) => (
                                                            <li key={i} className="truncate">{t}</li>
                                                        ))}
                                                        {subject.topics.length > 3 && <li>+ {subject.topics.length - 3} more...</li>}
                                                    </ul>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
                                    <span className="text-4xl mb-3">📚</span>
                                    <p>No syllabus uploaded yet.</p>
                                    <p className="text-xs mt-1">Upload a PDF to see subjects here.</p>
                                </div>
                            )
                        ) : activeTab === "exams" ? (
                            extractedExams.length > 0 ? (
                                <div className="grid gap-3 p-3">
                                    {normalizedExams.map((exam, idx) => (
                                        <div key={idx} className="bg-slate-800/60 p-4 rounded-lg border border-slate-700 hover:border-purple-500/30 transition-all flex items-center justify-between">
                                            <div>
                                                <h4 className="font-bold text-white text-sm mb-1">{exam.subject}</h4>
                                                <div className="flex items-center gap-3 text-xs text-slate-400">
                                                    <span className="flex items-center gap-1">🗓️ {exam.dateLabel}</span>
                                                    <span className="flex items-center gap-1">⏰ {exam.timeLabel}</span>
                                                </div>
                                                <div className="mt-1 text-xs text-slate-500">
                                                    📍 {exam.venue || "Venue TBA"}
                                                </div>
                                            </div>
                                            <div className="text-center bg-slate-700/50 p-2 rounded-lg min-w-[60px]">
                                                <div className="text-xs text-purple-400 font-bold uppercase">{exam.dayName.substring(0, 3)}</div>
                                                <div className="text-lg font-black text-white">{exam.dateObj ? exam.dateObj.getDate() : "?"}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
                                    <span className="text-4xl mb-3">📝</span>
                                    <p>No exams scheduled yet.</p>
                                    <p className="text-xs mt-1">Upload an exam timetable to see it here.</p>
                                </div>
                            )
                        ) : (
                            studySchedule && studySchedule.length > 0 ? (
                                <div className="space-y-4 p-3">
                                    <div className="grid grid-cols-2 gap-2 mb-2">
                                        <div className="bg-slate-800/50 p-3 rounded-lg text-center">
                                            <p className="text-xl font-bold text-emerald-400">{studySchedule.length}</p>
                                            <p className="text-[10px] text-slate-400">Total Days</p>
                                        </div>
                                        <div className="bg-slate-800/50 p-3 rounded-lg text-center">
                                            <p className="text-xl font-bold text-blue-400">
                                                {studySchedule.reduce((sum: number, day: any) => sum + day.sessions.reduce((s: any, sess: any) => s + sess.hours, 0), 0)}h
                                            </p>
                                            <p className="text-[10px] text-slate-400">Total Hours</p>
                                        </div>
                                    </div>

                                    {studySchedule.map((day: any, dayIndex: number) => (
                                        <div
                                            key={dayIndex}
                                            className={`border rounded-xl p-3 ${day.isWeekend
                                                ? "border-orange-500/30 bg-orange-500/5"
                                                : "border-slate-700/60 bg-slate-800/30"
                                                }`}
                                        >
                                            <div className="flex items-center justify-between mb-2">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-bold text-white">
                                                        {day.dateLabel}
                                                    </span>
                                                    {day.isWeekend && (
                                                        <span className="px-1.5 py-0.5 bg-orange-500/20 text-orange-300 text-[10px] rounded">
                                                            Wknd
                                                        </span>
                                                    )}
                                                </div>
                                                <span className="text-slate-500 text-[10px]">
                                                    {day.sessions.reduce((sum: any, s: any) => sum + s.hours, 0)}h
                                                </span>
                                            </div>

                                            {day.sessions.length === 0 ? (
                                                <p className="text-slate-500 text-xs">Rest day 🧘</p>
                                            ) : (
                                                <div className="space-y-2">
                                                    {day.sessions.map((session: any, sessIndex: number) => (
                                                        <div
                                                            key={sessIndex}
                                                            className={`p-3 rounded-lg border ${session.priority === "high"
                                                                ? "border-red-500/40 bg-red-500/10"
                                                                : session.priority === "medium"
                                                                    ? "border-yellow-500/40 bg-yellow-500/10"
                                                                    : "border-slate-600/40 bg-slate-700/30"
                                                                }`}
                                                        >
                                                            <div className="flex items-start justify-between mb-1">
                                                                <div>
                                                                    <p className="font-semibold text-white text-xs">{session.subject}</p>
                                                                    <p className="text-slate-400 text-[10px]">
                                                                        {session.startTime} - {session.endTime} ({session.hours}h)
                                                                    </p>
                                                                </div>
                                                                <div className="text-right">
                                                                    <span className="text-[10px] block">{getPriorityBadge(session.priority)}</span>
                                                                </div>
                                                            </div>

                                                            <div className="flex flex-wrap gap-1 mt-1">
                                                                {session.tasks.map((task: any, taskIndex: number) => (
                                                                    <span
                                                                        key={taskIndex}
                                                                        className={`px-1.5 py-0.5 text-[10px] rounded border ${getTaskTypeColor(task.type)}`}
                                                                    >
                                                                        {task.task} ({task.duration}h)
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full text-slate-500 p-8 text-center">
                                    <span className="text-4xl mb-3">🧬</span>
                                    <p>No schedule generated yet.</p>
                                    <p className="text-xs mt-1">Upload exams and click Generate to see your plan.</p>
                                </div>
                            )
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};
