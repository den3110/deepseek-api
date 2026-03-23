import os
from openai import OpenAI

# Initialize the official OpenAI client pointing to our local server
# You can use any API key that you generated in the UI
client = OpenAI(
    api_key="your-api-key-here", 
    base_url="http://localhost:5000/v1"
)

def test_chat():
    print("🤖 Bắt đầu thử nghiệm DeepSeek qua chuẩn OpenAI API...\n")
    
    # 1. Câu hỏi đầu tiên
    messages = [
        {"role": "user", "content": "Xin chào, bạn tên là gì?"}
    ]
    
    print("User: ", messages[0]['content'])
    print("Assistant (Đang gõ...): ", end="", flush=True)
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        stream=True # Test tính năng stream luôn
    )
    
    assistant_reply = ""
    for chunk in response:
        delta = chunk.choices[0].delta
        if hasattr(delta, 'content') and delta.content:
            content = delta.content
            print(content, end="", flush=True)
            assistant_reply += content
    print("\n")
    
    # 2. Câu hỏi phụ thuộc vào ngữ cảnh (test tính năng nhớ lịch sử bằng Hash mới làm)
    messages.append({"role": "assistant", "content": assistant_reply})
    messages.append({"role": "user", "content": "Bạn hãy lặp lại câu hỏi vừa rồi của tôi được không?"})
    
    print("-" * 50)
    print("User (hỏi móc nối lịch sử): ", messages[-1]['content'])
    print("Assistant (Đang gõ...): ", end="", flush=True)
    
    response2 = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        stream=True
    )
    
    for chunk in response2:
        delta = chunk.choices[0].delta
        if hasattr(delta, 'content') and delta.content:
            print(delta.content, end="", flush=True)
    print("\n\n✅ Đã test xong!")

if __name__ == "__main__":
    test_chat()
