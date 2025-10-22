# Placement Module - AI-Powered Company Research

A comprehensive placement preparation tool that uses Google's Gemini AI to generate detailed company insights for engineering students.

## 🌟 Features

### 1. **AI-Powered Company Research**
- Generate comprehensive company information using Gemini AI
- Automatic research based on company name and optional website
- 24-hour intelligent caching system

### 2. **Three Core Information Sections**
- **Vision & Mission**: Company vision, mission, and core values
- **Placement Process**: Detailed breakdown of interview rounds, eligibility, and preparation tips
- **Company Review**: Work culture, growth opportunities, salary packages, and honest reviews

### 3. **Intelligent Scoring System**
- Overall placement score (out of 10)
- Key strengths highlighted
- Important considerations for students
- Personalized recommendations

### 4. **Alumni Showcase**
- Display successful placements from previous batches
- Company, role, and package information
- Inspirational success stories

### 5. **Modern Dark Theme UI**
- Consistent with dashboard and schedule pages
- Cyan-blue-purple gradient color scheme
- Animated background effects
- Responsive design for all devices

## 🚀 Setup Instructions

### Backend Setup

1. **Install Dependencies**:
```bash
pip install google-generativeai fastapi uvicorn
```

2. **Configure Gemini API Key**:
- API key is already configured in `placement.py`
- Key: `AIzaSyAEVjafKd4U4cByblXTMjk2QuuMmfA87CM`

3. **Start Backend Server**:
```bash
# Option 1: Using batch file (Windows)
cd server
start_placement.bat

# Option 2: Direct Python command
python C:\Trackeneer\server\placement.py
```

Backend will run on: `http://localhost:5003`

### Frontend Setup

Frontend is already integrated at `/placement` route in Next.js app.

1. **Ensure Next.js is running**:
```bash
cd client
npm run dev
```

2. **Access the page**:
- Navigate to: `http://localhost:3000/placement`

## 📡 API Endpoints

### 1. Generate Company Information
```http
POST /api/placement/generate
Content-Type: multipart/form-data

Body:
- company_name: string (required)
- website: string (optional)

Response:
{
  "success": true,
  "company_name": "TCS",
  "website": "https://www.tcs.com",
  "sections": {
    "vision_mission": "...",
    "placement_process": "...",
    "company_review": "..."
  },
  "score_info": {
    "score": 8.5,
    "strengths": ["...", "...", "..."],
    "considerations": ["...", "..."],
    "recommendation": "..."
  },
  "generated_at": "2025-10-21T10:30:00",
  "cached": false
}
```

### 2. Get Cached Company Information
```http
GET /api/placement/company/{company_name}

Response: Same as generate endpoint, with cache status
```

### 3. List All Companies
```http
GET /api/placement/companies

Response:
{
  "companies": [
    {
      "company_name": "TCS",
      "website": "https://www.tcs.com",
      "generated_at": "2025-10-21T10:30:00",
      "cache_valid": true,
      "score": 8.5
    }
  ],
  "total": 1
}
```

### 4. Delete Company Cache
```http
DELETE /api/placement/company/{company_name}

Response:
{
  "message": "Company cache deleted successfully"
}
```

### 5. Get Alumni Data
```http
GET /api/placement/alumni

Response:
{
  "alumni": [
    {
      "name": "Priya Sharma",
      "batch": "2023",
      "company": "TCS",
      "role": "Software Engineer",
      "package": "7 LPA",
      "avatar": "👩‍💼"
    }
  ]
}
```

## 💡 Usage Workflow

1. **Navigate to Placement Page**: Go to `/placement` in your browser

2. **Enter Company Details**:
   - Enter company name (required)
   - Optionally add company website for more accurate results
   - Click "Generate Company Report"

3. **AI Processing**:
   - Gemini AI analyzes the company
   - Generates vision, mission, placement process, and reviews
   - Calculates overall score with strengths and considerations

4. **View Results**:
   - Three-column layout with all information
   - Overall score with star rating
   - Key strengths and considerations highlighted
   - Alumni placements shown at bottom

5. **Caching**:
   - Data cached for 24 hours
   - Subsequent requests use cached data (faster)
   - Cache automatically expires after 24 hours

## 🎨 UI Components

### Header Section
- Gradient cyan-blue-purple background
- User profile display (OAuth integration)
- Page title and description

