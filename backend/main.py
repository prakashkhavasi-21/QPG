from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pdfminer.high_level import extract_text
from pydantic import BaseModel
import fitz  # PyMuPDF for native text extraction
from pdf2image import convert_from_path
import pdfplumber
from PIL import Image, ImageEnhance
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
import google.generativeai as genai
import tempfile
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_LEFT

app = FastAPI()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Razorpay Configuration
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Gemini API Configuration
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

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

# --- Text Extraction Functions ---
# def extract_text_from_pdf(path: str) -> str:
#     text_chunks = []
#     try:
#         doc = fitz.open(path)
#         for page in doc:
#             chunk = page.get_text()
#             if chunk:
#                 text_chunks.append(chunk)
#     except Exception as e:
#         print(f"[native PDF extract] error: {e}")

#     full_text = "\n".join(text_chunks).strip()
#     if not full_text:
#         print("→ No native text found – falling back to OCR on PDF pages")
#         try:
#             pages = convert_from_path(path, dpi=300)
#             ocr_texts = []
#             for img in pages:
#                 ocr_texts.append(pytesseract.image_to_string(img))
#             full_text = "\n".join(ocr_texts).strip()
#         except Exception as e:
#             print(f"[PDF OCR] error: {e}")
#     return full_text

# def extract_text_from_image(path: str) -> str:
#     try:
#         img = Image.open(path)
#         return pytesseract.image_to_string(img).strip()
#     except Exception as e:
#         print(f"[image OCR] error: {e}")
#         return ""

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

# --- Generate Questions from Text ---
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
    # system_prompt = (
    #     f"You are a question paper generator. Based on the following text, "
    #     f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it."
    # )

    system_prompt = f"""
        You are an expert question paper generator. Based on the following text,
        If you need to add any commentary or preamble before the list of questions, that commentary **alone** may start with “A)”.
        generate {n} {types_str} question{'s' if n>1 else ''}:

        {full_text}

        Formatting rule for code snippets:
        - Whenever you wrap any part of a question in triple-backticks (```), keep the entire fence and its contents on the **same line** as the question.
        - Do NOT break the triple-backticks onto their own lines.

        If MCQs are requested:
        - Mark the correct choice with “✔” after the letter.
        - If a question contains the exact phrase “which of the following”, do not include it or mention it in any way—omit it silently.
        - If a question contains the exact phrase “which of the following is NOT”, do not include it or mention it in any way—omit it silently.
    """.strip()

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            system_prompt + "\n\n" + full_text,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=400
            )
        )
        content = response.text.strip()
        questions = [
            line.lstrip("0123456789. ").strip() for line in content.split("\n") if line.strip()
        ]
        return {"questions": questions}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

# --- Generate Answer ---
@app.post("/api/generate-answer")
async def generate_answer(req: AnswerRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    system_prompt = (
        "You are an expert tutor. "
        "Provide a clear, concise answer to the question below."
    )

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            system_prompt + "\n\n" + question,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=300
            )
        )
        answer_text = response.text.strip()
        return {"answer": answer_text}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")




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
                img = img.convert('L')  # Convert to grayscale
                img = ImageEnhance.Contrast(img).enhance(2.0)  # Increase contrast
                ocr_text = pytesseract.image_to_string(img).strip()
                ocr_texts.append(ocr_text)
            full_text = "\n".join(ocr_texts).strip()
        except Exception as e:
            print(f"[PDF OCR] error: {e}")
    return full_text

def extract_text_from_image(path: str) -> str:
    try:
        img = Image.open(path)
        img = img.convert('L')  # Convert to grayscale
        img = ImageEnhance.Contrast(img).enhance(2.0)  # Increase contrast
        text = pytesseract.image_to_string(img).strip()
        return text
    except Exception as e:
        print(f"[image OCR] error: {e}")
        return ""


# --- Upload Question Paper ---

@app.post("/api/upload-question-paper")
async def upload_question_paper(file: UploadFile = File(...)):
    """ Upload PDF/JPEG → Extract Questions → Return JSON """
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in [".pdf", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Save upload to temp file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File save error: {e}")

    # Extract text (PDF → native or OCR; image → OCR)
    try:
        if suffix == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)
        else:
            raw_text = extract_text_from_image(tmp_path)
    finally:
        os.remove(tmp_path)

    if not raw_text.strip():
        raise HTTPException(status_code=500, detail="Could not extract any text from file.")

    # Optional: detect stated number of questions
    match = re.search(r'No\.?\s*of\s*Questions\s*[:\-]?\s*(\d+)', raw_text, flags=re.I)
    total_q = int(match.group(1)) if match else None
    n_txt = f" The paper states there are {total_q} questions." if total_q else ""

    # Build system prompt
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

    # Call Gemini
    questions: list[str] = []  # ← initialize here
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([
            {"role": "user", "parts": [{"text": system_prompt}]},
            {"role": "user", "parts": [{"text": raw_text}]}
        ])
        resp_content = response.text.strip()
        print(f"[Gemini returned] >>>{resp_content}<<<")

        # strip any ```json fences
        resp_clean = re.sub(r"^```(?:json)?\s*", "", resp_content)
        resp_clean = re.sub(r"\s*```$", "", resp_clean).strip()

        if resp_clean.startswith("{"):
            try:
                obj = json.loads(resp_clean)
                questions = [
                    q.strip() for q in obj.get("questions", [])
                    if isinstance(q, str) and q.strip()
                ]
            except json.JSONDecodeError as je:
                print(f"[JSONDecodeError] {je}")
        else:
            print("[Gemini parse] cleaned response not JSON, falling back to regex")

    except Exception as e:
        print(f"[Gemini API error] {e}")

    # Fallback regex if necessary
    if not questions:
        fallback_matches = re.findall(
            r'(\d+\.\s+.*?(?=\n\d+\.|\Z))|(\([a-z]\)\s+.*?(?=\n\([a-z]\)|\n\d+\.|\Z))',
            raw_text,
            flags=re.S | re.I
        )
        questions = [m[0] or m[1] for m in fallback_matches if m[0] or m[1]]
        print(f"[Fallback regex found] {len(questions)} questions")

    if not questions:
        raise HTTPException(status_code=500, detail="Could not extract questions from paper.")

    return {"questions": questions}



