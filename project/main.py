from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from databases import Database
import httpx
import os
import json
from dotenv import load_dotenv
from datetime import date, datetime, timedelta
import logging

# завантажуємо .env
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CHAT_MODEL = "gpt-3.5-turbo"

database = Database(DATABASE_URL)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

if not OPENAI_API_KEY:
    logger.error("❌ Помилка: змінна середовища OPENAI_API_KEY не встановлена. Перевір файл .env")
else:
    logger.info("✅ OPENAI_API_KEY завантажено успішно")

@app.on_event("startup")
async def startup():
    await database.connect()
    logger.info(f"✅ Підключено до бази даних {DATABASE_URL}")

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    logger.info("❌ Відключено від бази даних")

@app.get("/", response_class=HTMLResponse)
async def read_form(request: Request):
    logger.info("Запит на / отримано")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/reports")
async def get_reports():
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    query = """
        SELECT id, report_text, kbjv_json, created_at 
        FROM reports 
        WHERE created_at >= :date_from
        ORDER BY created_at DESC
    """
    rows = await database.fetch_all(query=query, values={"date_from": three_days_ago})
    reports = []
    for row in rows:
        # kbjv_json зберігається як JSON-рядок, парсимо в словник
        try:
            kbjv = json.loads(row["kbjv_json"]) if row["kbjv_json"] else {}
        except Exception:
            kbjv = {}
        reports.append({
            "id": row["id"],
            "report_text": row["report_text"],
            "kbjv": kbjv,
            "created_at": row["created_at"].isoformat()
        })
    return {"reports": reports}

async def query_openai_kbjv(report_text: str):
    prompt = f"""
        Порахуй КБЖВ для такого звіту і виведи тільки підсумок у форматі JSON з полями:
        калорії, білки, жири, вуглеводи. Якщо є молочні продукти то беремо знежирені.
        Всі страви готувались без олії. Брати всі продукти в сирому вигляді.
        Ось звіт:
    {report_text}
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

    async with httpx.AsyncClient() as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        reply = result["choices"][0]["message"]["content"].strip()
        return reply

@app.post("/check_report")
async def check_report(food: str = Form(...)):
    report_text = food
    if not report_text:
        return JSONResponse(status_code=400, content={"error": "Параметр 'food' обов'язковий"})

    logger.info(f"Отримано звіт для перевірки КБЖВ: {report_text}")

    try:
        reply = await query_openai_kbjv(report_text)
        kbjv = json.loads(reply)
        logger.info(f"Отримано КБЖВ: {kbjv}")

        # Обгортаємо в структуру, як в твоєму фронтенді
        return {"kbjv": {"status_code": 200, "body": json.dumps({"КБЖВ": kbjv}, ensure_ascii=False)}}
    except json.JSONDecodeError:
        logger.error("Не вдалося розпарсити JSON з відповіді OpenAI")
        return JSONResponse(status_code=500, content={"error": "Не вдалося розпарсити JSON з відповіді OpenAI"})
    except httpx.HTTPStatusError as http_err:
        logger.error(f"Помилка API OpenAI: {http_err.response.text}")
        return JSONResponse(status_code=http_err.response.status_code, content={"error": "API response error", "details": http_err.response.text})
    except Exception as e:
        logger.error(f"Несподівана помилка: {str(e)}")
        return JSONResponse(status_code=500, content={"error": "Unexpected server error", "details": str(e)})

@app.post("/submit")
async def submit_report(food: str = Form(...)):
    logger.info(f"Отримано звіт для збереження: {food}")

    try:
        reply = await query_openai_kbjv(food)
        kbjv = json.loads(reply)

        calories = kbjv.get("калорії")
        protein = kbjv.get("білки")
        fat = kbjv.get("жири")
        carbs = kbjv.get("вуглеводи")

        await database.execute(
            """
            INSERT INTO reports (
                username, report_date, report_type,
                report_text, kbjv_json,
                calories, protein, fat, carbs
            )
            VALUES (
                :username, :report_date, :report_type,
                :text, :kbjv,
                :calories, :protein, :fat, :carbs
            )
            """,
            values={
                "username": "demo_user",  # фіксовано, можеш замінити на реального юзера
                "report_date": date.today(),
                "report_type": "харчування",
                "text": food,
                "kbjv": json.dumps(kbjv, ensure_ascii=False),
                "calories": calories,
                "protein": protein,
                "fat": fat,
                "carbs": carbs
            }
        )

        logger.info(f"Звіт збережено з КБЖВ: {kbjv}")

        return JSONResponse(content={"КБЖВ": kbjv})

    except json.JSONDecodeError:
        log
