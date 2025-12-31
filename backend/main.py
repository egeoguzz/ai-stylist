import os
import io
import json
import uuid
import random
import httpx
from datetime import date
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
from dotenv import load_dotenv

import google.generativeai as genai
from pinecone import Pinecone
from supabase import create_client, Client

# Import the celery task
from worker import process_clothing_image

load_dotenv()

app = FastAPI(title="AI Stylist Backend", description="RAG-based Fashion Recommendation API")

# --- SECURITY SETUP ---
security = HTTPBearer()

# --- GLOBALS ---
# Note: rembg_session is removed from here as it's now in worker.py
ai_model = None
index = None
supabase = None

# --- INITIALIZATION FUNCTIONS ---
def get_ai_model():
    global ai_model
    if ai_model is None:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        ai_model = genai.GenerativeModel('gemini-2.5-flash')
    return ai_model

def get_index():
    global index
    if index is None:
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        index = pc.Index("clothing-index")
    return index

def get_supabase():
    global supabase
    if supabase is None:
        supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    return supabase

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    auth_url = f"{supabase_url}/auth/v1/user"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                auth_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": supabase_key
                }
            )
            
            if response.status_code == 200:
                user_data = response.json()
                return user_data['id']
            else:
                print(f"Auth Failed: {response.text}")
                raise HTTPException(status_code=401, detail="Invalid Authentication Token")

    except Exception as e:
        print(f"Auth System Error: {e}")
        raise HTTPException(status_code=401, detail="Authentication Service Unavailable")

# --- DATA MODELS ---
# (Keep all your existing data models here exactly as they were)
class ClothingResponse(BaseModel):
    id: str
    status: str
    image_url: str
    analysis: dict
    
class ClothingItemDetail(BaseModel):
    id: str
    category: Optional[str] = None
    color: Optional[str] = None
    image_url: str
    season: Optional[str] = None
    formality: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None # Added status field

class RecommendationRequest(BaseModel):
    weather: str
    occasion: str

class RecommendationResponse(BaseModel):
    outfit_name: str
    selected_items: List[ClothingItemDetail]
    reasoning: str

class TravelRequest(BaseModel):
    destination: str
    days: int
    weather: str

class TravelResponse(BaseModel):
    pack_name: str
    items_to_pack: List[ClothingItemDetail]
    outfit_combinations: List[str]
    reasoning: str

class DailyTipResponse(BaseModel):
    date: str
    tip: str

class DefaultSuggestionItem(BaseModel):
    type: str
    title: str
    description: str
    image_url: str

# --- STATIC DATA ---
STYLING_TIPS = [
    "Accessories are the easiest way to upgrade a simple outfit.",
    "Invest in high-quality basics; they never go out of style.",
    "If you're wearing loose bottoms, try a tighter top for balance.",
    "A monochrome outfit always looks chic and expensive.",
    "When in doubt, wear a white shirt and blue jeans.",
    "Darker colors are generally more slimming and formal.",
    "Layering adds depth and interest to any look.",
    "Gold jewelry warms up skin tones; silver cools them down.",
    "Don't follow every trend; stick to what suits your body type.",
    "Match your belt color to your shoe color for a cohesive look."
]

# --- HELPER: EMBEDDING ---
def get_embedding(text: str) -> List[float]:
    try:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding Error: {e}")
        raise HTTPException(status_code=500, detail="Vector embedding failed")

# --- ENDPOINTS ---

# 1. UPLOAD (UPDATED FOR ASYNC WORKER)
@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(
    file: UploadFile = File(...), 
    user_id: str = Depends(get_current_user)
):
    try:
        image_data = await file.read()
        file_name = f"{uuid.uuid4()}.png"
        
        sb = get_supabase()
        path = f"{user_id}/{file_name}"
        
        # 1. Upload raw image directly to storage
        sb.storage.from_("wardrobe").upload(path, image_data, {"content-type": "image/png"})
        
        # 2. Create a database record with 'PROCESSING' status
        initial_data = {
            "user_id": user_id,
            "image_url": "", # Placeholder, will be updated by worker
            "status": "PROCESSING",
            "category": "Analyzing...",
            "color": "Analyzing..."
        }
        
        db_resp = sb.table("clothes").insert(initial_data).execute()
        clothing_id = db_resp.data[0]['id']

        # 3. Trigger the Celery task (Offload to worker)
        process_clothing_image.delay(user_id, path, clothing_id)

        # 4. Return immediate response
        return {
            "id": clothing_id, 
            "status": "PROCESSING", 
            "image_url": "", 
            "analysis": {"description": "Image is being processed in background..."}
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# (REST OF THE ENDPOINTS - Keep them exactly as they were in your original file)
# 2. LIST WARDROBE
@app.get("/wardrobe", response_model=List[ClothingItemDetail])
async def get_wardrobe(
    category: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user)
):
    try:
        sb = get_supabase()
        query = sb.table("clothes").select("*").eq("user_id", user_id).order("created_at", desc=True)
        
        if category:
            query = query.ilike("category", f"%{category}%")
            
        response = query.execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2.1 SINGLE WARDROBE ITEM
