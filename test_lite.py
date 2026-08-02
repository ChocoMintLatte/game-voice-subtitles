import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

print("Attempting to call gemini-3.1-flash-lite:")
try:
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    response = model.generate_content("Hello! What is your model name?")
    print(f"Success! Response: {response.text.strip()}")
except Exception as e:
    print(f"Failed: {e}")
