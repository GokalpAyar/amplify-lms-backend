from typing import Dict, List
import os
import re
import tempfile
import jsonlines
from pypdf import PdfReader
from docx import Document
from pdf2image import convert_from_path
from pydantic import BaseModel, Field
from llm_utils import get_model, image_content
from domain_information import PROBLEMS, TEXT_PATH, INDEX_NAME
from retriever.TextRetrieverConcepts import TextRetrieverConcepts

class Label(BaseModel):
    desctiption: str = Field(description="The characterisics of student rationales that are considered as this label (high, medium, low, or very low). This new description must contain domain knowledge identifed in previous steps.")
    lowest: int = Field(description="The lowest score of this label.")
    highest: int = Field(description="The highest score of this label.")

class Rubrics(BaseModel):
    criteria: str = Field(description="What this rubrics expects in student rationale.")
    high: Label = Field(description="The student rationales that satisfies all the criteria are considered as high.")
    medium: Label = Field(description="The student rationales that satisfies most of the criteria are considered as medium.")
    low: Label = Field(description="The student rationales that satisfies some of the criteria are considered as low.")
    very_low: Label = Field(description="The student rationales that fail to satisfy the criteria are considered as very low.")

class Analysis(BaseModel):
    analysis: str = Field(description="The analysis of the problem, espefically what concepts and principles it tests")
    concepts: str = Field(description="The explanation of how the concepts and principles are relevant to the problem")
    application: str = Field(description="The explanation of how to apply the concepts principles to solve the problem.")
    rubrics: Rubrics = Field(description="The new rubrics more specific to the problem, containing the domain knowledge from other parts.")

class DocumentProcessor:
    """
    Base class for processing documents.
    """

    def extract_text_from_pdf(self, file_path: str) -> str:
        """
        Extracts text from a PDF file.
        Args:
            file_path: Path to the PDF file
        Returns:
            Extracted text as a string
        """
        text = ""
        pdf_reader = PdfReader(file_path)
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    def extract_text_from_docx(self, file_path: str) -> str:
        """
        Extracts text from a DOCX file.
        Args:
            file_path: Path to the DOCX file
        Returns:
            Extracted text as a string
        """
        doc = Document(file_path)
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

    def process_document(self, file_path: str) -> str:
        """
        Processes a document based on its file type.
        Args:
            file_path: Path to the document
        Returns:
            Extracted text as a string
        """
        file_extension = os.path.splitext(file_path)[1].lower()
        
        if file_extension == '.pdf':
            return self.extract_text_from_pdf(file_path)
        if file_extension == '.docx':
            return self.extract_text_from_docx(file_path)
        raise ValueError("Unsupported file format")
    

class AssignmentProcessor(DocumentProcessor):
    """
    Handles the processing of different document types (PDF and DOCX)
    and text extraction from these documents.
    """

