import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import report


class ExtensionTaskTests(unittest.TestCase):
    def test_retry_constants_are_imported_from_practice3(self) -> None:
        self.assertEqual(report.practice3_retry.MAX_ATTEMPTS, 3)
        self.assertEqual(report.practice3_retry.BACKOFF_SECONDS, 0.05)

    def test_retry_succeeds_on_third_attempt(self) -> None:
        state = {"attempts": 0}

        def flaky_task() -> str:
            state["attempts"] += 1
            if state["attempts"] < 3:
                raise RuntimeError("temporary failure")
            return "ok"

        with patch.object(report.time, "sleep") as sleep:
            result = report.retry(flaky_task, 3, 2, "테스트")

        self.assertEqual(result, "ok")
        self.assertEqual(state["attempts"], 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

    def test_total2_chart_is_embedded_as_fragment(self) -> None:
        chart_html = report.create_total2_chart_html()

        self.assertIn("Plotly.newPlot", chart_html)
        self.assertIn('"type":"box"', chart_html)
        self.assertIn(r"\uc774\ud0c8 \uc5ec\ubd80", chart_html)
        self.assertNotIn("<html>", chart_html.lower())

    def test_email_uses_configured_recipient_and_html_attachment(self) -> None:
        smtp_class = MagicMock()
        smtp_client = smtp_class.return_value.__enter__.return_value
        environment = {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@test.com",
            "SMTP_PASSWORD": "secret",
            "SMTP_FROM": "sender@test.com",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
        }

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.html"
            report_path.write_text("<html><body>report</body></html>", encoding="utf-8")

            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(report.smtplib, "SMTP", smtp_class),
            ):
                result = report.send_email_notification(report_path)

        message = smtp_client.send_message.call_args.args[0]
        attachments = list(message.iter_attachments())
        self.assertTrue(result)
        self.assertEqual(message["To"], "hideonbush@faker.com")
        self.assertEqual(attachments[0].get_content_type(), "text/html")
        smtp_client.starttls.assert_called_once()
        smtp_client.login.assert_called_once_with("sender@test.com", "secret")


if __name__ == "__main__":
    unittest.main()
