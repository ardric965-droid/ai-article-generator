import json
from io import BytesIO
from unittest.mock import patch, mock_open, MagicMock
from django.test import SimpleTestCase

from generator.services.llm_service import (
    LLMConfigurationError,
    LLMRequestError,
    LLMTemporaryError,
    _validate_article_payload,
    build_prompt,
    call_groq_chat_completion,
    generate_article,
)

class BuildPromptTests(SimpleTestCase):
    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="Rows:\n{{ROWS_JSON}}\n")
    def test_build_prompt_inserts_rows_json(self, mock_file, mock_is_file):
        rows = [
            {'title': 'My Title', 'description': 'My Description'},
        ]
        prompt = build_prompt(rows)
        self.assertIn('Rows:', prompt)
        self.assertIn('[{"title": "My Title", "description": "My Description"}]', prompt)
        self.assertNotIn('{{ROWS_JSON}}', prompt)

    @patch('pathlib.Path.is_file', return_value=False)
    def test_build_prompt_raises_if_file_missing(self, mock_is_file):
        with self.assertRaises(LLMConfigurationError) as ctx:
            build_prompt([{'title': 'Title', 'description': 'Desc'}])
        self.assertIn("prompt template file not found", str(ctx.exception))

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', side_effect=Exception("Read failure"))
    def test_build_prompt_raises_on_read_failure(self, mock_file, mock_is_file):
        with self.assertRaises(LLMConfigurationError) as ctx:
            build_prompt([{'title': 'Title', 'description': 'Desc'}])
        self.assertIn("Failed to read prompt template", str(ctx.exception))

    @patch('pathlib.Path.is_file', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data="Some prompt without placeholder\n")
    def test_build_prompt_raises_if_placeholder_missing(self, mock_file, mock_is_file):
        with self.assertRaises(LLMConfigurationError) as ctx:
            build_prompt([{'title': 'Title', 'description': 'Desc'}])
        self.assertIn("{{ROWS_JSON}} placeholder", str(ctx.exception))


class ValidateArticlePayloadTests(SimpleTestCase):
    def test_accepts_single_article_object(self):
        payload = {
            'title': 'Test Title',
            'description': 'Test Description',
            'article': 'Generated article body.',
        }
        articles = _validate_article_payload(payload, json.dumps(payload))
        self.assertEqual(articles, [payload])

    def test_accepts_bare_list(self):
        payload = [
            {
                'title': 'Test Title',
                'description': 'Test Description',
                'article': 'Generated article body.',
            }
        ]
        articles = _validate_article_payload(payload, json.dumps(payload))
        self.assertEqual(articles, payload)

    def test_raises_request_error_for_non_list_non_dict(self):
        with self.assertRaises(LLMRequestError) as ctx:
            _validate_article_payload('not valid', 'not valid')
        self.assertIn("LLM response must be a JSON array or a single article object", str(ctx.exception))

        with self.assertRaises(LLMRequestError) as ctx:
            _validate_article_payload(123, '123')
        self.assertIn("Got int", str(ctx.exception))

    def test_raises_request_error_for_dict_without_required_keys_and_no_list(self):
        payload = {'unexpected': 'value'}
        with self.assertRaises(LLMRequestError) as ctx:
            _validate_article_payload(payload, json.dumps(payload))
        self.assertIn("LLM did not return a JSON array of articles", str(ctx.exception))

    def test_validates_multiple_articles_in_list(self):
        payload = [
            {
                'title': 'Title 1',
                'description': 'Description 1',
                'article': 'Article 1',
            },
            {
                'title': 'Title 2',
                'description': 'Description 2',
                'article': 'Article 2',
            },
        ]
        articles = _validate_article_payload(payload, json.dumps(payload))
        self.assertEqual(articles, payload)

    def test_raises_request_error_for_non_dict_entry_in_list(self):
        payload = ['not a dict']
        with self.assertRaises(LLMRequestError) as ctx:
            _validate_article_payload(payload, json.dumps(payload))
        self.assertIn("LLM response contains a non-object article entry", str(ctx.exception))


