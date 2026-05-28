"""
Help Handler for Lumy Chatbot
Manages help articles and search functionality
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime
from .supabase_handler import get_supabase_handler

logger = logging.getLogger(__name__)


class HelpHandler:
    """Handler for help articles and search functionality"""
    
    def __init__(self):
        self.supabase = get_supabase_handler()
    
    def create_tables(self):
        """Create help_articles and help_search_logs tables"""
        try:
            # Create help_articles table
            self.supabase.admin_client.rpc('exec_sql', {
                'sql': '''
                CREATE TABLE IF NOT EXISTS help_articles (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    category VARCHAR(100) NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    keywords TEXT[],
                    is_active BOOLEAN DEFAULT true,
                    order_index INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS idx_help_articles_category ON help_articles(category);
                CREATE INDEX IF NOT EXISTS idx_help_articles_is_active ON help_articles(is_active);
                CREATE INDEX IF NOT EXISTS idx_help_articles_keywords ON help_articles USING GIN(keywords);
                '''
            })
            
            # Create help_search_logs table
            self.supabase.admin_client.rpc('exec_sql', {
                'sql': '''
                CREATE TABLE IF NOT EXISTS help_search_logs (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    user_id UUID,
                    query TEXT NOT NULL,
                    matched_article_id UUID,
                    found_result BOOLEAN DEFAULT false,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY (matched_article_id) REFERENCES help_articles(id) ON DELETE SET NULL
                );
                
                CREATE INDEX IF NOT EXISTS idx_help_search_logs_user_id ON help_search_logs(user_id);
                CREATE INDEX IF NOT EXISTS idx_help_search_logs_created_at ON help_search_logs(created_at);
                '''
            })
            
            logger.info('[Help] Tables created successfully')
            return {'success': True}
            
        except Exception as e:
            logger.error('[Help] Error creating tables', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def normalize_search_text(self, text: str) -> str:
        """Normalize text for search - remove accents, lowercase"""
        import unicodedata
        import re
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove accents
        text = unicodedata.normalize('NFKD', text)
        text = ''.join([c for c in text if not unicodedata.combining(c)])
        
        # Remove special characters, keep only letters, numbers and spaces
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        
        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def calculate_match_score(self, query: str, article: Dict) -> float:
        """Calculate match score between query and article"""
        query_normalized = self.normalize_search_text(query)
        query_words = set(query_normalized.split())
        
        score = 0.0
        
        # Check question match
        question_normalized = self.normalize_search_text(article.get('question', ''))
        question_words = set(question_normalized.split())
        
        # Exact match in question
        if query_normalized in question_normalized:
            score += 2.0
        # Partial word matches in question
        query_in_question = query_words & question_words
        score += len(query_in_question) * 0.5
        
        # Check answer match
        answer_normalized = self.normalize_search_text(article.get('answer', ''))
        answer_words = set(answer_normalized.split())
        
        query_in_answer = query_words & answer_words
        score += len(query_in_answer) * 0.3
        
        # Check keywords match
        keywords = article.get('keywords', [])
        if keywords:
            for keyword in keywords:
                keyword_normalized = self.normalize_search_text(keyword)
                if query_normalized in keyword_normalized:
                    score += 1.0
                elif keyword_normalized in query_normalized:
                    score += 0.5
        
        # Boost exact category match
        category_normalized = self.normalize_search_text(article.get('category', ''))
        if query_normalized in category_normalized:
            score += 0.5
        
        return score
    
    def search_help_articles(self, query: str, limit: int = 5) -> Dict:
        """Search help articles by query"""
        try:
            logger.info('[Help] Searching articles', extra={'query': query})
            
            # Get all active articles
            response = self.supabase.admin_client.table('help_articles') \
                .select('*') \
                .eq('is_active', True) \
                .order('order_index') \
                .execute()
            
            if not response.data:
                return {'success': True, 'results': []}
            
            articles = response.data
            
            # Calculate scores for each article
            scored_articles = []
            for article in articles:
                score = self.calculate_match_score(query, article)
                if score > 0:
                    scored_articles.append({
                        'article': article,
                        'score': score
                    })
            
            # Sort by score (descending)
            scored_articles.sort(key=lambda x: x['score'], reverse=True)
            
            # Return top results
            results = [item['article'] for item in scored_articles[:limit]]
            
            logger.info('[Help] Search completed', extra={'results_count': len(results)})
            
            return {
                'success': True,
                'results': results,
                'total_found': len(results)
            }
            
        except Exception as e:
            logger.error('[Help] Error searching articles', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def log_help_search(self, user_id: str, query: str, matched_article_id: Optional[str] = None, found_result: bool = False) -> Dict:
        """Log help search for analytics"""
        try:
            data = {
                'user_id': user_id,
                'query': query,
                'matched_article_id': matched_article_id,
                'found_result': found_result
            }
            
            response = self.supabase.admin_client.table('help_search_logs') \
                .insert(data) \
                .execute()
            
            logger.info('[Help] Search logged', extra={'user_id': user_id, 'query': query})
            
            return {'success': True}
            
        except Exception as e:
            logger.error('[Help] Error logging search', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_categories(self) -> Dict:
        """Get all unique categories"""
        try:
            response = self.supabase.admin_client.table('help_articles') \
                .select('category') \
                .eq('is_active', True) \
                .execute()
            
            if not response.data:
                return {'success': True, 'categories': []}
            
            # Get unique categories
            categories = list(set([article['category'] for article in response.data]))
            categories.sort()
            
            return {'success': True, 'categories': categories}
            
        except Exception as e:
            logger.error('[Help] Error getting categories', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_popular_articles(self, limit: int = 10) -> Dict:
        """Get most searched articles"""
        try:
            response = self.supabase.admin_client.table('help_search_logs') \
                .select('matched_article_id, count(*) as search_count') \
                .group('matched_article_id') \
                .order('search_count', desc=True) \
                .limit(limit) \
                .execute()
            
            if not response.data:
                return {'success': True, 'articles': []}
            
            # Get article details
            article_ids = [log['matched_article_id'] for log in response.data if log['matched_article_id']]
            
            if not article_ids:
                return {'success': True, 'articles': []}
            
            articles_response = self.supabase.admin_client.table('help_articles') \
                .select('*') \
                .in_('id', article_ids) \
                .execute()
            
            return {'success': True, 'articles': articles_response.data if articles_response.data else []}
            
        except Exception as e:
            logger.error('[Help] Error getting popular articles', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def create_article(self, category: str, question: str, answer: str, keywords: List[str], order_index: int = 0) -> Dict:
        """Create a new help article"""
        try:
            data = {
                'category': category,
                'question': question,
                'answer': answer,
                'keywords': keywords,
                'order_index': order_index
            }
            
            response = self.supabase.admin_client.table('help_articles') \
                .insert(data) \
                .execute()
            
            logger.info('[Help] Article created', extra={'question': question})
            
            return {
                'success': True,
                'article': response.data[0] if response.data else None
            }
            
        except Exception as e:
            logger.error('[Help] Error creating article', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def update_article(self, article_id: str, category: str = None, question: str = None, 
                      answer: str = None, keywords: List[str] = None, is_active: bool = None, 
                      order_index: int = None) -> Dict:
        """Update a help article"""
        try:
            update_data = {}
            if category is not None:
                update_data['category'] = category
            if question is not None:
                update_data['question'] = question
            if answer is not None:
                update_data['answer'] = answer
            if keywords is not None:
                update_data['keywords'] = keywords
            if is_active is not None:
                update_data['is_active'] = is_active
            if order_index is not None:
                update_data['order_index'] = order_index
            update_data['updated_at'] = datetime.now().isoformat()
            
            response = self.supabase.admin_client.table('help_articles') \
                .update(update_data) \
                .eq('id', article_id) \
                .execute()
            
            logger.info('[Help] Article updated', extra={'article_id': article_id})
            
            return {
                'success': True,
                'article': response.data[0] if response.data else None
            }
            
        except Exception as e:
            logger.error('[Help] Error updating article', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def delete_article(self, article_id: str) -> Dict:
        """Delete a help article"""
        try:
            self.supabase.admin_client.table('help_articles') \
                .delete() \
                .eq('id', article_id) \
                .execute()
            
            logger.info('[Help] Article deleted', extra={'article_id': article_id})
            
            return {'success': True}
            
        except Exception as e:
            logger.error('[Help] Error deleting article', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def submit_feedback(self, user_id: str, article_id: str, helpful: bool) -> Dict:
        """Submit feedback for an article"""
        try:
            data = {
                'user_id': user_id,
                'article_id': article_id,
                'helpful': helpful
            }
            
            self.supabase.admin_client.table('help_feedback') \
                .insert(data) \
                .execute()
            
            logger.info('[Help] Feedback submitted', extra={'user_id': user_id, 'article_id': article_id, 'helpful': helpful})
            
            return {'success': True}
            
        except Exception as e:
            logger.error('[Help] Error submitting feedback', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_analytics(self) -> Dict:
        """Get analytics data for Lumy dashboard"""
        try:
            # Get most searched queries
            search_response = self.supabase.admin_client.table('help_search_logs') \
                .select('query, count(*) as search_count') \
                .group('query') \
                .order('search_count', desc=True) \
                .limit(20) \
                .execute()
            
            most_searched = search_response.data if search_response.data else []
            
            # Get searches without result
            no_result_response = self.supabase.admin_client.table('help_search_logs') \
                .select('query, count(*) as count') \
                .eq('found_result', False) \
                .group('query') \
                .order('count', desc=True) \
                .limit(20) \
                .execute()
            
            searches_no_result = no_result_response.data if no_result_response.data else []
            
            # Get total searches
            total_searches_response = self.supabase.admin_client.table('help_search_logs') \
                .select('count(*) as total') \
                .execute()
            
            total_searches = total_searches_response.data[0]['total'] if total_searches_response.data else 0
            
            # Get searches with result
            with_result_response = self.supabase.admin_client.table('help_search_logs') \
                .select('count(*) as total') \
                .eq('found_result', True) \
                .execute()
            
            with_result = with_result_response.data[0]['total'] if with_result_response.data else 0
            
            # Get article feedback stats
            feedback_response = self.supabase.admin_client.table('help_feedback') \
                .select('article_id, helpful, count(*) as count') \
                .group('article_id, helpful') \
                .execute()
            
            feedback_stats = feedback_response.data if feedback_response.data else []
            
            # Get most helpful articles
            helpful_articles = {}
            for feedback in feedback_stats:
                article_id = feedback['article_id']
                helpful = feedback['helpful']
                count = feedback['count']
                
                if article_id not in helpful_articles:
                    helpful_articles[article_id] = {'helpful': 0, 'not_helpful': 0}
                
                if helpful:
                    helpful_articles[article_id]['helpful'] = count
                else:
                    helpful_articles[article_id]['not_helpful'] = count
            
            # Calculate helpfulness score
            for article_id, stats in helpful_articles.items():
                total = stats['helpful'] + stats['not_helpful']
                if total > 0:
                    stats['score'] = stats['helpful'] / total
                else:
                    stats['score'] = 0
            
            # Sort by score
            sorted_articles = sorted(helpful_articles.items(), key=lambda x: x[1]['score'], reverse=True)
            
            # Get article details for top articles
            top_article_ids = [aid for aid, _ in sorted_articles[:10]]
            if top_article_ids:
                articles_response = self.supabase.admin_client.table('help_articles') \
                    .select('*') \
                    .in_('id', top_article_ids) \
                    .execute()
                
                articles_dict = {a['id']: a for a in articles_response.data} if articles_response.data else {}
                
                top_helpful = []
                for article_id, stats in sorted_articles[:10]:
                    if article_id in articles_dict:
                        top_helpful.append({
                            'article': articles_dict[article_id],
                            'stats': stats
                        })
            else:
                top_helpful = []
            
            return {
                'success': True,
                'most_searched': most_searched,
                'searches_no_result': searches_no_result,
                'total_searches': total_searches,
                'with_result': with_result,
                'without_result': total_searches - with_result,
                'success_rate': (with_result / total_searches * 100) if total_searches > 0 else 0,
                'top_helpful': top_helpful
            }
            
        except Exception as e:
            logger.error('[Help] Error getting analytics', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def suggest_category(self, keywords: List[str]) -> Dict:
        """Suggest category based on keywords using existing articles"""
        try:
            # Get all active articles
            response = self.supabase.admin_client.table('help_articles') \
                .select('category, keywords') \
                .eq('is_active', True) \
                .execute()
            
            if not response.data:
                return {'success': True, 'suggested_category': None}
            
            articles = response.data
            
            # Calculate category scores based on keyword overlap
            category_scores = {}
            
            for article in articles:
                category = article['category']
                article_keywords = article.get('keywords', [])
                
                if category not in category_scores:
                    category_scores[category] = 0
                
                # Count keyword matches
                for keyword in keywords:
                    keyword_normalized = self.normalize_search_text(keyword)
                    for article_keyword in article_keywords:
                        article_keyword_normalized = self.normalize_search_text(article_keyword)
                        if keyword_normalized in article_keyword_normalized or article_keyword_normalized in keyword_normalized:
                            category_scores[category] += 1
            
            # Return category with highest score
            if category_scores:
                suggested_category = max(category_scores, key=category_scores.get)
                return {
                    'success': True,
                    'suggested_category': suggested_category,
                    'confidence': category_scores[suggested_category]
                }
            else:
                return {'success': True, 'suggested_category': None}
            
        except Exception as e:
            logger.error('[Help] Error suggesting category', exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def get_related_articles(self, article_id: str, limit: int = 3) -> Dict:
        """Get related articles based on category and keywords"""
        try:
            # Get the article
            article_response = self.supabase.admin_client.table('help_articles') \
                .select('*') \
                .eq('id', article_id) \
                .execute()
            
            if not article_response.data:
                return {'success': True, 'related_articles': []}
            
            article = article_response.data[0]
            category = article['category']
            keywords = article.get('keywords', [])
            
            # Get articles from same category (excluding current)
            response = self.supabase.admin_client.table('help_articles') \
                .select('*') \
                .eq('category', category) \
                .eq('is_active', True) \
                .neq('id', article_id) \
                .order('order_index') \
                .limit(limit) \
                .execute()
            
            related = response.data if response.data else []
            
            return {'success': True, 'related_articles': related}
            
        except Exception as e:
            logger.error('[Help] Error getting related articles', exc_info=True)
            return {'success': False, 'error': str(e)}


# Singleton instance
_help_handler = None

def get_help_handler():
    """Get the singleton HelpHandler instance"""
    global _help_handler
    if _help_handler is None:
        _help_handler = HelpHandler()
    return _help_handler
