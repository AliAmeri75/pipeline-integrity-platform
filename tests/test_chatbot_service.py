import unittest

from chatbot_service import (
    MAX_USER_CHARACTERS,
    assistant_instructions,
    generate_assistant_reply,
    suggest_routes,
)


class _FakeResponse:
    output_text = "Use [Preliminary Analysis](/preliminary-analysis)."


class _FakeResponses:
    def __init__(self):
        self.arguments = None

    def create(self, **kwargs):
        self.arguments = kwargs
        return _FakeResponse()


class _FakeClient:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.responses = _FakeResponses()


class ChatbotServiceTests(unittest.TestCase):
    def test_route_suggestion_points_pof_question_to_preliminary_analysis(self):
        routes = suggest_routes("Where can I estimate POF and FPR for a crack profile?")
        self.assertEqual(routes[0]["path"], "/preliminary-analysis")

    def test_prompt_contains_boundaries_and_approved_routes(self):
        instructions = assistant_instructions()
        self.assertIn("not an engineering approval authority", instructions)
        self.assertIn("/data-integration", instructions)
        self.assertIn("/inspection", instructions)
        self.assertIn("under construction", instructions)

    def test_responses_api_receives_scoped_settings(self):
        created_clients = []

        def factory(**kwargs):
            client = _FakeClient(**kwargs)
            created_clients.append(client)
            return client

        answer = generate_assistant_reply(
            [{"role": "user", "content": "What is FPR?"}],
            api_key="test-key",
            model="test-model",
            client_factory=factory,
        )

        self.assertIn("Preliminary Analysis", answer)
        client = created_clients[0]
        self.assertEqual(client.responses.arguments["model"], "test-model")
        self.assertFalse(client.responses.arguments["store"])
        self.assertEqual(client.responses.arguments["max_output_tokens"], 500)

    def test_long_question_is_rejected_before_api_call(self):
        with self.assertRaisesRegex(ValueError, "below"):
            generate_assistant_reply(
                [{"role": "user", "content": "x" * (MAX_USER_CHARACTERS + 1)}],
                api_key="test-key",
                client_factory=lambda **_: _FakeClient(),
            )


if __name__ == "__main__":
    unittest.main()
