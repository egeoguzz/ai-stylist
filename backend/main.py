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

# AI Libraries
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

# Database Library
from supabase import create_client, Client

# Load environment variables
load_dotenv()

app = FastAPI(title="AI Stylist Backend", description="RAG-based Fashion Recommendation API")

# --- CONFIGURATION ---

# 1. Google Gemini (Vision & Intelligence)
# Using 'gemini-2.5-flash' for high speed and cost efficiency
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
ai_model = genai.GenerativeModel('gemini-2.5-flash')

# 2. Local Embedding Model
# Using 'all-MiniLM-L6-v2' to generate 384-dimensional vectors locally
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# 3. Supabase Client (Relational DB & Storage)
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# 4. Pinecone Client (Vector Database)
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("clothing-index")

# --- DATA MODELS ---

class ClothingResponse(BaseModel):
    id: str
    status: str
    image_url: str
    analysis: dict

class RecommendationRequest(BaseModel):
    weather: str   # e.g., "15 degrees, Rainy"
    occasion: str  # e.g., "Coffee date"

class RecommendationResponse(BaseModel):
    outfit_name: str
    selected_items: List[str]
    reasoning: str

# --- ENDPOINT 1: UPLOAD & ANALYZE (Vision Pipeline) ---

@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(file: UploadFile = File(...)):
    try:
        # --- STEP 1: Image Processing (Background Removal) ---
        image_data = await file.read()
        input_image = Image.open(io.BytesIO(image_data))
        
        # Remove background using Rembg to reduce visual noise
        output_image = remove(input_image)
        
        # Convert to bytes for storage and AI processing
        buffered = io.BytesIO()
        output_image.save(buffered, format="PNG")
        final_image_bytes = buffered.getvalue()

        # --- STEP 2: Storage Upload (Supabase) ---
        # Generate unique filename
        file_name = f"{uuid.uuid4()}.png"
        
        # Upload to 'wardrobe' bucket
        supabase.storage.from_("wardrobe").upload(
            path=file_name,
            file=final_image_bytes,
            file_options={"content-type": "image/png"}
        )
        
        # Get Public URL
        public_url_res = supabase.storage.from_("wardrobe").get_public_url(file_name)
        final_image_url = public_url_res if isinstance(public_url_res, str) else public_url_res.public_url

        # --- STEP 3: AI Analysis (Vision) ---
        prompt = """
        Analyze this clothing item. You are a fashion stylist.
        Return ONLY a JSON object strictly in this format: 
        {"category": "...", "color": "...", "season": "...", "formality": "...", "description": "..."} 
        Do not use markdown.
        """
        response = ai_model.generate_content([prompt, output_image])
        text_response = response.text.replace("```json", "").replace("```", "").strip()
        metadata = json.loads(text_response)
        
        # --- STEP 4: Database Persistence ---
        data_to_insert = {
            "category": metadata["category"],
            "color": metadata["color"],
            "season": metadata["season"],
            "formality": metadata["formality"],
            "description": metadata["description"],
            "image_url": final_image_url
        }
        
        db_response = supabase.table("clothes").insert(data_to_insert).execute()
        clothing_id = db_response.data[0]['id']
        
        # --- STEP 5: Vector Embeddings (Pinecone) ---
        # Create semantic text representation
        text_to_embed = f"{metadata['color']} {metadata['category']} {metadata['season']} {metadata['description']}"
        vector = embedding_model.encode(text_to_embed).tolist()
        
        # Add URL to metadata for retrieval
        metadata['image_url'] = final_image_url
        
        # Upsert to Vector DB
        index.upsert(vectors=[{
            "id": clothing_id,
            "values": vector,
            "metadata": metadata
        }])
        
        return {
            "id": clothing_id,
            "status": "Saved to Wardrobe successfully!",
            "image_url": final_image_url,
            "analysis": metadata
        }

    except Exception as e:
        print(f"Error in upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT 2: RECOMMENDATION ENGINE (RAG Pipeline) ---

@app.post("/recommend-outfit", response_model=RecommendationResponse)
async def recommend_outfit(request: RecommendationRequest):
    try:
        # --- STEP 1: Semantic Search ---
        # Convert user query (Context) into a vector
        search_query = f"{request.occasion} outfit for {request.weather} weather"
        query_vector = embedding_model.encode(search_query).tolist()
        
        # Retrieve top 10 most relevant items from Pinecone
        search_results = index.query(
            vector=query_vector,
            top_k=10,
            include_metadata=True
        )
        
        # --- STEP 2: Construct Context for LLM ---
        wardrobe_context = ""
        for match in search_results['matches']:
            meta = match['metadata']
            wardrobe_context += f"- ID: {match['id']}, Item: {meta.get('color')} {meta.get('category')} ({meta.get('description')})\n"
            
        if not wardrobe_context:
            raise HTTPException(status_code=404, detail="Wardrobe is empty or no matching items found.")

        # --- STEP 3: RAG Generation (Reasoning) ---
        prompt = f"""
        You are a professional fashion stylist.
        
        USER CONTEXT:
        Occasion: {request.occasion}
        Weather: {request.weather}
        
        AVAILABLE WARDROBE ITEMS (Retrieved from Vector DB):
        {wardrobe_context}
        
        TASK:
        Create the best possible outfit combination from the available items.
        You MUST select items from the list provided.
        
        Return ONLY a JSON object in this format:
        {{
            "outfit_name": "Creative Name",
            "selected_items": ["ID_1", "ID_2"],
            "reasoning": "Brief explanation of why this works for the weather and occasion."
        }}
        Do not use markdown.
        """
        
        response = ai_model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        recommendation = json.loads(clean_json)
        
        return recommendation

    except Exception as e:
        print(f"Error in recommendation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
