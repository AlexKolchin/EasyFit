from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from databases import Database
import httpx
import os
import json
from dotenv import load_dotenv

# завантажуємо .env
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CHAT_MODEL = "gpt-3.5-turbo"

database = Database(DATABASE_URL)

if not OPENAI_API_KEY:
    print("❌ Помилка: змінна середовища OPENAI_API_KEY не встановлена. Перевір файл .env")
else:
    print("✅ OPENAI_API_KEY завантажено успішно")

@app.get("/reports")
async def get_reports():
    query = "SELECT id, report_text, kbjv_json, created_at FROM reports ORDER BY created_at DESC"
    rows = await database.fetch_all(query)
    reports = [
        {
            "id": row["id"],
            "report_text": row["report_text"],
            "kbjv": row["kbjv_json"],
            "created_at": row["created_at"].isoformat()
        }
        for row in rows
    ]
    return {"reports": reports}

@app.on_event("startup")
async def startup():
    await database.connect()
    print("✅ Підключено до бази даних")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    print("❌ Відключено від бази даних")

@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    print("Запит на / отримано")  # Додай цей рядок
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

            reply_clean = reply.strip()
            try:
                kbjv = json.loads(reply_clean)
            except json.JSONDecodeError:
                return JSONResponse(content={"result": reply, "warning": "Не вдалося розпарсити JSON"})

            # --- ПРИКЛАД: збереження результату у базу (опційно) ---
            await database.execute(
                 "INSERT INTO reports (report_text, kbjv_json) VALUES (:text, :kbjv)",
                 values={"text": food, "kbjv": json.dumps(kbjv)}
            )

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

@app.get("/health")
async def health_check():
    try:
        result = await database.fetch_val("SELECT 1")
        return {"database_connection": "ok" if result == 1 else "error"}
    except Exception as e:
        return {"database_connection": "error", "details": str(e)}
