from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pdfminer.high_level import extract_text
from pydantic import BaseModel
import fitz  # PyMuPDF for native text extraction
from pdf2image import convert_from_path
import pdfplumber
from PIL import Image
import pytesseract
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_LEFT
import tempfile
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

app = FastAPI()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Razorpay Configuration
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Qwen 3 Model Setup
MODEL_NAME = "Qwen/Qwen3-8B"
device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    device_map="auto"
)
model.eval()

# CORS Middleware
origins = [
    "https://www.qnagenai.com",
    "https://qpg-4e99a2de660c.herokuapp.com",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_PDF = "temp_syllabus.pdf"
SYLLABUS_TXT = "syllabus.txt"

# Fake in-memory user data store
fake_users_db = {}

# --- User Management ---
class User(BaseModel):
    username: str
    email: str
    is_subscribed: bool = False
    credits_left: int = 1

@app.post("/api/register-user")
async def register_user(user: User):
    fake_users_db[user.email] = user
    return {"message": "User registered successfully", "user": user}

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
        payment_order = razorpay_client.order.create(dict(
            amount=int(order.amount * 100),
            currency='INR',
            payment_capture='1'
        ))
        return {"order_id": payment_order['id'], "amount": order.amount}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment order creation failed: {e}")

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

class QuestionIn(BaseModel):
    question: str

class AnswerRequest(BaseModel):
    question: str

# --- Helper Functions ---
def extract_text_from_pdf(path: str) -> str:
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

def generate_qwen_response(prompt, max_tokens=400, use_thinking_mode=True):
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": f"{'/think' if use_thinking_mode else '/no_think'} {prompt}"}
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(device)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_tokens,
        temperature=0.7,
        top_p=0.9,
        do_sample=True
    )
    response = tokenizer.decode(outputs[0][len(inputs.input_ids[0]):], skip_special_tokens=True)
    return response.strip()

