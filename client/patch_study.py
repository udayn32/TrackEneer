import re

file_path = "c:/Trackeneer/client/src/app/study/page.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Rename Header
content = content.replace("<h1>?? Knowledge Graph</h1>", "<h1>?? Study Module</h1>")
content = content.replace("<h1 className=\"text-3xl font-bold text-white flex items-center gap-3\">?? Knowledge Graph</h1>", "<h1 className=\"text-3xl font-bold text-white flex items-center gap-3\">?? Study Module</h1>")

# Subtitle
content = content.replace("Interactive force-directed concept map — drag nodes, scroll to zoom, pan the view", "Organize Subjects, upload notes, and explore them as an interactive Knowledge Graph")

# Document to Subject Name
content = content.replace("?? Document:", "?? Subject:")
content = content.replace("All Documents (", "All Subjects (")

# KnowledgeGraphPage to StudyPage
content = content.replace("export default function KnowledgeGraphPage", "export default function StudyPage")

# handleUpload
old_handle = '''    const handleUpload = async () => {
        if (!uploadFile) return
        const fileName = uploadFile.name
        setUploading(true)
        setPreprocessLog(null)
        try {
            const fd = new FormData()
            fd.append('file', uploadFile)
            fd.append('email', email)
            fd.append('strategy', 'llm')
            const uploadRes = await fetch(${API}/api/knowledge-graph/upload, { method: 'POST', body: fd })
            const uploadData = await uploadRes.json().catch(() => ({}))
            if (uploadData.preprocessing_stats) setPreprocessLog(uploadData.preprocessing_stats)

            // Upload now processes synchronously — refresh documents and graph immediately
            const docsRes = await fetch(${API}/api/knowledge-graph/documents?email=)
            const docsData = await docsRes.json().catch(() => ({}))
            const docs = docsData.documents || []
            setDocuments(docs)
            const found = docs.find(doc => doc.document === fileName)
            if (found) {
                setSelectedDoc(fileName)
                fetchGraph(fileName)
                setTab('graph')
            } else {
                fetchGraph()
            }
        } catch (e) { console.error(e) }
        finally { setUploading(false); setUploadFile(null) }
    }'''

new_handle = '''    const handleUpload = async () => {
        if (!uploadFile) return
        const subName = prompt("Enter Subject Name for this Note:") || "General"

        setUploading(true)
        setPreprocessLog(null)
        try {
            // Create or get subject
            const dfd = new FormData(); dfd.append('name', subName); fd.append('email', email);
            const rsub = await fetch(${API}/api/subjects, {method: 'POST', body: dfd})
            const subData = await rsub.json()
            const sid = subData.subject?.id || subData.id

            // Upload note
            const fd = new FormData()
            fd.append('file', uploadFile)
            fd.append('subject_id', sid)
            fd.append('email', email)
            
            // This triggers the process_file_background which processes it into the KG
            const uploadRes = await fetch(${API}/api/notes/upload, { method: 'POST', body: fd })
            const uploadData = await uploadRes.json().catch(() => ({}))
            
            alert(Uploaded note to subject ! The Knowledge Graph will start building in the background. Check back in a few moments.);
            
            // Refresh subjects selection list
            fetchDocuments()
        } catch (e) { console.error(e) }
        finally { setUploading(false); setUploadFile(null) }
    }'''

content = content.replace(old_handle, new_handle)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated page.jsx successfully.")
