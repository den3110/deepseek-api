from curl_cffi import requests
import requests as std_requests
from typing import Optional, Dict, Any, Generator, Literal, List
import json
from .pow import DeepSeekPOW
import pkg_resources
import sys
from pathlib import Path
import subprocess
import time
import threading
import pkg_resources

ThinkingMode = Literal['detailed', 'simple', 'disabled']
SearchMode = Literal['enabled', 'disabled']

class DeepSeekError(Exception):
    """Base exception for all DeepSeek API errors"""
    pass

class AuthenticationError(DeepSeekError):
    """Raised when authentication fails"""
    pass

class RateLimitError(DeepSeekError):
    """Raised when API rate limit is exceeded"""
    pass

class NetworkError(DeepSeekError):
    """Raised when network communication fails"""
    pass

class CloudflareError(DeepSeekError):
    """Raised when Cloudflare blocks the request"""
    pass

class APIError(DeepSeekError):
    """Raised when API returns an error response"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code

class PowCache:
    """Pre-fetches AND pre-solves PoW challenges in background threads for instant use."""

    def __init__(self, api: 'DeepSeekAPI'):
        self._api = api
        self._cache: Dict[str, tuple] = {}  # target_path -> (pow_response_b64, challenge, fetched_at)
        self._lock = threading.Lock()
        self._prefetching: set = set()  # track in-flight prefetches

    def get_solved(self, target_path: str = '/api/v0/chat/completion') -> str:
        """Get a pre-solved PoW response (instant) or solve one synchronously (fallback).
        Returns the base64-encoded PoW response string ready for headers."""
        with self._lock:
            cached = self._cache.pop(target_path, None)

        if cached:
            pow_response, challenge, fetched_at = cached
            # Check if challenge is still valid (not expired)
            expire_at = challenge.get('expire_at', 0)
            if expire_at > time.time():
                print(f"  ⚡ PoW pre-solved HIT (saved ~2-4s)", file=sys.stderr)
                self.prefetch(target_path)  # Start solving next one
                return pow_response

        # Cache miss or expired - fetch + solve synchronously
        challenge = self._api._get_pow_challenge_raw(target_path)
        pow_response = self._api.pow_solver.solve_challenge(challenge)
        self.prefetch(target_path)  # Pre-solve next one immediately
        return pow_response

    def prefetch(self, target_path: str = '/api/v0/chat/completion'):
        """Fetch + solve next challenge in background thread."""
        with self._lock:
            if target_path in self._prefetching:
                return  # Already prefetching
            self._prefetching.add(target_path)

        thread = threading.Thread(
            target=self._do_prefetch,
            args=(target_path,),
            daemon=True
        )
        thread.start()

    def _do_prefetch(self, target_path: str):
        """Background worker to fetch, solve, and cache a PoW challenge."""
        try:
            challenge = self._api._get_pow_challenge_raw(target_path)
            # Create a separate POW solver for this thread (wasmtime is NOT thread-safe)
            solver = DeepSeekPOW()
            pow_response = solver.solve_challenge(challenge)
            with self._lock:
                self._cache[target_path] = (pow_response, challenge, time.time())
            print(f"  ✅ PoW pre-solved and cached", file=sys.stderr)
        except Exception as e:
            print(f"  ⚠️ PoW pre-solve failed: {e}", file=sys.stderr)
        finally:
            with self._lock:
                self._prefetching.discard(target_path)


class DeepSeekAPI:
    BASE_URL = "https://chat.deepseek.com/api/v0"

    def __init__(self, auth_token: str):
        if not auth_token or not isinstance(auth_token, str):
            raise AuthenticationError("Invalid auth token provided")

        try:
            curl_cffi_version = pkg_resources.get_distribution('curl-cffi').version
            if curl_cffi_version != '0.8.1b9':
                print("\033[93mWarning: DeepSeek API requires curl-cffi version 0.8.1b9", file=sys.stderr)
                print("Please install the correct version using: pip install curl-cffi==0.8.1b9\033[0m", file=sys.stderr)
        except pkg_resources.DistributionNotFound:
            print("\033[93mWarning: curl-cffi not found. Please install version 0.8.1b9:", file=sys.stderr)
            print("pip install curl-cffi==0.8.1b9\033[0m", file=sys.stderr)

        self.auth_token = auth_token
        self.pow_solver = DeepSeekPOW()
        
        # Use a persistent session to maintain TCP/TLS connection and reduce TLS handshake latency
        self.session = requests.Session(impersonate='chrome120')

        # Initialize PoW cache for pre-solving challenges
        self.pow_cache = PowCache(self)

        # Load cookies from JSON file
        cookies_path = Path(__file__).parent / 'cookies.json'
        try:
            with open(cookies_path, 'r') as f:
                cookie_data = json.load(f)
                self.cookies = cookie_data.get('cookies', {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"\033[93mWarning: Could not load cookies from {cookies_path}: {e}\033[0m", file=sys.stderr)
            self.cookies = {}

        # Pre-solve first PoW challenge so first message is fast too
        self.pow_cache.prefetch()

    def _get_headers(self, pow_response: Optional[str] = None) -> Dict[str, str]:
        headers = {
            'accept': '*/*',
            'accept-language': 'en,fr-FR;q=0.9,fr;q=0.8,es-ES;q=0.7,es;q=0.6,en-US;q=0.5,am;q=0.4,de;q=0.3',
            'authorization': f'Bearer {self.auth_token}',
            'content-type': 'application/json',
            'origin': 'https://chat.deepseek.com',
            'referer': 'https://chat.deepseek.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-app-version': '20241129.1',
            'x-client-locale': 'en_US',
            'x-client-platform': 'web',
            'x-client-version': '1.0.0-always',
        }

        if pow_response:
            headers['x-ds-pow-response'] = pow_response

        return headers

    def _refresh_cookies(self) -> None:
        """Run the cookie refresh script and reload cookies"""
        try:
            # Get path to bypass.py
            script_path = Path(__file__).parent / 'bypass.py'

            # Run the script
            subprocess.run([sys.executable, script_path], check=True)

            # Wait briefly for cookies file to be written
            time.sleep(2)

            # Reload cookies
            cookies_path = Path(__file__).parent / 'cookies.json'
            with open(cookies_path, 'r') as f:
                cookie_data = json.load(f)
                self.cookies = cookie_data.get('cookies', {})

        except Exception as e:
            print(f"\033[93mWarning: Failed to refresh cookies: {e}\033[0m", file=sys.stderr)

    def _make_request(self, method: str, endpoint: str, json_data: Dict[str, Any], pow_required: bool = False) -> Any:
        url = f"{self.BASE_URL}{endpoint}"

        retry_count = 0
        max_retries = 2

        while retry_count < max_retries:
            try:
                headers = self._get_headers()
                if pow_required:
                    pow_response = self.pow_cache.get_solved()
                    headers = self._get_headers(pow_response)

                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    cookies=self.cookies,
                    timeout=None
                )

                # Check if we hit Cloudflare protection
                if "<!DOCTYPE html>" in response.text and "Just a moment" in response.text:
                    print("\033[93mWarning: Cloudflare protection detected. Bypassing...\033[0m", file=sys.stderr)
                    if retry_count < max_retries - 1:
                        self._refresh_cookies()  # Refresh cookies
                        retry_count += 1
                        continue

                # Handle other response codes
                if response.status_code == 401:
                    raise AuthenticationError("Invalid or expired authentication token")
                elif response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded")
                elif response.status_code >= 500:
                    raise APIError(f"Server error occurred: {response.text}", response.status_code)
                elif response.status_code != 200:
                    raise APIError(f"API request failed: {response.text}", response.status_code)

                return response.json()

            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Network error occurred: {str(e)}")
            except json.JSONDecodeError:
                raise APIError("Invalid JSON response from server")

        raise APIError("Failed to bypass Cloudflare protection after multiple attempts")

    def _get_pow_challenge_raw(self, target_path: str = '/api/v0/chat/completion') -> Dict[str, Any]:
        """Fetch a fresh PoW challenge from DeepSeek (no cache)."""
        try:
            response = self._make_request(
                'POST',
                '/chat/create_pow_challenge',
                {'target_path': target_path}
            )
            return response['data']['biz_data']['challenge']
        except KeyError:
            raise APIError("Invalid challenge response format from server")

    def _get_pow_challenge(self, target_path: str = '/api/v0/chat/completion') -> Dict[str, Any]:
        """Get a PoW challenge, without using cache."""
        return self._get_pow_challenge_raw(target_path)

    def create_chat_session(self) -> str:
        """Creates a new chat session and returns the session ID"""
        try:
            response = self._make_request(
                'POST',
                '/chat_session/create',
                {'character_id': None}
            )
            return response['data']['biz_data']['id']
        except KeyError:
            raise APIError("Invalid session creation response format from server")

    def upload_file(self, file_path: str, wait_for_ready: bool = True, max_wait: int = 30) -> Dict[str, Any]:
        """Upload a file to DeepSeek and return file info with ID.

        Args:
            file_path (str): Path to the file to upload
            wait_for_ready (bool): Wait for file to be processed (status: SUCCESS)
            max_wait (int): Max seconds to wait for file processing

        Returns:
            Dict with file info including 'id' to use in ref_file_ids
        """
        import os
        import mimetypes

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)

        # Get PoW challenge for upload endpoint
        pow_response = self.pow_cache.get_solved('/api/v0/file/upload_file')

        headers = {
            'authorization': f'Bearer {self.auth_token}',
            'origin': 'https://chat.deepseek.com',
            'referer': 'https://chat.deepseek.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-app-version': '20241129.1',
            'x-client-locale': 'en_US',
            'x-client-platform': 'web',
            'x-client-version': '1.0.0-always',
            'x-ds-pow-response': pow_response,
            'x-file-size': str(file_size),
        }

        filename = os.path.basename(file_path)
        mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'

        with open(file_path, 'rb') as f:
            response = std_requests.post(
                f'{self.BASE_URL.replace("/api/v0", "")}/api/v0/file/upload_file',
                headers=headers,
                files={'file': (filename, f, mime_type)},
                timeout=60
            )

        if response.status_code != 200:
            raise APIError(f"Upload failed: {response.text}", response.status_code)

        data = response.json()
        if data.get('code') != 0:
            raise APIError(f"Upload error: {data.get('msg', 'Unknown error')}")

        file_info = data['data']['biz_data']

        # Poll for file processing completion
        if wait_for_ready and file_info.get('status') == 'PENDING':
            file_info = self._wait_for_file_ready(file_info['id'], max_wait)

        return file_info

    def _wait_for_file_ready(self, file_id: str, max_wait: int = 30) -> Dict[str, Any]:
        """Poll file status until it's processed (SUCCESS) or timeout."""
        import time as _time

        headers = self._get_headers()
        poll_url = f"{self.BASE_URL}/file/fetch_files?file_ids={file_id}"

        for i in range(max_wait // 2):
            _time.sleep(2)
            try:
                response = self.session.get(
                    poll_url,
                    headers=headers,
                    cookies=self.cookies,
                    timeout=10
                )
                data = response.json()
                if data.get('code') == 0 and data.get('data', {}).get('biz_data'):
                    biz = data['data']['biz_data']
                    files = biz.get('files', biz) if isinstance(biz, dict) else biz
                    if isinstance(files, list) and len(files) > 0:
                        file_info = files[0]
                    elif isinstance(files, dict):
                        file_info = files
                    else:
                        continue
                    status = file_info.get('status', '')
                    if status in ('SUCCESS', 'CONTENT_EMPTY', 'UNSUPPORTED_FORMAT'):
                        return file_info
                    elif status not in ('PENDING', 'PROCESSING', 'PARSING'):
                        raise APIError(f"File processing failed with status: {status}")
            except (json.JSONDecodeError, KeyError):
                continue

        raise APIError(f"File processing timed out after {max_wait}s")


    def chat_completion(self,
                    chat_session_id: str,
                    prompt: str,
                    parent_message_id: Optional[str] = None,
                    thinking_enabled: bool = True,
                    search_enabled: bool = False,
                    ref_file_ids: Optional[List[str]] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Send a message and get streaming response

        Args:
            chat_session_id (str): The ID of the chat session
            prompt (str): The message to send
            parent_message_id (Optional[str]): ID of the parent message for threading
            thinking_enabled (bool): Whether to show the thinking process
            search_enabled (bool): Whether to enable web search for up-to-date information

        Returns:
            Generator[Dict[str, Any], None, None]: Yields message chunks with content and type

        Raises:
            AuthenticationError: If the authentication token is invalid
            RateLimitError: If the API rate limit is exceeded
            NetworkError: If a network error occurs
            APIError: If any other API error occurs
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("Prompt must be a non-empty string")
        if not chat_session_id or not isinstance(chat_session_id, str):
            raise ValueError("Chat session ID must be a non-empty string")

        json_data = {
            'chat_session_id': chat_session_id,
            'parent_message_id': parent_message_id,
            'prompt': prompt,
            'ref_file_ids': ref_file_ids or [],
            'thinking_enabled': thinking_enabled,
            'search_enabled': search_enabled,
        }

        try:
            # Get pre-solved PoW response (instant if cached, otherwise fetch+solve)
            t0 = time.time()
            pow_response = self.pow_cache.get_solved()
            headers = self._get_headers(pow_response=pow_response)
            t1 = time.time()
            print(f"  ⏱️ PoW total: {t1-t0:.2f}s", file=sys.stderr)

            # Use persistent session for Keep-Alive
            response = self.session.post(
                f"{self.BASE_URL}/chat/completion",
                headers=headers,
                json=json_data,
                cookies=self.cookies,  # Add cookies
                stream=True,
                timeout=None
            )

            if response.status_code != 200:
                error_text = next(response.iter_lines(), b'').decode('utf-8', 'ignore')
                if response.status_code == 401:
                    raise AuthenticationError("Invalid or expired authentication token")
                elif response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded")
                else:
                    raise APIError(f"API request failed: {error_text}", response.status_code)

            # We don't use iter_lines() because requests buffers it and causes multi-second delay.
            # We read raw bytes from the stream to get SSE chunks instantly.
            buffer = b''
            for chunk in response.iter_content(chunk_size=128):
                if chunk:
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        if line:
                            try:
                                parsed = self._parse_chunk(line)
                                if parsed:
                                    yield parsed
                                    if parsed.get('finish_reason') == 'stop':
                                        return
                            except Exception as e:
                                raise APIError(f"Error parsing response chunk: {str(e)}")

        except requests.exceptions.RequestException as e:
            raise NetworkError(f"Network error occurred during streaming: {str(e)}")

    def _parse_chunk(self, chunk: bytes) -> Optional[Dict[str, Any]]:
        """Parse a SSE chunk from the API response"""
        if not chunk:
            return None

        try:
            # Skip event: lines
            if chunk.startswith(b'event:'):
                return None

            if chunk.startswith(b'data: '):
                data = json.loads(chunk[6:])

                # Extract message_id from DeepSeek's response format:
                # Format 1: {"response_message_id": 2} (ready event)
                if 'response_message_id' in data:
                    self._current_message_id = data['response_message_id']
                    return None  # This is just metadata, not content

                # Format 2: {"v": {"response": {"message_id": 2, ...}}} (initial payload)
                if isinstance(data.get('v'), dict) and isinstance(data['v'].get('response'), dict):
                    resp = data['v']['response']
                    if 'message_id' in resp:
                        self._current_message_id = resp['message_id']
                    return None  # This is metadata/status info, not streamable content

                # Legacy format: {"id": "..."}
                if 'id' in data:
                    self._current_message_id = data['id']

                msg_id = getattr(self, '_current_message_id', None)

                # Chunk with path indicator (first chunk of a section or status updates)
                if 'p' in data:
                    path = data['p']
                    value = data.get('v', '')
                    
                    if path == 'response/content':
                        self._current_stream_type = 'text'
                        return {
                            'content': value,
                            'type': 'text',
                            'finish_reason': None,
                            'message_id': msg_id
                        }
                    elif path in ('response/thinking_content', 'response/thinking'):
                        self._current_stream_type = 'thinking'
                        return {
                            'content': value,
                            'type': 'thinking',
                            'finish_reason': None,
                            'message_id': msg_id
                        }
                    elif path == 'response/status' and value == 'FINISHED':
                        return {
                            'content': '',
                            'type': 'text',
                            'finish_reason': 'stop',
                            'message_id': msg_id
                        }

                # Continuation chunk (no path, just {"v": "..."})
                elif 'v' in data and isinstance(data['v'], str):
                    stream_type = getattr(self, '_current_stream_type', 'text')
                    return {
                        'content': data['v'],
                        'type': stream_type,
                        'finish_reason': None,
                        'message_id': msg_id
                    }

                # APPEND operation chunk ({"o": "APPEND", "v": "..."})
                elif 'o' in data and data['o'] == 'APPEND' and 'v' in data:
                    stream_type = getattr(self, '_current_stream_type', 'text')
                    return {
                        'content': data['v'],
                        'type': stream_type,
                        'finish_reason': None,
                        'message_id': msg_id
                    }

                # Legacy format: {"choices": [{"delta": {"content": ..., "type": ...}}]}
                elif 'choices' in data and data['choices']:
                    choice = data['choices'][0]
                    if 'delta' in choice:
                        delta = choice['delta']
                        return {
                            'content': delta.get('content', ''),
                            'type': delta.get('type', ''),
                            'finish_reason': choice.get('finish_reason'),
                            'message_id': data.get('id')
                        }
        except json.JSONDecodeError:
            raise APIError("Invalid JSON in response chunk")
        except Exception as e:
            raise APIError(f"Error parsing chunk: {str(e)}")

        return None

