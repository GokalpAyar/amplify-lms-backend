from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from openai import OpenAI, OpenAIError
from sqlmodel import Session, select

from models import Assignment, GradingResult, Response

logger = logging.getLogger(__name__)

GRADER_VERSION = "auto-grader-v2"
GRADING_MODEL_ENV_KEYS = ("AUTO_GRADER_MODEL", "OPENAI_GRADING_MODEL", "OPENAI_MODEL")
DEFAULT_GRADING_MODEL = "gpt-4o-mini"
CONFIDENCE_REVIEW_THRESHOLD = 0.6
VERY_SHORT_TRANSCRIPT_WORDS = 6
UNCLEAR_TRANSCRIPT_MARKERS = (
    "[inaudible",
    "(inaudible",
    "inaudible",
    "[unclear",
    "(unclear",
    "unclear",
    "unintelligible",
    "can't hear",
    "cannot hear",
    "audio unclear",
    "background noise",
)
TRANSCRIPT_UNAVAILABLE_MARKERS = (
    "no speech detected",
    "transcript unavailable",
    "transcription unavailable",
    "could not transcribe",
    "unable to transcribe",
)


class AutoGradingError(RuntimeError):
    """Raised when a saved response cannot be graded."""


def grade_saved_response(session: Session, response_id: str) -> GradingResult:
    """
    Grade one already-saved Response and persist a GradingResult.

    This function intentionally does not update Response.grade. That field stays
    reserved for instructor-approved final grades.
    """

    response = session.get(Response, response_id)
    if not response:
        raise ValueError(f"Response not found: {response_id}")

    model_name = _resolve_model_name()
    grader_version = _build_grader_version(model_name)

    try:
        assignment = session.get(Assignment, response.assignment_id)
        if not assignment:
            raise AutoGradingError(
                f"Assignment not found for response {response.id}: {response.assignment_id}"
            )

        questions = _normalize_questions(assignment.questions)
        if not questions:
            raise AutoGradingError(
                f"Assignment {assignment.id} does not contain gradable questions."
            )

        answers = _safe_dict(response.answers)
        transcripts = _safe_dict(response.transcripts)

        question_results: list[dict[str, Any]] = []
        ai_items: list[dict[str, Any]] = []
        total_possible = 0.0

        for index, question in enumerate(questions, start=1):
            normalized = _normalize_question(question)
            if not normalized["id"]:
                normalized["id"] = f"q{index}"
            question_id = normalized["id"]
            question_type = normalized["type"]
            points_possible = normalized["points_possible"]
            total_possible += points_possible

            if question_type in {"multiple", "multiple_choice", "mcq"}:
                question_results.append(
                    _grade_multiple_choice(normalized, answers.get(question_id))
                )
                continue

            if question_type == "oral":
                transcript_text = _as_text(transcripts.get(question_id))
                answer_text = transcript_text or _as_text(answers.get(question_id))
                source = "transcript"
            else:
                transcript_text = ""
                answer_text = _as_text(answers.get(question_id))
                source = "answer"

            ai_items.append(
                {
                    **normalized,
                    "answer_text": answer_text,
                    "transcript_text": transcript_text,
                    "source": source,
                }
            )

        if ai_items:
            if not os.getenv("OPENAI_API_KEY"):
                return _save_failed_with_partial_results(
                    session=session,
                    response_id=response.id,
                    grader_version=grader_version,
                    max_score=total_possible,
                    question_results=question_results,
                    ai_items=ai_items,
                    error_message=(
                        "OPENAI_API_KEY is not configured; AI grading for short-answer "
                        "and oral-transcript questions was skipped."
                    ),
                )

            try:
                ai_results, ai_summary = _grade_with_openai(ai_items, model_name)
            except Exception as exc:  # noqa: BLE001 - record failed result for review
                return _save_failed_with_partial_results(
                    session=session,
                    response_id=response.id,
                    grader_version=grader_version,
                    max_score=total_possible,
                    question_results=question_results,
                    ai_items=ai_items,
                    error_message=str(exc),
                )

            question_results.extend(ai_results)
            summary_feedback = ai_summary
        else:
            summary_feedback = "Deterministic grading completed."
            grader_version = _build_grader_version("deterministic")

        total_score = _sum_scores(question_results)
        percentage = _percentage(total_score, total_possible)

        return _save_grading_result(
            session=session,
            response_id=response.id,
            status="completed",
            total_score=total_score,
            max_score=total_possible,
            percentage=percentage,
            question_results=question_results,
            summary_feedback=summary_feedback,
            error_message=None,
            grader_version=grader_version,
        )

    except Exception as exc:  # noqa: BLE001 - preserve submission and record failure
        logger.exception("Automatic grading failed for response %s", response_id)
        session.rollback()
        return _save_grading_result(
            session=session,
            response_id=response.id,
            status="failed",
            total_score=None,
            max_score=None,
            percentage=None,
            question_results=[],
            summary_feedback=None,
            error_message=str(exc),
            grader_version=grader_version,
        )