# --- Upload Syllabus ---
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

# --- Generate Questions by Chapter ---
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
        f"generate {n} {types_str} question{'s' if n>1 else ''} relevant to it."
    )

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            system_prompt + "\n\n" + chapter_content,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=300
            )
        )
        raw = response.text.strip()
        questions = [
            line.lstrip("0123456789. ").strip()
            for line in raw.split("\n") if line.strip()
        ]
        return {"chapter": chapter, "questions": questions}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

# --- Generate Answer to Question ---
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
        "Only answer if relevant information is found. If not found, say 'Information not found in syllabus.'"
    )

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(
            system_prompt + f"\n\nSyllabus content:\n\n{syllabus_text}\n\nUser question: {user_question}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=400
            )
        )
        answer = response.text.strip()
        return {"question": user_question, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

# --- Export PDF ---
# @app.post("/api/export-pdf")
# async def export_pdf(request: Request):
#     data = await request.json()
#     questions = data.get("questions", [])

#     pdf_path = "generated_questions.pdf"
#     doc = SimpleDocTemplate(pdf_path, pagesize=A4,
#                             rightMargin=40, leftMargin=40,
#                             topMargin=50, bottomMargin=50)

#     styles = getSampleStyleSheet()
#     title_style = styles["Title"]
#     question_style = ParagraphStyle(
#         "Question", parent=styles["BodyText"],
#         leftIndent=10, spaceAfter=6,
#     )
#     answer_label = ParagraphStyle(
#         "AnswerLabel", parent=styles["BodyText"],
#         leftIndent=10, fontName="Helvetica-BoldOblique",
#         spaceAfter=4,
#     )
#     answer_style = ParagraphStyle(
#         "Answer", parent=styles["BodyText"],
#         leftIndent=20, textColor="#333333",
#         spaceAfter=12,
#     )

#     elements = []
#     elements.append(Paragraph("Generated Question Paper", title_style))
#     elements.append(Spacer(1, 12))

#     q_items = []
#     for idx, q in enumerate(questions, start=1):
#         text = q.get("question", "").replace("\n", "<br/>")
#         marks = q.get("marks", "")
#         q_text = f"   {text}"
#         if marks:
#             q_text += f" <i>({marks} marks)</i>"
#         q_items.append(ListItem(Paragraph(q_text, question_style), leftIndent=0))

#     elements.append(ListFlowable(q_items, bulletType="1", start="1", leftIndent=0))
#     elements.append(Spacer(1, 12))

#     for idx, q in enumerate(questions, start=1):
#         raw_answer = q.get("answer")
#         answer = raw_answer.strip() if isinstance(raw_answer, str) else ""
#         if answer:
#             elements.append(Paragraph(f"{idx}. Answer:", answer_label))
#             for line in answer.split("\n"):
#                 elements.append(Paragraph(line, answer_style))

#     doc.build(elements)
#     return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path)


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

    # Styles
    question_style_normal = ParagraphStyle(
        "QuestionNormal",
        parent=styles["BodyText"],
        leftIndent=0,
        spaceAfter=6,
        fontName="Helvetica"
    )

    question_style_bold = ParagraphStyle(
        "QuestionBold",
        parent=styles["BodyText"],
        leftIndent=0,
        spaceAfter=6,
        fontName="Helvetica-Bold"
    )

    answer_style = ParagraphStyle(
        "Answer",
        parent=styles["BodyText"],
        leftIndent=15,
        spaceAfter=4,
        fontName="Helvetica"
    )

    elements = []
    elements.append(Paragraph("Generated Question Paper", title_style))
    elements.append(Spacer(1, 12))

    # Go through each question
    for q in questions:
        text = q.get("question", "").replace("\n", "<br/>")
        marks = q.get("marks", "")

        # Check if ends with ?
        style = question_style_bold if text.strip().endswith('?') else question_style_normal

        q_text = f" {text}"
        if marks:
            q_text += f" <i>({marks} marks)</i>"

        # Add the question (NO numbering)
        elements.append(Paragraph(q_text, style))

        # If answer/choices present, show directly below (NO numbering)
        raw_answer = q.get("answer")
        answer = raw_answer.strip() if isinstance(raw_answer, str) else ""
        if answer:
            for line in answer.split("\n"):
                elements.append(Paragraph(line.strip(), answer_style))

        elements.append(Spacer(1, 6))  # small gap between Qs

    doc.build(elements)
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path)


# --- Static Files and React App ---
tessdata_dir = os.path.join(os.getcwd(), 'tessdata')
os.environ['TESSDATA_PREFIX'] = tessdata_dir

app.mount("/static", StaticFiles(directory="frontend/dist", html=True), name="static")

@app.get("/{full_path:path}")
async def serve_react_app():
    return HTMLResponse(open("frontend/dist/index.html").read())