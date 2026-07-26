import unittest

from shared.rendering import json_to_html


class RenderingTests(unittest.TestCase):
    def test_zero_candidate_distribution_does_not_fail_search_rendering(self):
        result = {
            "Name": "IN Example",
            "Grade distribution": {
                "1.0": "0",
                "5.0": "0",
            },
        }

        html = json_to_html(result, query="IN")

        self.assertIn('<span class="highlight">IN</span> Example', html)
        self.assertIn("0.0%", html)
        self.assertIn(">0.0</td>", html)


if __name__ == "__main__":
    unittest.main()