def _grade_multiple_choice(
    question: dict[str, Any],
    submitted_answer: Any,
) -> dict[str, Any]:
    points_possible = question["points_possible"]
    correct_answer = _resolve_correct_answer(question)
    submitted_text = _as_text(submitted_answer)

    if correct_answer is None:
        return {
            "question_id": question["id"],
            "question_type": question["type"],
            "points_possible": points_possible,
            "auto_score": 0.0,
            "feedback": "No correct answer is configured for this multiple-choice question.",
            "source": "multiple_choice",
            "grading_method": "deterministic",
            "needs_review": True,
        }

    is_correct = _normalize_answer(submitted_text) == _normalize_answer(correct_answer)
    return {
        "question_id": question["id"],
        "question_type": question["type"],
        "points_possible": points_possible,
        "auto_score": points_possible if is_correct else 0.0,
        "feedback": "Correct." if is_correct else "Incorrect.",
        "source": "multiple_choice",
        "grading_method": "deterministic",
        "expected_answer": correct_answer,
    }


def _save_failed_with_partial_results(
    *,
    session: Session,
    response_id: str,
    grader_version: str,
    max_score: float,
    question_results: list[dict[str, Any]],
    ai_items: list[dict[str, Any]],
    error_message: str,
) -> GradingResult:
    failed_results = [
        *question_results,
        *[_ungraded_ai_result(item, error_message) for item in ai_items],
    ]
    return _save_grading_result(
        session=session,
        response_id=response_id,
        status="failed",
        total_score=None,
        max_score=max_score,
        percentage=None,
        question_results=failed_results,
        summary_feedback=None,
        error_message=error_message,
        grader_version=grader_version,
    )


def _ungraded_ai_result(item: dict[str, Any], error_message: str) -> dict[str, Any]:
    return {
        "question_id": item["id"],
        "question_type": item["type"],
        "points_possible": item["points_possible"],
        "auto_score": None,
        "feedback": error_message,
        "strengths": "",
        "missing_points": "Automatic grading could not be completed for this question.",
        "confidence": 0.0,
        "source": item["source"],
        "grading_method": "ai",
        "needs_review": True,
        "transcript_quality_flags": _transcript_quality_flags(item),
    }


