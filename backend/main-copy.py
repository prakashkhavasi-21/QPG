
from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pdfminer.high_level import extract_text
from pydantic import BaseModel
import pdfkit
import openai
import os
import re
#from dotenv import load_dotenv

# Load environment variables
#load_dotenv()

# Configure OpenAI / OpenRouter

#openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = "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"
openai.api_base = "https://openrouter.ai/api/v1"


# PDFKit configuration
PDFKIT_CONFIG = pdfkit.configuration(
    wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_PDF = "temp_syllabus.pdf"
SYLLABUS_TXT = "syllabus.txt"

@app.get("/")
def read_root():
    return {"message": "Backend is running"}

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
# Generate questions from arbitrary text
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


# --- Export PDF ---
@app.post("/api/export-pdf")
async def export_pdf(request: Request):
    data = await request.json()
    questions = data.get("questions", [])

    html = "<html><head><meta charset='utf-8'></head><body>"
    html += "<h1>Generated Question Paper</h1><ol>"

    for q in questions:
        text = q.get("question", "").replace("\n", "<br/>")
        marks = q.get("marks")
        if marks is not None and marks != "":
            html += f"<li>{text} <em>({marks} marks)</em></li>"
        else:
            html += f"<li>{text}</li>"

    html += "</ol></body></html>"

    pdf_bytes = pdfkit.from_string(html, False, configuration=PDFKIT_CONFIG)
    pdf_path = "generated_questions.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path)