import re
file_path = "c:/Trackeneer/client/src/components/EduKGView.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add useEffect hook to sync prop subjectName down to selectedDoc
sync_hook = '''    useEffect(() => {
        if (subjectName) {
            setSelectedDoc(subjectName)
            fetchGraph(subjectName)
        }
    }, [subjectName, fetchGraph])'''

content = content.replace("    const { data: session } = useSession()", f"    const {{ data: session }} = useSession()\n{sync_hook}")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Added sync hook")
