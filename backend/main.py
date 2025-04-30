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
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}




# RAZORPAY_KEY_ID = "rzp_test_zd5xResUDz8apY"
# RAZORPAY_KEY_SECRET = "A4gxMDCwI6UCMitXCe12yOi8"
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# OpenAI API Configuration
openai.api_key = os.environ.get("OPENAI_API_KEY")
openai.api_base = os.environ.get("OPENAI_API_BASE")

# PDFKit Configuration
#PDFKIT_CONFIG = pdfkit.configuration(
    #wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
#)

wk_path = os.environ.get("WKHTMLTOPDF_PATH", None)
PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=wk_path) if wk_path else None


origins = [
    #"http://localhost:5173",                          # React dev server
    "https://qpg-4e99a2de660c.herokuapp.com"         # your deployed React app
]

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    # 1) Save PDF
    contents = await file.read()
    tmp_path = "uploaded_question_paper.pdf"
    with open(tmp_path, "wb") as f:
        f.write(contents)

    # 2) Extract raw text
    try:
        raw = extract_text(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF parse error: {e}")

    match = re.search(r'No\.?\s*of\s*Questions\s*[:\-]?\s*(\d+)', raw, flags=re.I)
    total_q = int(match.group(1)) if match else None
    # 3) Ask OpenAI to return ONLY the numbered exam questions (JSON array)
    n_txt = f" The paper states there are {total_q} questions." if total_q else ""
    system_prompt = f"""
        You are an assistant that receives the full text of an exam paper (including headings, instructions, passages, and questions).

        Your task is to return a JSON object in the following format:
        {{"questions": ["..."]}}

        Where:
        - Each item in the "questions" array is a full question or sub-question, in the order it appears.
        - Include ALL types of questions: 
        - Standard numbered questions (e.g., "1.", "2.")
        - Sub-questions from reading passages or comprehension sections (e.g., "(a)", "(b)", etc.)
        - Fill-in-the-blanks, matching, MCQs, essay questions — everything.
        - Remove all numbering or lettering ("1.", "(a)", etc.) from each question text.
        - DO NOT exclude comprehension questions. Questions referring to a passage or text must be included.
        - DO NOT include general instructions like "Answer any six", "Read the passage", etc.
        - DO NOT include answers, explanations, or anything outside of the JSON.

        {n_txt}

        Return ONLY a valid JSON object. Do not include commentary or markdown.
        """.strip()

    questions = []
    try:
        resp = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": raw}
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        arr = json.loads(resp.choices[0].message.content.strip())
        # Accept any non-empty strings
        questions = [q.strip() for q in arr if isinstance(q, str) and q.strip()]
    except Exception:
        # 4) Fallback: regex-find all `1. …`, `2. …` blocks

        fallback_matches = re.findall(
            r'(\d+\.\s+.*?(?=\n\d+\.|\Z))|(\([a-z]\)\s+.*?(?=\n\([a-z]\)|\n\d+\.|\Z))',
            raw,
            flags=re.S | re.I
        )
        questions = [m[0] or m[1] for m in fallback_matches if m[0] or m[1]]
        #matches = re.findall(r'\d+\.\s+(.*?)(?=\n\d+\.|\Z)', raw, flags=re.S)
        #questions = [m.strip() for m in matches if m.strip()]



    
    # 5) Filter out instructional text
    instruction_keywords = [
        "limit", "write", "choose", "answer the following", "prescribed", "guidelines"
    ]
    filtered_questions = [
        q for q in questions
        if not any(keyword in q.lower() for keyword in instruction_keywords)
    ]

    if not filtered_questions:
        raise HTTPException(status_code=404, detail="No valid questions found in the uploaded paper.")
    return {"questions": filtered_questions}


# Serve static assets under /static
app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")

# Catch all React routes
from fastapi.responses import HTMLResponse

@app.get("/{full_path:path}")
async def serve_react_app():
    return HTMLResponse(open("frontend/dist/index.html").read())