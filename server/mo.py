import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import pdfplumber

# --- Flask App Initialization ---
app = Flask(__name__)
# Allow requests from your Next.js frontend (http://localhost:3000)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

# --- Configuration ---
UPLOAD_FOLDER = 'upload_folder'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- The Heuristic AI/ML Core ---
def extract_subjects_from_pdf(file_path):
    """
    Parses a PDF and uses a heuristic algorithm to extract syllabus headings.
    """
    subjects = []
    try:
        with pdfplumber.open(file_path) as pdf:
            all_text_elements = []
            # First, gather all text elements to calculate an average font size
            for page in pdf.pages:
                # Extract text with metadata
                words = page.extract_words(extra_attrs=["fontname", "size"])
                all_text_elements.extend(words)

            if not all_text_elements:
                return []
            
            # Heuristic: Calculate average font size for "body" text
            # We'll consider text smaller than the overall average to be body text
            overall_avg_size = sum(el['size'] for el in all_text_elements) / len(all_text_elements)
            body_sizes = [el['size'] for el in all_text_elements if el['size'] < overall_avg_size * 1.2]
            avg_body_size = sum(body_sizes) / len(body_sizes) if body_sizes else overall_avg_size
            
            # Heuristic: A heading is likely 1.5x larger than body text and/or bold
            heading_size_threshold = avg_body_size * 1.5

            # Second, iterate through pages and lines to find headings
            for page in pdf.pages:
                lines = page.extract_text_lines()
                for line in lines:
                    line_text = line['text'].strip()
                    # Calculate average size and check for bold font in the line
                    line_word_sizes = [word['size'] for word in line['words']]
                    avg_line_size = sum(line_word_sizes) / len(line_word_sizes) if line_word_sizes else 0
                    is_bold = any('Bold' in word['fontname'] for word in line['words'])

                    # Define heading patterns using Regex
                    # Matches "1.", "1.1.", "Module 1", "CHAPTER I", etc.
                    is_pattern_match = re.match(r'^((\d+(\.\d+)*\s)|(Module\s\d+)|(CHAPTER\s[IVXLCDM]+))', line_text, re.IGNORECASE)

                    # Apply Heuristics to classify a line as a heading
                    if line_text and (avg_line_size > heading_size_threshold or is_bold or is_pattern_match):
                        # Clean the text
                        cleaned_text = re.sub(r'^\d+(\.\d+)*\s*', '', line_text).strip()
                        if len(cleaned_text) > 3: # Avoid capturing stray numbers or letters
                            subjects.append(cleaned_text)
        
        # Remove duplicates while preserving order
        unique_subjects = list(dict.fromkeys(subjects))
        return unique_subjects

    except Exception as e:
        print(f"Error processing PDF: {e}")
        return []

# --- API Endpoint ---
@app.route("/api/extract-syllabus", methods=['POST'])
def upload_and_extract():
    if 'syllabus_pdf' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    
    file = request.files['syllabus_pdf']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(file_path)
            # This is where the AI/ML work happens
            extracted_subjects = extract_subjects_from_pdf(file_path)
            return jsonify({"subjects": extracted_subjects})
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
        finally:
            # Clean up the uploaded file after processing
            if os.path.exists(file_path):
                os.remove(file_path)
    
    return jsonify({"error": "File type not allowed"}), 400

# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)