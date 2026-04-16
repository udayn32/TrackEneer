# TrackEneer — Architecture & Module Interaction Diagrams

This document captures the architecture and interaction flows for every major module of the **TrackEneer** platform, including the updated **Insights** diagram, the **Career Readiness** module, and the **Scheduling** module.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Insights Module](#2-insights-module)
3. [Career Readiness Module](#3-career-readiness-module)
4. [Scheduling Module](#4-scheduling-module)
5. [Module Interaction Map](#5-module-interaction-map)

---

## 1. System Overview

```mermaid
graph TB
    User(["👤 User"])

    subgraph TrackEneer["TrackEneer Platform"]
        direction TB
        AUTH["🔐 Auth & Profile"]
        DASH["📊 Dashboard"]

        subgraph MODULES["Core Modules"]
            INS["📈 Insights"]
            SCHED["📅 Scheduling"]
            CR["🎓 Career Readiness"]
        end
    end

    DB[("🗄️ Database")]
    EXT["🌐 External APIs\n(News / Trends / LLM)"]

    User --> AUTH
    AUTH --> DASH
    DASH --> INS
    DASH --> SCHED
    DASH --> CR
    INS & SCHED & CR --> DB
    CR --> EXT
```

---

## 2. Insights Module

The Insights module aggregates academic performance data, visualises progress across subjects, and surfaces actionable analytics to the student.

```mermaid
flowchart TD
    START(["Student opens\nInsights Tab"])

    subgraph DATA_COLLECTION["Data Collection Layer"]
        AT["Attendance Records"]
        MK["Marks / Grades"]
        AS["Assignment Submissions"]
        EX["Exam Scores"]
    end

    subgraph PROCESSING["Processing & Analytics Engine"]
        AGG["Data Aggregation"]
        TREND["Trend Analysis\n(Moving Average)"]
        RANK["Subject-wise\nPerformance Ranking"]
        GAP["Gap / Weak Area\nDetection"]
        PRED["Predictive Score\nEstimation (ML)"]
    end

    subgraph VISUALISATION["Visualisation Layer"]
        RADAR["📡 Radar Chart\n(Subject Balance)"]
        LINE["📉 Line Graph\n(Progress Over Time)"]
        BAR["📊 Bar Chart\n(Marks Distribution)"]
        HEAT["🔥 Heatmap\n(Attendance × Performance)"]
        CARD["🃏 Summary Cards\n(GPA · CGPA · Rank)"]
    end

    subgraph ACTIONS["Actionable Insights"]
        RECM["📌 Study Recommendations"]
        ALERT["⚠️ Low-Score Alerts"]
        GOAL["🎯 Goal Tracker"]
    end

    START --> DATA_COLLECTION
    AT & MK & AS & EX --> AGG
    AGG --> TREND & RANK & GAP & PRED
    TREND --> LINE
    RANK --> RADAR & BAR
    GAP --> HEAT & ALERT
    PRED --> CARD & GOAL
    CARD & GOAL & ALERT --> RECM
    RADAR & LINE & BAR & HEAT & CARD --> END_VIS(["📲 Rendered on Dashboard"])
    RECM --> END_VIS
```

### Key Insight Metrics

| Metric | Source | Visualisation |
|---|---|---|
| Subject-wise GPA | Marks records | Radar chart |
| Attendance rate | Attendance records | Heatmap |
| Score trend | Historical exam scores | Line graph |
| Rank (batch/class) | Aggregated marks | Summary card |
| Weak areas | Gap detection engine | Alert cards |
| Predicted final score | ML estimation model | Goal tracker |

---

## 3. Career Readiness Module

The Career Readiness module prepares students for placements by offering aptitude practice, skill assessment, and live IT trend monitoring.

```mermaid
flowchart TD
    CR_START(["Student opens\nCareer Readiness Tab"])

    subgraph TABS["Module Tabs"]
        TAB1["🧩 Aptitude Practice"]
        TAB2["🔗 Latest IT Trends"]
        TAB3["💼 Skill Profiling"]
        TAB4["📝 Resume Builder"]
    end

    CR_START --> TABS

    %% ── Aptitude Practice Tab ──
    subgraph APT["Aptitude Practice Flow"]
        direction TB
        APT_SEL["Select Topic\n(Quant · Verbal · Logical · Technical)"]
        APT_DIFF["Select Difficulty\n(Easy · Medium · Hard)"]
        APT_GEN["🤖 APT Question Generator\n(LLM / Question Bank)"]
        APT_Q["Display Question\n+ Options"]
        APT_ANS["Student Answers"]
        APT_EVAL["Evaluate Answer\n+ Explanation"]
        APT_SCORE["Update Score &\nPerformance Tracker"]
    end

    TAB1 --> APT_SEL --> APT_DIFF --> APT_GEN --> APT_Q
    APT_Q --> APT_ANS --> APT_EVAL --> APT_SCORE
    APT_SCORE -->|"Next Question"| APT_Q

    %% ── Latest IT Trends Tab ──
    subgraph TRENDS["Latest IT Trends Flow"]
        direction TB
        TR_FETCH["Fetch Live IT Trends\n(RSS / News API / Scraper)"]
        TR_CAT["Categorise by Domain\n(AI · Cloud · Cybersecurity\n· Web Dev · Data Science)"]
        TR_LINK["Display as Curated\nLink Cards 🔗"]
        TR_FILTER["Filter / Search\nby Keyword or Domain"]
        TR_SAVE["Bookmark Trends\nfor Later Reading"]
    end

    TAB2 --> TR_FETCH --> TR_CAT --> TR_LINK
    TR_LINK --> TR_FILTER
    TR_LINK --> TR_SAVE

    %% ── Skill Profiling Tab ──
    subgraph SKILL["Skill Profiling"]
        SK_ASSESS["Self / Quiz-based\nSkill Assessment"]
        SK_MAP["Skill Gap Map\nvs Job Role Requirements"]
        SK_ROAD["Learning Roadmap\nSuggestion"]
    end

    TAB3 --> SK_ASSESS --> SK_MAP --> SK_ROAD

    %% ── Resume Builder Tab ──
    subgraph RESUME["Resume Builder"]
        RES_FORM["Fill Profile Details"]
        RES_GEN["Auto-generate Resume\n(Template Engine)"]
        RES_DL["Download PDF / DOCX"]
    end

    TAB4 --> RES_FORM --> RES_GEN --> RES_DL
```

### APT Question Generator — Detail

```mermaid
sequenceDiagram
    participant S as Student
    participant UI as Career Readiness UI
    participant QG as Question Generator
    participant QB as Question Bank (DB)
    participant LLM as LLM API (optional)

    S->>UI: Select topic + difficulty
    UI->>QG: Request question (topic, difficulty, count)
    QG->>QB: Fetch matching questions
    QB-->>QG: Return pool of questions
    alt Questions available in bank
        QG-->>UI: Serve question(s)
    else Insufficient questions
        QG->>LLM: Generate new question(s)
        LLM-->>QG: Return generated questions
        QG->>QB: Store new questions
        QG-->>UI: Serve generated question(s)
    end
    UI-->>S: Display question + options
    S->>UI: Submit answer
    UI->>QG: Evaluate answer
    QG-->>UI: Correct / Incorrect + Explanation
    UI-->>S: Show result & update score
```

### Latest IT Trends Tab — Link Card Format

```mermaid
flowchart LR
    API["🌐 News / Trends API\n(e.g., Hacker News · Dev.to\n· Google Trends · TechCrunch RSS)"]
    PARSE["Parser & Normaliser"]
    CACHE["Cache Layer\n(Redis / In-memory)"]

    subgraph DISPLAY["Trends Display"]
        D1["🔗 AI & Machine Learning"]
        D2["🔗 Cloud & DevOps"]
        D3["🔗 Cybersecurity"]
        D4["🔗 Web / Mobile Dev"]
        D5["🔗 Data Science & Analytics"]
        D6["🔗 Emerging Tech\n(Quantum · Blockchain · AR/VR)"]
    end

    API --> PARSE --> CACHE --> DISPLAY
```

> **Each link card contains:** Article title · Source name · Published date · Direct URL · Domain tag

---

## 4. Scheduling Module

The Scheduling module creates an optimised personal study schedule by combining user-defined tasks, syllabus subjects, exam timetable, and the Eisenhower priority matrix, solved via **NSGA-II** multi-objective optimisation.

```mermaid
flowchart TD
    SCH_START(["Student opens\nScheduling Module"])

    subgraph INPUTS["📥 Input Sources"]
        I1["📋 Manual Tasks\n(Title · Due Date · Priority · Duration)"]
        I2["📚 Syllabus Upload\n(PDF / Text)"]
        I3["📅 Exam Timetable\n(Subject · Date · Time · Venue)"]
        I4["⏰ Student Availability\n(Free slots, Sleep/Break prefs)"]
    end

    SCH_START --> INPUTS

    subgraph PROCESSING["⚙️ Processing Pipeline"]
        SYL_EXT["🔍 Subject Extractor\n(NLP / PDF Parser)\nExtracts units & topics\nfrom syllabus"]
        TASK_AGG["Task Aggregator\n(Merge manual + syllabus tasks)"]
        EISEN["🧩 Eisenhower Matrix\nClassifier\n│ Urgent+Important │ Important │\n│ Urgent           │ Neither   │"]
        WEIGHT["Priority Weighting\n(Deadline proximity · Exam date\n· Importance score)"]
        NSGA["🧬 NSGA-II Optimiser\nObjectives:\n① Maximise coverage of syllabus\n② Minimise deadline violations\n③ Balance daily cognitive load\n④ Respect exam timetable gaps"]
        CONFLICT["Conflict Resolver\n(Overlapping slots · Buffer time)"]
    end

    I1 --> TASK_AGG
    I2 --> SYL_EXT --> TASK_AGG
    I3 --> WEIGHT
    I4 --> NSGA
    TASK_AGG --> EISEN --> WEIGHT --> NSGA
    NSGA --> CONFLICT

    subgraph OUTPUT["📤 Output Views"]
        CAL["📆 Weekly Calendar View"]
        DAY["🗓️ Day-wise Study Plan"]
        EXAM_VIEW["📌 Exam Countdown\nPanel"]
        STATS["📊 Load Distribution\nChart"]
    end

    CONFLICT --> CAL & DAY & EXAM_VIEW & STATS
```

### Eisenhower Matrix Classification

```mermaid
quadrantChart
    title Eisenhower Matrix — Task Prioritisation
    x-axis Low Urgency --> High Urgency
    y-axis Low Importance --> High Importance
    quadrant-1 Do First (Schedule immediately)
    quadrant-2 Schedule (Plan for later)
    quadrant-3 Delegate / Minimise
    quadrant-4 Eliminate
    Exam Revision: [0.85, 0.9]
    Assignment Due Today: [0.9, 0.75]
    Project Research: [0.4, 0.8]
    Skill Building: [0.35, 0.7]
    Emails & Admin: [0.7, 0.35]
    Social Media: [0.6, 0.2]
    Elective Reading: [0.2, 0.45]
    Low-priority Tasks: [0.25, 0.25]
```

### NSGA-II Multi-Objective Optimisation Flow

```mermaid
flowchart TD
    INIT["Initialise Population\n(Random schedule candidates)"]
    EVAL["Evaluate Fitness\nfor all 4 objectives"]

    subgraph OBJECTIVES["Fitness Objectives (minimise)"]
        O1["① Uncovered syllabus topics"]
        O2["② Deadline violations"]
        O3["③ Daily load imbalance\n(variance across days)"]
        O4["④ Exam-day study gaps\n(too close / too sparse)"]
    end

    FRONT["Non-dominated Sorting\n→ Pareto Fronts"]
    CROWD["Crowding Distance\nCalculation"]
    SELECT["Binary Tournament\nSelection"]
    CROSS["Crossover\n(Schedule Slot Swap)"]
    MUTATE["Mutation\n(Task Time Shift)"]
    NEWPOP["New Population"]
    CONV{"Convergence?\n(Max gen / ΔFitness < ε)"}
    RESULT["🏆 Pareto-optimal\nSchedule Set"]
    PICK["Present Best Schedule\nto Student\n(with alt options)"]

    INIT --> EVAL
    EVAL --> O1 & O2 & O3 & O4
    O1 & O2 & O3 & O4 --> FRONT --> CROWD --> SELECT
    SELECT --> CROSS --> MUTATE --> NEWPOP --> EVAL
    NEWPOP --> CONV
    CONV -- No --> SELECT
    CONV -- Yes --> RESULT --> PICK
```

### Syllabus Subject Extractor — Detail

```mermaid
flowchart LR
    UP["📄 Syllabus Upload\n(PDF · DOCX · Text)"]
    PARSE2["Document Parser\n(PyMuPDF / python-docx)"]
    NLP["NLP Pipeline\n(tokenise · POS tag · NER)"]

    subgraph EXTRACT["Extraction Steps"]
        E1["Detect Unit / Module\nHeadings"]
        E2["Extract Topic Names\nunder each Unit"]
        E3["Estimate Study Hours\nper Topic (heuristic)"]
        E4["Tag by Subject /\nCourse Code"]
    end

    STRUCT["Structured JSON\n{ subject, units, topics,\n  estimatedHours }"]
    TASK_OUT["→ Feeds into\nTask Aggregator"]

    UP --> PARSE2 --> NLP --> EXTRACT
    E1 & E2 & E3 & E4 --> STRUCT --> TASK_OUT
```

---

## 5. Module Interaction Map

Shows how the three core modules share data and interact at runtime.

```mermaid
flowchart TD
    subgraph USER["👤 User Layer"]
        U["Student"]
    end

    subgraph PLATFORM["TrackEneer Platform"]
        direction LR

        subgraph INS2["📈 Insights Module"]
            INS_PERF["Performance\nAnalytics"]
            INS_WEAK["Weak Area\nDetection"]
        end

        subgraph CR2["🎓 Career Readiness Module"]
            CR_APT["Aptitude\nPractice"]
            CR_TRENDS["IT Trends\nLinks"]
            CR_SKILL["Skill\nProfiler"]
        end

        subgraph SCHED2["📅 Scheduling Module"]
            SCH_NSGA["NSGA-II\nOptimiser"]
            SCH_CAL["Calendar\nView"]
        end

        DB2[("🗄️ Shared\nDatabase")]
    end

    subgraph EXTERNAL["🌐 External Services"]
        NEWS_API["News / Trends API"]
        LLM_API["LLM API"]
        SYLLABUS_PARSER["Syllabus Parser\nService"]
    end

    U --> INS2 & CR2 & SCHED2

    %% Insights → Scheduling
    INS_WEAK -->|"Weak subjects\n→ prioritise in schedule"| SCH_NSGA

    %% Insights → Career Readiness
    INS_WEAK -->|"Weak areas\n→ suggest aptitude topics"| CR_APT

    %% Career Readiness → Scheduling
    CR_APT -->|"Practice session\ntime blocks"| SCH_CAL

    %% External connections
    CR_TRENDS --> NEWS_API
    CR_APT --> LLM_API
    SCHED2 --> SYLLABUS_PARSER

    %% Database
    INS2 & CR2 & SCHED2 <--> DB2
```

---

*Last updated: April 2026 — TrackEneer Architecture Team*
