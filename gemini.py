import os
import google.genai as genai
from dotenv import load_dotenv
from PIL import Image

load_dotenv()
key = os.getenv("API_KEY")
client = genai.Client(api_key=key)

item = "basketball"

image = Image.open("nbaplayoffs.jpeg")

prompt = f"""
Detect {item} in this image.

If the object isn't in the photo, say "OBJECT NOT FOUND" and exit

Return ONLY lines in this exact format:
<class_id> <x_center> <y_center> <width> <height>

Rules:
- Normalize all values from 0 to 1
- Do NOT include explanations
- class_id should be an integer label
"""

r = client.models.generate_content(
    model = "gemini-3-pro-preview",
    contents=[prompt, image]
)

print(r.candidates[0].content.parts[0].text)
