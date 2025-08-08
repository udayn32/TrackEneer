# Add this import to the top of your file
from transformers import pipeline

def summarize_text(text: str) -> str:
    """
    Summarizes a long piece of text using a pre-trained Hugging Face model.
    """
    # Load the summarization pipeline. 
    # This model is a good balance of speed and quality.
    summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

    # The model works best on text up to 1024 tokens. 
    # We'll feed it the first chunk of the scraped text.
    summary = summarizer(text, max_length=150, min_length=50, do_sample=False)

    return summary[0]['summary_text']