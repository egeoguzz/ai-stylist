# AI Stylist Backend

This repository contains the backend service for an AI-powered fashion and wardrobe assistant application.

The backend is responsible for image processing, clothing analysis, recommendation generation, and all AI-driven functionality consumed by a client application. It is deployed as a production service and operates independently from the client-side codebase.

This repository is a fork created specifically for backend development, infrastructure management, and production deployment.

---

## Project Overview

The AI Stylist backend enables users to build a digital wardrobe and receive outfit recommendations based on their own clothing items, context, and preferences.

Users upload images of clothing items, which are processed asynchronously. The system analyzes each item, stores structured metadata, and enables recommendation flows such as daily outfits, travel packing suggestions, and general styling guidance.

The backend is designed to support real-world usage, background processing, and scalable AI workflows.

---

## Core Features

### Clothing Image Processing
- Upload and store user clothing images
- Background removal performed asynchronously
- AI-based analysis to extract category, color, season, formality, and descriptive attributes
- Processed images and metadata stored for future retrieval

---

### Wardrobe Management
- Persistent wardrobe storage per user
- List, view, and delete clothing items
- Status tracking for processing lifecycle (processing, completed, error)

---

### Outfit Recommendations
- Context-based outfit generation (occasion and weather)
- Uses vector similarity search over the user’s wardrobe
- Produces structured outfit selections with reasoning
- Designed to avoid hard-coded rules in favor of AI-driven selection

---

### Travel Packing Recommendations
- Generates capsule wardrobes for trips
- Suggests items to pack based on destination, duration, and weather
- Provides outfit combinations using existing wardrobe items

---

### Daily Styling Tips
- Returns a daily styling suggestion
- Deterministic per day to ensure consistent user experience

---

## Architecture Overview

- FastAPI-based asynchronous API
- Queue-based background processing using Celery and Redis
- Separation between request handling and heavy image processing workloads
- Multimodal AI pipelines combining image and text inputs
- Vector search using Pinecone for retrieval-augmented recommendations
- Persistent storage using Supabase (database and object storage)

The backend is implemented as a single service with a dedicated worker process to ensure responsiveness and operational stability.

---

## Deployment

- Deployed as a production backend service
- Uses environment-based configuration for secrets and runtime settings
- Runs with separate web and worker processes
- Managed and deployed on Railway
- Startup configuration documented via Procfile

---

## Collaboration and Ownership

This repository represents ownership of the backend systems, AI pipelines, and production infrastructure.

The client application (iOS) is developed and maintained separately by the iOS developer. Client-side code is not the source of truth for this repository and is not required for backend operation or deployment.

---

## Tech Stack

- Python
- FastAPI
- Celery
- Redis
- Google Gemini (Multimodal Generative AI)
- Pinecone (Vector Database)
- Supabase (Database and Object Storage)
- Railway (Deployment)

---

## Notes

This fork exists to allow independent iteration on backend architecture, AI logic, and infrastructure without coupling to client-side development workflows.

The backend service operates as a standalone system and powers a consumer-facing application through a structured API.

