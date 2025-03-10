
import os
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import time
import uuid
from datetime import datetime
import logging

# Import our custom modules
from app.database import get_db, SessionLocal, engine, Base
from app.models import Conversation, Message
from app.llm_service import process_message, get_llm_client
from app.auth import get_current_user, User

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(title="Scalable LLM Chatbot API")

@app.get("/health")
def health_check():
    if check_db_connection():
        return {"status": "Database connected"}
    else:
        return {"status": "Database connection failed"}

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for request/response
class MessageRequest(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    model_name: str = "gpt-3.5-turbo"  # Default model

class MessageResponse(BaseModel):
    id: str
    content: str
    role: str
    created_at: datetime
    conversation_id: str

class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    messages: List[MessageResponse]

# Routes
@app.post("/api/messages/", response_model=MessageResponse)
async def create_message(
    message_request: MessageRequest, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    try:
        # Generate conversation_id if not provided
        conversation_id = message_request.conversation_id
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            # Create new conversation
            new_conversation = Conversation(
                id=conversation_id,
                user_id=current_user.id,
                title=message_request.content[:50] + "..." if len(message_request.content) > 50 else message_request.content
            )
            db.add(new_conversation)
            db.commit()
        
        # Save user message
        user_message = Message(
            id=str(uuid.uuid4()),
            content=message_request.content,
            role="user",
            conversation_id=conversation_id,
            user_id=current_user.id
        )
        db.add(user_message)
        db.commit()
        
        # Process message in background to avoid blocking
        background_tasks.add_task(
            process_message_task,
            message_request.content,
            conversation_id,
            current_user.id,
            message_request.model_name
        )
        
        return MessageResponse(
            id=user_message.id,
            content=user_message.content,
            role=user_message.role,
            created_at=user_message.created_at,
            conversation_id=conversation_id
        )
        
    except Exception as e:
        logger.error(f"Error creating message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")

async def process_message_task(content: str, conversation_id: str, user_id: str, model_name: str):
    """Background task to process messages through LLM"""
    db = SessionLocal()
    try:
        # Get conversation history
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).all()
        
        # Convert to format expected by LLM service
        message_history = [{"role": msg.role, "content": msg.content} for msg in messages]
        
        # Get response from LLM
        llm_client = get_llm_client(model_name)
        response_content = await process_message(llm_client, message_history, content)
        
        # Save assistant response
        assistant_message = Message(
            id=str(uuid.uuid4()),
            content=response_content,
            role="assistant",
            conversation_id=conversation_id,
            user_id=user_id
        )
        db.add(assistant_message)
        db.commit()
        
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}")
    finally:
        db.close()

@app.get("/api/conversations/", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: SessionLocal = Depends(get_db)
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).all()
    
    result = []
    for conv in conversations:
        messages = db.query(Message).filter(
            Message.conversation_id == conv.id
        ).order_by(Message.created_at).all()
        
        message_responses = [
            MessageResponse(
                id=msg.id,
                content=msg.content,
                role=msg.role,
                created_at=msg.created_at,
                conversation_id=msg.conversation_id
            ) for msg in messages
        ]
        
        result.append(ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            messages=message_responses
        ))
    
    return result

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