class GenerateArticleTests(SimpleTestCase):
    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_returns_article_field(self, mock_call, mock_build_prompt):
        response_json = [
            {
                'title': 'Test Title',
                'description': 'Test Description',
                'article': 'Generated article body.',
            }
        ]
        mock_call.return_value = json.dumps(response_json)

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description')

        self.assertEqual(article, 'Generated article body.')
        mock_call.assert_called_once()
        messages = mock_call.call_args.kwargs['messages']
        self.assertEqual(messages[1]['content'], 'Formatted Prompt')

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_accepts_wrapped_array(self, mock_call, mock_build_prompt):
        # Some models running in json_object mode wrap the array in an object.
        response_json = {
            'articles': [
                {
                    'title': 'Test Title',
                    'description': 'Test Description',
                    'article': 'Body from wrapped array.',
                }
            ]
        }
        mock_call.return_value = json.dumps(response_json)

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description')

        self.assertEqual(article, 'Body from wrapped array.')

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_accepts_single_object(self, mock_call, mock_build_prompt):
        mock_call.return_value = json.dumps(
            {
                'title': 'Test Title',
                'description': 'Test Description',
                'article': 'Single object article body.',
            }
        )

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description')

        self.assertEqual(article, 'Single object article body.')

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_rejects_non_list_non_dict(self, mock_call, mock_build_prompt):
        mock_call.return_value = '"just a string"'

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as ctx:
                generate_article('Title', 'Description')

        self.assertIn("LLM response must be a JSON array or a single article object", str(ctx.exception))


    def test_generate_article_requires_api_key(self):
        with patch.dict('os.environ', {'LLM_API_KEY': ''}, clear=False):
            with self.assertRaisesMessage(
                LLMConfigurationError,
                'LLM_API_KEY is missing. Add your Groq API key to the .env file.',
            ):
                generate_article('Title', 'Description')

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.time.sleep')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_retries_temporary_failures(
        self,
        mock_call,
        mock_sleep,
        mock_build_prompt,
    ):
        response_json = [
            {
                'title': 'Title',
                'description': 'Description',
                'article': 'Recovered article.',
            }
        ]
        mock_call.side_effect = [
            LLMTemporaryError('temporary outage'),
            LLMTemporaryError('still down'),
            json.dumps(response_json),
        ]

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            article = generate_article('Title', 'Description', max_retries=3)

        self.assertEqual(article, 'Recovered article.')
        self.assertEqual(mock_call.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.time.sleep')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_raises_after_max_retries(
        self,
        mock_call,
        mock_sleep,
        mock_build_prompt,
    ):
        mock_call.side_effect = LLMTemporaryError('service unavailable')

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description', max_retries=2)

        self.assertIn('Failed to generate article after 2 attempts', str(context.exception))
        self.assertEqual(mock_call.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_invalid_json(self, mock_call, mock_build_prompt):
        mock_call.return_value = 'not json'

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description')
        self.assertIn("is not a valid JSON object", str(context.exception))

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_rejects_empty_article(self, mock_call, mock_build_prompt):
        mock_call.return_value = json.dumps([
            {
                'title': 'Test Title',
                'description': 'Test Description',
                'article': '   ',
            }
        ])

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description')

        self.assertIn("field 'article' must be a non-empty string", str(context.exception))

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_missing_schema_keys(self, mock_call, mock_build_prompt):
        mock_call.return_value = json.dumps([
            {'title': 'Test Title', 'description': 'Test Description'},
        ])

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description')
        self.assertIn("missing required keys: article", str(context.exception))

    @patch('generator.services.llm_service.build_prompt', return_value='Formatted Prompt')
    @patch('generator.services.llm_service.call_groq_chat_completion')
    def test_generate_article_rejects_missing_article_list(self, mock_call, mock_build_prompt):
        mock_call.return_value = json.dumps({'title': 'No list of articles'})

        with patch.dict('os.environ', {'LLM_API_KEY': 'test-key'}, clear=False):
            with self.assertRaises(LLMRequestError) as context:
                generate_article('Title', 'Description')
        self.assertIn("did not return a JSON array of articles", str(context.exception))



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
                    {'message': {'content': '  {"content": "ok"}  '}},
                ],
            },
        )

        response = call_groq_chat_completion(
            api_key='test-key',
            messages=[{'role': 'user', 'content': 'Prompt'}],
        )

        self.assertEqual(response, '{"content": "ok"}')

    @patch('generator.services.llm_service.urllib.request.urlopen')
    def test_call_groq_chat_completion_sends_json_mode_payload(self, mock_urlopen):
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
        
        data_sent = json.loads(request.data.decode('utf-8'))
        self.assertEqual(data_sent['response_format'], {'type': 'json_object'})

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
