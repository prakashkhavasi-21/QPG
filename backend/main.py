from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pdfminer.high_level import extract_text
from pydantic import BaseModel
import pdfkit
import openai
import os
import re
from fastapi import Depends
from pydantic import BaseModel
from typing import Optional
import razorpay

# RAZORPAY_KEY_ID = "rzp_test_zd5xResUDz8apY"
# RAZORPAY_KEY_SECRET = "A4gxMDCwI6UCMitXCe12yOi8"
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# OpenAI API Configuration
openai.api_key = "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"
openai.api_base = "https://openrouter.ai/api/v1"

# PDFKit Configuration
PDFKIT_CONFIG = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_PDF = "temp_syllabus.pdf"
SYLLABUS_TXT = "syllabus.txt"

# Fake in-memory user data store (in a production scenario, you would store this in a database)
fake_users_db = {}

# --- User Management ---
class User(BaseModel):
    username: str
    email: str
    is_subscribed: bool = False  # User subscription status
    credits_left: int = 1  # Free credit by default

# Register or login a user
@app.post("/api/register-user")
async def register_user(user: User):
    fake_users_db[user.email] = user
    return {"message": "User registered successfully", "user": user}

# Check user status
def get_user(email: str):
    if email in fake_users_db:
        return fake_users_db[email]
    return None

class OrderRequest(BaseModel):
    amount: float
    user_email: str

@app.post("/api/create-order")
async def create_order(order: OrderRequest):
    try:
        # Create Razorpay order
        payment_order = razorpay_client.order.create(dict(
            amount=int(order.amount * 100),  # Razorpay accepts amount in paise (1 INR = 100 paise)
            currency='INR',
            payment_capture='1'
        ))

        return {"order_id": payment_order['id'], "amount": order.amount}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment order creation failed: {e}")


# --- Upload syllabus and extract text ---
@app.post("/api/upload-syllabus")
async def upload_syllabus(file: UploadFile = File(...)):
    contents = await file.read()
    with open(TEMP_PDF, "wb") as f:
        f.write(contents)
    try:
        text = extract_text(TEMP_PDF)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse error: {e}")
    with open(SYLLABUS_TXT, "w", encoding="utf-8") as f:
        f.write(text)
    return {"text": text}

# --- Models ---
class TextIn(BaseModel):
    text: str
    numQuestions: int
    mcq: bool
    shortAnswer: bool
    longAnswer: bool

class ChapterIn(BaseModel):
    chapter: str
    numQuestions: int
    mcq: bool
    shortAnswer: bool
    longAnswer: bool

# --- Generate questions from arbitrary text ---
@app.post("/api/nlp-generate-questions")
async def generate_questions(payload: TextIn):
    full_text = payload.text.strip()
    if not full_text:
        raise HTTPException(status_code=400, detail="No text provided.")

    # Determine selected types
    types = []
    if payload.mcq: types.append("MCQ")
    if payload.shortAnswer: types.append("short answer")
    if payload.longAnswer: types.append("long answer")
    if not types:
        raise HTTPException(status_code=400, detail="Select at least one question type.")
    types_str = ", ".join(types)

    n = payload.numQuestions
    system_prompt = (
        f"You are a question paper generator. Based on the following text, "
        f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role":"system","content":system_prompt},
                {"role":"user","content":full_text},
            ],
            temperature=0.7,
            max_tokens=400,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"API error: {e}")

    if "choices" not in resp or not resp["choices"]:
        raise HTTPException(status_code=502, detail="No choices returned from API.")

    content = resp["choices"][0]["message"]["content"].strip()
    questions = [
        line.lstrip("0123456789. ").strip() for line in content.split("\n") if line.strip()
    ]
    return {"questions": questions}

