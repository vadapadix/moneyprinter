import unittest
from unittest import mock

from app.models.schema import VideoParams
from app.services import task


class TaskTermsTest(unittest.TestCase):
    def test_generate_terms_falls_back_when_llm_hits_quota(self):
        params = VideoParams(
            video_subject="Marilyn Monroe mystery",
            news_query="Marilyn Monroe",
        )

        with mock.patch.object(task.llm, "generate_terms", return_value="Error: 429 quota exceeded"):
            terms = task.generate_terms(
                task_id="task-1",
                params=params,
                video_script="Marilyn Monroe remains the focus of a mystery around the night of her death.",
            )

        self.assertIsInstance(terms, list)
        self.assertNotIn("Error:", " ".join(terms))
        self.assertTrue(any("marilyn" in term.lower() for term in terms))


if __name__ == "__main__":
    unittest.main()
