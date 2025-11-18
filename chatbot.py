from langchain_core.language_models.chat_models import BaseChatModel

def response_generator(model: BaseChatModel, messages: list) -> str:
    """
    Streamed response emulator
    """
    response = model.invoke(messages)
    return response.content.split("</think>")[-1]

def _write_scores(criterion, details, prefix="") -> str:
    scores = f"\n{prefix}**Criterion:** {criterion}"
    scores += f"\n{prefix}**Description:** {details['description']}"
    scores += f"\n{prefix}**Max Points:** {details['max_points']:.1f}"
    if 'similarity' in details:
        scores += f"\n{prefix}**Similarity Score:** {details['similarity']:.2f}"
    scores += f"\n{prefix}**Points Earned:** {details['score']:.2f}"
    if 'label' in details:
        scores += f"\n{prefix}**Label:** {details['label']}"
    if 'justification' in details:
        scores += f"\n{prefix}**Explanation:** {details['justification']}"
    return scores

def _results_to_str(results):
    grades = "Grading Results:"
    grades += f"\nFinal Grade: {results['final_grade']*100:.1f}%"
    grades += f"\nTotal Points Earned: {results['total_points_earned']:.1f}/{results['total_points_possible']:.1f}"
        
    # Display detailed criteria breakdown
    grades += "\nCriteria Breakdown:"
    for criterion, details in results['criteria_scores'].items():
        grades += "\n---"
        grades += _write_scores(criterion, details)
        if len(details['sub_scores']) > 0:
            grades += "\n**Sub-Criteria Breakdown:**"
            for sub_criterion, sub_details in details['sub_scores'].items():
                grades += _write_scores(sub_criterion, sub_details, "\t")
        
        # Display grammar feedback if available
        if 'feedback' in details:
            grades += "\n**Grammar Analysis:**"
            stats = details['feedback']['statistics']
            grades += f"\n- Words: {stats['word_count']}"
            grades += f"\n- Sentences: {stats['sentence_count']}"
            if details['feedback']['errors']:
                grades += "\n**Detailed Error Feedback:**"
                for error in details['feedback']['errors']:
                    grades += f"\n- {error['message']}"
                    if 'suggestion' in error:
                        grades += f"\n  Suggestion: {error['suggestion']}"
    return grades

def get_submission_prompt(results: dict) -> dict:
    """
    Returns the user message for the chatbot with the student's plan and grading results.
    """
    return {
            "role": "user",
            "content": f"Plan:\n{results["assignment_text"]}\n\n{_results_to_str(results)}"
        }

def get_system_prompt() -> dict:
    """
    Returns the system prompt for the chatbot.
    """
    return {
            "role": "system", 
            "content": 'You are an AI tutor. Your student submitted a semester plan for a course to a teacher and received grades. Your task is to help your student understand the grades and improve their semester plan. First, your student will give you their plan followed by "Plan:" and grades they have got from the teacher followed by "Grading Results:". Then, you will analyze the plan and the grades and pick the criterion with the most room for improvement. Next, make at most 3 questions that help your student recognize how to improve their plan through conversation. Ask one question per turn so that the student can answer one by one. Finally, ask them to resubmit a plan. Once they resubmit, you will receive a revised plan and grades in the same format as before. You will keep the same procedure until all of the student\'s weak points are resolved. Your replies to your student must be short and friendly, no more than 2 sentences.',
        }