import os
import io
import json
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from PIL import Image
from rembg import remove
from dotenv import load_dotenv
import google.generativeai as genai
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

load_dotenv()

app = FastAPI()

# Config
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
vision_model = genai.GenerativeModel('gemini-2.5-flash')
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("clothing-index")

class ClothingResponse(BaseModel):
    id: str
    status: str
    image_url: str
    analysis: dict

@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(file: UploadFile = File(...)):
    try:
        # ... (Resim işleme ve Storage kısmı aynı) ...
        image_data = await file.read()
        input_image = Image.open(io.BytesIO(image_data))
        output_image = remove(input_image)
        buffered = io.BytesIO()
        output_image.save(buffered, format="PNG")
        final_image_bytes = buffered.getvalue()
        file_name = f"{uuid.uuid4()}.png"
        supabase.storage.from_("wardrobe").upload(file_name, final_image_bytes, {"content-type": "image/png"})
        public_url_resp = supabase.storage.from_("wardrobe").get_public_url(file_name)
        final_image_url = public_url_resp if isinstance(public_url_resp, str) else public_url_resp.public_url

        # Analysis & DB
        prompt = "Analyze this clothing item. Return ONLY JSON: {'category': '...', 'color': '...', 'season': '...', 'formality': '...', 'description': '...'}"
        response = vision_model.generate_content([prompt, output_image])
        metadata = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        data_to_insert = {"category": metadata["category"], "color": metadata["color"], "season": metadata["season"], "formality": metadata["formality"], "description": metadata["description"], "image_url": final_image_url}
        db_response = supabase.table("clothes").insert(data_to_insert).execute()
        clothing_id = db_response.data[0]['id']
        
        # --- VECTOR EMBEDDING ---
        text_to_embed = f"{metadata['color']} {metadata['category']} {metadata['season']} {metadata['description']}"
        vector = embedding_model.encode(text_to_embed).tolist()
        metadata['image_url'] = final_image_url
        index.upsert(vectors=[{"id": clothing_id, "values": vector, "metadata": metadata}])
        
        return {"id": clothing_id, "status": "Saved!", "image_url": final_image_url, "analysis": metadata}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))