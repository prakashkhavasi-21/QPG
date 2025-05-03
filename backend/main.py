from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pdfminer.high_level import extract_text
from pydantic import BaseModel
import fitz  # PyMuPDF for native text extraction
from pdf2image import convert_from_path
import pdfplumber
from PIL import Image
import pytesseract
import openai
import os
import re
from fastapi import Depends
from pydantic import BaseModel
from typing import Optional
import razorpay
from fastapi.staticfiles import StaticFiles
import json
import io
import pdfkit


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

# wk_path = os.environ.get("WKHTMLTOPDF_PATH", None)
# PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=wk_path) if wk_path else None


origins = [
    "https://www.qnagenai.com",
    "https://qpg-4e99a2de660c.herokuapp.com",         # your deployed React app
    "http://localhost:5173",                          # React dev server
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
        text = extract_text_from_pdf(TEMP_PDF)
        if not text:
            raise Exception("No extractable text found in PDF (native + OCR).")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF text extraction failed: {e}")

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
            model="openai/gpt-4-turbo",
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
            model="openai/gpt-4-turbo",
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


# main.py



from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_LEFT

@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    data = await request.json()
    questions = data.get("questions", [])

    pdf_path = "generated_questions.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            rightMargin=40, leftMargin=40,
                            topMargin=50, bottomMargin=50)

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    question_style = ParagraphStyle(
        "Question", parent=styles["BodyText"],
        leftIndent=10, spaceAfter=6,
    )
    answer_label = ParagraphStyle(
        "AnswerLabel", parent=styles["BodyText"],
        leftIndent=10, fontName="Helvetica-BoldOblique",
        spaceAfter=4,
    )
    answer_style = ParagraphStyle(
        "Answer", parent=styles["BodyText"],
        leftIndent=20, textColor="#333333",
        spaceAfter=12,
    )

    elements = []
    elements.append(Paragraph("Generated Question Paper", title_style))
    elements.append(Spacer(1, 12))

    # questions list
    q_items = []
    for idx, q in enumerate(questions, start=1):
        text   = q.get("question", "").replace("\n", "<br/>")
        marks  = q.get("marks", "")
        q_text = f".{text}"
        if marks:
            q_text += f"  <i>({marks} marks)</i>"
        q_items.append(ListItem(Paragraph(q_text, question_style), leftIndent=0))

    elements.append(ListFlowable(q_items, bulletType="1", start="1", leftIndent=0))
    elements.append(Spacer(1, 12))

    # answers
    for idx, q in enumerate(questions, start=1):
        raw_answer = q.get("answer")
        answer = raw_answer.strip() if isinstance(raw_answer, str) else ""
        if answer:
            elements.append(Paragraph(f"{idx}. Answer:", answer_label))
            for line in answer.split("\n"):
                elements.append(Paragraph(line, answer_style))

    doc.build(elements)
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
            model="openai/gpt-4-turbo",
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

import tempfile


def extract_text_from_pdf(path: str) -> str:
    # 1) Try native text extraction
    text_chunks = []
    try:
        doc = fitz.open(path)
        for page in doc:
            chunk = page.get_text()
            if chunk:
                text_chunks.append(chunk)
    except Exception as e:
        print(f"[native PDF extract] error: {e}")

    full_text = "\n".join(text_chunks).strip()

    # 2) If no native text, fall back to OCR on each page image
    if not full_text:
        print("→ No native text found – falling back to OCR on PDF pages")
        try:
            pages = convert_from_path(path, dpi=300)
            ocr_texts = []
            for img in pages:
                ocr_texts.append(pytesseract.image_to_string(img))
            full_text = "\n".join(ocr_texts).strip()
        except Exception as e:
            print(f"[PDF OCR] error: {e}")

    return full_text

def extract_text_from_image(path: str) -> str:
    try:
        img = Image.open(path)
        return pytesseract.image_to_string(img).strip()
    except Exception as e:
        print(f"[image OCR] error: {e}")
        return ""

@app.post("/api/upload-question-paper")
async def upload_question_paper(file: UploadFile = File(...)):
    # 1) Save uploaded file temporarily
    suffix = os.path.splitext(file.filename)[1]
    if suffix.lower() not in [".pdf", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save error: {e}")

    # 2) Extract text
    raw = ""
    try:
        if suffix.lower() == ".pdf":
            raw = extract_text_from_pdf(tmp_path)
        else:
            raw = extract_text_from_image(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction error: {e}")
    finally:
        os.remove(tmp_path)  # Always clean up temp file

    if not raw:
        raise HTTPException(status_code=500, detail="Could not extract any text from file.")

    # 3) Try to get total number of questions (optional)
    match = re.search(r'No\.?\s*of\s*Questions\s*[:\-]?\s*(\d+)', raw, flags=re.I)
    total_q = int(match.group(1)) if match else None

    # 4) Prompt OpenAI
    n_txt = f" The paper states there are {total_q} questions." if total_q else ""
    system_prompt = f"""
        You are an assistant that receives the full text of an exam paper (including headings, instructions, passages, and questions).

        Your task is to return a JSON object in the following format:
        {{"questions": ["..."]}}

        Where:
        - Each item in the "questions" array is a full question or sub-question, in the order it appears.
        - Include ALL types of questions.
        - Remove all numbering or lettering ("1.", "(a)", etc.) from each question text.
        - DO NOT include general instructions or answers.

        {n_txt}

        Return ONLY a valid JSON object. Do not include commentary or markdown.
    """.strip()

    questions = []
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw}
            ],
            temperature=0.0,
            max_tokens=1500,
        )
        resp_content = resp.choices[0].message.content.strip()
        obj = json.loads(resp_content)
        questions = [q.strip() for q in obj["questions"] if isinstance(q, str) and q.strip()]
    except Exception as e:
        print(f"[OpenAI parse fallback] {e}")

        # Fallback regex
        fallback_matches = re.findall(
            r'(\d+\.\s+.*?(?=\n\d+\.|\Z))|(\([a-z]\)\s+.*?(?=\n\([a-z]\)|\n\d+\.|\Z))',
            raw,
            flags=re.S | re.I
        )
        questions = [m[0] or m[1] for m in fallback_matches if m[0] or m[1]]

    if not questions:
        raise HTTPException(status_code=500, detail="Could not extract questions from paper.")

    return {"questions": questions}