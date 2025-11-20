import os
import io
import json
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from PIL import Image
from rembg import remove
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = FastAPI()

# Configuration
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
vision_model = genai.GenerativeModel('gemini-2.5-flash')

class ClothingResponse(BaseModel):
    analysis: dict

@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(file: UploadFile = File(...)):
    try:
        # Image Processing
        image_data = await file.read()
        input_image = Image.open(io.BytesIO(image_data))
        output_image = remove(input_image)
        
        # AI Analysis
        prompt = "Analyze this clothing item. Return ONLY JSON: {'category': '...', 'color': '...', 'season': '...', 'formality': '...', 'description': '...'}"
        response = vision_model.generate_content([prompt, output_image])
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        metadata = json.loads(text_response)
        
        return {"analysis": metadata}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))