# Study Module

A complete study management system for organizing subjects, notes, and files.

## Features

### Backend (FastAPI)
- **Subject Management**: Create, list, and delete subjects
- **File Upload**: Upload study materials (PDF, DOCX, TXT, etc.)
- **File Download**: Download uploaded files
- **File Preview**: View files directly in browser (PDF, images, text files)
- **Statistics**: Track total subjects, notes, storage used
- **Recent Notes**: Quick access to recently uploaded materials

### Frontend (Next.js)
- **Dark Theme**: Consistent with landing page (cyan, blue, purple)
- **Subject Sidebar**: Easy navigation between subjects
- **File Management**: Upload, download, and delete files
- **File Preview**: View PDFs, images, and text files in-browser
- **Statistics Dashboard**: Visual overview of study materials
- **Responsive Design**: Works on desktop and mobile

## Backend Setup

1. **Navigate to server directory**:
   ```bash
   cd c:\Trackeneer\server
   ```

2. **Start the Study API** (Port 5002):
   ```bash
   python study.py
   ```
   Or double-click `start_study.bat`

## Frontend Setup

The study page is already integrated at `/study` route.

**Environment Variable** (Optional):
Add to `client/.env.local`:
```
NEXT_PUBLIC_STUDY_API=http://localhost:5002
```

## API Endpoints

### Subjects
- `GET /api/subjects` - Get all subjects
- `POST /api/subjects` - Create new subject
- `DELETE /api/subjects/{id}` - Delete subject

### Notes
- `GET /api/notes` - Get all notes (optional: `?subject_id=`)
- `POST /api/notes/upload` - Upload file
- `GET /api/notes/{id}/download` - Download file
- `GET /api/notes/{id}/preview` - Preview file in browser
- `DELETE /api/notes/{id}` - Delete note
- `GET /api/notes/recent?limit=5` - Get recent notes

### Statistics
- `GET /api/study/stats` - Get study statistics

## Data Storage

- **Subjects**: Stored in `server/subjects.json`
- **Notes Metadata**: Stored in `server/notes.json`
- **Files**: Stored in `server/uploads/` directory

## Usage

1. **Start Backend**: Run `python study.py` (port 5001)
2. **Start Frontend**: Run `npm run dev` in client directory (port 3000)
3. **Access**: Navigate to `http://localhost:3000/study`

### Workflow:
1. Click "Add Subject" to create a new subject
2. Select a subject from the sidebar
3. Click "Upload File" to add study materials
4. Click "👁️ View" to preview files in browser (PDF, images, text)
5. Download or delete files as needed
6. View statistics at the top of the page

## File Types Supported

### Previewable Files:
- **PDF documents** 📄 - Full preview in browser
- **Images** 🖼️ - PNG, JPG, JPEG, GIF, SVG
- **Text files** � - TXT, MD, JSON, HTML, CSS, JS

### Downloadable Only:
- Word documents (DOCX) 📝
- Other files �

All file types can be uploaded and downloaded. Previewable files have a "�️ View" button for instant preview.

## Dashboard Integration

The "Recent Files" widget on the dashboard shows your recently uploaded study materials. Click "Go to Study" to access the full Study Hub.

## Notes

- Files are stored with unique IDs to prevent conflicts
- File metadata includes original filename, size, upload date
- Subjects track the number of associated notes
- All data persists in JSON files for simplicity
