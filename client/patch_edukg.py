import re

file_path = "c:/Trackeneer/client/src/components/EduKGView.jsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace StudyPage with EduKGView
content = content.replace("export default function StudyPage() {", "export default function EduKGView({ subjectName }) {")

# Remove the bg-gradient from the main wrapper, just make it a clean div
content = re.sub(r'<main className="min-h-screen bg-gradient-to-br.*?">', '<div className="w-full relative">', content)
content = content.replace("</main>", "</div>")

# Remove the absolute gradient circles
content = re.sub(r'<div className="absolute inset-0 overflow-hidden pointer-events-none">.*?</div>\n\s*<div className="relative z-10 max-w-7xl mx-auto">', '<div className="relative z-10 w-full mb-12">', content, flags=re.DOTALL)

# Hide the header since the outer Study Hub has its own header
header_regex = r"\{/\* Header \*/\}.*?<div className=\"flex gap-3\">.*?</div>\n\s*</div>"
content = re.sub(header_regex, "", content, flags=re.DOTALL)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated EduKGView.jsx successfully.")
