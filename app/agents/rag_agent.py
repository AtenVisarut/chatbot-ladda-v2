"""
RAG Agent: Handles vector search and product recommendations
"""
from typing import Dict, Any, List
from langgraph.graph import MessageGraph
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class RAGAgent(BaseModel):
    """Agent for retrieving product recommendations using RAG"""
    
    supabase_client: Any = Field(description="Supabase client instance")
    openai_client: Any = Field(description="OpenAI client instance")
    
    async def search_products(self, disease_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for relevant products using RAG"""
        try:
            # Extract relevant info for search
            disease_name = disease_info.get("disease_name", "")
            pest_type = disease_info.get("pest_type", "")
            
            # Build search query
            query_text = f"{disease_name} {disease_name} {disease_name} {pest_type} โรคพืช ป้องกันโรค"
            
            # Generate embedding
            emb_resp = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query_text
            )
            query_vec = emb_resp.data[0].embedding
            
            # Search in Supabase
            results = await self.supabase_client.rpc(
                'match_products',
                {
                    'query_embedding': query_vec,
                    'match_threshold': 0.3,
                    'match_count': 5
                }
            ).execute()
            
            if not results.data:
                return []
                
            return results.data
            
        except Exception as e:
            logger.error(f"Product search failed: {str(e)}")
            return []

    async def __call__(self, message: Dict) -> Dict:
        """Process message in graph"""
        if "vision_result" not in message:
            return {"error": "No vision analysis result provided"}
            
        products = await self.search_products(message["vision_result"])
        return {
            "vision_result": message["vision_result"],
            "products": products
        }