class RubricProcessor(DocumentProcessor):
    """
    Handles the processing and extraction of grading criteria from rubric files.
    """

    def __init__(self):
        super().__init__()
        llm = get_model("qwen2.5vl")
        self.llm = llm.with_structured_output(Rubrics)
        
        # Define patterns for identifying rubric sections
        self.section_patterns = [
            r'\n(?=Criteria:|CRITERIA:|Criterion:|CRITERION:)',
            r'\n(?=\d+\.|\d+\))',
            r'\n(?=[A-Z][^a-z]+:)',
            r'\n(?=\*|\-|\•)',
            r'\n\n(?=[A-Z][^\.]+(?:\.|:))'
        ]
        self.retriever = None
    
    def set_retriever(self, model_name, text_path, index_root, index_name):
        self.retriever = TextRetrieverConcepts(model_name, text_path, index_root, index_name)
        
    def _extract_points(self, section: str):
        """
        Extract points using various patterns.
        Args:
            section: The section of text to search for points
        Returns:
            Extracted points as a float
        """
        points_patterns = [
            r'(?:Points:|points:?)\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*(?:Points|points)',
            r'(?:Worth|worth|Value|value):\s*(\d+(?:\.\d+)?)',
            r'\((\d+(?:\.\d+)?)\s*pts?\)',
            r'\[(\d+(?:\.\d+)?)\s*pts?\]',
            r'(\d+(?:\.\d+)?)\s*(?:marks|Marks|point|Point)'
        ]
        
        for p_pattern in points_patterns:
            points_match = re.search(p_pattern, section, re.IGNORECASE)
            if points_match:
                return float(points_match.group(1))
        return None
    
    def _extract_range(self, line: str):
        """
        Extracts a range of points from a line.
        Args:
            line: The line of text to search for a range
        Returns:
            Extracted range as a tuple (min, max)
        """
        range_patterns = [
            r'(?:Points:|points:?)\s*(\d+)\s*-\s*(\d+)',
            r'(\d+)\s*-\s*(\d+)\s*(?:Points|points)',
            r'(?:Worth|worth|Value|value):\s*(\d+)\s*-\s*(\d+)',
            r'\((\d+)\s*-\s*(\d+)\s*pts?\)',
            r'\[(\d+)\s*-\s*(\d+)\s*pts?\]',
            r'(\d+)\s*-\s*(\d+)\s*(?:marks|Marks|point|Point)'
        ]
        
        for r_pattern in range_patterns:
            match = re.search(r_pattern, line)
            if match:
                return (float(match.group(1)), float(match.group(2))), re.split(r_pattern, line)
        return None, None
    
    def _format_criteria(self, criteria_line: str, description_lines: List[str], points: float, labels: List[Dict]) -> Dict:
        criteria = re.sub(r'^(?:\d+[\.\)]\s*|\*\s*|\-\s*|\•\s*)', '', criteria_line)
        criteria = criteria.strip(':').strip()
        
        description = ' '.join(description_lines).strip()
        if not description:
            description = criteria
        
        return {
            'criteria': criteria,
            'description': description,
            'points': points,
            'labels': labels
        }
    
    def _extract_criteria(self, text: str):
        # Process rubric sections
        rubric_items = []
        for pattern in self.section_patterns:
            sections = re.split(pattern, text)
            if len(sections) > 1:
                for section in sections:
                    if not section.strip():
                        continue
                    
                    # Extract points using various patterns
                    points = self._extract_points(section)
                    
                    if points is not None:
                        # Extract criteria and description
                        lines = [line.strip() for line in section.split('\n') if line.strip()]
                        
                        criteria_line = None
                        description_lines = []
                        capture_description = False
                        labels = []
                        sub_criteria_lines = []
                        sub_description_lines = []
                        capture_sub_description = False
                        sub_points = []
                        sub_labels = []
                        
                        for line in lines:
                            sub_range, splitted_range = self._extract_range(line)
                            if sub_range is not None:
                                # If a line contains a range, it is a label
                                label_item = {
                                        'label': splitted_range[0].strip('(').strip(),
                                        'description': splitted_range[-1].strip(')').strip(':').strip(),
                                        'min': sub_range[0],
                                        'max': sub_range[1]
                                }
                                if capture_sub_description:
                                    sub_labels[-1].append(label_item)
                                else:
                                    labels.append(label_item)
                            else:
                                sub_point = self._extract_points(line)
                                if sub_point is not None:
                                    # If a line contains points, it is a criteria line or a sub-criterion
                                    if criteria_line is None: # Criteria line
                                        criteria_line = line
                                        capture_description = True
                                    else: #Sub-criterion
                                        sub_criteria_lines.append(line)
                                        capture_sub_description = True
                                        sub_description_lines.append([])
                                        sub_labels.append([])
                                        sub_points.append(sub_point)
                                elif capture_sub_description:
                                    sub_description_lines[-1].append(line)
                                elif capture_description:
                                    description_lines.append(line)
                        
                        if criteria_line:
                            criteria_item = self._format_criteria(criteria_line, description_lines, points, labels)
                            criteria_item['sub_criteria'] = []
                            for sub_criteria_line, sub_description, sub_point, sub_label in zip(sub_criteria_lines, sub_description_lines, sub_points, sub_labels):
                                sub_criteria_item = self._format_criteria(sub_criteria_line, sub_description, sub_point, sub_label)
                                criteria_item['sub_criteria'].append(sub_criteria_item)
                            rubric_items.append(criteria_item)
                
                if rubric_items:
                    break
        
        if not rubric_items:
            raise ValueError("No valid criteria found in rubric")
        return rubric_items
    
    def get_user_content(self, problem: dict, page_images: list):
        user_content = [{
            "type": "text",
            "text": f"""Please tailor the rubrics to evaluate student written rationales for their choice to the multiple-choice problem by incorporating knowledge needed for the problem. 
I will give you the problem, rubrics, and seven images. The first image is the system diagram of the problem, the second image contains the choices, and the remaining images are textbook pages that may contain knowledge helpful to solve the problem.
Problem: {problem["problem"]}"""}]
        for img in problem["images"]:
            user_content.append(image_content(img))
        for img in page_images:
            user_content.append(image_content(img))
        return user_content
    
    def _modify_rubric(self, text: str, problem_name: str) -> str:
        problem = PROBLEMS[problem_name]
        model_name = "qwen2.5vl"
        index_root = "./index"
        index_name = INDEX_NAME
        if self.retriever is None:
            self.set_retriever(model_name, TEXT_PATH, index_root, index_name)
        pages = self.retriever.retrieve(problem)
        
        base_messsage = [{
            "role": "system",
            "content": "Adapt the given rubric for the given multiple-choice problem, using the knowledge from the attached textbook pages. The first image is the system diagram of the problem, the second image contains the choices, and the remaining images are textbook pages that contain knowledge required to solve the problem."
        }]
        page_images = []
        modified_text = ""
        with tempfile.TemporaryDirectory() as path:
            for page in pages:
                page_images.extend(convert_from_path(
                    TEXT_PATH,
                    thread_count=os.cpu_count() - 1,
                    output_folder=path,
                    dpi=300,
                    fmt="png",
                    first_page=page,
                    last_page=page,
                    paths_only=True
                ))
            user_content = self.get_user_content(problem, page_images)
            
            for pattern in self.section_patterns:
                sections = re.split(pattern, text)
                if len(sections) > 1:
                    for i, section in enumerate(sections):
                        if not section.strip():
                            continue
                        user_content.append({
                            "type": "text",
                            "text": f"Rubric: {section}"})
                        messages = base_messsage + [{
                            "role": "user",
                            "content": user_content
                        }]
                        print(messages)
                        response = self.llm.invoke(messages).rubric
                        modified_text += f"{i+1}. {response}\n"

        print(modified_text)
        return modified_text.strip()
    
    def extract_rubric(
            self,
            file_path: str,
            problem_name: str = None,
            modify_rubric: bool = False) -> List[Dict]:
        """
        Extracts rubric details from a file.
        Args:
            file_path: Path to the rubric file
        Returns:
            List of dictionaries containing criteria, descriptions, and points
        """
        try:
            # Use cached rubrics if there exist
            if modify_rubric:
                assert problem_name is not None, "problem_name must be set to modify a rubric"
                problem_rubric_path = os.path.join("./problems", problem_name, "rubrics.jsonl")
                if os.path.exists(problem_rubric_path):
                    with jsonlines.open(problem_rubric_path, "r") as reader:
                        return [obj for obj in reader]
                    
            # Extract text
            text = self.process_document(file_path)
            if not text.strip():
                raise ValueError("No text could be extracted from the rubric DOCX")
            
            # Modify the rubrics and save them
            if modify_rubric:
                text = self._modify_rubric(text, problem_name)
            
            # Process rubric sections
            rubric_items = self._extract_criteria(text)
            if modify_rubric:
                with jsonlines.open(problem_rubric_path, "w") as writer:
                    writer.write_all(rubric_items)
            
            return rubric_items
            
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Error processing rubric: {str(e)}")