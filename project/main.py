from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
CHAT_MODEL = "gpt-3.5-turbo"

if not OPENAI_API_KEY:
    print("❌ Помилка: змінна середовища OPENAI_API_KEY не встановлена. Перевір файл .env")
else:
    print("✅ OPENAI_API_KEY завантажено успішно")

@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


@app.post("/submit")
async def submit_report(food: str = Form(...)):
    prompt = f"""
        Порахуй КБЖВ для такого звіту і виведи тільки підсумок у форматі JSON з полями:
        калорії, білки, жири, вуглеводи.
        Ось звіт:
    {food}
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": CHAT_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            reply = result["choices"][0]["message"]["content"]

            # Видаляємо можливі зайві пробіли та перенос рядків
            reply_clean = reply.strip()

            # Спроба розпарсити JSON
            try:
                kbjv = json.loads(reply_clean)
            except json.JSONDecodeError:
                return JSONResponse(content={"result": reply, "warning": "Не вдалося розпарсити JSON"})

            return JSONResponse(content={"КБЖВ": kbjv})

    except httpx.HTTPStatusError as http_err:
        return JSONResponse(status_code=response.status_code, content={
            "error": "API response error",
            "details": response.text
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": "Unexpected server error",
            "details": str(e)
        })

