from typing import Dict, Tuple
from spellchecker import SpellChecker
from textblob import TextBlob
import spacy
from document_processor import AssignmentProcessor, RubricProcessor

class GradingSystem:
    """
    A superclass of grading systems that handle rubric-based grading and grammar checking.
    """
    def __init__(self):
        self.doc_processor = AssignmentProcessor()
        self.rubric_processor = RubricProcessor()
        self.spell = SpellChecker()
        self.nlp = spacy.load('en_core_web_sm')
    
    def check_grammar(self, text: str) -> Tuple[float, Dict]:
        """
        Checks grammar and spelling in the text.
        Args:
            text: Text to check
        Returns:
            Tuple of (score, feedback dictionary)
        """
        try:
            # Process text with spaCy
            doc = self.nlp(text)
            
            # Count words and sentences
            words = [token.text.lower() for token in doc if not token.is_punct and not token.is_space]
            word_count = len(words)
            sentences = list(doc.sents)
            sentence_count = len(sentences)
            
            if sentence_count == 0 or word_count == 0:
                return 0, {"errors": [], "feedback": "No valid text found"}
            
            # Spell check
            misspelled = list(self.spell.unknown(words))
            spelling_errors = len(misspelled)
            
            # Grammar and analysis using TextBlob
            blob = TextBlob(text)
            
            error_categories = {
                'spelling': spelling_errors,
                'grammar': 0,
                'punctuation': 0
            }
            
            grammar_issues = []
            correct_sentences = 0
            
            # Analyze each sentence
            for sent in sentences:
                sent_text = str(sent).strip()
                sent_doc = self.nlp(sent_text)
                
                sentence_errors = 0
                
                # Check basic sentence structure
                has_subject = False
                has_verb = False
                has_proper_case = sent_text[0].isupper() if sent_text else False
                has_end_punct = sent_text[-1] in '.!?' if sent_text else False
                
                for token in sent_doc:
                    if token.dep_ in ['nsubj', 'nsubjpass']:
                        has_subject = True
                    if token.pos_ == 'VERB':
                        has_verb = True
                
                # Grammar checks
                if not (has_subject and has_verb):
                    error_categories['grammar'] += 1
                    sentence_errors += 1
                    grammar_issues.append({
                        'error_type': 'Sentence Structure',
                        'message': f'Missing subject or verb in: "{sent_text}"',
                        'suggestion': 'Ensure sentence has both subject and verb'
                    })
                
                if not has_proper_case:
                    error_categories['grammar'] += 1
                    sentence_errors += 1
                    grammar_issues.append({
                        'error_type': 'Capitalization',
                        'message': f'Sentence should start with capital letter: "{sent_text}"',
                        'suggestion': f'Change to: "{sent_text[0].upper() + sent_text[1:]}"'
                    })
                
                if not has_end_punct:
                    error_categories['punctuation'] += 1
                    sentence_errors += 1
                    grammar_issues.append({
                        'error_type': 'Missing Punctuation',
                        'message': f'Sentence missing end punctuation: "{sent_text}"',
                        'suggestion': 'Add appropriate end punctuation (. ! ?)'
                    })
                
                if sentence_errors == 0:
                    correct_sentences += 1
            
            # Add spelling suggestions
            for word in misspelled:
                grammar_issues.append({
                    'error_type': 'Spelling',
                    'message': f'Misspelled word: "{word}"',
                    'suggestion': f'Suggestions: {", ".join(self.spell.candidates(word))}'
                })
            
            # Calculate scores
            if word_count <= 20:  # Short text adjustments
                base_spelling_score = max(0.4, 1 - (spelling_errors / word_count * 2))
                base_grammar_score = max(0.4, correct_sentences / sentence_count)
                base_punct_score = max(0.4, 1 - (error_categories['punctuation'] / sentence_count))
            else:  # Normal scoring for longer texts
                base_spelling_score = max(0, 1 - (spelling_errors / word_count * 2))
                base_grammar_score = max(0, 1 - (error_categories['grammar'] / sentence_count))
                base_punct_score = max(0, 1 - (error_categories['punctuation'] / sentence_count))
            
            # Calculate final score
            final_score = (
                base_spelling_score * 0.3 +
                base_grammar_score * 0.5 +
                base_punct_score * 0.2
            )
            
            if correct_sentences > 0:
                final_score = max(0.4, final_score)
            
            feedback = {
                'errors': grammar_issues,
                'statistics': {
                    'word_count': word_count,
                    'sentence_count': sentence_count,
                    'correct_sentences': correct_sentences,
                    'words_per_sentence': round(word_count/sentence_count if sentence_count else 0, 1),
                    'total_errors': len(grammar_issues),
                    'error_categories': error_categories
                },
                'component_scores': {
                    'spelling': round(base_spelling_score, 2),
                    'grammar': round(base_grammar_score, 2),
                    'punctuation': round(base_punct_score, 2)
                }
            }
            
            return round(final_score, 2), feedback
            
        except Exception as e:
            raise Exception(f"Error in grammar checking: {str(e)}")
    
    def _add_labels(self, score: float, item: Dict, results: Dict) -> Dict:
        """
        Adds labels to the score based on predefined ranges in the rubric item.
        Args:
            score: Calculated score for the item
            item: Rubric item containing labels
        Returns:
            Dictionary containing the score and label if applicable
        """
        if len(item['labels']) > 0:
            for label in item['labels']:
                if label['min'] <= score < label['max']:
                    results['label'] = label['label']
        
        return results
    
    def _get_score(self, item: Dict, assignment_text: str) -> Dict:
        """
        To be impremented by subclasses to calculate score based on item criteria.
        Args:
            item: Rubric item containing criteria and description
            assignment_text: Text of the assignment to grade
        Returns:
            Dictionary containing five fields:
            - description: Description of the rubric item
            - max_points: Maximum points for this item
            - similarity: Similarity score between assignment and rubric item
            - score: Calculated score based on similarity and max points
            - word_count: Number of words in the assignment text
        """
        raise NotImplementedError("This method should be implemented by subclasses")
    
    def grade_assignment(self, assignment_path: str, rubric_path: str, problem_name: str = None) -> Dict:
        """
        Grades an assignment based on the provided rubric.
        Args:
            assignment_path: Path to the assignment file
            rubric_path: Path to the rubric file
        Returns:
            Dictionary containing grading results
        """
        try:
            # Process assignment
            assignment_text = self.doc_processor.process_document(assignment_path)
            if not assignment_text.strip():
                raise ValueError("No text extracted from assignment")
            
            # Process rubric
            if problem_name:
                modify_rubric = True
            else:
                modify_rubric = False
            rubric_items = self.rubric_processor.extract_rubric(rubric_path, problem_name, modify_rubric)
            if not rubric_items:
                raise ValueError("No criteria extracted from rubric")
            
            total_points_possible = sum(item['points'] for item in rubric_items)
            if total_points_possible <= 0:
                raise ValueError("Total points must be greater than 0")
            
            # Calculate scores for each criterion
            scores = {}
            earned_points = 0
            
            for item in rubric_items:
                if 'grammar' in item['criteria'].lower() or 'spelling' in item['criteria'].lower():
                    # Use grammar checker for grammar-related criteria
                    similarity, feedback = self.check_grammar(assignment_text)
                    score = similarity * item['points']
                    scores[item['criteria']] = {
                        'description': item['description'],
                        'max_points': item['points'],
                        'similarity': similarity,
                        'score': score,
                        'feedback': feedback
                    }
                else:
                    # Enhanced content scoring
                    if len(item['sub_criteria']) > 0:
                        sub_scores = {}
                        for sub_item in item['sub_criteria']:
                            sub_scores[sub_item['criteria']] = self._get_score(sub_item, assignment_text)
                        score = {
                            'description': item['description'],
                            'max_points': item['points'],
                            'score': sum(sub_score['score'] for sub_score in sub_scores.values()),
                            'word_count': len(assignment_text.split()),
                            'sub_scores': sub_scores
                        }
                        if 'similarity' in sub_scores[item['sub_criteria'][0]['criteria']]:
                            score['similarity'] = sum(sub_score['similarity'] for sub_score in sub_scores.values()) / len(sub_scores)
                    else:
                        score = self._get_score(item, assignment_text)
                        score['sub_scores'] = []
                    
                    scores[item['criteria']] = score
                
                earned_points += scores[item['criteria']]['score']
            
            final_grade = earned_points / total_points_possible
            
            return {
                'criteria_scores': scores,
                'final_grade': final_grade,
                'total_points_possible': total_points_possible,
                'total_points_earned': earned_points,
                'assignment_text': assignment_text,
            }
            
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Error grading assignment: {str(e)}")