from dsk.api import DeepSeekAPI, AuthenticationError, RateLimitError, NetworkError, APIError
from typing import Generator, Dict, Any
from dotenv import load_dotenv

load_dotenv()

def print_response(chunks: Generator[Dict[str, Any], None, None]) -> str:
    """Helper function to print response chunks in a clean format"""
    thinking_lines = []
    text_content = []

    try:
        for chunk in chunks:
            if chunk['type'] == 'thinking':
                if chunk['content'] and chunk['content'] not in thinking_lines:
                    thinking_lines.append(chunk['content'])
            elif chunk['type'] == 'text':
                text_content.append(chunk['content'])
    except KeyError as e:
        return (f"❌ Error: Malformed response chunk - missing key {str(e)}")

    return (''.join(text_content))

def run_chat_example(api: DeepSeekAPI, title: str, prompt: str, thinking_enabled: bool = True, search_enabled: bool = False) -> str:
    """Run a chat example with error handling"""

    try:
        chunks = api.chat_completion(
            api.create_chat_session(),
            prompt,
            thinking_enabled=thinking_enabled,
            search_enabled=search_enabled
        )
        return print_response(chunks)

    except AuthenticationError as e:
        return(f"❌ Authentication Error: {str(e)}")
    except RateLimitError as e:
        return(f"❌ Rate Limit Error: {str(e)}")
    except NetworkError as e:
        return(f"❌ Network Error: {str(e)}")
    except APIError as e:
        return(f"❌ API Error: {str(e)}")
    except Exception as e:
        return(f"❌ Unexpected Error: {str(e)}")

def main(prompt: str) -> str:
    try:
        api = DeepSeekAPI("TOKEN")

        # Улучшенный промпт
        system_prompt = (
            "Ты — профессиональный литературный ассистент. Соблюдай правила:\n"
            "1. Анализируй стиль, темы и атмосферу из запроса\n"
            "2. Подбирай 10 неочевидных, но релевантных книг\n"
            "3. Формат: Автор — Название (каждая с новой строки)\n"
            "4. Избегай популярных бестселлеров и книг из запроса\n"
            "5. Разнообразь жанры, если это уместно\n"
            "6. Добавь 1-2 редких произведения\n"
            "7. Ответ только на русском языке\n"
            "8. Убедись в существовании рекомендуемых книг\n\n"
            f"Пользовательские предпочтения: {prompt}"
        )

        return run_chat_example(
            api,
            "Books recommendation",
            system_prompt,
            thinking_enabled=False
        )

    except KeyboardInterrupt:
        return "⚠️ Операция прервана"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

if __name__ == "__main__":
    main()
