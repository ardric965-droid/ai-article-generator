import json
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from generator.services.llm_service import (
    LLMConfigurationError,
    LLMRequestError,
    LLMTemporaryError,
    build_prompt,
    call_groq_chat_completion,
    generate_article,
)


class BuildPromptTests(SimpleTestCase):
    def test_build_prompt_includes_title_and_description(self):
        prompt = build_prompt('My Title', 'My Description')

        self.assertIn('Title: My Title', prompt)
        self.assertIn('Description: My Description', prompt)
        self.assertIn('Return only the article text.', prompt)


class GenerateArticleTests(SimpleTestCase):
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_returns_api_content(self, mock_call):
        mock_call.return_value = 'Generated article body.'

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description')

        self.assertEqual(article, 'Generated article body.')
        mock_call.assert_called_once()
        messages = mock_call.call_args.kwargs['messages']
        self.assertEqual(messages[1]['content'], build_prompt('Title', 'Description'))

    def test_generate_article_requires_api_key(self):
        with patch.dict('os.environ', {'LLM_API_KEY': ''}, clear=False):
            with self.assertRaisesMessage(
                LLMConfigurationError,
                'LLM_API_KEY is missing. Add your Groq API key to the .env file.',
            ):
                generate_article('Title', 'Description')

    @patch('generator.services.llm_service.time.sleep')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_retries_temporary_failures(
        self,
        mock_call,
        mock_sleep,
    ):
        mock_call.side_effect = [
            LLMTemporaryError('temporary outage'),
            LLMTemporaryError('still down'),
            'Recovered article.',
        ]

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description', max_retries=3)

        self.assertEqual(article, 'Recovered article.')
        self.assertEqual(mock_call.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('generator.services.llm_service.time.sleep')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_raises_after_max_retries(
        self,
        mock_call,
        mock_sleep,
    ):
        mock_call.side_effect = LLMTemporaryError('service unavailable')

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description', max_retries=2)

        self.assertIn('Failed to generate article after 2 attempts', str(context.exception))
        self.assertEqual(mock_call.call_count, 2)
        mock_sleep.assert_called_once()


class CallGroqChatCompletionTests(SimpleTestCase):
    def _mock_response(self, *, status: int, payload: dict | str):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        response = BytesIO(body.encode('utf-8'))
        response.getcode = lambda: status
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    @patch('generator.services.llm_service.urllib.request.urlopen')
    def test_call_groq_chat_completion_parses_success_response(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response(
            status=200,
            payload={
                'choices': [
                    {'message': {'content': '  Article text.  '}},
                ],
            },
        )

        article = call_groq_chat_completion(
            api_key='test-key',
            messages=[{'role': 'user', 'content': 'Prompt'}],
        )

        self.assertEqual(article, 'Article text.')

    @patch('generator.services.llm_service.urllib.request.urlopen')
    def test_call_groq_chat_completion_sends_user_agent(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_response(
            status=200,
            payload={'choices': [{'message': {'content': 'ok'}}]},
        )

        call_groq_chat_completion(
            api_key='test-key',
            messages=[{'role': 'user', 'content': 'Prompt'}],
        )

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'), 'ai-article-generator/1.0')

    @patch('generator.services.llm_service.urllib.request.urlopen')
    def test_call_groq_chat_completion_raises_temporary_error_for_429(
        self,
        mock_urlopen,
    ):
        import urllib.error

        error = urllib.error.HTTPError(
            url='https://api.groq.com/openai/v1/chat/completions',
            code=429,
            msg='Too Many Requests',
            hdrs=None,
            fp=BytesIO(b'rate limited'),
        )
        mock_urlopen.side_effect = error

        with self.assertRaises(LLMTemporaryError):
            call_groq_chat_completion(
                api_key='test-key',
                messages=[{'role': 'user', 'content': 'Prompt'}],
            )

    @patch('generator.services.llm_service.urllib.request.urlopen')
    def test_call_groq_chat_completion_raises_request_error_for_401(
        self,
        mock_urlopen,
    ):
        import urllib.error

        error = urllib.error.HTTPError(
            url='https://api.groq.com/openai/v1/chat/completions',
            code=401,
            msg='Unauthorized',
            hdrs=None,
            fp=BytesIO(b'invalid key'),
        )
        mock_urlopen.side_effect = error

        with self.assertRaises(LLMRequestError):
            call_groq_chat_completion(
                api_key='bad-key',
                messages=[{'role': 'user', 'content': 'Prompt'}],
            )