def _grade_with_openai(
    ai_items: list[dict[str, Any]],
    model_name: str,
) -> tuple[list[dict[str, Any]], str]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    transcript_quality_by_id = {
        item["id"]: _transcript_quality_flags(item)
        for item in ai_items
    }
    payload = [
        {
            "question_id": item["id"],
            "question_type": item["type"],
            "prompt": item["text"],
            "points_possible": item["points_possible"],
            "student_answer": item["answer_text"],
            "source": item["source"],
            "transcript_quality_notes": transcript_quality_by_id[item["id"]],
            # Teacher-authored guidance belongs here. Rubric is the main source
            # for partial credit; expected_answer gives the model an anchor.
            "rubric": item.get("rubric"),
            "expected_answer": item.get("expected_answer"),
        }
        for item in ai_items
    ]

    try:
        completion = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful instructor grading saved student answers for an LMS. "
                        "Grade only from the evidence provided. Evaluate correctness, "
                        "completeness, reasoning quality, rubric adherence, and expected answer "
                        "alignment. Use this precedence: first rubric criteria, then "
                        "expected_answer, then the question prompt. Treat expected_answer as a "
                        "target concept, not a requirement for identical wording. Award partial "
                        "credit proportional to demonstrated evidence and keep every auto_score "
                        "between 0 and points_possible. Do not give credit for unsupported or "
                        "contradictory claims. For oral/transcript answers, grade the available "
                        "content without penalizing accent or speech style, but lower confidence "
                        "when transcript_quality_notes indicate an empty, very short, unclear, "
                        "or suspicious transcript. If there is no gradable student content, the "
                        "score should usually be 0 and confidence should be low. "
                        "Confidence means reliability of the automatic grade, not student "
                        "performance. Return only one JSON object with keys `results` and "
                        "`summary_feedback`. Each result must have exactly these grading keys: "
                        "`question_id`, `auto_score`, `feedback`, `strengths`, "
                        "`missing_points`, and `confidence`. `confidence` must be a number "
                        "from 0 to 1. Use confidence below 0.6 when the answer is ambiguous, "
                        "the transcript is weak, or the grading guidance is insufficient. "
                        "Do not include Markdown, code fences, or extra prose."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"questions": payload}, ensure_ascii=True),
                },
            ],
        )
    except OpenAIError as exc:
        raise AutoGradingError(f"OpenAI grading request failed: {exc}") from exc

    content = completion.choices[0].message.content if completion.choices else ""
    parsed = _parse_json_object(content)
    raw_results = parsed.get("results", [])
    if not isinstance(raw_results, list):
        raise AutoGradingError("AI grading response did not contain a results list.")

    by_question_id = {
        _as_text(result.get("question_id")): result
        for result in raw_results
        if isinstance(result, dict)
    }

    results: list[dict[str, Any]] = []
    for item in ai_items:
        raw = by_question_id.get(item["id"], {})
        score = _clamp_score(raw.get("auto_score"), item["points_possible"])
        transcript_quality_flags = transcript_quality_by_id[item["id"]]
        confidence = _clamp_confidence(raw.get("confidence"))
        confidence = _adjust_confidence(
            confidence=confidence,
            item=item,
            transcript_quality_flags=transcript_quality_flags,
        )
        needs_review = confidence < CONFIDENCE_REVIEW_THRESHOLD
        results.append(
            {
                "question_id": item["id"],
                "question_type": item["type"],
                "points_possible": item["points_possible"],
                "auto_score": score,
                "feedback": _as_text(raw.get("feedback")) or "AI grading completed.",
                "strengths": _as_text(raw.get("strengths")),
                "missing_points": _as_text(raw.get("missing_points")),
                "confidence": confidence,
                "needs_review": needs_review,
                "source": item["source"],
                "grading_method": "ai",
                "model": model_name,
                "transcript_quality_flags": transcript_quality_flags,
            }
        )

    summary_feedback = _as_text(parsed.get("summary_feedback")) or "AI grading completed."
    return results, summary_feedback


def _save_grading_result(
    *,
    session: Session,
    response_id: str,
    status: str,
    total_score: float | None,
    max_score: float | None,
    percentage: float | None,
    question_results: list[dict[str, Any]],
    summary_feedback: str | None,
    error_message: str | None,
    grader_version: str,
) -> GradingResult:
    now = datetime.utcnow()
    result = session.exec(
        select(GradingResult).where(GradingResult.response_id == response_id)
    ).first()

    if not result:
        result = GradingResult(response_id=response_id)

    result.status = status
    result.total_score = total_score
    result.max_score = max_score
    result.percentage = percentage
    result.question_results = question_results
    result.summary_feedback = summary_feedback
    result.error_message = error_message
    result.grader_version = grader_version
    result.updated_at = now
    result.reviewed_at = None
    result.approved_at = None
    result.approved_score = None
    result.approved_by = None

    session.add(result)
    session.commit()
    session.refresh(result)
    return result


def _normalize_questions(raw_questions: Any) -> list[dict[str, Any]]:
    if isinstance(raw_questions, list):
        return [q for q in raw_questions if isinstance(q, dict)]
    if isinstance(raw_questions, dict):
        nested = raw_questions.get("questions")
        if isinstance(nested, list):
            return [q for q in nested if isinstance(q, dict)]
        return [raw_questions]
    return []


def _normalize_question(question: dict[str, Any]) -> dict[str, Any]:
    question_id = _as_text(question.get("id")) or _as_text(question.get("question_id"))
    question_type = (_as_text(question.get("type")) or "short").lower()
    points_possible = _as_float(
        _first_present(
            question.get("points"),
            question.get("max_points"),
            question.get("maxPoints"),
        ),
        default=1.0,
    )

    return {
        **question,
        "id": question_id,
        "type": question_type,
        "text": _as_text(question.get("text") or question.get("prompt")),
        "points_possible": points_possible,
        "rubric": _first_text(
            question.get("rubric"),
            question.get("gradingRubric"),
            question.get("criteria"),
        ),
        "expected_answer": _first_text(
            question.get("expectedAnswer"),
            question.get("expected_answer"),
            question.get("sampleAnswer"),
            question.get("answer"),
            question.get("correctAnswer"),
        ),
    }


