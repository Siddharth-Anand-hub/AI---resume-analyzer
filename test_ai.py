import unittest
from unittest.mock import Mock, patch

import ai

STRONG = """Priya Sharma
priya@example.com | +91 98765 43210 | linkedin.com/in/priya | github.com/priya
Summary
Backend engineer with 5 years building scalable APIs.
Experience
Senior Backend Engineer, FinCo  Jan 2021 - Present
- Built REST APIs in Python and Flask serving 2M requests/day
- Reduced query latency by 45% by redesigning PostgreSQL schema
- Deployed services with Docker and GitHub Actions CI/CD
Education
B.Tech Computer Science, 2019
Skills
Python, SQL, Docker, Redis, Git, AWS
"""
WEAK = "Responsible for helping with web stuff. Worked on websites. Hard working team player. I know HTML."


class ResumeAnalysisTests(unittest.TestCase):
    def test_every_role_skill_exists_in_taxonomy(self):
        for role, data in ai.ROLES.items():
            for skill in data["skills"]:
                self.assertIn(skill, ai.SKILLS, f"{skill} used by {role}")

    def test_different_resumes_give_different_results(self):
        a = ai._build_local_analysis(STRONG, "Backend Developer")
        b = ai._build_local_analysis(WEAK, "Backend Developer")
        self.assertGreater(a["score"], b["score"] + 30)
        self.assertNotEqual(a["skills"], b["skills"])
        self.assertNotEqual(a["interview_questions"], b["interview_questions"])
        self.assertNotEqual(a["improvements"], b["improvements"])

    def test_same_resume_different_role_changes_result(self):
        backend = ai._build_local_analysis(STRONG, "Backend Developer")
        designer = ai._build_local_analysis(STRONG, "UX Designer")
        self.assertEqual(backend["role"], "Backend Developer")
        self.assertEqual(designer["role"], "UX / Product Designer")
        self.assertGreater(backend["score"], designer["score"])

    def test_specific_role_beats_generic_developer_match(self):
        self.assertEqual(ai._select_role("Backend Developer"), "Backend Developer")
        self.assertEqual(ai._select_role("Python developer"), "Backend Developer")
        self.assertEqual(ai._select_role("developer"), "Software Engineer")

    def test_unknown_goal_falls_back_to_closest_profile(self):
        result = ai._build_local_analysis(STRONG, "Chief Happiness Officer")
        self.assertFalse(result["role_recognized"])
        self.assertIn("closest profile", result["summary"])

    def test_roadmap_only_covers_missing_skills(self):
        result = ai._build_local_analysis(STRONG, "Backend Developer")
        roadmap_skills = {r["skill"] for r in result["roadmap_detailed"]}
        self.assertTrue(roadmap_skills.issubset(set(result["missing_skills"])))
        self.assertFalse(roadmap_skills & set(result["skills"]))

    def test_questions_reference_resume_content(self):
        result = ai._build_local_analysis(STRONG, "Backend Developer")
        joined = " ".join(result["interview_questions"])
        self.assertTrue("REST APIs" in joined or "Python" in joined or "SQL" in joined)

    def test_score_is_bounded_and_empty_resume_is_low(self):
        self.assertTrue(0 <= ai._build_local_analysis(STRONG, "Backend Developer")["score"] <= 100)
        self.assertLessEqual(ai._build_local_analysis("hello", "Backend Developer")["score"], 20)

    def test_experience_years_from_date_ranges(self):
        self.assertGreaterEqual(ai._experience_years("Engineer Jan 2018 - Dec 2021"), 3)
        self.assertEqual(ai._experience_years("nothing here"), 0)

    def test_no_api_key_returns_local_result(self):
        with patch.object(ai, "client", None):
            result = ai.analyze_resume(STRONG, "Backend Developer")
        self.assertEqual(result["source"], "local")
        self.assertNotIn("error", result)

    def test_ai_response_is_merged_with_local_facts(self):
        response = Mock()
        response.choices = [Mock(message=Mock(content=(
            '{"summary": "Solid backend profile.", "strengths": ["Good APIs"],'
            ' "improvements": [{"priority": "High", "title": "Add Kubernetes", "detail": "x"}],'
            ' "roadmap": [{"skill": "Kubernetes", "priority": "Important", "weeks": 3, "action": "Deploy"}],'
            ' "interview_questions": ["Tell me about FinCo."]}'
        )))]
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = response
        with patch.object(ai, "client", mock_client):
            result = ai.analyze_resume(STRONG, "Backend Developer")
        self.assertEqual(result["source"], "ai")
        self.assertEqual(result["summary"], "Solid backend profile.")
        self.assertEqual(result["interview_questions"], ["Tell me about FinCo."])
        self.assertIn("score", result)  # numeric facts still come from the local engine

    def test_ai_failure_falls_back_with_notice(self):
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = ai.OpenAIError("quota exceeded")
        with patch.object(ai, "client", mock_client):
            result = ai.analyze_resume(STRONG, "Backend Developer")
        self.assertEqual(result["source"], "local")
        self.assertIn("quota exceeded", result["error"])
        self.assertTrue(result["skills"])


if __name__ == "__main__":
    unittest.main()
