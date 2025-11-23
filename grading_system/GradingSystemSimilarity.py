from typing import Dict
from functools import lru_cache
from langchain_huggingface import HuggingFaceEmbeddings
import numpy as np
from GradingSystem import GradingSystem

class GradingSystemSimilarity(GradingSystem):
    """
    Main grading system that handles the grading process using semantic similarity
    and grammar checking.
    """
    def __init__(self, device ='cpu'):
        super().__init__()
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2",
            model_kwargs={'device': device}
        )
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculates semantic similarity between two texts.
        Args:
            text1: First text to compare
            text2: Second text to compare
        Returns:
            Similarity score between 0 and 1
        """
        try:
            if not text1.strip() or not text2.strip():
                raise ValueError("Empty text provided for similarity calculation")
            
            # Preprocess texts
            doc1 = self.nlp(text1.lower())
            doc2 = self.nlp(text2.lower())
            
            # Word-by-word analysis
            words1 = [token for token in doc1 if not token.is_stop and not token.is_punct]
            words2 = [token for token in doc2 if not token.is_stop and not token.is_punct]
            
            # Calculate word-level similarities
            word_similarities = []
            for word1 in words1:
                word_scores = []
                for word2 in words2:
                    if word1.text == word2.text or word1.lemma_ == word2.lemma_:
                        word_scores.append(1.0)
                    else:
                        emb1 = self.embeddings.embed_query(word1.text)
                        emb2 = self.embeddings.embed_query(word2.text)
                        sim = np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
                        word_scores.append(float(sim))
                
                if word_scores:
                    word_similarities.append(max(word_scores))
            
            # Calculate overall similarities
            word_level_sim = sum(word_similarities) / len(words1) if words1 else 0
            
            text1_processed = ' '.join([token.lemma_ for token in doc1 
                                      if not token.is_stop and not token.is_punct])
            text2_processed = ' '.join([token.lemma_ for token in doc2 
                                      if not token.is_stop and not token.is_punct])
            
            emb1 = self.embeddings.embed_query(text1_processed)
            emb2 = self.embeddings.embed_query(text2_processed)
            
            full_text_sim = float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
            
            # Calculate key term overlap
            key_terms1 = set(token.lemma_ for token in doc1 
                           if token.pos_ in ['NOUN', 'VERB', 'ADJ'] and not token.is_stop)
            key_terms2 = set(token.lemma_ for token in doc2 
                           if token.pos_ in ['NOUN', 'VERB', 'ADJ'] and not token.is_stop)
            
            common_terms = key_terms1.intersection(key_terms2)
            term_similarity = len(common_terms) / max(len(key_terms1), len(key_terms2)) if key_terms1 else 0
            
            # Combine similarity measures
            final_similarity = (
                word_level_sim * 0.4 +
                full_text_sim * 0.4 +
                term_similarity * 0.2
            )
            
            return max(0, min(1, round(final_similarity * 10) / 10))
            
        except Exception as e:
            raise Exception(f"Error calculating similarity: {str(e)}")
    
    def _get_score(self, item: Dict, assignment_text: str):
        criteria_sim = self._calculate_similarity(assignment_text, item['criteria'])
        desc_sim = self._calculate_similarity(assignment_text, item['description'])
        
        # Check for key phrases in description
        desc_doc = self.nlp(item['description'].lower())
        key_phrases = [chunk.text for chunk in desc_doc.noun_chunks]
        
        # Calculate phrase matches
        phrase_scores = []
        for phrase in key_phrases:
            phrase_sim = self._calculate_similarity(assignment_text, phrase)
            phrase_scores.append(phrase_sim)
        
        # Calculate final similarity score
        if phrase_scores:
            similarity = (
                max(criteria_sim, desc_sim) * 0.6 +
                sum(phrase_scores) / len(phrase_scores) * 0.4
            )
        else:
            similarity = max(criteria_sim, desc_sim)
        
        # Adjust score based on content length
        min_words = 50  # Minimum words expected for full credit
        word_count = len(assignment_text.split())
        length_factor = min(1.0, word_count / min_words)
        
        # Calculate final score
        adjusted_similarity = similarity * length_factor
        score = adjusted_similarity * item['points']

        results = {
            'description': item['description'],
            'max_points': item['points'],
            'similarity': adjusted_similarity,
            'score': score,
            'word_count': word_count
        }

        return self._add_labels(score, item, results)

@lru_cache(maxsize=1000)
def get_word_embedding(self, word: str):
    return self.embeddings.embed_query(word) 