# --- Endpoints ---
@app.post("/api/upload-syllabus")
async def upload_syllabus(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in [".pdf", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type. Only PDF, JPG or JPEG allowed.")
    contents = await file.read()
    if suffix == ".pdf":
        with open(TEMP_PDF, "wb") as f:
            f.write(contents)
        text = extract_text_from_pdf(TEMP_PDF)
        if not text.strip():
            text = extract_text_from_image(TEMP_PDF)
    else:
        image_path = f"temp_syllabus_image{suffix}"
        with open(image_path, "wb") as f:
            f.write(contents)
        text = extract_text_from_image(image_path)
        os.remove(image_path)
    if not text.strip():
        raise HTTPException(status_code=500, detail="Could not extract any text from file.")
    with open(SYLLABUS_TXT, "w", encoding="utf-8") as f:
        f.write(text)
    return {"text": text}

@app.post("/api/nlp-generate-questions")
async def generate_questions(payload: TextIn):
    full_text = payload.text.strip()
    if not full_text:
        raise HTTPException(status_code=400, detail="No text provided.")
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
        f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it. "
        f"Return only the questions, one per line, without numbering."
    )
    try:
        response = generate_qwen_response(f"{system_prompt}\n\nText:\n{full_text}", max_tokens=400)
        questions = [q.strip() for q in response.split("\n") if q.strip()]
        return {"questions": questions[:n]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qwen 3 inference error: {e}")

@app.post("/api/upload-question-paper")
async def upload_question_paper(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in [".pdf", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save error: {e}")
    raw_text = ""
    try:
        if suffix == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)
        else:
            raw_text = extract_text_from_image(tmp_path)
    finally:
        os.remove(tmp_path)
    if not raw_text:
        raise HTTPException(status_code=500, detail="Could not extract any text from file.")
    match = re.search(r'No\.?\s*of\s*Questions\s*[:\-]?\s*(\d+)', raw_text, flags=re.I)
    total_q = int(match.group(1)) if match else None
    n_txt = f" The paper states there are {total_q} questions." if total_q else ""
    system_prompt = f"""
        You are an assistant that receives the full text of an exam paper (including headings, instructions, passages, and questions).
        Your task is to return a JSON object: {{"questions": ["..."]}}
        Where:
        - Each item in the "questions" array is a full question or sub-question, in order.
        - Include ALL types of questions.
        - Remove all numbering or lettering ("1.", "(a)", etc.) from each question text.
        - DO NOT include general instructions or answers.
        {n_txt}
        Return ONLY a valid JSON object.
    """.strip()
    try:
        response = generate_qwen_response(system_prompt + f"\n\n{raw_text}", max_tokens=1500, use_thinking_mode=False)
        obj = json.loads(response)
        questions = [q.strip() for q in obj.get("questions", []) if isinstance(q, str) and q.strip()]
    except Exception as e:
        print(f"[Qwen 3 parse fallback] {e}")
        fallback_matches = re.findall(
            r'(\d+\.\s+.*?(?=\n\d+\.|\Z))|(\([a-z]\)\s+.*?(?=\n\([a-z]\)|\n\d+\.|\Z))',
            raw_text,
            flags=re.S | re.I
        )
        questions = [m[0] or m[1] for m in fallback_matches if m[0] or m[1]]
    if not questions:
        raise HTTPException(status_code=500, detail="Could not extract questions from paper.")
    return {"questions": questions}

@app.post("/api/nlp-generate-questions-by-chapter")
async def generate_questions_by_chapter(payload: ChapterIn):
    chapter = payload.chapter.strip()
    n = payload.numQuestions
    types = []
    if payload.mcq: types.append("MCQ")
    if payload.shortAnswer: types.append("short answer")
    if payload.longAnswer: types.append("long answer")
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
    next_units = [
        m.start() for m in re.finditer(r"(?:unit[\s\-]*\d+\b)", text_lower)
        if m.start() > start_idx
    ]
    end_idx = next_units[0] if next_units else len(syllabus_text)
    chapter_content = syllabus_text[start_idx:end_idx].strip()
    system_prompt = (
        f"You are an expert question generator. Based on the following syllabus section, "
        f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it. "
        f"Return only the questions, one per line, without numbering."
    )
    try:
        response = generate_qwen_response(f"{system_prompt}\n\n{chapter_content}", max_tokens=300)
        questions = [q.strip() for q in response.split("\n") if q.strip()]
        return {"chapter": chapter, "questions": questions[:n]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qwen 3 inference error: {e}")

@app.post("/api/generate-answer")
async def generate_answer(req: AnswerRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")
    system_prompt = (
        "You are an expert tutor. Provide a clear, concise answer to the following question."
    )
    try:
        response = generate_qwen_response(f"{system_prompt}\n\nQuestion: {question}", max_tokens=300)
        return {"answer": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qwen 3 inference error: {e}")

@app.post("/api/nlp-generate-answer-to-question")
async def generate_answer_to_question(payload: QuestionIn):
    user_question = payload.question.strip()
    if not user_question:
        raise HTTPException(status_code=400, detail="Question is required.")
    try:
        syllabus_text = open(SYLLABUS_TXT, "r", encoding="utf-8").read()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No syllabus uploaded.")
    system_prompt = (
        "You are an expert academic assistant. Using the provided syllabus content, "
        "answer the user's question clearly, concisely, and accurately. "
        "If no relevant information is found, say 'Information not found in syllabus.'"
    )
    try:
        response = generate_qwen_response(
            f"{system_prompt}\n\nSyllabus content:\n{syllabus_text}\n\nUser question: {user_question}",
            max_tokens=400
        )
        return {"question": user_question, "answer": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qwen 3 inference error: {e}")

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
    option_style = ParagraphStyle(
        "Option", parent=styles["BodyText"],
        leftIndent=20, spaceAfter=4,
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
    q_items = []

    for idx, q in enumerate(questions, start=1):
        text = q.get("question", "").replace("\n", "<br/>")
        marks = q.get("marks", "")

        # Split the question into lines to check for MCQ format
        lines = text.split("<br/>")
        is_mcq = any(re.match(r'^[A-Da-d1-4][).]\s+', line.strip()) for line in lines[1:])

        if is_mcq:
            # Extract the question stem (first line) and options (remaining lines)
            question_text = lines[0].strip()
            q_text = f".{question_text}"
            if marks:
                q_text += f"  <i>({marks} marks)</i>"
            
            # Create the question stem as a ListItem
            question_item = ListItem(Paragraph(q_text, question_style), leftIndent=0)

            # Create a nested list for options
            option_items = []
            for opt in lines[1:]:
                opt = opt.strip()
                if opt and re.match(r'^[A-Da-d1-4][).]\s+', opt):
                    option_items.append(ListItem(Paragraph(opt, option_style), leftIndent=10))
            
            # Combine the question and options into a nested ListFlowable
            nested_list = ListFlowable(option_items, bulletType='bullet', start='circle', leftIndent=20)
            q_items.append([question_item, nested_list])
        else:
            # Non-MCQ question: treat as a single paragraph
            q_text = f".{text}"
            if marks:
                q_text += f"  <i>({marks} marks)</i>"
            q_items.append(ListItem(Paragraph(q_text, question_style), leftIndent=0))

    # Add the questions list to elements
    elements.append(ListFlowable([item if isinstance(item, ListItem) else ListFlowable(item, bulletType='1') for item in q_items], bulletType="1", start="1", leftIndent=0))
    elements.append(Spacer(1, 12))

    # Add answers if present
    for idx, q in enumerate(questions, start=1):
        raw_answer = q.get("answer")
        answer = raw_answer.strip() if isinstance(raw_answer, str) else ""
        if answer:
            elements.append(Paragraph(f"{idx}. Answer:", answer_label))
            for line in answer.split("\n"):
                elements.append(Paragraph(line, answer_style))

    doc.build(elements)
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path)

# Serve static assets
app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")

@app.get("/{full_path:path}")
async def serve_react_app():
    return HTMLResponse(open("frontend/dist/index.html").read())