def _resolve_correct_answer(question: dict[str, Any]) -> str | None:
    explicit = _first_text(
        question.get("correctAnswer"),
        question.get("correct_answer"),
        question.get("answer"),
    )
    if explicit:
        return explicit

    correct_index = question.get("correctOption")
    options = question.get("options")
    if isinstance(correct_index, int) and isinstance(options, list):
        if 0 <= correct_index < len(options):
            return _as_text(options[correct_index])
    return None


def _transcript_quality_flags(item: dict[str, Any]) -> list[str]:
    if item.get("source") != "transcript" and item.get("type") != "oral":
        return []

    transcript_text = _as_text(item.get("transcript_text"))
    if not transcript_text:
        return ["empty transcript"]

    flags: list[str] = []
    normalized = transcript_text.casefold()
    words = _words(transcript_text)

    if any(marker in normalized for marker in TRANSCRIPT_UNAVAILABLE_MARKERS):
        flags.append("transcription unavailable marker")
    if len(words) < VERY_SHORT_TRANSCRIPT_WORDS:
        flags.append("very short transcript")
    if any(marker in normalized for marker in UNCLEAR_TRANSCRIPT_MARKERS):
        flags.append("unclear transcript markers")
    if "??" in transcript_text or transcript_text.count("?") >= 3:
        flags.append("uncertain transcript text")
    if len(words) >= 8:
        unique_words = {word for word in words if word}
        if unique_words and len(unique_words) / len(words) < 0.35:
            flags.append("highly repetitive transcript")

    return flags


def _adjust_confidence(
    *,
    confidence: float,
    item: dict[str, Any],
    transcript_quality_flags: list[str],
) -> float:
    adjusted = confidence

    if not _as_text(item.get("answer_text")):
        adjusted = min(adjusted, 0.1)
    if not item.get("rubric") and not item.get("expected_answer"):
        adjusted = min(adjusted, 0.85)

    flag_caps = {
        "empty transcript": 0.1,
        "transcription unavailable marker": 0.15,
        "very short transcript": 0.45,
        "unclear transcript markers": 0.5,
        "uncertain transcript text": 0.55,
        "highly repetitive transcript": 0.55,
    }
    for flag in transcript_quality_flags:
        cap = flag_caps.get(flag)
        if cap is not None:
            adjusted = min(adjusted, cap)

    return round(adjusted, 2)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("answer", "transcript", "value", "text"):
            text = _as_text(value.get(key))
            if text:
                return text
    return ""


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _as_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _normalize_answer(value: Any) -> str:
    return " ".join(_as_text(value).casefold().split())


def _words(value: str) -> list[str]:
    return [
        word.strip(".,!?;:()[]{}\"'").casefold()
        for word in value.split()
        if word.strip(".,!?;:()[]{}\"'")
    ]


def _clamp_score(value: Any, points_possible: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(points_possible, score))


def _clamp_confidence(value: Any, *, default: float = 0.5) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return round(max(0.0, min(1.0, confidence)), 2)


def _sum_scores(question_results: list[dict[str, Any]]) -> float:
    total = 0.0
    for result in question_results:
        points_possible = _as_float(result.get("points_possible"), default=0.0)
        total += _clamp_score(result.get("auto_score"), points_possible)
    return round(total, 2)


def _percentage(total_score: float, max_score: float) -> float | None:
    if max_score <= 0:
        return None
    return round((total_score / max_score) * 100, 2)


def _parse_json_object(content: str | None) -> dict[str, Any]:
    if not content:
        raise AutoGradingError("AI grading response was empty.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AutoGradingError("AI grading response was not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise AutoGradingError("AI grading response must be a JSON object.")
    return parsed


def _resolve_model_name() -> str:
    for key in GRADING_MODEL_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value.strip()
    return DEFAULT_GRADING_MODEL


def _build_grader_version(model_name: str) -> str:
    return f"{GRADER_VERSION}:{model_name}"
