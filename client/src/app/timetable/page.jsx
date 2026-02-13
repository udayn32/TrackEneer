"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:5000";

export default function TimetablePage() {
  const { data: session } = useSession();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [extractedCourses, setExtractedCourses] = useState([]);
  const [examTimetableFile, setExamTimetableFile] = useState(null);
  const [extractedExams, setExtractedExams] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const [activeTab, setActiveTab] = useState("syllabus");
  const [studySchedule, setStudySchedule] = useState(null);
  const [generatingSchedule, setGeneratingSchedule] = useState(false);
  const [saving, setSaving] = useState(false);

  // Multi-schedule support
  const [availableSchedules, setAvailableSchedules] = useState([]);
  const [selectedScheduleIdx, setSelectedScheduleIdx] = useState(0);

  const userEmail = session?.user?.email || "demo@trackeneer.local";

  // Fetch previously extracted courses on load
  useEffect(() => {
    fetchExtractedCourses();
  }, []);

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

  const uploadExamTimetable = async () => {
    if (!examTimetableFile) {
      showMessage("Please select an exam timetable PDF", "error");
      return;
    }

    setLoading(true);
    showMessage("Uploading and extracting exam timetable with OCR + AI...", "info");

    const formData = new FormData();
    formData.append("file", examTimetableFile);
    formData.append("email", userEmail);

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload/exam-timetable`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();

      if (res.ok) {
        showMessage(`✅ Exam timetable extracted! Found ${data.exams?.length || 0} exams.`, "success");
        if (data.exams) {
          setExtractedExams(data.exams.map(e => ({ ...e, selected: true })));
        }
        setExamTimetableFile(null);
        const fileInput = document.getElementById("exam-input");
        if (fileInput) fileInput.value = "";
      } else {
        showMessage(data.detail || "Upload failed", "error");
      }
    } catch (err) {
      showMessage(`Error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (text, type = "info") => {
    setMessage({ text, type });
    setTimeout(() => setMessage(null), 6000);
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type === "application/pdf") {
        setSyllabusFile(file);
      } else {
        showMessage("Please upload a PDF file", "error");
      }
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files[0]) {
      setSyllabusFile(e.target.files[0]);
    }
  };

  const uploadSyllabus = async () => {
    if (!syllabusFile) {
      showMessage("Please select a syllabus PDF", "error");
      return;
    }

    setLoading(true);
    showMessage("Uploading and extracting syllabus with AI...", "info");

    const formData = new FormData();
    formData.append("file", syllabusFile);
    formData.append("email", userEmail);

    try {
      const res = await fetch(`${API_BASE}/api/documents/upload/syllabus`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();

      if (res.ok) {
        showMessage(`✅ Syllabus extracted successfully! Found ${data.subjects?.length || 0} courses.`, "success");
        if (data.subjects) {
          setExtractedCourses(data.subjects);
        }
        setSyllabusFile(null);
        // Reset file input
        const fileInput = document.getElementById("syllabus-input");
        if (fileInput) fileInput.value = "";
      } else {
        showMessage(data.detail || "Upload failed", "error");
      }
    } catch (err) {
      showMessage(`Error: ${err.message}`, "error");
    } finally {
      setLoading(false);
    }
  };

  const getDifficultyColor = (difficulty) => {
    switch (difficulty) {
      case "hard": return "text-red-400 bg-red-500/20 border-red-500/30";
      case "medium": return "text-yellow-400 bg-yellow-500/20 border-yellow-500/30";
      case "easy": return "text-green-400 bg-green-500/20 border-green-500/30";
      default: return "text-slate-400 bg-slate-500/20 border-slate-500/30";
    }
  };

  const to12Hour = (timeStr) => {
    if (!timeStr) return null;
    const match = timeStr.match(/(\d{1,2})(?:[:\.](\d{2}))/);
    if (!match) return timeStr.trim();
    let hour = parseInt(match[1], 10);
    const minute = match[2];
    const suffix = hour >= 12 ? "PM" : "AM";
    if (hour === 0) hour = 12;
    if (hour > 12) hour -= 12;
    return `${hour}:${minute} ${suffix}`;
  };

  const formatTimeRange = (start, end) => {
    const startFmt = to12Hour(start);
    const endFmt = to12Hour(end);
    if (startFmt && endFmt) return `${startFmt} – ${endFmt}`;
    if (startFmt) return `${startFmt} – TBA`;
    if (endFmt) return `TBA – ${endFmt}`;
    return "TBA";
  };

  const cleanOCRText = (text) => {
    if (!text) return "";
    // Fix common OCR errors - conservative approach
    let cleaned = String(text)
      // Fix "loT" -> "IoT" specifically for IoT context
      .replace(/\bloT/g, "IoT")
      .replace(/\bloTCS/gi, "IoTCS")
      // Remove parenthetical noise
      .replace(/\(.*\).*$/g, "")
      // Keep alphanumeric, space, dash, dot, slash, ampersand
      .replace(/[^a-zA-Z0-9\s\-\.\/&]/g, "")
      .replace(/\s+/g, " ")
      .trim();
    return cleaned;
  };

  // Clean paper name by removing course codes and OCR artifacts
  const cleanPaperName = (paper, subject = "") => {
    if (!paper) return subject || "";

    // Pre-clean OCR artifacts (parenthetical noise etc.)
    let text = cleanOCRText(String(paper).trim());

    // Remove "- null" literal
    text = text.replace(/\s*-\s*null\s*$/i, "");

    // Remove course codes with "- P" prefix (e.g., "- P loTCSBCC701")
    text = text.replace(/\s*-\s*P\s+[A-Za-z]*[Ii][Oo][Tt][A-Z0-9]*\d+[A-Z0-9]*\s*$/gi, "");
    text = text.replace(/\s*-\s*P\s+[A-Z0-9]+\s*$/gi, "");

    // Remove parenthetical code followed by token (e.g., "- PAM) loTESBEDOTOL")
    text = text.replace(/\s*-\s*\([^)]*\)\s*[A-Za-z0-9]+\s*$/gi, "");

    // Remove IoT course codes (e.g., "- IoTCSBCC503", "- IoTCSBCDLOS5013")
    text = text.replace(/\s*-\s*[Ii][Oo][Tt][A-Z0-9]*\d{3,}[A-Z0-9]*\s*$/gi, "");

    // Remove standard course codes (e.g., "- TCSBCC701", "- HAIMLC701", "- HAIMLCS01")
    // Broaden to allow 2+ digit codes at the end
    text = text.replace(/\s*-\s*[A-Z]{2,}[A-Z0-9]*\d{2,}[A-Z0-9]*\s*$/gi, "");

    // Remove short codes (e.g., "- OEC301", "- ILO7016")
    text = text.replace(/\s*-\s*[A-Z]+\d{3,}\s*$/gi, "");

    // Remove pure numeric codes (e.g., "- 153111", "- 2153112")
    text = text.replace(/\s*-\s*\d{4,}\s*$/gi, "");

    // Remove generic trailing all-caps/digit tokens after dash (e.g., "- ABC123", "- XYZ")
    text = text.replace(/\s*-\s*[A-Z0-9]{4,}\s*$/gi, "");
    text = text.replace(/\s*-\s*[A-Z]\s*$/gi, "");

    // Remove OCR artifacts like "- P", "- P.", "- PAM", "P P", etc.
    text = text.replace(/\s*-\s*P\s*$/i, "");
    text = text.replace(/\s*-\s*P\.\s*$/i, "");
    text = text.replace(/\s*-\s*P\s+P\s*$/i, "");
    text = text.replace(/\s*P\s*P\s*$/i, "");
    text = text.replace(/\s*-\s*PAM\s*$/i, "");
    text = text.replace(/\s+P\s*$/i, "");
    text = text.replace(/\s+P\.\s*$/i, "");

    // Remove trailing dash and clean up
    text = text.replace(/\s*-\s*$/, "");
    text = text.replace(/\s+/g, " ").trim();

    // If empty or too short, use subject
    if (text.length < 3) {
      text = subject?.trim() || "Unknown Subject";
    }

    // Add subject prefix if not present
    if (subject && subject.trim().length > 2) {
      const subj = subject.trim();
      if (!text.toLowerCase().startsWith(subj.toLowerCase().substring(0, 5))) {
        if (!text.toLowerCase().includes(subj.toLowerCase())) {
          text = `${subj} ${text}`;
        }
      }
    }

    return text.trim();
  };

  const joinPaperName = (subject = "", paper = "") => {
    // Combine subject and paper into a proper paper name
    const subj = cleanOCRText(subject).trim();
    const pap = cleanOCRText(paper).trim();

    if (!subj && !pap) return "";
    if (!subj) return pap;
    if (!pap) return subj;

    // If paper already starts with subject, don't duplicate
    if (pap.toLowerCase().startsWith(subj.toLowerCase())) {
      return pap;
    }

    // Check if they should be joined with "&" or just space
    // If both parts are descriptive (contain spaces or are short words), join with space
    // If one is an acronym, join with "&"
    const hasNumInSubj = /\d/.test(subj);
    const hasNumInPap = /\d/.test(pap);

    // If one part is all uppercase and not a code, it's an acronym
    const subjIsAcronym = /^[A-Z]{2,6}$/.test(subj) && !hasNumInSubj;
    const papIsAcronym = /^[A-Z]{2,6}$/.test(pap) && !hasNumInPap;

    // Join with "&" if either is an acronym or if parts are single words
    if (subjIsAcronym || papIsAcronym || (!subj.includes(" ") && !pap.includes(" "))) {
      return subj + " & " + pap;
    }

    // Otherwise join with space
    return subj + " " + pap;
  };

  const scoreAsCode = (text) => {
    // Boolean + fuzzy logic: score text likelihood of being a course code
    if (!text) return 0;

    const t = text.trim();
    let score = 0;

    // Has digits (very strong indicator)
    if (/\d/.test(t)) score += 40;

    // Alphanumeric only (strong indicator)
    if (/^[A-Za-z0-9]+$/.test(t)) score += 20;

    // Length 2-15 chars (typical code length)
    if (t.length >= 2 && t.length <= 15) score += 15;

    // Starts with uppercase (typical pattern)
    if (/^[A-Z]/.test(t)) score += 10;

    // All uppercase (typical pattern)
    if (/^[A-Z0-9]+$/.test(t)) score += 10;

    // Contains no spaces (important)
    if (!/\s/.test(t)) score += 5;

    // Single uppercase letter (could be valid code like "P")
    if (/^[A-Z]$/.test(t)) score += 30;

    // Short uppercase acronym (like "PAM", "OEC")
    if (/^[A-Z]{2,4}$/.test(t)) score += 25;

    // Penalize long text (likely description)
    if (t.length > 20) score -= 30;

    // Penalize multiple words
    if (/\s+/.test(t)) score -= 20;

    return Math.max(0, score);
  };

  const scoreAsPaper = (text) => {
    // Boolean + fuzzy logic: score text likelihood of being a paper name
    if (!text) return 0;

    const t = text.trim();
    let score = 0;

    // Contains spaces (strong indicator of descriptive text)
    if (/\s+/.test(t)) score += 30;

    // Reasonable length for a name (5-100 chars)
    if (t.length >= 5 && t.length <= 100) score += 20;

    // Contains common descriptive words
    if (/\b(for|and|in|of|with|to|at)\b/i.test(t)) score += 15;

    // Contains ampersand or dash (connectors in paper names)
    if (/[&\-]/.test(t)) score += 10;

    // Mix of letters and possibly some digits
    if (/[a-zA-Z]/.test(t)) score += 5;

    // Penalize if looks like a code
    if (/^[A-Z0-9]{2,10}$/.test(t)) score -= 40;

    // Penalize if very short (likely not a paper name)
    if (t.length < 3) score -= 20;

    return Math.max(0, score);
  };

  const findCodeAndPaperPattern = (exam) => {
    // Use boolean + fuzzy logic scoring to find best code/paper split
    const { subject = "", paper = "", course_code, subject_code, code } = exam || {};

    // Strategy 0: Check explicit code fields first
    if (course_code && scoreAsCode(course_code) > 30) {
      return { code: cleanOCRText(String(course_code)).trim(), paper: cleanOCRText(subject + " " + paper).trim() };
    }
    if (subject_code && scoreAsCode(subject_code) > 30) {
      return { code: cleanOCRText(String(subject_code)).trim(), paper: cleanOCRText(subject + " " + paper).trim() };
    }
    if (code && scoreAsCode(code) > 30) {
      return { code: cleanOCRText(String(code)).trim(), paper: cleanOCRText(subject + " " + paper).trim() };
    }

    const paperStr = String(paper).trim();
    const subjectStr = String(subject).trim();

    // Score combinations and pick the best one
    let bestResult = { code: "N/A", paper: cleanOCRText(subjectStr + " " + paperStr).trim(), score: 0 };

    // Strategy 1: Look for "Something - CODE" pattern
    const match1 = paperStr.match(/(.+?)\s*-\s*([A-Za-z0-9]{2,20})$/);
    if (match1) {
      const potentialCode = cleanOCRText(match1[2]).trim();
      const potentialPaper = cleanOCRText(match1[1]).trim();
      const codeScore = scoreAsCode(potentialCode);
      const paperScore = scoreAsPaper(potentialPaper);
      const combinedScore = codeScore + paperScore;

      if (combinedScore > bestResult.score && codeScore > 20 && paperScore > 10) {
        bestResult = {
          code: potentialCode,
          paper: potentialPaper,
          subject: cleanOCRText(subjectStr).trim(),
          score: combinedScore
        };
      }
    }

    // Strategy 2: Look for "Something CODE" pattern (space-separated)
    const match2 = paperStr.match(/(.+?)\s+([A-Za-z0-9]{2,20})$/);
    if (match2) {
      const potentialCode = cleanOCRText(match2[2]).trim();
      const potentialPaper = cleanOCRText(match2[1]).trim();
      const codeScore = scoreAsCode(potentialCode);
      const paperScore = scoreAsPaper(potentialPaper);
      const combinedScore = codeScore + paperScore;

      if (combinedScore > bestResult.score && codeScore > 20 && paperScore > 10) {
        bestResult = {
          code: potentialCode,
          paper: potentialPaper,
          subject: cleanOCRText(subjectStr).trim(),
          score: combinedScore
        };
      }
    }

    // Strategy 3: Combined subject + paper with pattern matching
    const combined = cleanOCRText(subjectStr + " " + paperStr).trim();
    const match3 = combined.match(/(.+?)\s*-\s*([A-Za-z0-9]{2,20})$/);
    if (match3) {
      const potentialCode = cleanOCRText(match3[2]).trim();
      const potentialPaper = cleanOCRText(match3[1]).trim();
      const codeScore = scoreAsCode(potentialCode);
      const paperScore = scoreAsPaper(potentialPaper);
      const combinedScore = codeScore + paperScore;

      if (combinedScore > bestResult.score && codeScore > 20 && paperScore > 10) {
        bestResult = {
          code: potentialCode,
          paper: potentialPaper,
          subject: "",
          score: combinedScore
        };
      }
    }

    // Strategy 4: Find best code/paper split by scoring all tokens
    const tokens = paperStr.split(/\s+|-/);
    for (let i = 0; i < tokens.length; i++) {
      const potentialCode = cleanOCRText(tokens[i]).trim();
      const codeScore = scoreAsCode(potentialCode);

      if (codeScore > 20) {
        const beforeTokens = tokens.slice(0, i).join(" ");
        const potentialPaper = cleanOCRText(beforeTokens + " " + subjectStr).trim();
        const paperScore = scoreAsPaper(potentialPaper);
        const combinedScore = codeScore + paperScore;

        if (combinedScore > bestResult.score && paperScore > 5) {
          bestResult = {
            code: potentialCode,
            paper: potentialPaper,
            subject: "",
            score: combinedScore
          };
        }
      }
    }

    // Strategy 5: Last token fallback - even single letters
    if (bestResult.code === "N/A") {
      const lastToken = tokens[tokens.length - 1];
      const cleaned = cleanOCRText(lastToken).trim();
      if (cleaned && /^[A-Z0-9]+$/i.test(cleaned)) {
        const beforeTokens = tokens.slice(0, -1).join(" ");
        bestResult = {
          code: cleaned,
          paper: cleanOCRText(subjectStr + " " + beforeTokens).trim() || "N/A",
          subject: "",
          score: 10
        };
      }
    }

    // Cleanup: remove score from result
    const { score, ...result } = bestResult;
    return result;
  };

  const extractCourseCode = (exam) => {
    const result = findCodeAndPaperPattern(exam);
    return result.code;
  };

  const extractPaperName = (exam) => {
    // Prefer explicit paper field; fallback to subject. Clean codes/artifacts.
    const base = (exam?.paper && String(exam.paper).trim().length > 0)
      ? String(exam.paper)
      : String(exam?.subject || "");
    return cleanPaperName(base, base);
  };

  const safeDateFromISO = (isoDate) => {
    if (!isoDate) return null;
    // Avoid timezone drift by constructing UTC date from parts
    const match = isoDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return null;
    const [_, y, m, d] = match;
    const dateObj = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
    return isNaN(dateObj.getTime()) ? null : dateObj;
  };

  const normalizedExams = extractedExams
    .map((exam) => {
      const dateObj = safeDateFromISO(exam.date);
      const validDate = Boolean(dateObj);
      return {
        ...exam,
        courseCode: extractCourseCode(exam),
        paperName: extractPaperName(exam),
        dateLabel: validDate
          ? dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
          : "Date TBA",
        dayName: validDate
          ? dateObj.toLocaleDateString("en-US", { weekday: "long" })
          : "TBA",
        timeLabel: formatTimeRange(exam.start_time, exam.end_time),
        sortTime: (exam.start_time || "").padStart(5, "0"),
        dateObj: validDate ? dateObj : null
      };
    })
    .sort((a, b) => {
      if (a.dateObj && b.dateObj) {
        if (a.dateObj.getTime() !== b.dateObj.getTime()) return a.dateObj - b.dateObj;
        return a.sortTime.localeCompare(b.sortTime);
      }
      if (a.dateObj) return -1;
      if (b.dateObj) return 1;
      return 0;
    });

  // ============== NSGA-II STUDY SCHEDULE GENERATOR ==============

  // NSGA-II Configuration
  const NSGA2_CONFIG = {
    populationSize: 100,
    generations: 150,
    crossoverRate: 0.9,
    mutationRate: 0.1,
    studyHoursPerDay: 8,
    breakDurationMins: 15,
    sessionDurationMins: 90,
    daysBeforeExam: 60 // 2 months
  };

  // Objective functions for NSGA-II (minimization)
  const evaluateObjectives = (chromosome, exams, startDate) => {
    // Objective 1: Minimize cramming (spread study evenly)
    // Objective 2: Minimize subject switching cost
    // Objective 3: Maximize revision before exam (prioritize closer exams)

    let crammingScore = 0;
    let switchingCost = 0;
    let revisionScore = 0;

    const subjectStudyDays = {};
    let prevSubject = null;

    chromosome.forEach((gene, dayIndex) => {
      const { subjectIndex, hours } = gene;
      if (subjectIndex < 0 || subjectIndex >= exams.length) return;

      const exam = exams[subjectIndex];
      if (!exam) return; // Safety check

      const subject = exam.paperName || `Subject ${subjectIndex + 1}`;
      const examDate = exam.dateObj;

      // Track study distribution
      if (!subjectStudyDays[subject]) subjectStudyDays[subject] = [];
      subjectStudyDays[subject].push({ day: dayIndex, hours });

      // Switching cost
      if (prevSubject && prevSubject !== subject) switchingCost += 1;
      prevSubject = subject;

      // Revision score: study closer to exam is better (weighted)
      if (examDate) {
        const currentDay = new Date(startDate);
        currentDay.setDate(currentDay.getDate() + dayIndex);
        const daysUntilExam = Math.max(1, Math.floor((examDate - currentDay) / (1000 * 60 * 60 * 24)));
        // Exponential decay: studying 1-3 days before is most valuable
        revisionScore += hours * Math.exp(-daysUntilExam / 7);
      }
    });

    // Calculate cramming score (variance of study hours per subject)
    Object.values(subjectStudyDays).forEach(days => {
      if (days.length < 2) {
        crammingScore += 10; // Penalize studying all in one day
      } else {
        const gaps = [];
        for (let i = 1; i < days.length; i++) {
          gaps.push(days[i].day - days[i - 1].day);
        }
        const avgGap = gaps.reduce((a, b) => a + b, 0) / gaps.length;
        const variance = gaps.reduce((sum, g) => sum + Math.pow(g - avgGap, 2), 0) / gaps.length;
        crammingScore += variance; // Lower variance = more evenly spread
      }
    });

    return {
      cramming: crammingScore,
      switching: switchingCost,
      revision: -revisionScore // Negative because we maximize revision but NSGA-II minimizes
    };
  };

  // Check if solution A dominates solution B
  const dominates = (a, b) => {
    let dominated = false;
    let dominates = true;

    for (const key of Object.keys(a.objectives)) {
      if (a.objectives[key] > b.objectives[key]) dominates = false;
      if (a.objectives[key] < b.objectives[key]) dominated = true;
    }

    return dominates && dominated;
  };

  // Non-dominated sorting
  const nonDominatedSort = (population) => {
    const fronts = [[]];
    const dominationCount = new Array(population.length).fill(0);
    const dominatedSolutions = population.map(() => []);

    for (let i = 0; i < population.length; i++) {
      for (let j = i + 1; j < population.length; j++) {
        if (dominates(population[i], population[j])) {
          dominatedSolutions[i].push(j);
          dominationCount[j]++;
        } else if (dominates(population[j], population[i])) {
          dominatedSolutions[j].push(i);
          dominationCount[i]++;
        }
      }

      if (dominationCount[i] === 0) {
        population[i].rank = 0;
        fronts[0].push(i);
      }
    }

    let frontIndex = 0;
    while (fronts[frontIndex].length > 0) {
      const nextFront = [];
      for (const i of fronts[frontIndex]) {
        for (const j of dominatedSolutions[i]) {
          dominationCount[j]--;
          if (dominationCount[j] === 0) {
            population[j].rank = frontIndex + 1;
            nextFront.push(j);
          }
        }
      }
      frontIndex++;
      fronts.push(nextFront);
    }

    return fronts.slice(0, -1);
  };

  // Crowding distance calculation
  const calculateCrowdingDistance = (population, front) => {
    const n = front.length;
    if (n <= 2) {
      front.forEach(i => population[i].crowdingDistance = Infinity);
      return;
    }

    front.forEach(i => population[i].crowdingDistance = 0);
    const objectives = Object.keys(population[0].objectives);

    for (const obj of objectives) {
      front.sort((a, b) => population[a].objectives[obj] - population[b].objectives[obj]);

      population[front[0]].crowdingDistance = Infinity;
      population[front[n - 1]].crowdingDistance = Infinity;

      const minVal = population[front[0]].objectives[obj];
      const maxVal = population[front[n - 1]].objectives[obj];
      const range = maxVal - minVal || 1;

      for (let i = 1; i < n - 1; i++) {
        const prev = population[front[i - 1]].objectives[obj];
        const next = population[front[i + 1]].objectives[obj];
        population[front[i]].crowdingDistance += (next - prev) / range;
      }
    }
  };

  // Tournament selection
  const tournamentSelect = (population) => {
    const i = Math.floor(Math.random() * population.length);
    const j = Math.floor(Math.random() * population.length);

    if (population[i].rank < population[j].rank) return population[i];
    if (population[j].rank < population[i].rank) return population[j];

    return population[i].crowdingDistance > population[j].crowdingDistance
      ? population[i]
      : population[j];
  };

  // Crossover (uniform crossover)
  const crossover = (parent1, parent2) => {
    if (Math.random() > NSGA2_CONFIG.crossoverRate) {
      return [{ ...parent1 }, { ...parent2 }];
    }

    const child1Chromosome = [];
    const child2Chromosome = [];

    for (let i = 0; i < parent1.chromosome.length; i++) {
      if (Math.random() < 0.5) {
        child1Chromosome.push({ ...parent1.chromosome[i] });
        child2Chromosome.push({ ...parent2.chromosome[i] });
      } else {
        child1Chromosome.push({ ...parent2.chromosome[i] });
        child2Chromosome.push({ ...parent1.chromosome[i] });
      }
    }

    return [
      { chromosome: child1Chromosome },
      { chromosome: child2Chromosome }
    ];
  };

  // Mutation
  const mutate = (individual, numSubjects) => {
    const mutated = { chromosome: individual.chromosome.map(g => ({ ...g })) };
    const safeNumSubjects = Math.max(1, numSubjects);

    for (let i = 0; i < mutated.chromosome.length; i++) {
      if (Math.random() < NSGA2_CONFIG.mutationRate) {
        // Mutate subject or hours
        if (Math.random() < 0.5) {
          mutated.chromosome[i].subjectIndex = Math.floor(Math.random() * safeNumSubjects);
        } else {
          mutated.chromosome[i].hours = Math.max(1, Math.min(NSGA2_CONFIG.studyHoursPerDay,
            mutated.chromosome[i].hours + (Math.random() < 0.5 ? 1 : -1)));
        }
      }
    }

    return mutated;
  };

  // Create random chromosome
  const createRandomChromosome = (numDays, numSubjects) => {
    const chromosome = [];
    const safeNumSubjects = Math.max(1, numSubjects);
    for (let day = 0; day < numDays; day++) {
      // 2-3 study sessions per day
      const sessions = 2 + Math.floor(Math.random() * 2);
      for (let s = 0; s < sessions; s++) {
        chromosome.push({
          day,
          subjectIndex: Math.floor(Math.random() * safeNumSubjects),
          hours: 1 + Math.floor(Math.random() * 3)
        });
      }
    }
    return chromosome;
  };

  // Run NSGA-II algorithm
  const runNSGA2 = (exams) => {
    if (!exams || exams.length === 0) return null;

    const numSubjects = exams.length;
    const startDate = new Date();
    const earliestExam = exams.find(e => e.dateObj)?.dateObj || new Date(Date.now() + 60 * 24 * 60 * 60 * 1000);
    const numDays = Math.min(NSGA2_CONFIG.daysBeforeExam, Math.max(14, Math.floor((earliestExam - startDate) / (1000 * 60 * 60 * 24))));

    // Initialize population
    let population = [];
    for (let i = 0; i < NSGA2_CONFIG.populationSize; i++) {
      const chromosome = createRandomChromosome(numDays, numSubjects);
      const objectives = evaluateObjectives(chromosome, exams, startDate);
      population.push({ chromosome, objectives });
    }

    // Evolution loop
    for (let gen = 0; gen < NSGA2_CONFIG.generations; gen++) {
      // Non-dominated sorting
      const fronts = nonDominatedSort(population);

      // Calculate crowding distance
      fronts.forEach(front => calculateCrowdingDistance(population, front));

      // Create offspring
      const offspring = [];
      while (offspring.length < NSGA2_CONFIG.populationSize) {
        const parent1 = tournamentSelect(population);
        const parent2 = tournamentSelect(population);
        const [child1, child2] = crossover(parent1, parent2);

        const mutatedChild1 = mutate(child1, numSubjects);
        const mutatedChild2 = mutate(child2, numSubjects);

        mutatedChild1.objectives = evaluateObjectives(mutatedChild1.chromosome, exams, startDate);
        mutatedChild2.objectives = evaluateObjectives(mutatedChild2.chromosome, exams, startDate);

        offspring.push(mutatedChild1, mutatedChild2);
      }

      // Combine parent and offspring
      const combined = [...population, ...offspring];
      const combinedFronts = nonDominatedSort(combined);
      combinedFronts.forEach(front => calculateCrowdingDistance(combined, front));

      // Select next generation
      population = [];
      for (const front of combinedFronts) {
        if (population.length + front.length <= NSGA2_CONFIG.populationSize) {
          front.forEach(i => population.push(combined[i]));
        } else {
          // Sort by crowding distance and add remaining
          const sorted = front.sort((a, b) =>
            combined[b].crowdingDistance - combined[a].crowdingDistance
          );
          for (const i of sorted) {
            if (population.length >= NSGA2_CONFIG.populationSize) break;
            population.push(combined[i]);
          }
          break;
        }
      }
    }

    // Return best solution from Pareto front
    const paretoFront = population.filter(p => p.rank === 0);
    const bestSolution = paretoFront.reduce((best, current) => {
      const bestScore = best.objectives.cramming + best.objectives.switching + best.objectives.revision;
      const currentScore = current.objectives.cramming + current.objectives.switching + current.objectives.revision;
      return currentScore < bestScore ? current : best;
    }, paretoFront[0]);

    return { solution: bestSolution, startDate, numDays, exams };
  };

  // Convert NSGA-II solution to readable schedule
  const convertToSchedule = (result) => {
    if (!result) return null;

    const { solution, startDate, numDays, exams } = result;
    const schedule = [];

    // Group chromosome by day
    const dayGroups = {};
    solution.chromosome.forEach(gene => {
      if (!dayGroups[gene.day]) dayGroups[gene.day] = [];
      dayGroups[gene.day].push(gene);
    });

    for (let day = 0; day < numDays; day++) {
      const currentDate = new Date(startDate);
      currentDate.setDate(currentDate.getDate() + day);

      const sessions = dayGroups[day] || [];
      const daySchedule = {
        date: currentDate,
        dateLabel: currentDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }),
        isWeekend: currentDate.getDay() === 0 || currentDate.getDay() === 6,
        sessions: []
      };

      // Consolidate sessions by subject
      const subjectHours = {};
      sessions.forEach(s => {
        // Safely access exam with bounds checking
        const safeIndex = Math.min(Math.max(0, s.subjectIndex), exams.length - 1);
        const exam = exams[safeIndex];
        const subject = exam?.paperName || `Subject ${safeIndex + 1}`;
        subjectHours[subject] = (subjectHours[subject] || 0) + s.hours;
      });

      let startHour = 9; // Start at 9 AM
      Object.entries(subjectHours).forEach(([subject, hours]) => {
        const exam = exams.find(e => e.paperName === subject);
        const daysUntilExam = exam?.dateObj
          ? Math.floor((exam.dateObj - currentDate) / (1000 * 60 * 60 * 24))
          : 999;

        daySchedule.sessions.push({
          subject,
          hours,
          startTime: `${startHour}:00`,
          endTime: `${startHour + hours}:00`,
          priority: daysUntilExam <= 3 ? "high" : daysUntilExam <= 7 ? "medium" : "normal",
          daysUntilExam,
          tasks: generateStudyTasks(subject, hours, daysUntilExam)
        });

        startHour += hours + 0.5; // Add 30 min break
      });

      schedule.push(daySchedule);
    }

    return schedule;
  };

  // Generate study tasks based on days until exam
  const generateStudyTasks = (subject, hours, daysUntilExam) => {
    const tasks = [];

    if (daysUntilExam > 30) {
      // Early phase: concept learning
      tasks.push({ task: "Read textbook chapters", duration: Math.ceil(hours * 0.4), type: "learn" });
      tasks.push({ task: "Watch video lectures", duration: Math.ceil(hours * 0.3), type: "learn" });
      tasks.push({ task: "Make summary notes", duration: Math.ceil(hours * 0.3), type: "notes" });
    } else if (daysUntilExam > 14) {
      // Mid phase: practice
      tasks.push({ task: "Review notes", duration: Math.ceil(hours * 0.2), type: "review" });
      tasks.push({ task: "Solve practice problems", duration: Math.ceil(hours * 0.5), type: "practice" });
      tasks.push({ task: "Create flashcards", duration: Math.ceil(hours * 0.3), type: "notes" });
    } else if (daysUntilExam > 3) {
      // Final phase: revision
      tasks.push({ task: "Quick revision", duration: Math.ceil(hours * 0.3), type: "review" });
      tasks.push({ task: "Solve past papers", duration: Math.ceil(hours * 0.5), type: "practice" });
      tasks.push({ task: "Review weak topics", duration: Math.ceil(hours * 0.2), type: "review" });
    } else {
      // Last days: final prep
      tasks.push({ task: "Flashcard review", duration: Math.ceil(hours * 0.3), type: "review" });
      tasks.push({ task: "Formula/key points revision", duration: Math.ceil(hours * 0.4), type: "review" });
      tasks.push({ task: "Light practice", duration: Math.ceil(hours * 0.3), type: "practice" });
    }

    return tasks;
  };



  const saveScheduleToCalendar = async () => {
    if (!studySchedule || studySchedule.length === 0) return;
    setSaving(true);
    showMessage("Saving schedule to your calendar...", "info");

    try {
      // Format schedule for backend
      const formattedSchedule = studySchedule.map(day => ({
        date: day.date instanceof Date ? day.date.toISOString().split('T')[0] : day.date,
        sessions: day.sessions.map(s => ({
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
    } catch (err) {
      showMessage(`Error saving schedule: ${err.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  // Generate study schedule using backend NSGA-II API
  const generateStudySchedule = async () => {
    // If no selection property exists, treat as selected (backward compatibility)
    const selectedExams = extractedExams.filter(e => e.selected !== false);

    if (selectedExams.length === 0) {
      showMessage("Please select at least one exam from the list above", "error");
      return;
    }

    setGeneratingSchedule(true);
    showMessage(`🧬 Scheduling for ${selectedExams.length} selected exams...`, "info");

    try {
      const response = await fetch(`${API_BASE}/api/study/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ exams: selectedExams }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to generate schedule");
      }

      const result = await response.json();

      // Handle both old single-object and new list-based responses
      const rawSchedules = result.schedules || [{ label: "Optimized Plan", schedule: result.schedule }];

      const processedSchedules = rawSchedules.map(plan => ({
        ...plan,
        schedule: plan.schedule.map(day => ({
          date: new Date(day.date),
          dateLabel: day.date_label,
          isWeekend: day.is_weekend,
          sessions: day.sessions.map(sess => ({
            subject: sess.subject,
            hours: sess.hours,
            startTime: sess.start_time,
            endTime: sess.end_time,
            priority: sess.priority,
            daysUntilExam: sess.days_until_exam,
            tasks: sess.tasks.map(t => ({
              task: t.task,
              duration: t.duration,
              type: t.type
            }))
          }))
        }))
      }));

      setAvailableSchedules(processedSchedules);
      setSelectedScheduleIdx(0); // Default to first (Balanced)
      setStudySchedule(processedSchedules[0].schedule);

      showMessage(`✅ Generated ${processedSchedules.length} schedule options!`, "success");

    } catch (err) {
      console.error("Schedule generation error:", err);
      showMessage(`Error generating schedule: ${err.message}`, "error");
    } finally {
      setGeneratingSchedule(false);
    }
  };

  const getTaskTypeColor = (type) => {
    switch (type) {
      case "learn": return "bg-blue-500/20 text-blue-300 border-blue-500/30";
      case "practice": return "bg-green-500/20 text-green-300 border-green-500/30";
      case "review": return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
      case "notes": return "bg-purple-500/20 text-purple-300 border-purple-500/30";
      default: return "bg-slate-500/20 text-slate-300 border-slate-500/30";
    }
  };

  const getPriorityBadge = (priority) => {
    switch (priority) {
      case "high": return "🔴 URGENT";
      case "medium": return "🟡 Soon";
      default: return "🟢 Normal";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white relative overflow-hidden" >
      {/* Background effects */}
      < div className="absolute inset-0 pointer-events-none" >
        <div className="absolute top-0 left-0 w-[600px] h-[600px] bg-gradient-to-br from-cyan-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 right-0 w-[700px] h-[700px] bg-gradient-to-tl from-purple-500/10 via-blue-500/5 to-transparent rounded-full blur-3xl"></div>
      </div >

      <div className="relative z-10 p-8 max-w-6xl mx-auto">
        {/* Header */}
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-black bg-gradient-to-r from-cyan-400 via-blue-400 to-purple-400 bg-clip-text text-transparent">
            📚 Academic Document Extractor
          </h1>
          <p className="text-slate-400 mt-2">
            Upload PDFs to extract data using AI with OCR support for scanned documents
          </p>
          <div className="mt-3 flex justify-center gap-2 text-xs">
            <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded">LayoutLMv3</span>
            <span className="px-2 py-1 bg-blue-500/20 text-blue-300 rounded">Tesseract OCR</span>
            <span className="px-2 py-1 bg-green-500/20 text-green-300 rounded">Groq AI</span>
          </div>
        </header>

        {/* Tabs */}
        <div className="flex justify-center gap-4 mb-8">
          <button
            onClick={() => setActiveTab("syllabus")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${activeTab === "syllabus"
              ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg"
              : "bg-slate-800/50 text-slate-400 hover:text-white"
              }`}
          >
            📚 Syllabus
          </button>
          <button
            onClick={() => setActiveTab("exam")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${activeTab === "exam"
              ? "bg-gradient-to-r from-purple-500 to-pink-600 text-white shadow-lg"
              : "bg-slate-800/50 text-slate-400 hover:text-white"
              }`}
          >
            📅 Exam Timetable
          </button>
          <button
            onClick={() => setActiveTab("schedule")}
            className={`px-6 py-3 rounded-lg font-semibold transition-all ${activeTab === "schedule"
              ? "bg-gradient-to-r from-green-500 to-emerald-600 text-white shadow-lg"
              : "bg-slate-800/50 text-slate-400 hover:text-white"
              }`}
          >
            🧬 AI Study Schedule
          </button>
        </div>

        {/* Status Message */}
        {message && (
          <div className={`mb-6 p-4 rounded-lg border ${message.type === "success" ? "bg-green-500/10 border-green-500/30 text-green-400" :
            message.type === "error" ? "bg-red-500/10 border-red-500/30 text-red-400" :
              "bg-blue-500/10 border-blue-500/30 text-blue-400"
            }`}>
            {message.type === "info" && "⏳ "}
            {message.type === "success" && "✅ "}
            {message.type === "error" && "❌ "}
            {message.text}
          </div>
        )}

        {/* Syllabus Upload Section */}
        {activeTab === "syllabus" && (
          <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-cyan-500/20 shadow-2xl mb-8">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <span className="text-2xl">📄</span>
              Upload Syllabus PDF
            </h2>

            {/* Drag & Drop Area */}
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${dragActive
                ? "border-cyan-400 bg-cyan-500/10"
                : syllabusFile
                  ? "border-green-500/50 bg-green-500/5"
                  : "border-slate-600 hover:border-cyan-500/50 hover:bg-slate-800/50"
                }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              {syllabusFile ? (
                <div className="space-y-4">
                  <div className="text-5xl">📄</div>
                  <p className="text-lg font-semibold text-green-400">{syllabusFile.name}</p>
                  <p className="text-slate-400 text-sm">
                    {(syllabusFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                  <button
                    onClick={() => setSyllabusFile(null)}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    ✕ Remove
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="text-5xl">📥</div>
                  <p className="text-lg text-slate-300">
                    Drag & drop your syllabus PDF here
                  </p>
                  <p className="text-slate-500">or</p>
                  <label className="inline-block cursor-pointer">
                    <span className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-6 py-2 rounded-lg hover:shadow-lg hover:shadow-cyan-500/30 transition-all font-semibold">
                      Browse Files
                    </span>
                    <input
                      id="syllabus-input"
                      type="file"
                      accept=".pdf"
                      onChange={handleFileSelect}
                      className="hidden"
                    />
                  </label>
                  <p className="text-slate-500 text-sm">Supports: PDF (Mumbai University Syllabus)</p>
                </div>
              )}
            </div>

            {/* Upload Button */}
            {syllabusFile && (
              <button
                onClick={uploadSyllabus}
                disabled={loading}
                className={`mt-6 w-full py-4 rounded-xl font-bold text-lg transition-all duration-300 ${loading
                  ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                  : "bg-gradient-to-r from-cyan-500 to-blue-600 text-white hover:shadow-xl hover:shadow-cyan-500/30 hover:scale-[1.02]"
                  }`}
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Extracting with AI...
                  </span>
                ) : (
                  "🚀 Upload & Extract Syllabus"
                )}
              </button>
            )}
          </div>
        )}

        {/* Exam Timetable Upload Section */}
        {activeTab === "exam" && (
          <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-purple-500/20 shadow-2xl mb-8">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <span className="text-2xl">📅</span>
              Upload Exam Timetable PDF
            </h2>

            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 ${dragActive
                ? "border-purple-400 bg-purple-500/10"
                : examTimetableFile
                  ? "border-green-500/50 bg-green-500/5"
                  : "border-slate-600 hover:border-purple-500/50 hover:bg-slate-800/50"
                }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setDragActive(false);
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  const file = e.dataTransfer.files[0];
                  if (file.type === "application/pdf") {
                    setExamTimetableFile(file);
                  } else {
                    showMessage("Please upload a PDF file", "error");
                  }
                }
              }}
            >
              {examTimetableFile ? (
                <div className="space-y-4">
                  <div className="text-5xl">📅</div>
                  <p className="text-lg font-semibold text-green-400">{examTimetableFile.name}</p>
                  <p className="text-slate-400 text-sm">
                    {(examTimetableFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                  <button
                    onClick={() => setExamTimetableFile(null)}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    ✕ Remove
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="text-5xl">📥</div>
                  <p className="text-lg text-slate-300">
                    Drag & drop your exam timetable PDF here
                  </p>
                  <p className="text-slate-500">or</p>
                  <label className="inline-block cursor-pointer">
                    <span className="bg-gradient-to-r from-purple-500 to-pink-600 text-white px-6 py-2 rounded-lg hover:shadow-lg hover:shadow-purple-500/30 transition-all font-semibold">
                      Browse Files
                    </span>
                    <input
                      id="exam-input"
                      type="file"
                      accept=".pdf"
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          setExamTimetableFile(e.target.files[0]);
                        }
                      }}
                      className="hidden"
                    />
                  </label>
                  <p className="text-slate-500 text-sm">Supports: PDF (Including scanned images)</p>
                </div>
              )}
            </div>

            {examTimetableFile && (
              <button
                onClick={uploadExamTimetable}
                disabled={loading}
                className={`mt-6 w-full py-4 rounded-xl font-bold text-lg transition-all duration-300 ${loading
                  ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                  : "bg-gradient-to-r from-purple-500 to-pink-600 text-white hover:shadow-xl hover:shadow-purple-500/30 hover:scale-[1.02]"
                  }`}
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Extracting with OCR + AI...
                  </span>
                ) : (
                  "🚀 Upload & Extract Exam Timetable"
                )}
              </button>
            )}
          </div>
        )}

        {/* Extracted Exams */}
        {activeTab === "exam" && normalizedExams.length > 0 && (
          <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-pink-500/20 shadow-2xl">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <span className="text-2xl">📅</span>
              Extracted Exam Schedule ({normalizedExams.length} exams)
            </h2>

            <div className="mb-4 flex items-center justify-between">
              <div className="text-sm text-slate-400">
                Select which exams to include in your study plan
              </div>
              <button
                onClick={() => {
                  if (extractedExams.every(e => e.selected !== false)) {
                    setExtractedExams(current => current.map(e => ({ ...e, selected: false })));
                  } else {
                    setExtractedExams(current => current.map(e => ({ ...e, selected: true })));
                  }
                }}
                className="text-sm px-3 py-1.5 rounded bg-slate-800 text-cyan-400 hover:bg-slate-700 transition-colors border border-slate-700"
              >
                {extractedExams.every(e => e.selected !== false) ? "Deselect All" : "Select All"}
              </button>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-700/60 bg-slate-950/50">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-800/60 text-slate-300 uppercase tracking-wide text-xs">
                  <tr>
                    <th className="px-4 py-3 text-left w-10">
                      <input
                        type="checkbox"
                        checked={extractedExams.length > 0 && extractedExams.every(e => e.selected !== false)}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          setExtractedExams(current => current.map(ex => ({ ...ex, selected: checked })));
                        }}
                        className="rounded border-slate-600 bg-slate-800 text-purple-500 focus:ring-purple-500 cursor-pointer"
                      />
                    </th>
                    <th className="px-4 py-3 text-left">Days and Dates</th>
                    <th className="px-4 py-3 text-left">Paper</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {normalizedExams.map((exam, index) => {
                    const isSelected = exam.selected !== false;
                    return (
                      <tr
                        key={index}
                        className={`hover:bg-slate-800/40 transition-colors cursor-pointer ${isSelected ? "bg-purple-500/5" : "opacity-60"}`}
                        onClick={() => {
                          setExtractedExams(current =>
                            current.map((e, i) => i === index ? { ...e, selected: !isSelected } : e)
                          );
                        }}
                      >
                        <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                          <div className="flex items-center justify-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => {
                                setExtractedExams(current =>
                                  current.map((e, i) => i === index ? { ...e, selected: !isSelected } : e)
                                );
                              }}
                              className="rounded border-slate-600 bg-slate-800 text-purple-500 focus:ring-purple-500 cursor-pointer w-4 h-4"
                            />
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <p className={`font-semibold ${isSelected ? "text-white" : "text-slate-400"}`}>{exam.dayName},</p>
                          <p className="text-slate-500 text-sm">{exam.dateLabel}</p>
                        </td>
                        <td className="px-4 py-3 min-w-[280px]">
                          <p className={`${isSelected ? "text-white" : "text-slate-400"}`}>{exam.paperName}</p>
                          {exam.venue && <p className="text-xs text-slate-500 mt-1">📍 {exam.venue}</p>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* NSGA-II Study Schedule Tab */}
        {activeTab === "schedule" && (
          <div className="space-y-6">
            {/* Generate Schedule Section */}
            <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-green-500/20 shadow-2xl">
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <span className="text-2xl">🧬</span>
                NSGA-II Study Schedule Generator
              </h2>
              <p className="text-slate-400 mb-6">
                Generate an optimized 2-month study schedule using the NSGA-II (Non-dominated Sorting Genetic Algorithm II)
                multi-objective optimization. The algorithm balances:
              </p>
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-slate-800/50 p-4 rounded-lg border border-blue-500/20">
                  <p className="text-blue-400 font-semibold">📊 Even Distribution</p>
                  <p className="text-xs text-slate-400 mt-1">Spreads study sessions evenly to avoid cramming</p>
                </div>
                <div className="bg-slate-800/50 p-4 rounded-lg border border-yellow-500/20">
                  <p className="text-yellow-400 font-semibold">🔄 Context Switching</p>
                  <p className="text-xs text-slate-400 mt-1">Minimizes subject changes for focused learning</p>
                </div>
                <div className="bg-slate-800/50 p-4 rounded-lg border border-green-500/20">
                  <p className="text-green-400 font-semibold">⏰ Exam Priority</p>
                  <p className="text-xs text-slate-400 mt-1">Prioritizes subjects with upcoming exams</p>
                </div>
              </div>

              {normalizedExams.length === 0 ? (
                <div className="text-center py-8 text-slate-500">
                  <p className="text-4xl mb-2">📅</p>
                  <p>Upload an exam timetable first to generate a study schedule</p>
                </div>
              ) : (
                <div className="flex items-center gap-4">
                  <button
                    onClick={generateStudySchedule}
                    disabled={generatingSchedule}
                    className={`px-6 py-3 rounded-lg font-semibold transition-all ${generatingSchedule
                      ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                      : "bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 text-white shadow-lg hover:shadow-green-500/25"
                      }`}
                  >
                    {generatingSchedule ? (
                      <>
                        <span className="animate-spin inline-block mr-2">⚙️</span>
                        Running NSGA-II...
                      </>
                    ) : (
                      <>🧬 Generate Optimized Schedule</>
                    )}
                  </button>
                  <span className="text-slate-400 text-sm">
                    Based on {normalizedExams.length} exams
                  </span>
                </div>
              )}
            </div>

            {/* Display Generated Schedule */}
            {studySchedule && studySchedule.length > 0 && (
              <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-emerald-500/20 shadow-2xl">
                <h2 className="text-xl font-bold mb-6 flex items-center gap-2 flex-1">
                  <span className="text-2xl">📅</span>
                  Your Optimized Study Schedule ({studySchedule.length} days)
                </h2>

                {/* Schedule Selection Tabs */}
                {availableSchedules.length > 1 && (
                  <div className="mb-6 bg-slate-800/50 p-2 rounded-xl flex flex-wrap gap-2">
                    {availableSchedules.map((option, idx) => (
                      <button
                        key={option.id}
                        onClick={() => {
                          setSelectedScheduleIdx(idx);
                          setStudySchedule(option.schedule);
                        }}
                        className={`flex-1 min-w-[150px] py-3 px-4 rounded-lg transition-all text-sm font-semibold flex flex-col items-center gap-1 ${selectedScheduleIdx === idx
                            ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-lg"
                            : "bg-slate-700/50 text-slate-400 hover:bg-slate-700 hover:text-white"
                          }`}
                      >
                        <span className="text-base">{option.label}</span>
                        {option.objectives && (
                          <span className="text-[10px] opacity-80 font-normal">
                            Spread: {option.objectives.cramming.toFixed(1)} |
                            Switches: {option.objectives.switching}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                <button
                  onClick={saveScheduleToCalendar}
                  disabled={saving}
                  className={`px-4 py-2 rounded-lg font-bold text-sm transition-all mb-6 ${saving
                    ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                    : "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-500/20"
                    }`}
                >
                  {saving ? "Saving..." : "💾 Save to Calendar"}
                </button>


                {/* Schedule Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                    <p className="text-2xl font-bold text-emerald-400">{studySchedule.length}</p>
                    <p className="text-xs text-slate-400">Total Days</p>
                  </div>
                  <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                    <p className="text-2xl font-bold text-blue-400">
                      {studySchedule.reduce((sum, day) => sum + day.sessions.reduce((s, sess) => s + sess.hours, 0), 0)}h
                    </p>
                    <p className="text-xs text-slate-400">Total Study Hours</p>
                  </div>
                  <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                    <p className="text-2xl font-bold text-yellow-400">
                      {studySchedule.reduce((sum, day) => sum + day.sessions.length, 0)}
                    </p>
                    <p className="text-xs text-slate-400">Study Sessions</p>
                  </div>
                  <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                    <p className="text-2xl font-bold text-purple-400">
                      {Math.round(studySchedule.reduce((sum, day) => sum + day.sessions.reduce((s, sess) => s + sess.hours, 0), 0) / studySchedule.length * 10) / 10}h
                    </p>
                    <p className="text-xs text-slate-400">Avg Hours/Day</p>
                  </div>
                </div>

                {/* Schedule Grid */}
                <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
                  {studySchedule.map((day, dayIndex) => (
                    <div
                      key={dayIndex}
                      className={`border rounded-xl p-4 ${day.isWeekend
                        ? "border-orange-500/30 bg-orange-500/5"
                        : "border-slate-700/60 bg-slate-800/30"
                        }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <span className="text-lg font-bold text-white">
                            {day.dateLabel}
                          </span>
                          {day.isWeekend && (
                            <span className="px-2 py-1 bg-orange-500/20 text-orange-300 text-xs rounded">
                              Weekend
                            </span>
                          )}
                        </div>
                        <span className="text-slate-400 text-sm">
                          {day.sessions.reduce((sum, s) => sum + s.hours, 0)} hours total
                        </span>
                      </div>

                      {day.sessions.length === 0 ? (
                        <p className="text-slate-500 text-sm">Rest day 🧘</p>
                      ) : (
                        <div className="space-y-3">
                          {day.sessions.map((session, sessIndex) => (
                            <div
                              key={sessIndex}
                              className={`p-4 rounded-lg border ${session.priority === "high"
                                ? "border-red-500/40 bg-red-500/10"
                                : session.priority === "medium"
                                  ? "border-yellow-500/40 bg-yellow-500/10"
                                  : "border-slate-600/40 bg-slate-700/30"
                                }`}
                            >
                              <div className="flex items-start justify-between mb-2">
                                <div>
                                  <p className="font-semibold text-white">{session.subject}</p>
                                  <p className="text-slate-400 text-xs">
                                    {session.startTime} - {session.endTime} ({session.hours}h)
                                  </p>
                                </div>
                                <div className="text-right">
                                  <span className="text-xs">{getPriorityBadge(session.priority)}</span>
                                  {session.daysUntilExam < 999 && (
                                    <p className="text-slate-400 text-xs mt-1">
                                      Exam in {session.daysUntilExam} days
                                    </p>
                                  )}
                                </div>
                              </div>

                              {/* Study Tasks */}
                              <div className="flex flex-wrap gap-2 mt-2">
                                {session.tasks.map((task, taskIndex) => (
                                  <span
                                    key={taskIndex}
                                    className={`px-2 py-1 text-xs rounded border ${getTaskTypeColor(task.type)}`}
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
              </div>
            )}
          </div>
        )}

        {/* Extracted Courses */}
        {activeTab === "syllabus" && extractedCourses.length > 0 && (
          <div className="bg-slate-900/80 backdrop-blur-sm p-8 rounded-2xl border border-purple-500/20 shadow-2xl">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              <span className="text-2xl">🎓</span>
              Extracted Courses ({extractedCourses.length})
            </h2>

            {/* Summary Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                <p className="text-2xl font-bold text-cyan-400">{extractedCourses.length}</p>
                <p className="text-xs text-slate-400">Courses</p>
              </div>
              <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                <p className="text-2xl font-bold text-blue-400">
                  {extractedCourses.reduce((sum, c) => sum + (c.modules?.length || 0), 0)}
                </p>
                <p className="text-xs text-slate-400">Modules</p>
              </div>
              <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                <p className="text-2xl font-bold text-green-400">
                  {extractedCourses.reduce((sum, c) => sum + (c.total_hours || c.estimated_hours || 0), 0)}h
                </p>
                <p className="text-xs text-slate-400">Total Hours</p>
              </div>
              <div className="bg-slate-800/50 p-4 rounded-lg text-center">
                <p className="text-2xl font-bold text-purple-400">
                  {extractedCourses.reduce((sum, c) => sum + (c.topics?.length || 0), 0)}
                </p>
                <p className="text-xs text-slate-400">Topics</p>
              </div>
            </div>

            <div className="grid gap-4">
              {extractedCourses.map((course, index) => (
                <div
                  key={index}
                  className="bg-gradient-to-br from-slate-800/80 to-slate-700/50 p-5 rounded-xl border border-slate-600/30 hover:border-purple-500/40 transition-all"
                >
                  <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                    <div>
                      <h3 className="text-lg font-bold text-white">{course.name}</h3>
                      {course.code && (
                        <p className="text-cyan-400 text-sm font-mono">{course.code}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-3 py-1 rounded-full text-xs font-semibold border ${getDifficultyColor(course.difficulty)}`}>
                        {course.difficulty?.toUpperCase() || "MEDIUM"}
                      </span>
                      <span className="text-slate-400 text-sm">
                        {course.total_hours || course.estimated_hours || 48} hrs
                      </span>
                    </div>
                  </div>

                  {/* Modules */}
                  {course.modules && course.modules.length > 0 && (
                    <div className="mb-3">
                      <p className="text-slate-400 text-xs font-semibold mb-2">📘 MODULES ({course.modules.length})</p>
                      <div className="flex flex-wrap gap-2">
                        {course.modules.slice(0, 6).map((module, mi) => (
                          <span key={mi} className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-xs">
                            {typeof module === 'string' ? module : module.title || module.name}
                          </span>
                        ))}
                        {course.modules.length > 6 && (
                          <span className="text-slate-500 text-xs">+{course.modules.length - 6} more</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Topics */}
                  {course.topics && course.topics.length > 0 && (
                    <div>
                      <p className="text-slate-400 text-xs font-semibold mb-2">🎯 TOPICS ({course.topics.length})</p>
                      <div className="flex flex-wrap gap-2">
                        {course.topics.slice(0, 8).map((topic, ti) => (
                          <span key={ti} className="bg-purple-500/20 text-purple-300 px-2 py-1 rounded text-xs">
                            {topic}
                          </span>
                        ))}
                        {course.topics.length > 8 && (
                          <span className="text-slate-500 text-xs">+{course.topics.length - 8} more</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {activeTab === "syllabus" && extractedCourses.length === 0 && !loading && (
          <div className="text-center py-12 text-slate-500">
            <p className="text-6xl mb-4">📚</p>
            <p className="text-lg">No syllabus uploaded yet</p>
            <p className="text-sm">Upload a PDF to extract courses automatically</p>
          </div>
        )}
        {activeTab === "exam" && extractedExams.length === 0 && !loading && (
          <div className="text-center py-12 text-slate-500">
            <p className="text-6xl mb-4">📅</p>
            <p className="text-lg">No exam timetable uploaded yet</p>
            <p className="text-sm">Upload a PDF to extract exam schedule (supports scanned images)</p>
          </div>
        )}
      </div>
    </div >
  );
}
