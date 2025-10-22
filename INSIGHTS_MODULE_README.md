# Insights Module - AI-Powered Student Guidance

A comprehensive student guidance system that uses Cohere AI to generate personalized preparation guides based on year and branch.

## 🌟 Features

### 1. **Personalized Year-Wise Guidance**
- FE (First Year) - Foundation & Basics
- SE (Second Year) - Core Subjects & Skills
- TE (Third Year) - Specialization & Projects
- BE (Final Year) - Placement & Advanced Topics

### 2. **Branch-Specific Insights**
- Computer Engineering
- Information Technology
- Electronics Engineering
- Mechanical Engineering
- Civil Engineering
- Electrical Engineering

### 3. **Comprehensive Content Sections**
- Key Focus Areas
- Study Strategy
- Technical Skills to Develop
- Project Ideas
- Placement Preparation
- Extracurricular Activities
- Career Guidance
- Common Mistakes to Avoid

### 4. **Smart Caching**
- 24-hour cache for frequently requested insights
- Instant responses for cached data
- Reduces API calls and costs

### 5. **Beautiful Dark Theme UI**
- Consistent with placement and schedule modules
- Cyan-blue-purple gradient design
- Responsive for all devices
- OAuth profile integration

## 🚀 Setup Instructions

### Backend Setup

1. **Install Dependencies**:
```powershell
pip install cohere fastapi uvicorn
```

2. **Configure Cohere API Key**:
- API key is already configured in `insights.py`
- Key: `rM2zziYqveYXde5i74mQjLRSVU2NE22klhea4Xu1` (Cohere Free Trial)

3. **Start Backend Server**:
```powershell
# Option 1: Using batch file (Windows)
cd server
start_insights.bat

# Option 2: Direct Python command
python C:\Trackeneer\server\insights.py
```

Backend will run on: `http://localhost:5004`

### Frontend Setup

Frontend is already integrated at `/insights` route in Next.js app.

1. **Ensure Next.js is running**:
```powershell
cd client
npm run dev
```

2. **Access the page**:
- Navigate to: `http://localhost:3000/insights`

## 📡 API Endpoints

### 1. Generate Insights
```http
POST /api/insights/generate
Content-Type: multipart/form-data

Body:
- year: string (required) - FE, SE, TE, or BE
- branch: string (optional) - Computer, IT, Electronics, etc.

Response:
{
  "success": true,
  "year": "TE",
  "year_full_name": "Third Year Engineering",
  "branch": "Computer Engineering",
  "content": "...",
  "generated_at": "2025-10-21T10:30:00",
  "cached": false
}
```

### 2. Get Quick Tips
```http
GET /api/insights/quick-tips/{year}

Response:
{
  "success": true,
  "year": "FE",
  "tips": "..."
}
```

### 3. List Available Years
```http
GET /api/insights/years

Response:
{
  "years": [
    {
      "code": "FE",
      "full_name": "First Year Engineering",
      "focus": "Foundation & Basics"
    }
  ]
}
```

### 4. List Available Branches
```http
GET /api/insights/branches

Response:
{
  "branches": [
    {
      "code": "Computer",
      "full_name": "Computer Engineering"
    }
  ]
}
```

### 5. Clear Cache
```http
DELETE /api/insights/cache/{year}?branch=Computer

Response:
{
  "message": "Cache cleared successfully"
}
```

## 💡 Usage Workflow

1. **Navigate to Insights Page**: Go to `/insights` in your browser

2. **Select Your Details**:
   - Choose your year (FE/SE/TE/BE)
   - Optionally select your branch
   - Click "Generate My Preparation Guide"

3. **AI Processing**:
   - Cohere AI analyzes your year and branch
   - Generates comprehensive preparation guide
   - Includes focus areas, skills, projects, tips

4. **View Your Guide**:
   - Scrollable content with all sections
   - Formatted with headers, bullets, and emphasis
   - Actionable advice specific to your level

5. **Caching**:
   - Data cached for 24 hours
   - Subsequent requests use cached data (faster)
   - Cache automatically expires

## 🎨 UI Components

### Header Section
- Gradient cyan-blue-purple background
- User profile display (OAuth integration)
- Page title and description

### Selection Form
- Year dropdown (required)
- Branch dropdown (optional)
- Loading state with spinner
- Error handling with styled messages

