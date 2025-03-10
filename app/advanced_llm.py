
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import json
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load embedding model
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception as e:
    logger.error(f"Error loading embedding model: {str(e)}")
    embedding_model = None

class Document(BaseModel):
    """Class for representing a document in the knowledge base"""
    id: str
    content: str
    metadata: Dict[str, Any] = {}
    embedding: Optional[List[float]] = None

class KnowledgeBase:
    """Class for managing the knowledge base with vector search capabilities"""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)  # L2 distance index
        self.documents = {}
        self.document_ids = []
    
    def add_document(self, document: Document):
        """Add a document to the knowledge base"""
        if not document.embedding:
            # Create embedding if not provided
            if embedding_model:
                document.embedding = embedding_model.encode(document.content).tolist()
            else:
                raise ValueError("Embedding model not loaded")
        
        # Add to index
        embedding_array = np.array([document.embedding], dtype=np.float32)
        self.index.add(embedding_array)
        
        # Store document
        self.documents[document.id] = document
        self.document_ids.append(document.id)
    
    def search(self, query: str, k: int = 5) -> List[Document]:
        """Search the knowledge base for relevant documents"""
        if not embedding_model:
            raise ValueError("Embedding model not loaded")
        
        # Create query embedding
        query_embedding = embedding_model.encode(query)
        query_array = np.array([query_embedding], dtype=np.float32)
        
        # Search index
        distances, indices = self.index.search(query_array, k)
        
        # Get documents
        results = []
        for i in indices[0]:
            if i < len(self.document_ids):
                doc_id = self.document_ids[i]
                results.append(self.documents[doc_id])
        
        return results
    
    def save(self, filepath: str):
        """Save the knowledge base to disk"""
        # Save index
        faiss.write_index(self.index, f"{filepath}.index")
        
        # Save documents
        documents_data = {
            doc_id: {
                "id": doc.id,
                "content": doc.content,
                "metadata": doc.metadata,
                "embedding": doc.embedding
            }
            for doc_id, doc in self.documents.items()
        }
        
        with open(f"{filepath}.json", "w") as f:
            json.dump({
                "documents": documents_data,
                "document_ids": self.document_ids
            }, f)
    
    @classmethod
    def load(cls, filepath: str):
        """Load knowledge base from disk"""
        # Create instance
        kb = cls()
        
        # Load index
        kb.index = faiss.read_index(f"{filepath}.index")
        
        # Load documents
        with open(f"{filepath}.json", "r") as f:
            data = json.load(f)
            kb.document_ids = data["document_ids"]
            kb.documents = {
                doc_id: Document(
                    id=doc_data["id"],
                    content=doc_data["content"],
                    metadata=doc_data["metadata"],
                    embedding=doc_data["embedding"]
                )
                for doc_id, doc_data in data["documents"].items()
            }
        
        return kb

class RAGProcessor:
    """Retrieval-Augmented Generation processor"""
    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
    
    def process_query(self, query: str, k: int = 3) -> str:
        """Process a query using RAG"""
        try:
            # Search for relevant documents
            relevant_docs = self.knowledge_base.search(query, k=k)
            
            # Create context string
            context = "\n\n".join([f"Document {i+1}:\n{doc.content}" for i, doc in enumerate(relevant_docs)])
            
            # Create prompt with retrieved context
            prompt = f"""
            I'll provide you with some relevant information to help answer a question.
            
            Question: {query}
            
            Relevant Information:
            {context}
            
            Please provide a comprehensive answer to the question based on the information provided above.
            If the information doesn't contain the answer, say so clearly rather than making up information.
            """
            
            return prompt
        except Exception as e:
            logger.error(f"Error in RAG processing: {str(e)}")
            return f"I'll help you answer: {query}"

# Example usage of RAG in llm_service.py
# We would modify process_message to use RAG when appropriate
"""
async def process_message(
    llm_client: BaseLLMClient,
    message_history: List[Dict[str, str]],
    current_message: str,
    use_rag: bool = True
) -> str:
    # Check if we should use RAG
    if use_rag:
        # Load knowledge base
        kb = KnowledgeBase.load("path/to/knowledge_base")
        rag_processor = RAGProcessor(kb)
        
        # Process query with RAG
        enhanced_prompt = rag_processor.process_query(current_message)
        
        # Add enhanced prompt as system message
        messages = message_history.copy()
        messages.insert(0, {
            "role": "system",
            "content": enhanced_prompt
        })
        
        # Generate response with enhanced context
        response = await llm_client.generate_response(messages)
        return response
    else:
        # Original processing without RAG
        # ...
"""
