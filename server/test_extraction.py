"""Test script for syllabus extraction"""

from document_processor import DocumentProcessor

# Test full flow
processor = DocumentProcessor()

# Parse the uploaded syllabus
subjects = processor.process_syllabus('uploads/documents/syllabus/20260118_233902_AIMLSyllabus.pdf')

print(f'=== Syllabus Extraction Complete ===')
print(f'Courses found: {len(subjects)}')
print()

total_hours = 0
total_modules = 0
total_topics = 0

for s in subjects:
    # Count modules (lines starting with 📘)
    modules = [t for t in s.topics if t.startswith('📘')]
    # Count topics (lines with •)
    topics = [t for t in s.topics if '•' in t]
    
    total_modules += len(modules)
    total_topics += len(topics)
    total_hours += s.estimated_hours
    
    print(f'📚 {s.name}')
    print(f'   Hours: {s.estimated_hours}h | Difficulty: {s.difficulty} | Priority: {s.priority}')
    print(f'   Modules: {len(modules)} | Topics: {len(topics)}')
    print(f'   Topics:')
    for t in s.topics:
        if t.startswith('📘'):
            print(f'      {t}')
        else:
            # Show truncated topics
            txt = t.strip()
            if len(txt) > 80:
                txt = txt[:77] + "..."
            print(f'        {txt}')
    print()

print('=' * 50)
print('📊 Summary:')
print(f'   Total Courses: {len(subjects)}')
print(f'   Total Modules: {total_modules}')
print(f'   Total Topics: {total_topics}')
print(f'   Total Hours: {total_hours}h')
if subjects:
    print(f'   Avg Hours/Course: {total_hours/len(subjects):.1f}h')
