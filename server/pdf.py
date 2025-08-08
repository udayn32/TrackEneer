import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pdfplumber

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- The Heuristic & AI/ML Core ---
def extract_subjects_from_pdf(file_path):
    candidate_subjects = []
    try:
        with pdfplumber.open(file_path) as pdf:
            all_text_elements = []
            for page in pdf.pages:
                words = page.extract_words(extra_attrs=["fontname", "size"])
                all_text_elements.extend(words)

            if not all_text_elements:
                return []
            
            # --- START OF HEURISTIC SETUP ---
            overall_avg_size = sum(el['size'] for el in all_text_elements) / len(all_text_elements)
            body_sizes = [el['size'] for el in all_text_elements if el['size'] < overall_avg_size * 1.2]
            avg_body_size = sum(body_sizes) / len(body_sizes) if body_sizes else overall_avg_size
            
            # You can TUNE this value. 1.5 means headings are 50% larger than body text.
            heading_size_threshold = avg_body_size * 1.5
            # --- END OF HEURISTIC SETUP ---

            for page in pdf.pages:
                lines = page.extract_text_lines()
                for line in lines:
                    line_text = line['text'].strip()
                    if not line_text:
                        continue

                    # --- APPLYING THE HEURISTICS ---
                    # Get word information if available
                    line_words = line.get('words', [])
                    if line_words:
                        line_word_sizes = [word['size'] for word in line_words if 'size' in word]
                        avg_line_size = sum(line_word_sizes) / len(line_word_sizes) if line_word_sizes else 0
                        
                        # HEURISTIC 1: Is the font size significantly larger?
                        is_large_font = avg_line_size > heading_size_threshold
                        
                        # HEURISTIC 2: Is the text bold?
                        is_bold = any('Bold' in word.get('fontname', '') for word in line_words if 'fontname' in word)
                    else:
                        # Fallback if word-level data is not available
                        is_large_font = False
                        is_bold = False

                    # HEURISTIC 3: Does it match a common heading pattern (e.g., "1.1", "Chapter 1")?
                    is_pattern_match = re.match(r'^((\d+(\.\d+)*\s)|(Module\s\d+)|(CHAPTER\s[IVXLCDM]+)|(Unit\s\d+)|(UNIT\s[IVXLCDM]+))', line_text, re.IGNORECASE)
                    
                    # HEURISTIC 4: Check for subject-like patterns (all caps, title case)
                    is_subject_pattern = (
                        line_text.isupper() and len(line_text.split()) <= 6 or  # All caps, short
                        (line_text.istitle() and len(line_text.split()) <= 4)   # Title case, short
                    )

                    # If ANY of the heuristics are true, we classify it as a heading.
                    if is_large_font or is_bold or is_pattern_match or is_subject_pattern:
                        cleaned_text = re.sub(r'^\d+(\.\d+)*\s*', '', line_text).strip()
                        if len(cleaned_text) > 3:
                            candidate_subjects.append(cleaned_text)
        
        unique_candidates = list(dict.fromkeys(candidate_subjects))

        # --- HEURISTIC FILTERING STEP ---
        final_subjects = []
        non_topic_keywords = [
            "references", "recommended books", "index", "bibliography", "contents", 
            "table of contents", "page", "fig", "figure", "to learn", "to understand",
            "understand", "evaluate", "discuss", "delineate", "prerequisite", "exam", "test"
        ]
        
        for heading in unique_candidates:
            # Filter out non-topic headings using simple keyword matching
            is_non_topic = any(keyword in heading.lower() for keyword in non_topic_keywords)
            
            # Filter out very short headings or page numbers
            is_too_short = len(heading.strip()) < 5
            
            # Filter out headings that are mostly numbers
            is_mostly_numbers = len(re.sub(r'[0-9\s\.\-]', '', heading)) < 3
            
            # Filter out very long sentences (likely learning objectives, not topics)
            is_too_long = len(heading.split()) > 8
            
            # Filter out headings that start with "To " (learning objectives)
            starts_with_to = heading.strip().lower().startswith('to ')
            
            if not is_non_topic and not is_too_short and not is_mostly_numbers and not is_too_long and not starts_with_to:
                final_subjects.append(heading)
        
        return final_subjects

    except Exception as e:
        print(f"Error processing PDF: {e}")
        return []

# (The API Endpoint code remains the same)
@app.route("/api/extract-syllabus", methods=['POST'])
def upload_and_extract():
    # ...
    # No changes needed here
    # ...
    if 'syllabus_pdf' not in request.files: return jsonify({"error": "No file part in the request"}), 400
    file = request.files['syllabu=s_pdf']
    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            file.save(file_path)
            extracted_subjects = extract_subjects_from_pdf(file_path)
            return jsonify({"subjects": extracted_subjects})
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    return jsonify({"error": "File type not allowed"}), 400

# --- Test Runner & Main Execution ---
# Your test function is perfect for running the heuristics on a local file.
def test_local_pdf():
    pdf_filename = 'MLBC.pdf' # Your specified filename

    if not os.path.exists(pdf_filename):
        print(f"\n--- ❌ ERROR ---")
        print(f"The file '{pdf_filename}' was not found in this directory.")
        print("Please place your PDF here and update the 'pdf_filename' variable.")
        return

    print(f"--- Testing extraction on: {pdf_filename} ---")
    extracted_subjects = extract_subjects_from_pdf(pdf_filename) # This calls the function with all the heuristics

    if extracted_subjects:
        print("\n--- ✅ Successfully Extracted Subjects ---")
        for i, subject in enumerate(extracted_subjects, 1):
            print(f"{i}. {subject}")
    else:
        print("\n--- ⚠️ No subjects were extracted. ---")
        print("This might be due to the PDF's format or the heuristic rules not matching the document structure.")

    print("\n--- Test Complete ---")


if __name__ == '__main__':
    # To test the PDF extraction directly on a local file, we call the test function.
    test_local_pdf()

    # To run the Flask web server, comment out the line above and uncomment the line below.
    # app.run(debug=True, port=5000)