### Search Form
- Company name input (required)
- Website input (optional)
- Loading state with spinner
- Error handling with styled messages

### Company Display Card
- Company name and website
- Overall score (out of 10) with star rating
- Strengths (green badges)
- Considerations (yellow badges)
- AI recommendation (blue highlight)

### Information Sections
- **Vision & Mission** (Cyan border)
- **Placement Process** (Purple border)
- **Company Review** (Blue border)
- Formatted content with headers, bullets, and paragraphs

### Alumni Section
- Grid layout with alumni cards
- Avatar, name, batch, company, role, package
- Hover effects on cards

## 🔧 Technical Details

### Backend (FastAPI)
- **File**: `server/placement.py`
- **Port**: 5003
- **AI Model**: Google Gemini Pro
- **Data Storage**: `companies.json` (file-based caching)
- **CORS**: Enabled for localhost:3000

### Frontend (Next.js)
- **File**: `client/src/app/placement/page.jsx`
- **Route**: `/placement`
- **Framework**: React with Next.js 15
- **Styling**: Tailwind CSS
- **Auth**: NextAuth session integration

### AI Prompting Strategy
The Gemini AI is prompted with a structured format to generate:
1. Vision, mission, and core values
2. Detailed placement process with rounds
3. Comprehensive company review including:
   - Work culture
   - Career growth
   - Salary information
   - Benefits
   - Work-life balance
   - Honest pros and cons

### Caching Mechanism
- Cache duration: 24 hours
- Timestamp-based validation
- Automatic cache invalidation
- Manual cache deletion option

## 🎯 Sample Companies to Try

- **IT Services**: TCS, Infosys, Wipro, Accenture, Cognizant
- **Product**: Google, Microsoft, Amazon, Adobe, Salesforce
- **Startups**: Zomato, Swiggy, Razorpay, CRED, Meesho
- **Consulting**: Deloitte, PwC, EY, KPMG
- **Core**: L&T, Siemens, ABB, Schneider Electric

## 🐛 Troubleshooting

### Backend Issues

**Problem**: Module not found error
```bash
ModuleNotFoundError: No module named 'google.generativeai'
```
**Solution**: Install the package
```bash
pip install google-generativeai
```

**Problem**: Port already in use
```bash
ERROR: [Errno 10048] error while attempting to bind on address
```
**Solution**: Change port in `placement.py` or kill existing process

**Problem**: API key invalid
```bash
ERROR: Invalid API key
```
**Solution**: Check Gemini API key configuration

### Frontend Issues

**Problem**: Cannot connect to backend
```bash
Failed to fetch
```
**Solution**: Ensure backend is running on port 5003

**Problem**: CORS error
```bash
CORS policy blocked
```
**Solution**: Backend already configured for localhost:3000

## 📊 Data Structure

### Company Data Format (companies.json)
```json
{
  "tcs": {
    "success": true,
    "company_name": "TCS",
    "website": "https://www.tcs.com",
    "sections": {
      "vision_mission": "Content...",
      "placement_process": "Content...",
      "company_review": "Content..."
    },
    "score_info": {
      "score": 8.5,
      "strengths": ["...", "...", "..."],
      "considerations": ["...", "..."],
      "recommendation": "..."
    },
    "raw_content": "Full AI response...",
    "generated_at": "2025-10-21T10:30:00.000000"
  }
}
```

## 🔐 Security Notes

- API key is hardcoded (suitable for development)
- For production, move to environment variables
- Implement rate limiting for API calls
- Add user authentication for access control

## 🚀 Future Enhancements

1. **Save to Profile**: Save researched companies to user profile
2. **Comparison Tool**: Compare multiple companies side-by-side
3. **Interview Questions**: Add company-specific interview questions
4. **Alumni Network**: Connect with alumni from specific companies
5. **Notification System**: Alert when new alumni join from target companies
6. **PDF Export**: Export company reports as PDF
7. **Real-time Updates**: WebSocket for live generation progress

## 📝 Notes

- First query may take 10-15 seconds (AI generation)
- Cached queries respond instantly
- Cache expires after 24 hours automatically
- Alumni data is currently sample data (to be integrated with database)

---

**Module Status**: ✅ Fully Functional
**Backend Port**: 5003
**Frontend Route**: /placement
**AI Model**: Gemini Pro
**Last Updated**: October 21, 2025
