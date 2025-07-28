service-import base64
import requests
import uuid
import json # <-- 新增導入 json 模組
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# --- 您的 Dify 設定 ---
DIFY_BASE_URL = "http://203.145.221.245"
DIFY_API_KEY = "app-JpZfI8ufo4Di4UNgPHa6Dpeq"
# --------------------

app = FastAPI()

@app.post("/v1/chat/completions")
async def handle_openwebui_request(request: Request):
    try:
        # ... (前面的程式碼保持不變) ...
        body = await request.json()
        messages = body.get("messages", [])
        last_message = messages[-1] if messages else {}
        content = last_message.get("content", [])

        user_prompt = ""
        image_base64 = ""

        if isinstance(content, list):
            for part in content:
                if part.get("type") == "text":
                    user_prompt = part.get("text")
                elif part.get("type") == "image_url":
                    image_base64 = part.get("image_url", {}).get("url", "").split(",")[-1]
        
        if not image_base64:
            raise HTTPException(status_code=400, detail="請求中未包含圖片資料")

        image_data = base64.b64decode(image_base64)

        dify_headers = {"Authorization": f"Bearer {DIFY_API_KEY}"}
        files = {'file': ('uploaded_image.png', image_data, 'image/png')}
        data = {'user': 'openwebui-user'}

        upload_response = requests.post(
            f"{DIFY_BASE_URL}/v1/files/upload",
            headers=dify_headers, data=data, files=files, timeout=180
        )
        upload_response.raise_for_status()
        upload_file_id = upload_response.json().get("id")

        if not upload_file_id:
            raise HTTPException(status_code=500, detail="從 Dify 取得 upload_file_id 失敗")

        # 4. 執行 Dify 的第二步
        dify_chat_payload = {
            "inputs": {},
            "query": user_prompt or " ",
            "user": "openwebui-user",
            "response_mode": "blocking",
            "files": [{
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": upload_file_id
            }]
        }

        # --- [偵錯] --- 在發送前，印出我們要傳送的內容
        print("--- [DEBUG] Sending this payload to Dify chat-messages:")
        print(json.dumps(dify_chat_payload, indent=2, ensure_ascii=False))
        # ---------------

        dify_response = requests.post(
            f"{DIFY_BASE_URL}/v1/chat-messages",
            headers=dify_headers, json=dify_chat_payload, timeout=180
        )
        dify_response.raise_for_status()
        dify_result = dify_response.json()

        # ... (後面的 response_payload 部分保持不變) ...
        final_answer = dify_result.get("answer", "處理完成，但未收到回覆。")
        response_payload = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(uuid.uuid4().time_low),
            "model": body.get("model", "dify-workflow"),
            "choices": [{
                "index": 0, "message": {"role": "assistant", "content": final_answer}, "finish_reason": "stop"
            }]
        }
        return JSONResponse(content=response_payload)

    # --- [偵錯] --- 修改 except 區塊來捕捉更詳細的錯誤
    except requests.exceptions.HTTPError as e:
        print("--- [DEBUG] Dify returned an HTTP error! ---")
        print(f"--- [DEBUG] Status Code: {e.response.status_code}")
        # 這一步最關鍵，印出 Dify 回傳的詳細錯誤內容
        print(f"--- [DEBUG] Response Body from Dify: {e.response.text}")
        print(f"發生錯誤: {e}")
        raise HTTPException(status_code=500, detail=f"Error from Dify: {e.response.text}")
    # ----------------------------------------------------
    except Exception as e:
        print(f"發生了一個非 HTTP 錯誤: {e}")
        raise HTTPException(status_code=500, detail=str(e))