import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyCjdJbU8lCtZUT00P_uzQSrUw33tf9Ij6A"
genai.configure(api_key=GEMINI_API_KEY)

print("Available Gemini models:")
print("-" * 50)

for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"Model: {model.name}")
        print(f"  Display Name: {model.display_name}")
        print(f"  Supported Methods: {model.supported_generation_methods}")
        print("-" * 50)
