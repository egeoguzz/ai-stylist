import os
import io
import json
import uuid
import random
from datetime import date
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
from rembg import remove, new_session
from dotenv import load_dotenv

import google.generativeai as genai
from pinecone import Pinecone
from supabase import create_client, Client

load_dotenv()

app = FastAPI(title="AI Stylist Backend", description="RAG-based Fashion Recommendation API")

# --- SECURITY SETUP ---
security = HTTPBearer()

# --- LAZY LOADING GLOBALS ---
rembg_session = None
ai_model = None
index = None
supabase = None

# --- INITIALIZATION FUNCTIONS ---
def get_rembg_session():
    global rembg_session
    if rembg_session is None:
        rembg_session = new_session("u2netp") # Lite Model (4MB)
    return rembg_session

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

# --- AUTHENTICATION HELPER (Kritik Kısım) ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    sb = get_supabase()
    
    try:
        user_response = sb.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid Authentication Token")
        return user_response.user.id
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")

# --- DATA MODELS ---
class ClothingResponse(BaseModel):
    id: str
    status: str
    image_url: str
    analysis: dict

class ClothingItemDetail(BaseModel):
    id: str
    category: str
    color: str
    image_url: str
    season: Optional[str] = None
    formality: Optional[str] = None
    description: Optional[str] = None

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

# 1. UPLOAD 
@app.post("/upload-clothing", response_model=ClothingResponse)
async def upload_clothing(
    file: UploadFile = File(...), 
    user_id: str = Depends(get_current_user)
):
    try:
        image_data = await file.read()
        input_image = Image.open(io.BytesIO(image_data))
        input_image.thumbnail((800, 800))
        
        session = get_rembg_session()
        output_image = remove(input_image, session=session)
        
        buffered = io.BytesIO()
        output_image.save(buffered, format="PNG")
        final_image_bytes = buffered.getvalue()

        file_name = f"{uuid.uuid4()}.png"
        sb = get_supabase()
        path = f"{user_id}/{file_name}"
        
        sb.storage.from_("wardrobe").upload(path, final_image_bytes, {"content-type": "image/png"})
        public_url_res = sb.storage.from_("wardrobe").get_public_url(path)
        final_image_url = public_url_res if isinstance(public_url_res, str) else public_url_res.public_url

        prompt = "Analyze this clothing. Return JSON: {'category': '...', 'color': '...', 'season': '...', 'formality': '...', 'description': '...'}"
        model = get_ai_model()
        response = model.generate_content([prompt, output_image])
        metadata = json.loads(response.text.replace("```json", "").replace("```", "").strip())
        
        data_to_insert = {**metadata, "image_url": final_image_url, "user_id": user_id}
        db_resp = sb.table("clothes").insert(data_to_insert).execute()
        clothing_id = db_resp.data[0]['id']
        
        text_to_embed = f"{metadata['color']} {metadata['category']} {metadata['season']} {metadata['description']}"
        vector = get_embedding(text_to_embed)
        
        metadata['image_url'] = final_image_url
        metadata['user_id'] = user_id
        
        idx = get_index()
        idx.upsert(vectors=[{"id": clothing_id, "values": vector, "metadata": metadata}])
        
        return {"id": clothing_id, "status": "Saved!", "image_url": final_image_url, "analysis": metadata}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        search_results = idx.query(
            vector=query_vector, 
            top_k=15, 
            include_metadata=True,
            filter={"user_id": user_id}
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

# 5. TRAVEL
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
            filter={"user_id": user_id}
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

# 6. DAILY TIP (No login - Public)
@app.get("/daily-tip", response_model=DailyTipResponse)
async def get_daily_tip():
    today = date.today()
    random.seed(today.toordinal())
    selected_tip = random.choice(STYLING_TIPS)
    return {"date": today.isoformat(), "tip": selected_tip}

# 7. DEFAULT SUGGESTIONS (No login - Public)
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
