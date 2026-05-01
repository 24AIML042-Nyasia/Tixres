from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import os
import sys

# Add current directory to path so we can import our modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import CHATBOT_HOST, CHATBOT_PORT

from rag import RAGManager
from llm import LLMManager

app = FastAPI(title="Tixres Chatbot Microservice")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize managers (lazy initialization or global)
# In a real microservice, you might want to use a singleton or dependency injection
rag_manager = RAGManager()
llm_manager = None # Will initialize on first request or startup

class Document(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = {}

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = []

class ChatResponse(BaseModel):
    response: str
    context_used: Optional[List[str]] = []

@app.on_event("startup")
async def startup_event():
    global llm_manager
    # Note: Initializing LLM might take time and memory
    try:
        llm_manager = LLMManager()
    except Exception as e:
        print(f"Error loading LLM: {e}")

@app.post("/ingest", status_code=201)
async def ingest_document(doc: Document):
    try:
        rag_manager.add_documents([doc.dict()])
        return {"message": "Document ingested successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ingest/bulk", status_code=201)
async def ingest_bulk_documents(docs: List[Document]):
    try:
        rag_manager.add_documents([doc.dict() for doc in docs])
        return {"message": f"{len(docs)} documents ingested successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if llm_manager is None:
        raise HTTPException(status_code=503, detail="LLM service not initialized")
    
    try:
        # 1. Retrieve context
        context = rag_manager.get_context(request.message)
        relevant_docs = rag_manager.search(request.message)
        
        # 2. Construct prompt
        prompt = llm_manager.get_rag_prompt(context, request.message)
        
        # 3. Generate response
        response = llm_manager.generate_response(prompt)
        
        return ChatResponse(
            response=response,
            context_used=[doc.page_content for doc in relevant_docs]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "llm_loaded": llm_manager is not None,
        "vector_store_size": len(rag_manager.vectorstore.index_to_docstore_id)
    }

if __name__ == "__main__":
    uvicorn.run(app, host=CHATBOT_HOST, port=CHATBOT_PORT)