### Content Display Card
- Year and branch display
- Comprehensive guide content
- Formatted sections with proper styling
- Markdown-like formatting (bold text, headers, bullets)

### Action Card
- Motivation section
- "Generate Again" button
- Success encouragement

### Empty State
- Year cards with icons
- Quick selection buttons
- Description of what to expect

## 🔧 Technical Details

### Backend (FastAPI)
- **File**: `server/insights.py`
- **Port**: 5004
- **AI Model**: Cohere Command-R (for comprehensive insights), Command-Light (for quick tips)
- **Data Storage**: `insights.json` (file-based caching)
- **CORS**: Enabled for localhost:3000

### Frontend (Next.js)
- **File**: `client/src/app/insights/page.jsx`
- **Route**: `/insights`
- **Framework**: React with Next.js 15
- **Styling**: Tailwind CSS
- **Auth**: NextAuth session integration

### AI Prompting Strategy
The Cohere AI is prompted with a structured format to generate:
1. Key focus areas for the year/branch
2. Study strategy and time management
3. Technical skills to develop
4. Project ideas with difficulty levels
5. Placement preparation timeline
6. Extracurricular recommendations
7. Career guidance options
8. Common mistakes to avoid

### Caching Mechanism
- Cache duration: 24 hours
- Timestamp-based validation
- Automatic cache invalidation
- Manual cache deletion option
- Reduces API calls and improves response time

## 🎯 Sample Use Cases

### First Year Student
- **Input**: FE + Computer Engineering
- **Output**: Foundation programming languages, basic data structures, first projects, study habits, time management

### Final Year Student
- **Input**: BE + IT
- **Output**: Advanced technologies, placement preparation, interview tips, project ideas for resume, higher education options

### General Guidance
- **Input**: SE (no branch selected)
- **Output**: General second-year advice applicable to all branches

## 🐛 Troubleshooting

### Backend Issues

**Problem**: Module not found error
```powershell
ModuleNotFoundError: No module named 'cohere'
```
**Solution**: Install the package
```powershell
pip install cohere
```

**Problem**: Port already in use
```bash
ERROR: [Errno 10048] error while attempting to bind on address
```
**Solution**: Change port in `insights.py` or kill existing process

**Problem**: API key invalid
```bash
ERROR: Invalid API key
```
**Solution**: Check Cohere API key configuration (trial key should work)

### Frontend Issues

**Problem**: Cannot connect to backend
```bash
Failed to fetch
```
**Solution**: Ensure backend is running on port 5004

**Problem**: Years/branches not loading
```bash
Empty dropdowns
```
**Solution**: Check backend `/api/insights/years` and `/api/insights/branches` endpoints

## 📊 Data Structure

### Insights Data Format (insights.json)
```json
{
  "FE_Computer": {
    "success": true,
    "year": "FE",
    "year_full_name": "First Year Engineering",
    "branch": "Computer Engineering",
    "content": "Detailed guide content...",
    "generated_at": "2025-10-21T10:30:00.000000"
  }
}
```

## 🔐 API Key Information

- **Service**: Cohere
- **Type**: Free Trial Key
- **Key**: `rM2zziYqveYXde5i74mQjLRSVU2NE22klhea4Xu1`
- **Limitations**: Rate-limited (sufficient for student use)
- **Valid for**: Non-commercial/educational purposes

## 🚀 Future Enhancements

1. **Progress Tracking**: Save user progress through the guide
2. **Custom Goals**: Let students set and track custom learning goals
3. **Resource Links**: Add links to courses, tutorials, books
4. **Community Features**: Share tips and experiences with peers
5. **Mentor Matching**: Connect with alumni or seniors
6. **Quiz Generation**: Generate quizzes for self-assessment
7. **PDF Export**: Export guide as PDF for offline reading
8. **Mobile App**: Build React Native app for mobile access

## 📝 Notes

- First query may take 5-10 seconds (AI generation)
- Cached queries respond instantly
- Cache expires after 24 hours automatically
- Year selection is required, branch is optional
- Content is specific to Xavier Institute of Engineering context

---

**Module Status**: ✅ Fully Functional
**Backend Port**: 5004
**Frontend Route**: /insights
**AI Model**: Cohere Command-R
**Last Updated**: October 21, 2025
