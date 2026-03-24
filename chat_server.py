"""
DeepSeek Chat Server
Flask backend that wraps the dsk API with SSE streaming support.
"""

import os
import json
import tempfile
import sqlite3
import secrets
import base64
import urllib.request
from urllib.parse import urlparse
from typing import Dict, Tuple, Optional
from flask import Flask, request, Response, jsonify, send_from_directory  # type: ignore
from flask_cors import CORS  # type: ignore
from dotenv import load_dotenv  # type: ignore
from dsk.api import DeepSeekAPI  # type: ignore

load_dotenv()

DB_FILE = "api_keys.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                key_text TEXT PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

init_db()

app = Flask(__name__, static_folder='frontend/dist', static_url_path='')
CORS(app)

# Initialize DeepSeek API
AUTH_TOKEN = os.getenv('DEEPSEEK_AUTH_TOKEN', '')
api = None

def get_api():
    global api
    if api is None:
        if not AUTH_TOKEN:
            raise ValueError("DEEPSEEK_AUTH_TOKEN not set in .env")
        api = DeepSeekAPI(AUTH_TOKEN)
    return api


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok'}), 200


@app.route('/api/chat/sessions', methods=['POST'])
def create_session():
    """Create a new chat session"""
    try:
        deepseek = get_api()
        session_id = deepseek.create_chat_session()
        return jsonify({'session_id': session_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- API Key Management Endpoints ---

@app.route('/api/keys', methods=['GET'])
def list_keys():
    """List all custom API keys"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT key_text, name, created_at FROM api_keys ORDER BY created_at DESC")
        keys = [{"key": row[0], "name": row[1], "created_at": row[2]} for row in cursor]
    return jsonify({'keys': keys})

@app.route('/api/keys/generate', methods=['POST'])
def generate_key():
    """Generate a new custom API key"""
    data = request.get_json(silent=True) or {}
    name = data.get('name', 'Default Key')
    new_key = "sk-" + secrets.token_urlsafe(32)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT INTO api_keys (key_text, name) VALUES (?, ?)", (new_key, name))
    return jsonify({'key': new_key, 'name': name})

@app.route('/api/keys/<key_id>', methods=['DELETE'])
def delete_key(key_id):
    """Delete a custom API key"""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("DELETE FROM api_keys WHERE key_text = ?", (key_id,))
    return jsonify({'success': True})

def verify_api_key(key):
    """Verify if a key exists in DB or matches CUSTOM_API_KEY in env"""
    custom_key = os.getenv('CUSTOM_API_KEY')
    if custom_key and key == custom_key:
        return True
        
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.execute("SELECT 1 FROM api_keys WHERE key_text = ?", (key,))
        return cursor.fetchone() is not None

# --- Chat & Upload Endpoints ---


@app.route('/api/chat/upload', methods=['POST'])
def upload_file():
    """Upload a file and return its file_id"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Save to temp file
        ext = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        # Upload to DeepSeek
        deepseek = get_api()
        file_info = deepseek.upload_file(tmp_path)

        # Clean up temp file
        os.unlink(tmp_path)

        return jsonify({
            'file_id': file_info['id'],
            'file_name': file_info.get('file_name', file.filename),
            'status': file_info.get('status', 'unknown'),
            'file_size': file_info.get('file_size', 0),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/send', methods=['POST'])
def send_message():
    """Send a message and stream the response via SSE"""
    data = request.get_json(silent=True)
    if not data or 'prompt' not in data or 'session_id' not in data:
        return jsonify({'error': 'Missing prompt or session_id'}), 400

    session_id = data['session_id']
    prompt = data['prompt']
    thinking_enabled = data.get('thinking_enabled', False)
    search_enabled = data.get('search_enabled', False)
    parent_message_id = data.get('parent_message_id', None)
    ref_file_ids = data.get('ref_file_ids', [])
    import time as _time
    t_start = _time.time()
    print(f"📨 [{session_id[:8]}] Request received | parent={parent_message_id} | thinking={thinking_enabled} | search={search_enabled}", flush=True)

    def generate():
        try:
            deepseek = get_api()
            first_chunk = True
            first_content = True
            t_first_chunk = None
            t_first_content = None
            for chunk in (deepseek.chat_completion(
                session_id,
                prompt,
                parent_message_id=parent_message_id,
                thinking_enabled=thinking_enabled,
                search_enabled=search_enabled,
                ref_file_ids=ref_file_ids
            ) or []):
                if chunk:
                    if first_chunk:
                        first_chunk = False
                        t_first_chunk = _time.time()
                        print(f"  📦 [{session_id[:8]}] First chunk: +{t_first_chunk - t_start:.2f}s", flush=True)
                    if first_content and chunk.get('content'):
                        first_content = False
                        t_first_content = _time.time()
                        print(f"  ✍️  [{session_id[:8]}] First content ({chunk.get('type','')}): +{t_first_content - t_start:.2f}s", flush=True)
                    yield f"data: {json.dumps(chunk)}\n\n"
            t_done = _time.time()
            print(f"  ✅ [{session_id[:8]}] Done: +{t_done - t_start:.2f}s total", flush=True)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            print(f"  ❌ [{session_id[:8]}] Error: {e} (+{_time.time() - t_start:.2f}s)", flush=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


import uuid
import time
import hashlib

V1_SESSION_MAP: Dict[str, Tuple[str, Optional[str]]] = {}  # Maps conversation history hash -> (session_id, parent_message_id)

def get_history_hash(messages):
    """Create a hash of the conversation history to map to a continuous DeepSeek session."""
    canonical = [{"role": m.get("role", ""), "content": m.get("content", "")} for m in messages]
    return hashlib.md5(json.dumps(canonical, sort_keys=True).encode('utf-8')).hexdigest()

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def openai_chat_completions():
    """OpenAI-compatible chat completions endpoint"""
    if request.method == 'OPTIONS':
        return Response(status=200)

    # API Key Authentication
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({
            'error': {
                'message': 'Missing Authentication',
                'type': 'authentication_error',
                'code': 'missing_api_key'
            }
        }), 401

    api_key = auth_header.split(' ')[1]
    if not verify_api_key(api_key):
        return jsonify({
            'error': {
                'message': 'Invalid Authentication',
                'type': 'authentication_error',
                'code': 'invalid_api_key'
            }
        }), 401

    data = request.get_json(silent=True)
    if not data or 'messages' not in data:
        return jsonify({'error': {'message': 'Missing messages', 'type': 'invalid_request_error'}}), 400

    messages = data['messages']
    stream = data.get('stream', False)
    model = data.get('model', 'deepseek-chat')
    
    history = messages[:-1] if messages else []
    last_msg = messages[-1] if messages else {"role": "user", "content": ""}
    last_user_msg = last_msg.get('content', '')

    try:
        deepseek = get_api()
    except Exception as e:
        return jsonify({'error': {'message': str(e), 'type': 'api_error'}}), 500

    session_id = None
    parent_message_id = None
    prompt = ""
    ref_file_ids = []

    def process_content(msg_content):
        text_content = ""
        if isinstance(msg_content, list):
            for item in msg_content:
                if item.get("type") == "text":
                    text_content += item.get("text", "") + "\n\n"
                elif item.get("type") == "image_url":
                    img_url = item.get("image_url", {}).get("url", "")
                    if img_url:
                        try:
                            tmp_path = None
                            if img_url.startswith("data:"):
                                header, encoded = img_url.split(",", 1)
                                ext = ".png"
                                if "image/jpeg" in header: ext = ".jpg"
                                elif "image/png" in header: ext = ".png"
                                elif "image/webp" in header: ext = ".webp"
                                elif "image/gif" in header: ext = ".gif"
                                img_data = base64.b64decode(encoded)
                                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                                    tmp.write(img_data)
                                    tmp_path = tmp.name
                            elif img_url.startswith("http"):
                                parsed_url = urlparse(img_url)
                                ext = os.path.splitext(parsed_url.path)[1]
                                if not ext: ext = ".png"
                                req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(req, timeout=10) as response:
                                    if response.status == 200:
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                                            tmp.write(response.read())
                                            tmp_path = tmp.name
                            if tmp_path:
                                file_info = deepseek.upload_file(tmp_path)
                                ref_file_ids.append(file_info['id'])
                                os.unlink(tmp_path)
                        except Exception as e:
                            print(f"Error processing image: {e}")
                            raise Exception(f"Failed to process image {img_url[:30]}... : {e}")
        else:
            text_content = str(msg_content)
        return text_content.strip()

    # Try to resume an existing DeepSeek session based on chat history
    if len(messages) > 1:
        history_hash = get_history_hash(history)
        mapping = V1_SESSION_MAP.get(history_hash, None)
        if mapping is not None:
            session_id, parent_message_id = mapping

    try:
        if session_id:
            # Resuming context, only send the final user message
            prompt = process_content(last_user_msg)
        else:
            # Completely new thread or session expired/not found, create a new DeepSeek session.
            # DeepSeek UI needs the full context flat-packed into the first prompt.
            session_id = deepseek.create_chat_session()
            for idx, msg in enumerate(messages):
                role = msg.get('role', 'user')
                content_str = process_content(msg.get('content', ''))
                if idx == len(messages) - 1: # Last message handles regardless of role
                    prompt += f"{content_str}"
                else:
                    prompt += f"{role.capitalize()}: {content_str}\n\n"
    except Exception as e:
        return jsonify({'error': {'message': str(e), 'type': 'invalid_request_error'}}), 400

    def update_session_map(assistant_text, final_message_id):
        new_history = history + [last_msg, {"role": "assistant", "content": assistant_text}]
        V1_SESSION_MAP[get_history_hash(new_history)] = (session_id, final_message_id)  # type: ignore
        # Prevent memory leak over long uptime by capping items
        if len(V1_SESSION_MAP) > 1000:
            keys_to_remove = list(V1_SESSION_MAP.keys())[:500]  # type: ignore
            for k in keys_to_remove:
                V1_SESSION_MAP.pop(k, None)

    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if stream:
        def generate_openai_stream():
            full_response = ""
            thinking_enabled = (model == 'deepseek-reasoner')
            try:
                last_msg_id = None
                for chunk in (deepseek.chat_completion(session_id, prompt, parent_message_id=parent_message_id, thinking_enabled=thinking_enabled, ref_file_ids=ref_file_ids) or []):
                    if chunk:
                        if chunk.get('message_id'):
                            last_msg_id = chunk['message_id']
                        
                        if chunk.get('content'):
                            choice_delta = {}
                            if chunk.get('type') == 'thinking':
                                choice_delta['reasoning_content'] = chunk['content']
                            elif chunk.get('type') == 'text':
                                choice_delta['content'] = chunk['content']
                                full_response += chunk['content']
                            
                        if choice_delta:
                            response_chunk = {
                                "id": chat_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": choice_delta,
                                        "finish_reason": None
                                    }
                                ]
                            }
                            yield f"data: {json.dumps(response_chunk)}\n\n"
                # Send the [DONE] signal
                final_chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }
                    ]
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"
                update_session_map(full_response, last_msg_id)
            except Exception as e:
                error_chunk = {
                    "error": {"message": str(e), "type": "api_error"}
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"

        return Response(
            generate_openai_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive',
            }
        )
    else:
        # Non-streaming response
        try:
            full_content = ""
            full_reasoning = ""
            last_msg_id = None
            thinking_enabled = (model == 'deepseek-reasoner')
            print(f"  🖼️  ref_file_ids={ref_file_ids}", flush=True)
            print(f"  📝 prompt length={len(prompt)}, session={session_id}, parent={parent_message_id}", flush=True)
            print(f"  📝 prompt preview: {prompt[:200]}...", flush=True)
            chunk_count = 0
            for chunk in (deepseek.chat_completion(session_id, prompt, parent_message_id=parent_message_id, thinking_enabled=thinking_enabled, ref_file_ids=ref_file_ids) or []):
                if chunk:
                    chunk_count += 1
                    if chunk_count <= 5:
                        print(f"  📦 chunk#{chunk_count}: type={chunk.get('type')} content_len={len(str(chunk.get('content','')))} keys={list(chunk.keys())}", flush=True)
                    if chunk.get('message_id'):
                        last_msg_id = chunk['message_id']
                        
                    if chunk.get('content'):
                        if chunk.get('type') == 'thinking':
                            full_reasoning += str(chunk['content'])  # type: ignore
                        elif chunk.get('type') == 'text':
                            full_content += str(chunk['content'])  # type: ignore
            
            print(f"  ✅ total chunks={chunk_count}, content_len={len(full_content)}, reasoning_len={len(full_reasoning)}", flush=True)
            if not full_content:
                print(f"  ⚠️  WARNING: DeepSeek returned EMPTY content!", flush=True)

            msg = {
                "role": "assistant",
                "content": full_content
            }
            if full_reasoning:
                msg["reasoning_content"] = full_reasoning
                
            update_session_map(full_content, last_msg_id)
                
            response_data = {
                "id": chat_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": msg,
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": len(prompt) // 4,
                    "completion_tokens": (len(full_content) + len(full_reasoning)) // 4,
                    "total_tokens": (len(prompt) + len(full_content) + len(full_reasoning)) // 4
                }
            }
            return jsonify(response_data)
        except Exception as e:
            print(f"  ❌ non-stream error: {e}", flush=True)
            return jsonify({'error': {'message': str(e), 'type': 'api_error'}}), 500


# Serve React frontend
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    print("🚀 DeepSeek Chat Server starting...")
    print(f"   Token: {'✅ loaded' if AUTH_TOKEN else '❌ missing'}")
    print(f"   URL: http://localhost:5024")
    app.run(host='0.0.0.0', port=5024, debug=True)
