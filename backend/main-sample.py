import os
import re
import json
import logging

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

import pdfkit
import openai
import razorpay
from pdfminer.high_level import extract_text
from pydantic import BaseModel

#
# ─── ENV & LOGGING ────────────────────────────────────────────────────────────────
#
logger = logging.getLogger("uvicorn.error")

# OpenAI
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")
if not OPENAI_API_KEY or not OPENAI_API_BASE:
    logger.error("Missing OPENAI_API_KEY / OPENAI_API_BASE")
    raise RuntimeError("Set OPENAI_API_KEY & OPENAI_API_BASE in config vars")

openai.api_key  = OPENAI_API_KEY
openai.api_base = OPENAI_API_BASE

# Razorpay
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# wkhtmltopdf via buildpack+apt
WK_PATH = os.getenv("WKHTMLTOPDF_PATH", "/app/.apt/usr/bin/wkhtmltopdf")
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=WK_PATH) if os.path.exists(WK_PATH) else None

#
# ─── FASTAPI SETUP ───────────────────────────────────────────────────────────────
#
app = FastAPI()

# CORS
origins = [
    "https://qpg-4e99a2de660c.herokuapp.com",
    "http://localhost:5173",    
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve React's **dist** at `/static/...`
app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")

#
# ─── UTILITY MODELS & CONSTS ────────────────────────────────────────────────────
#
TEMP_PDF    = "temp_syllabus.pdf"
SYLLABUS_TXT = "syllabus.txt"
fake_users_db = {}  # replace with real DB in prod

class User(BaseModel):
    username: str
    email:    str
    is_subscribed: bool = False
    credits_left:  int  = 1

class OrderRequest(BaseModel):
    amount:     float
    user_email: str

class TextIn(BaseModel):
    text:        str
    numQuestions:int
    mcq:         bool
    shortAnswer: bool
    longAnswer:  bool

class ChapterIn(BaseModel):
    chapter:     str
    numQuestions:int
    mcq:         bool
    shortAnswer: bool
    longAnswer:  bool

class AnswerRequest(BaseModel):
    question: str

#
# ─── API ROUTES ────────────────────────────────────────────────────────────────
#
@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/register-user")
async def register_user(user: User):
    fake_users_db[user.email] = user
    return {"message": "User registered", "user": user}


@app.post("/api/create-order")
async def create_order(order: OrderRequest):
    try:
        payment_order = razorpay_client.order.create(dict(
            amount=int(order.amount * 100),
            currency="INR",
            payment_capture="1"
        ))
        return {"order_id": payment_order["id"], "amount": order.amount}
    except Exception as e:
        raise HTTPException(500, f"Order creation failed: {e}")


@app.post("/api/upload-syllabus")
async def upload_syllabus(file: UploadFile = File(...)):
    data = await file.read()
    with open(TEMP_PDF, "wb") as f:
        f.write(data)
    try:
        text = extract_text(TEMP_PDF)
    except Exception as e:
        raise HTTPException(500, f"PDF parse error: {e}")
    with open(SYLLABUS_TXT, "w", encoding="utf-8") as f:
        f.write(text)
    return {"text": text}


@app.post("/api/nlp-generate-questions")
async def generate_questions(payload: TextIn):
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "No text provided")

    types = []
    if payload.mcq: types.append("MCQ")
    if payload.shortAnswer: types.append("short answer")
    if payload.longAnswer: types.append("long answer")
    if not types:
        raise HTTPException(400, "Select at least one question type")

    prompt = (
        f"You are a question paper generator. Based on the following text, "
        f"generate {payload.numQuestions} {', '.join(types)} question"
        f"{'s' if payload.numQuestions>1 else ''}."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role":"system", "content": prompt},
                {"role":"user",   "content": text}
            ],
            temperature=0.7,
            max_tokens=400,
        )
    except Exception as e:
        logger.error("OpenAI error", exc_info=e)
        raise HTTPException(502, f"OpenAI API error: {e}")

    choices = resp.get("choices")
    if not choices:
        raise HTTPException(502, "No response from OpenAI")

    body = choices[0]["message"]["content"].strip()
    questions = [
        line.lstrip("0123456789. ").strip()
        for line in body.split("\n") if line.strip()
    ]
    return {"questions": questions}


@app.post("/api/nlp-generate-questions-by-chapter")
async def generate_questions_by_chapter(payload: ChapterIn):
    # similar pattern, omitted for brevity
    ...


@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    data = await request.json()
    qlist = data.get("questions", [])

    html = "<html><head><meta charset='utf-8'></head><body><h1>Generated Questions</h1><ol>"
    for q in qlist:
        question = q.get('question', '').replace('\n', '<br/>')
        answer = q.get('answer', '').replace('\n', '<br/>')
        html += f"<li>{question}<br/><strong>Answer:</strong> {answer}</li><br/>"
    html += "</ol></body></html>"

    # Add wkhtmltopdf safe options (works on Heroku)
    options = {
        'enable-local-file-access': '',
        'quiet': '',
        'no-sandbox': '',
        'disable-gpu': '',
        'disable-smart-shrinking': '',
    }

    try:
        pdf = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG, options=options)
    except Exception as e:
        logger.error("PDF generation failed", exc_info=e)
        raise HTTPException(500, f"PDF generation error: {e}")

    path = "generated_questions.pdf"
    with open(path, "wb") as f:
        f.write(pdf)

    return FileResponse(path, media_type="application/pdf", filename="generated_questions.pdf")



@app.post("/api/generate-answer")
async def generate_answer(req: AnswerRequest):
    prompt = (
        "You are an expert tutor. Provide a clear, concise answer:\n\n"
        f"{req.question}"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role":"system","content":prompt}
            ],
            temperature=0.7,
            max_tokens=300,
        )
    except Exception as e:
        logger.error("Answer generation failed", exc_info=e)
        raise HTTPException(502, f"OpenAI API error: {e}")

    choices = resp.get("choices")
    if not choices:
        raise HTTPException(502, "No answer returned")

    ans = choices[0]["message"]["content"].strip()
    return {"answer": ans}


#
# ─── FALLBACK ROUTE FOR REACT ──────────────────────────────────────────────────
#
@app.get("/{full_path:path}")
async def serve_react(full_path: str):
    # Always serve your built index.html so client‐side routing works
    return HTMLResponse(open("frontend/dist/index.html", "r").read())