@app.get("/wardrobe/{item_id}", response_model=ClothingItemDetail)
async def get_clothing_item(
    item_id: str,
    user_id: str = Depends(get_current_user)
):
    try:
        sb = get_supabase()
        response = sb.table("clothes").select("*").eq("id", item_id).eq("user_id", user_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Item not found")
            
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. DELETE ITEM
@app.delete("/wardrobe/{item_id}")
async def delete_item(
    item_id: str,
    user_id: str = Depends(get_current_user)
):
    try:
        sb = get_supabase()
        sb.table("clothes").delete().eq("id", item_id).eq("user_id", user_id).execute()
        
        idx = get_index()
        idx.delete(ids=[item_id])
        
        return {"status": "success", "message": "Item deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 4. RECOMMEND
@app.post("/recommend-outfit", response_model=RecommendationResponse)
async def recommend_outfit(
    request: RecommendationRequest,
    user_id: str = Depends(get_current_user)
):
    try:
        search_query = f"{request.occasion} outfit for {request.weather} weather"
        query_vector = get_embedding(search_query)
        
        idx = get_index()
        # Filter for COMPLETED items only to avoid processing errors
        search_results = idx.query(
            vector=query_vector, 
            top_k=15, 
            include_metadata=True,
            filter={"user_id": user_id, "status": "COMPLETED"} 
        )
        
        wardrobe_context = ""
        item_map = {}
        for match in search_results['matches']:
            meta = match['metadata']
            item_id = match['id']
            item_map[item_id] = {
                "id": item_id,
                "category": meta.get('category'),
                "color": meta.get('color'),
                "image_url": meta.get('image_url')
            }
            wardrobe_context += f"- ID: {item_id}, Item: {meta.get('color')} {meta.get('category')}\n"

        if not wardrobe_context:
             return {
                 "outfit_name": "Wardrobe Empty",
                 "selected_items": [],
                 "reasoning": "You need to upload clothes first!"
             }

        prompt = f"""
        Act as a stylist. Context: {request.occasion}, {request.weather}
        Wardrobe: {wardrobe_context}
        Task: Pick ONE Top and ONE Bottom (or Dress).
        Return JSON: {{ "outfit_name": "Name", "selected_items": ["ID_1", "ID_2"], "reasoning": "..." }}
        """
        model = get_ai_model()
        response = model.generate_content(prompt)
        recommendation = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        full_items = []
        for item_id in recommendation.get('selected_items', []):
            if item_id in item_map:
                full_items.append(item_map[item_id])
        
        return {
            "outfit_name": recommendation.get('outfit_name', 'Outfit'),
            "selected_items": full_items,
            "reasoning": recommendation.get('reasoning', '')
        }
    except Exception as e:
        print(f"Rec Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 5. TRAVEL (Keep as is)
@app.post("/recommend-travel-pack", response_model=TravelResponse)
async def recommend_travel_pack(
    request: TravelRequest,
    user_id: str = Depends(get_current_user)
):
    try:
        search_query = f"Clothes suitable for {request.destination} in {request.weather}"
        query_vector = get_embedding(search_query)
        
        idx = get_index()
        search_results = idx.query(
            vector=query_vector, 
            top_k=30, 
            include_metadata=True,
            filter={"user_id": user_id, "status": "COMPLETED"}
        )
        
        item_map = {}
        wardrobe_context = ""
        for match in search_results['matches']:
            meta = match['metadata']
            item_id = match['id']
            item_map[item_id] = {
                "id": item_id,
                "category": meta.get('category'),
                "color": meta.get('color'),
                "image_url": meta.get('image_url')
            }
            wardrobe_context += f"- ID: {item_id}, {meta.get('color')} {meta.get('category')}\n"

        if not wardrobe_context:
             return {
                 "pack_name": "Empty Wardrobe",
                 "items_to_pack": [],
                 "outfit_combinations": [],
                 "reasoning": "Upload clothes to use this feature."
             }

        prompt = f"""
        You are a Travel Stylist. Trip: {request.days} days to {request.destination}. Weather: {request.weather}.
        Available Items: {wardrobe_context}
        Task: Create a 'Capsule Wardrobe'.
        Return JSON: {{ "pack_name": "Name", "items_to_pack": ["ID_1", ...], "outfit_combinations": ["..."], "reasoning": "..." }}
        """
        model = get_ai_model()
        response = model.generate_content(prompt)
        ai_result = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        packed_items_details = []
        for item_id in ai_result.get('items_to_pack', []):
            if item_id in item_map:
                packed_items_details.append(item_map[item_id])

        return {
            "pack_name": ai_result.get('pack_name', 'Trip Pack'),
            "items_to_pack": packed_items_details,
            "outfit_combinations": ai_result.get('outfit_combinations', []),
            "reasoning": ai_result.get('reasoning', '')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 6. DAILY TIP (Keep as is)
@app.get("/daily-tip", response_model=DailyTipResponse)
async def get_daily_tip():
    today = date.today()
    random.seed(today.toordinal())
    selected_tip = random.choice(STYLING_TIPS)
    return {"date": today.isoformat(), "tip": selected_tip}

# 7. DEFAULT SUGGESTIONS (Keep as is)
@app.get("/default-suggestions", response_model=List[DefaultSuggestionItem])
async def get_default_suggestions():
    return [
        {
            "type": "casual",
            "title": "Effortless Weekend",
            "description": "Pair your favorite blue jeans with a white tee and white sneakers.",
            "image_url": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800"
        },
        {
            "type": "work",
            "title": "Modern Professional",
            "description": "A sharp navy blazer over a light grey turtleneck.",
            "image_url": "https://images.unsplash.com/photo-1487222477894-8943e31ef7b2?w=800"
        }
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