# --- Generate questions by chapter with dynamic types and counts ---
@app.post("/api/nlp-generate-questions-by-chapter")
async def generate_questions_by_chapter(payload: ChapterIn):
    chapter = payload.chapter.strip()
    n = payload.numQuestions
    # Determine types
    types = []
    if payload.mcq:        types.append("MCQ")
    if payload.shortAnswer: types.append("short answer")
    if payload.longAnswer:  types.append("long answer")
    if not types:
        raise HTTPException(status_code=400, detail="Select at least one question type.")
    types_str = ", ".join(types)

    if not chapter:
        raise HTTPException(status_code=400, detail="Chapter name is required.")
    try:
        syllabus_text = open(SYLLABUS_TXT, "r", encoding="utf-8").read()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No syllabus uploaded.")

    text_lower = syllabus_text.lower()
    start_idx = text_lower.find(chapter.lower())
    if start_idx == -1:
        raise HTTPException(status_code=404, detail="Chapter not found in syllabus.")

    # find next UNIT marker
    next_units = [
        m.start() for m in re.finditer(r"(?:unit[\s\-]*\d+\b)", text_lower)
        if m.start() > start_idx
    ]
    end_idx = next_units[0] if next_units else len(syllabus_text)
    chapter_content = syllabus_text[start_idx:end_idx].strip()

    system_prompt = (
        f"You are an expert question generator. Based on the following syllabus section, "
        f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it."
    )
    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": chapter_content},
            ],
            temperature=0.7,
            max_tokens=300,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"API call failed: {e}")

    if "choices" not in resp or not resp["choices"]:
        raise HTTPException(status_code=502, detail="No choices returned.")
    raw = resp["choices"][0]["message"]["content"].strip()
    questions = [
        line.lstrip("0123456789. ").strip()
        for line in raw.split("\n") if line.strip()
    ]
    return {"chapter": chapter, "questions": questions}


# --- Export PDF (with answers) ---
# --- Export PDF (with better answer formatting for code/equations) ---
@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    data = await request.json()
    questions = data.get("questions", [])

    html = "<html><head><meta charset='utf-8'></head><body>"
    html += "<h1>Generated Question Paper</h1><ol>"

    for q in questions:
        text   = q.get("question", "").replace("\n", "<br/>")
        answer = q.get("answer", "")
        marks  = q.get("marks")

        html += "<li>"
        html += f"{text}"

        if marks is not None and marks != "":
            html += f" <em>({marks} marks)</em>"

        if answer:
            html += "<br/><br/>"
            html += "<strong>Answer:</strong><br/>"

            # Detect if answer looks like code block (basic check)
            if "\n" in answer or "    " in answer:  # multi-line or indented
                html += f"<pre style='background-color:#f4f4f4;padding:10px;border-radius:8px;'>{answer}</pre>"
            else:
                html += f"<p>{answer}</p>"

        html += "</li><br/>"

    html += "</ol></body></html>"

    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG)
    pdf_path  = "generated_questions.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path)




class AnswerRequest(BaseModel):
    question: str

from fastapi import HTTPException
from pydantic import BaseModel

# --- Add (or update) this model ---
class AnswerRequest(BaseModel):
    question: str

# --- Replace your current /api/generate-answer with this ---
@app.post("/api/generate-answer")
async def generate_answer(req: AnswerRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    # Craft a system prompt to guide the answer style
    system_prompt = (
        "You are an expert tutor. "
        "Provide a clear, concise answer to the question below."
    )

    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": question},
            ],
            temperature=0.7,
            max_tokens=300,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {e}")

    # Validate response
    choices = resp.get("choices")
    if not choices or not choices[0].get("message", {}).get("content"):
        raise HTTPException(status_code=502, detail="No answer returned from OpenAI.")

    answer_text = choices[0]["message"]["content"].strip()
    return {"answer": answer_text}




# … your existing imports and setup …

@app.post("/api/upload-question-paper")
async def upload_question_paper(file: UploadFile = File(...)):
    # 1) Save the incoming file
    contents = await file.read()
    temp_path = "uploaded_question_paper.pdf"
    with open(temp_path, "wb") as f:
        f.write(contents)

    # 2) Extract raw text
    try:
        raw_text = extract_text(temp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse error: {e}")

    # 3) Use OpenAI to pull out **only** the numbered questions
    #    and skip any instructions/guidelines at the top.
    system_prompt = """
        You are an assistant that receives the full text of an exam paper (including
        instructions, formatting notes, etc.) and must return a JSON array of only the
        numbered exam questions.  Discard any introductory instructions or guidelines.
        Each element should be a string *without* the leading “1.”, “2.”, etc.
        """
    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system",  "content": system_prompt.strip()},
                {"role": "user",    "content": raw_text}
            ],
            temperature=0.0,
            max_tokens=1000
        )
        ai_content = resp.choices[0].message.content.strip()
        # Expect the model to respond with something like:
        # ["What is ...?", "Explain ...", ...]
        questions = json.loads(ai_content)
        if not isinstance(questions, list):
            raise ValueError("OpenAI did not return a JSON list")
    except Exception as e:
        # Fallback to regex-splitting if OpenAI fails
        parts = re.split(r'\n\d+\.\s+', raw_text)
        questions = [p.strip() for p in parts[1:] if len(p.split()) > 5]

    if not questions:
        raise HTTPException(status_code=404, detail="No questions found.")

    return {"questions": questions}