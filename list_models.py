import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in environment or .env file.")
    exit(1)

genai.configure(api_key=api_key)

print("Listing models available for your API Key:")
try:
    models = genai.list_models()
    for m in models:
        print(f"Model Name: {m.name}")
        print(f"  Supported methods: {m.supported_generation_methods}")
        print(f"  Description: {m.description}")
        print("-" * 40)
except Exception as e:
    print(f"Error listing models: {e}")
