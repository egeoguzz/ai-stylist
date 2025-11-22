import os
import io
import json
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
from rembg import remove
from dotenv import load_dotenv

import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from supabase import create_client, Client

load_dotenv()

app = FastAPI(title="AI Stylist Backend", description="RAG-based Fashion Recommendation API")

# --- CONFIGURATION ---
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
# Using 'gemini-2.5-flash' for optimal speed/cost balance
ai_model = genai.GenerativeModel('gemini-2.5-flash')

# Local embedding model to generate vectors without external API calls
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("clothing-index")

# --- DATA MODELS ---

class ClothingResponse(BaseModel):
    id: str
    status: str
    image_url: str
    analysis: dict

# Detailed item model for Frontend/iOS consumption
class ClothingItemDetail(BaseModel):
    id: str
    category: str
    color: str
    image_url: str

class RecommendationRequest(BaseModel):
    weather: str
    occasion: str

class RecommendationResponse(BaseModel):
    outfit_name: str
    selected_items: List[ClothingItemDetail] # Returning full objects instead of just IDs
    reasoning: str

# --- ENDPOINTS ---

@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(file: UploadFile = File(...)):
    try:
        # 1. Image Processing (Background Removal)
        image_data = await file.read()
        input_image = Image.open(io.BytesIO(image_data))
        output_image = remove(input_image)
        
        buffered = io.BytesIO()
        output_image.save(buffered, format="PNG")
        final_image_bytes = buffered.getvalue()

        # 2. Upload to Supabase Storage
        file_name = f"{uuid.uuid4()}.png"
        supabase.storage.from_("wardrobe").upload(file_name, final_image_bytes, {"content-type": "image/png"})
        public_url_res = supabase.storage.from_("wardrobe").get_public_url(file_name)
        final_image_url = public_url_res if isinstance(public_url_res, str) else public_url_res.public_url

        # 3. AI Analysis (Vision)
        prompt = "Analyze this clothing. Return JSON: {'category': '...', 'color': '...', 'season': '...', 'formality': '...', 'description': '...'}"
        response = ai_model.generate_content([prompt, output_image])
        metadata = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        # 4. Save to Database
        data_to_insert = {**metadata, "image_url": final_image_url}
        db_resp = supabase.table("clothes").insert(data_to_insert).execute()
        clothing_id = db_resp.data[0]['id']
        
        # 5. Generate Embeddings & Save to Pinecone
        text_to_embed = f"{metadata['color']} {metadata['category']} {metadata['season']} {metadata['description']}"
        vector = embedding_model.encode(text_to_embed).tolist()
        
        # Store image_url in metadata for retrieval during search
        metadata['image_url'] = final_image_url
        index.upsert(vectors=[{"id": clothing_id, "values": vector, "metadata": metadata}])
        
        return {"id": clothing_id, "status": "Saved!", "image_url": final_image_url, "analysis": metadata}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/recommend-outfit", response_model=RecommendationResponse)
async def recommend_outfit(request: RecommendationRequest):
    try:
        # 1. Semantic Search via Pinecone
        search_query = f"{request.occasion} outfit for {request.weather} weather"
        query_vector = embedding_model.encode(search_query).tolist()
        
        # Retrieve top 15 relevant items
        search_results = index.query(vector=query_vector, top_k=15, include_metadata=True)
        
        wardrobe_context = ""
        item_map = {}
        
        for match in search_results['matches']:
            meta = match['metadata']
            item_id = match['id']
            # Map ID to full details for response hydration
            item_map[item_id] = {
                "id": item_id,
                "category": meta.get('category', 'Unknown'),
                "color": meta.get('color', 'Unknown'),
                "image_url": meta.get('image_url', '')
            }
            wardrobe_context += f"- ID: {item_id}, Item: {meta.get('color')} {meta.get('category')} ({meta.get('description')})\n"

        # 2. LLM Decision Making
        prompt = f"""
        Act as a stylist. Context: {request.occasion}, {request.weather}
        Wardrobe: {wardrobe_context}
        Task: Pick ONE Top and ONE Bottom (or Dress).
        Return JSON: {{ "outfit_name": "Name", "selected_items": ["ID_1", "ID_2"], "reasoning": "..." }}
        """
        response = ai_model.generate_content(prompt)
        recommendation = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        # 3. Hydrate IDs with full object details
        full_items = []
        for item_id in recommendation['selected_items']:
            if item_id in item_map:
                full_items.append(item_map[item_id])
        
        return {
            "outfit_name": recommendation['outfit_name'],
            "selected_items": full_items,
            "reasoning": recommendation['reasoning']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
