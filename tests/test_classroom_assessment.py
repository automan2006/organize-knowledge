"""Synthetic classroom cases: local only; never writes real course data."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from test_github_archive import FakeGitHub, archive_module

SCRIPT = (Path(__file__).resolve().parents[1] / 'plugins/organize-knowledge/skills/'
          'classroom-knowledge-check/scripts/assessment.py')
spec = importlib.util.spec_from_file_location('assessment', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    prompts = ['Define displacement.', 'Define velocity.', 'Distinguish speed from velocity.',
               'Find velocity for 20 metres in 4 seconds.',
               'Find displacement at 3 metres per second for 2 seconds.']
    solutions = ['Change in position.', 'Rate of displacement.',
                 'Speed is scalar; velocity is a vector.', '5 m/s', '6 m']
    quiz = {'lesson_key': 'SYNTHETIC mechanics lesson', 'questions': []}
    for i, (points, minutes) in enumerate(zip([15, 15, 20, 25, 25], [1, 1, 2, 3, 3])):
        quiz['questions'].append({'id': 'Q' + str(i + 1), 'prompt': prompts[i],
                                 'points': points, 'minutes': minutes, 'core': i in (2, 3),
                                 'knowledge_point': 'SYNTHETIC kinematics',
                                 'answer': solutions[i], 'rubric': 'PRIVATE-GRADING-KEY'})
    grades = {q['id']: {'answer': q['answer'], 'score': q['points']} for q in quiz['questions']}
    return quiz, grades


class ClassroomAssessment(unittest.TestCase):
    def setUp(self):
        self.quiz, self.grades = fixture()

    def test_classroom_only_and_explicit_skip(self):
        self.assertTrue(module.should_offer('course', 'organized'))
        for kind in ['knowledge', 'reading', 'handwritten']:
            self.assertFalse(module.should_offer(kind, 'organized'))
        for action in ['preview', 'update_plugin', 'ocr']:
            self.assertFalse(module.should_offer('course', action))
        self.assertFalse(module.should_offer('course', 'organized', skip=True))
        self.assertFalse(module.should_offer('course', 'organized', already_offered=True))

    def test_paper_does_not_disclose_answers(self):
        projected = module.paper(self.quiz)
        for q in projected['questions']:
            self.assertNotIn('answer', q)
            self.assertNotIn('rubric', q)
        self.assertNotIn('PRIVATE-GRADING-KEY', json.dumps(projected))
        self.assertEqual(sum(q['minutes'] for q in projected['questions']), 10)

    def test_id_stable_and_retest_distinct(self):
        first = module.paper(self.quiz)['quiz_id']
        self.quiz['questions'][0]['answer'] = 'Equivalent revised rubric'
        self.assertEqual(module.paper(self.quiz)['quiz_id'], first)
        self.quiz['questions'][0]['prompt'] = 'New transfer problem'
        self.assertNotEqual(module.paper(self.quiz)['quiz_id'], first)

    def test_partial_answers_not_graded(self):
        result = module.evaluate(self.quiz, {'Q1': self.grades['Q1']})
        self.assertEqual(result['status'], 'awaiting_answers')
        self.assertIsNone(result['score'])
        self.assertIsNone(result['passed'])

    def test_explicit_handover_leaves_blank_unverified(self):
        result = module.evaluate(self.quiz, {'Q1': self.grades['Q1']}, submitted=True)
        self.assertEqual(result['score'], 15)
        self.assertEqual(result['questions'][1]['status'], 'unanswered_unverified')

    def test_ocr_pending_prevents_final_grade(self):
        self.grades['Q4']['ocr_pending'] = True
        result = module.evaluate(self.quiz, self.grades, True)
        self.assertEqual(result['status'], 'awaiting_confirmation')
        self.assertIsNone(result['score'])

    def test_exact_eighty_with_core_thresholds_passes(self):
        for q in self.quiz['questions']:
            self.grades[q['id']]['score'] = q['points'] * 0.8
        result = module.evaluate(self.quiz, self.grades, True)
        self.assertEqual(result['score'], 80)
        self.assertTrue(result['passed'])

    def test_high_total_cannot_hide_failed_core(self):
        self.grades['Q3']['score'] = 15
        result = module.evaluate(self.quiz, self.grades, True)
        self.assertEqual(result['score'], 95)
        self.assertFalse(result['passed'])

    def test_critical_error_and_assistance_block_pass(self):
        for flag in ['critical_error', 'assisted']:
            grades = copy.deepcopy(self.grades)
            grades['Q1'][flag] = True
            self.assertFalse(module.evaluate(self.quiz, grades, True)['passed'])

    def test_bad_marks_are_rejected(self):
        for mark in [-1, 16, float('nan'), float('inf'), True]:
            self.grades['Q1']['score'] = mark
            with self.assertRaises(ValueError):
                module.evaluate(self.quiz, self.grades, True)

    def test_core_flags_cannot_be_missing_or_faked(self):
        self.quiz['questions'][0]['core'] = True
        with self.assertRaises(ValueError):
            module.paper(self.quiz)

    def test_synthetic_report_duplicate_and_github_failure(self):
        result = module.evaluate(self.quiz, self.grades, True)
        # Local draft includes verbatim answers and solutions only after submission.
        draft = ('---\ntitle: "SYNTHETIC classroom assessment"\n'
                 'related_candidates: ["velocity"]\nquiz_id: ' + result['quiz_id'] +
                 '\n---\n' + json.dumps({'quiz': self.quiz, 'answers': self.grades,
                                          'result': result}, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'record.md'
            source.write_text(draft, encoding='utf-8')
            manifest = {'repository': 'example/private-notes', 'files': [
                {'file': str(source), 'path': 'courses/SYNTHETIC/assessment/round1.md'}]}
            api = FakeGitHub()
            archive_module.archive(manifest, api=api)
            puts = len(api.puts)
            archive_module.archive(manifest, api=api)
            self.assertEqual(len(api.puts), puts)
            self.assertEqual(api.files['courses/SYNTHETIC/assessment/round1.md'], source.read_bytes())
            failed_api = FakeGitHub()
            failed_api.failure = 'permission'
            archive_module.archive(manifest, api=failed_api)
            self.assertTrue(result['passed'])  # Feedback unaffected by upload failure.
            self.assertTrue(source.exists())
