"""Offline quiz projection and score validation; no semantic grading or uploads."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def should_offer(content_type, action, skip=False, already_offered=False):
    return (content_type == 'course' and action == 'organized'
            and not skip and not already_offered)


def validate_quiz(quiz):
    questions = quiz['questions']
    if (len(questions) != 5 or [q['id'] for q in questions] != ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
            or [q['points'] for q in questions] != [15, 15, 20, 25, 25]
            or [q['minutes'] for q in questions] != [1, 1, 2, 3, 3]):
        raise ValueError('Expected the five-question, 100-point, ten-minute paper')
    for q in questions:
        if type(q['core']) is not bool or not q['prompt'].strip() or not q['knowledge_point'].strip():
            raise ValueError('Each question needs a prompt, knowledge point and boolean core flag')
    if sum(q['core'] for q in questions) != 2 or not quiz['lesson_key'].strip():
        raise ValueError('Exactly two preselected core questions and a real lesson key required')
    return questions


def paper(quiz):
    questions = validate_quiz(quiz)
    # Explicit allowlist: never output embedded rubrics/answers or arbitrary metadata.
    public = [{key: q[key] for key in ['id', 'prompt', 'points', 'minutes', 'knowledge_point', 'core']}
              for q in questions]
    payload = {'lesson_key': quiz['lesson_key'], 'questions': public}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                      separators=(',', ':')).encode()).hexdigest()[:20]
    return dict(payload, quiz_id='quiz-' + digest, status='awaiting_answers')


def evaluate(quiz, grades, submitted=False):
    questions = validate_quiz(quiz)
    ids = {q['id'] for q in questions}
    if not isinstance(grades, dict) or set(grades) - ids:
        raise ValueError('Unexpected answer ID')
    if type(submitted) is not bool:
        raise ValueError('submitted must be boolean')
    result = {'quiz_id': paper(quiz)['quiz_id'], 'score': None, 'passed': None,
              'status': 'awaiting_answers', 'questions': []}
    if not submitted:
        return result
    total = 0
    cores = True
    critical = False
    assisted = False
    for q in questions:
        row = grades.get(q['id']) or {}
        if type(row) is not dict:
            raise ValueError('Expected a grade record')
        for flag in ['ocr_pending', 'critical_error', 'assisted']:
            if flag in row and type(row[flag]) is not bool:
                raise ValueError('Grade flags must be boolean')
        if row.get('ocr_pending'):
            result.update(status='awaiting_confirmation')
            return result
        answer = row.get('answer')
        unanswered = answer is None or (isinstance(answer, str) and not answer.strip())
        if not unanswered and not isinstance(answer, str):
            raise ValueError('Answer must be a verbatim string')
        if unanswered:
            if row.get('score', 0) != 0:
                raise ValueError('Unanswered question cannot receive points')
            score, status = 0, 'unanswered_unverified'
        else:
            score = row.get('score')
            if (type(score) not in (int, float) or not math.isfinite(score)
                    or not 0 <= score <= q['points']):
                raise ValueError('Grade must be finite and within question points')
            status = 'correct' if score == q['points'] else 'partial' if score else 'incorrect'
        total += score
        critical |= row.get('critical_error', False)
        assisted |= row.get('assisted', False)
        if q['core'] and score < q['points'] * 0.8:
            cores = False
        result['questions'].append({'id': q['id'], 'score': score, 'status': status})
    result.update(score=total, passed=total >= 80 and cores and not critical and not assisted,
                  core_threshold_passed=cores, critical_error=critical, assisted=assisted,
                  status='assisted_completed' if assisted else 'graded')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Local JSON with quiz, grades, submitted')
    parser.add_argument('--mode', choices=['paper', 'grade'], default='paper')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    result = paper(data['quiz']) if args.mode == 'paper' else evaluate(
        data['quiz'], data.get('grades', {}), data.get('submitted', False))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
