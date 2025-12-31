import os
import io
import json
import httpx
from celery import Celery
from rembg import remove, new_session
from PIL import Image
import google.generativeai as genai
from pinecone import Pinecone
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
# Use the REDIS_URL provided by Railway, or localhost for testing
redis_url = os.getenv("REDIS_URL")

if redis_url:
    masked_url = redis_url.replace(redis_url.split("@")[0], "redis://*****")
    print(f"[DEBUG] REDIS_URL FOUND: {masked_url}")
else:
    print("[DEBUG] REDIS_URL NOT FOUND! (None)")

if not redis_url:
    raise ValueError("FATAL: REDIS_URL environment variable is MISSING. API cannot connect to Queue.")
    
celery_app = Celery(
    "worker",
    broker=redis_url,
    backend=redis_url
)

# --- LAZY LOADING GLOBALS FOR WORKER ---
# These are initialized once when the worker starts
rembg_session = new_session("u2netp") # Lite Model
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
ai_model = genai.GenerativeModel('gemini-2.5-flash')
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("clothing-index")

# --- HELPER: EMBEDDING (Re-defined here for the worker) ---
def get_embedding(text: str):
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding Error: {e}")
        return []

# --- TASKS ---
@celery_app.task(name="process_clothing_image")
def process_clothing_image(user_id: str, raw_image_path: str, item_id: str):
    """
    Background task to process the image:
    1. Download raw image
    2. Remove background
    3. Analyze with AI
    4. Generate embeddings
    5. Update DB and Vector Store
    """
    try:
        print(f"[{item_id}] Processing started...")

        # 1. Download raw image from Supabase
        image_bytes = supabase.storage.from_("wardrobe").download(raw_image_path)
        input_image = Image.open(io.BytesIO(image_bytes))
        
        # Optimization: Resize to save RAM during inference
        input_image.thumbnail((600, 600)) 

        # 2. Remove background (Heavy Operation)
        output_image = remove(input_image, session=rembg_session)
        
        buffered = io.BytesIO()
        output_image.save(buffered, format="PNG")
        final_image_bytes = buffered.getvalue()

        # 3. Upload processed image
        processed_filename = f"processed_{item_id}.png"
        processed_path = f"{user_id}/{processed_filename}"
        
        supabase.storage.from_("wardrobe").upload(
            processed_path, 
            final_image_bytes, 
            {"content-type": "image/png", "upsert": "true"}
        )
        
        public_url_res = supabase.storage.from_("wardrobe").get_public_url(processed_path)
        final_url = public_url_res if isinstance(public_url_res, str) else public_url_res.public_url

        # 4. AI Analysis
        buffered.seek(0)
        temp_img_for_ai = Image.open(buffered)
        
        prompt = "Analyze this clothing. Return JSON: {'category': '...', 'color': '...', 'season': '...', 'formality': '...', 'description': '...'}"
        response = ai_model.generate_content([prompt, temp_img_for_ai])
        
        # Clean up JSON response
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        metadata = json.loads(cleaned_text)
        
        # 5. Create Embeddings & Update Pinecone
        text_to_embed = f"{metadata.get('color')} {metadata.get('category')} {metadata.get('season')} {metadata.get('description')}"
        vector = get_embedding(text_to_embed)
        
        metadata['image_url'] = final_url
        metadata['user_id'] = user_id
        metadata['status'] = 'COMPLETED' # Mark as done

        # Update Pinecone
        index.upsert(vectors=[{"id": item_id, "values": vector, "metadata": metadata}])
        
        # 6. Update Supabase Record
        supabase.table("clothes").update(metadata).eq("id", item_id).execute()
        
        print(f"[{item_id}] Processing completed successfully.")
        return "Success"

    except Exception as e:
        print(f"[{item_id}] Worker Error: {e}")
        # Update status to ERROR so the frontend knows
        supabase.table("clothes").update({"status": "ERROR", "description": str(e)}).eq("id", item_id).execute()
        return "Failed"
