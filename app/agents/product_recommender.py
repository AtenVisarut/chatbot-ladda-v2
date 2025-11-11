"""
Product recommendation agent that suggests products based on analysis
"""
from typing import Any, Dict, List, Optional
from .base_agent import BaseAgent
from supabase import create_client, Client
import os

class ProductRecommenderAgent(BaseAgent):
    def __init__(self):
        super().__init__("ProductRecommender")
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", "")
        )
    
    async def can_handle(self, data: Dict[str, Any]) -> bool:
        return "analysis_result" in data or "disease_info" in data
    
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate product recommendations based on analysis and user input
        """
        try:
            # Extract keywords from analysis
            keywords = self._extract_keywords(data)
            
            # Search products in database
            products = await self._search_products(keywords)
            
            # Rank and filter products
            recommendations = self._rank_products(products, data)
            
            return {
                "recommendations": recommendations,
                "success": True
            }
            
        except Exception as e:
            return {
                "error": f"Product recommendation failed: {str(e)}",
                "success": False
            }
    
    def _extract_keywords(self, data: Dict[str, Any]) -> List[str]:
        """
        Extract relevant keywords for product search
        """
        keywords = []
        
        if "analysis_result" in data:
            analysis = data["analysis_result"]
            # Add your keyword extraction logic here
            
        if "disease_info" in data:
            disease = data["disease_info"]
            # Add disease-specific keyword extraction
            
        return keywords
    
    async def _search_products(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Search for relevant products in Supabase database
        """
        try:
            # Construct search query
            query = self.supabase.table("products")
            for keyword in keywords:
                query = query.or_(f"description.ilike.%{keyword}%")
            
            response = await query.execute()
            return response.data
            
        except Exception as e:
            logger.error(f"Product search failed: {e}")
            return []
    
    def _rank_products(self, products: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Rank and filter products based on relevance and context
        """
        # Add your product ranking logic here
        ranked_products = sorted(products, key=lambda x: x.get("relevance_score", 0), reverse=True)
        return ranked_products[:5]  # Return top 5 recommendations