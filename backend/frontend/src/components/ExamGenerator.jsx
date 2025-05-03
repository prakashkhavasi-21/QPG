// src/components/ExamGenerator.jsx
import React, { useState, useEffect } from 'react';
import { Link, useNavigate  } from 'react-router-dom';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { db }                         from '../firebase';
import { auth }                       from '../firebase';
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'


export default function ExamGenerator({ user }) {
  // --- State hooks ---
  const [examTitle, setExamTitle] = useState('');
  const [duration, setDuration] = useState(60);
  const [numQuestions, setNumQuestions] = useState(5);
  const [questionTypes, setQuestionTypes] = useState({
    mcq: false,
    shortAnswer: true,
    longAnswer: false,
  });
  const [mode, setMode] = useState('paste');
  const [topics, setTopics] = useState([{ id: Date.now(), name: '', marks: '' }]);
  const [pasteText, setPasteText] = useState('');
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [chapterRequests, setChapterRequests] = useState([
    { id: Date.now(), chapter: '', numQuestions: 5, marks: 5, selected: true },
  ]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loginPrompt, setLoginPrompt] = useState(false);

  const navigate = useNavigate();
  const [credits, setCredits] = useState(null);
  const [subscriptionExpires, setSubscriptionExpires] = useState(null);

  const [questionPaperFile, setQuestionPaperFile] = useState(null);

  //const API_URL = "http://localhost:8001";
  //const API_URL = "https://qpg-4e99a2de660c.herokuapp.com";
  const API_URL = "https://www.qnagenai.com";

  // Reset prompt if user logs in
  useEffect(() => {
    if (user && loginPrompt) {
      setLoginPrompt(false);
    }
  }, [user, loginPrompt]);

   // 1) On mount: fetch (or init) your free credit
  useEffect(() => {
    const loadCredits = async () => {
      const ref = doc(db, 'users', user.uid);
      const snap = await getDoc(ref);
      if (snap.exists()) {
        setCredits(snap.data().credits);

        const expires = snap.data().subscriptionExpires;
        setSubscriptionExpires(expires ? new Date(expires.seconds * 1000) : null);
      } else {
        // first-time login via Google: give 1 free credit
        await setDoc(ref, { credits: 1, subscriptionExpires: null });
        setCredits(1);
      }
    };
    loadCredits();
  }, [user, navigate]);

  // --- Helpers for manual topics ---
  const addTopic = () =>
    setTopics(prev => [...prev, { id: Date.now(), name: '', marks: '' }]);
  const updateTopic = (id, field, value) =>
    setTopics(prev =>
      prev.map(t => (t.id === id ? { ...t, [field]: value } : t))
    );
  const removeTopic = id =>
    setTopics(prev => prev.filter(t => t.id !== id));

  // --- Helpers for multi-chapter ---
  const addChapter = () =>
    setChapterRequests(prev => [
      ...prev,
      { id: Date.now(), chapter: '', numQuestions: 5, marks: 5, selected: true },
    ]);
  const updateChapter = (id, field, value) =>
    setChapterRequests(prev =>
      prev.map(c => (c.id === id ? { ...c, [field]: value } : c))
    );
  const removeChapter = id =>
    setChapterRequests(prev => prev.filter(c => c.id !== id));

  // --- File upload (multi-chapter) ---
  const handleUpload = async () => {
    if (!syllabusFile) throw new Error('Please upload a syllabus PDF.');
    const fd = new FormData();
    fd.append('file', syllabusFile);
    const res = await fetch(`${API_URL}/api/upload-syllabus`, {
      method: 'POST',
      body: fd,
    });
    if (!res.ok) throw new Error('Upload failed');
    await res.json();
  };

  // --- Generate Questions ---
  const generate = async () => {
    setLoading(true);
    setError('');
    setQuestions([]);
    try {
      // Build types array
      if (credits > 0 || (subscriptionExpires && subscriptionExpires > new Date())) {
        // use one credit
        const ref = doc(db, 'users', user.uid);
        if(credits > 0){
          await updateDoc(ref, { credits: credits - 1 });
          setCredits(credits - 1);
        }

        const types = [];
        if (questionTypes.mcq) types.push('MCQ');
        if (questionTypes.shortAnswer) types.push('short answer');
        if (questionTypes.longAnswer) types.push('long answer');
        if (!types.length) throw new Error('Select at least one question type.');

        // Manual topics flow
        if (mode === 'manual') {
          const listText = topics
            .map(t => `${t.name} (${t.marks} marks)`)
            .join('\n');
          const payload = {
            text: `Exam: ${examTitle}\nDuration: ${duration} mins\n${listText}`,
            numQuestions,
            mcq: questionTypes.mcq,
            shortAnswer: questionTypes.shortAnswer,
            longAnswer: questionTypes.longAnswer
          };
          const res = await fetch(`${API_URL}/api/nlp-generate-questions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (!res.ok) throw new Error('Generation failed');
          const { questions } = await res.json();
          setQuestions(questions.map(q => ({ question: q, marks: null })));
          return;
        }

        // Paste text flow
        if (mode === 'paste') {
          const payload = {
            text: pasteText,
            numQuestions,
            mcq: questionTypes.mcq,
            shortAnswer: questionTypes.shortAnswer,
            longAnswer: questionTypes.longAnswer
          };
          const res = await fetch(`${API_URL}/api/nlp-generate-questions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (!res.ok) throw new Error('Generation failed');
          const { questions } = await res.json();
          setQuestions(questions.map(q => ({ question: q, marks: null, showAnswer: false, answer: null })));
          return;
        }

        // Multiple chapters flow
        if (mode === 'multi') {
          await handleUpload();
          const aggregated = [];
          for (const c of chapterRequests.filter(x => x.selected && x.chapter.trim())) {
            const res = await fetch(`${API_URL}/api/nlp-generate-questions-by-chapter`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                chapter: c.chapter,
                numQuestions: c.numQuestions,
                mcq: questionTypes.mcq,
                shortAnswer: questionTypes.shortAnswer,
                longAnswer: questionTypes.longAnswer
              })
            });
            if (!res.ok) throw new Error(`Generation failed for ${c.chapter}`);
            const { questions } = await res.json();
            questions.forEach(q => aggregated.push({ question: q, marks: c.marks }));
          }
          setQuestions(aggregated);
          return;
        }

        if (mode === 'questionPaper') {
          if (!questionPaperFile) {
            throw new Error("Please upload a question‐paper PDF first.");
          }
          // Build form data & call your endpoint
          const fd = new FormData();
          fd.append('file', questionPaperFile);
          const res = await fetch(`${API_URL}/api/upload-question-paper`, {
            method: 'POST',
            body: fd,
          });
          if (!res.ok) throw new Error("Failed to extract questions from paper.");
          const { questions: qs } = await res.json();
          // Wrap into your UI shape:
          setQuestions(qs.map(q => ({
            question:    q,
            showAnswer:  false,
            answer:      '',
            loadingAnswer: false
          })));
          return;
        }
      }
      else if (!user) {
        return setLoginPrompt(true);
        } else {
        alert('You have no free credits left. Please subscribe for ₹99/month.'); 
      }
    } catch (e) {
      console.error(e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };


  const generateAnswer = async (idx) => {
    const qText = questions[idx].question;
    setQuestions(q =>
      q.map((item, i) =>
        i === idx ? { ...item, showAnswer: false, answer: '', loadingAnswer: true } : item
      )
    );



    try {
      const res = await fetch(`${API_URL}/api/generate-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: qText })
      });
      const { answer } = await res.json();

      setQuestions(q =>
        q.map((item, i) =>
          i === idx
            ? { ...item, answer, showAnswer: true, loadingAnswer: false }
            : item
        )
      );
    } catch (e) {
      console.error(e);
      setError('Failed to generate answer');
      setQuestions(q =>
        q.map((item, i) =>
          i === idx ? { ...item, loadingAnswer: false } : item
        )
      );
    }
  };

  const collapseAnswer = (idx) => {
    const updatedQuestions = [...questions];
    updatedQuestions[idx].showAnswer = false;
    setQuestions(updatedQuestions);
  };

  // --- Download PDF ---
  const downloadPdf = async () => {
    try {
      const res = await fetch(`${API_URL}/api/export-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ questions }),
      });
      if (!res.ok) throw new Error('PDF export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'questions.pdf';
      a.click();
    } catch (e) {
      console.error(e);
      setError('Failed to download PDF');
    }
  };



  return (
    <div className="container my-5 pt-5">
      <div className="card shadow">
        <div className="card-header">
          <h4 className="mb-0">Generate Questions and Answers</h4>          
          {/* <h4>
          <strong>
            {subscriptionExpires === null
              ? 'No Subscription'
              : `Expires on: ${subscriptionExpires.toLocaleDateString('en-IN')}`}
          </strong>
        </h4>        */}
        </div>
        <div className="card-body">
          {/* Settings */}
          <div className="row g-3 mb-4">
            <div className="col-md-4">
              <label className="form-label">Title</label>
              <input
                type="text"
                className="form-control"
                value={examTitle}
                onChange={e => setExamTitle(e.target.value)}
                placeholder="Exam Title"
              />
            </div>
            <div className="col-md-4">
              <label className="form-label">Duration (mins)</label>
              <input
                type="number"
                className="form-control"
                value={duration}
                onChange={e => setDuration(+e.target.value)}
              />
            </div>
            <div className="col-md-4">
              <label className="form-label"># Questions</label>
              <input
                type="number"
                className="form-control"
                value={numQuestions}
                onChange={e => setNumQuestions(+e.target.value)}
              />
            </div>
          </div>

          {/* Question Types */}
          <div className="mb-4">
            {['mcq', 'shortAnswer', 'longAnswer'].map(key => (
              <div className="form-check form-check-inline" key={key}>
                <input
                  className="form-check-input"
                  type="checkbox"
                  id={key}
                  checked={questionTypes[key]}
                  onChange={e =>
                    setQuestionTypes(prev => ({ ...prev, [key]: e.target.checked }))
                  }
                />
                <label className="form-check-label" htmlFor={key}>
                  {key === 'mcq'
                    ? 'MCQ'
                    : key === 'shortAnswer'
                    ? 'Short Answer'
                    : 'Long Answer'}
                </label>
              </div>
            ))}
          </div>

          {/* Mode Selection */}
          <div className="mb-4">
            {['paste', 'multi','questionPaper'].map(m => (
              <div className="form-check form-check-inline" key={m}>
                <input
                  className="form-check-input"
                  type="radio"
                  name="mode"
                  id={m}
                  value={m}
                  checked={mode === m}
                  onChange={() => setMode(m)}
                />
                <label className="form-check-label" htmlFor={m}>
                  {m === 'paste' ? 'Enter Your Text' : m === 'multi' ? 'Upload Syllabus' : 'Upload Question Paper'}
                </label>
              </div>
            ))}
          </div>

          

          {/* Paste Text */}
          {mode === 'paste' && (
            <div className="mb-4">
              <textarea
                rows={6}
                className="form-control"
                placeholder="Enter text..."
                value={pasteText}
                onChange={e => setPasteText(e.target.value)}
              />
            </div>
          )}

          {/* Multiple Chapters */}
          {mode === 'multi' && (
            <>
              <div className="mb-3">
                <label className="form-label">Upload Syllabus PDF</label>
                <input
                  type="file"
                  accept=".pdf"
                  className="form-control"
                  onChange={e => setSyllabusFile(e.target.files[0])}
                />
              </div>
              <table className="table table-bordered mb-3">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Topic Name</th>
                    <th>#Q</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {chapterRequests.map(c => (
                    <tr key={c.id}>
                      <td className="text-center" style={{ width: '10%' }}>
                        <input
                          type="checkbox"
                          className="form-check-input"
                          checked={c.selected}
                          onChange={e => updateChapter(c.id, 'selected', e.target.checked)}
                        />
                      </td>
                      <td style={{ width: '60%' }}>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="Chapter name"
                          value={c.chapter}
                          onChange={e => updateChapter(c.id, 'chapter', e.target.value)}
                        />
                      </td>
                      <td style={{ width: '25%' }}>
                        <input
                          type="number"
                          className="form-control"
                          value={c.numQuestions}
                          onChange={e => updateChapter(c.id, 'numQuestions', e.target.value)}
                        />
                      </td>
                      <td style={{ display: 'none' }}>
                        <input
                          type="number"
                          className="form-control"
                          value={c.marks}
                          onChange={e => updateChapter(c.id, 'marks', e.target.value)}
                        />
                      </td>
                      <td className="text-center" style={{ width: '10%' }}>
                        <button
                          className="btn btn-sm btn-outline-danger"
                          onClick={() => removeChapter(c.id)}
                        >
                          &times;
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn btn-sm btn-success mb-4" onClick={addChapter}>
                + Add Chapter
              </button>
            </>
          )}

            {/* Upload Question Paper */}
            {mode === 'questionPaper' && (
              <div className="mb-3">
                <label className="form-label">Upload Question Paper PDF</label>
                <input
                  type="file"
                  accept=".pdf, .jpg, .jpeg"
                  className="form-control"
                  onChange={e => {
                    setError('');
                    setQuestions([]);
                    setQuestionPaperFile(e.target.files[0] || null);
                  }}
                />
              </div>
            )}

          {/* Error */}
          {error && <div className="alert alert-danger">{error}</div>}

          {/* Login Prompt */}
          {loginPrompt && (
            <div className="alert alert-warning d-flex justify-content-between align-items-center">
              <span>Please sign in to generate questions.</span>
              <Link to="/auth" className="btn btn-sm btn-primary">
                Sign In
              </Link>
            </div>
          )}

          {/* Actions */}
          <div className="d-flex gap-2 mb-4">
            <button className="btn btn-primary" onClick={generate} disabled={loading}>
              {loading ? 'Generating...' : 'Generate Questions'}
            </button>
            {questions.length > 0 && (
              <button className="btn btn-success" onClick={downloadPdf}>
                Download PDF
              </button>
            )}
          </div>

            {questions.length > 0 && (
              <div className="mt-5">
                <h5>Generated Questions:</h5>
                {questions.map((q, idx) => {
                  // Detect MCQ by looking for lines like "A. option"
                  const lines = q.question.split('\n');
                  const isMCQ = lines.some(line => /^[-\s]*[A-Za-z0-9][).]\s+/.test(line.trim()));

                  

                  return (
                    <div key={idx} className="card mb-3">
                      <div className="card-body" style={{ overflowX: 'hidden' }}>
                        
                        {isMCQ ? (
                          <h6>{lines[0]}</h6>
                        ):(
                          <h6>Q{idx + 1}. {lines[0]}</h6>
                        )}

                        {/* Render MCQ options */}
                        {isMCQ && (
                          <div className="mt-2">
                            {lines.slice(1).map((opt, i) => (
                              <div key={i} className="form-check">
                                <input
                                  className="form-check-input"
                                  type="radio"
                                  name={`q${idx}`}
                                  id={`q${idx}_opt${i}`}
                                />
                                <label className="form-check-label" htmlFor={`q${idx}_opt${i}`}>
                                  {opt}
                                </label>
                              </div>
                            ))}
                          </div>
                        )}

                      

                        {/* Render "Generate Answer" button only for non-MCQs */}
                        {!isMCQ && !q.showAnswer && (
                          <button
                            className="btn btn-sm btn-primary mt-2"
                            onClick={() => generateAnswer(idx)}
                            disabled={q.loadingAnswer}
                          >
                            {q.loadingAnswer ? 'Generating...' : 'Generate Answer'}
                          </button>
                        )}

                        {/* Render the answer if available */}
                        {/* {q.showAnswer && (
                          <div
                            className="alert alert-success mt-3 text-break mw-100 w-100"
                            style={{
                              maxWidth: '100%',
                              wordBreak: 'break-word',      // forces breaks even inside long strings
                              overflowWrap: 'break-word',  // wrap at word boundaries when possible
                              whiteSpace: 'pre-wrap',      // preserve manual line breaks
                            }}
                          >
                            <strong>Answer:</strong>
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                code({ node, inline, className, children, ...props }) {
                                  if (inline) {
                                    return <code {...props} className={className}>{children}</code>;
                                  }
                                  return (
                                    <pre
                                      {...props}
                                      className="p-2 rounded overflow-auto text-break"
                                      style={{
                                        backgroundColor: '#d4edda',
                                        padding: '5px',
                                        borderRadius: '4px',
                                        overflowX: 'auto',
                                        maxWidth: '100%',
                                        overflowX: 'auto',
                                        wordBreak: 'pre-wrap',
                                      }}
                                    >
                                      <code className={className}>{children}</code>
                                    </pre>
                                  );
                                },
                              }}
                            >
                              {q.answer}
                            </ReactMarkdown>
                          </div>
                          
                        )} */}

                        {q.showAnswer && (
                          <div className="alert alert-success mt-3 answer-container">
                            <strong>Answer:</strong>
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                code({ inline, className, children, ...props }) {
                                  if (inline) {
                                    return <code {...props} className={className}>{children}</code>;
                                  }
                                  return (
                                    <pre {...props}>
                                      <code className={className}>{children}</code>
                                    </pre>
                                  );
                                }
                              }}
                            >
                              {q.answer}
                            </ReactMarkdown>
                          </div>
                        )}
                      </div>
                      {/* Add the "X" button */}
                      {!isMCQ && q.showAnswer && (
                        <button
                          className="btn btn-sm position-absolute"
                          style={{ bottom: '2px', right: '2px', backgroundColor: 'orange', color: 'white', border: 'none' }}
                          onClick={() => collapseAnswer(idx)}
                        >
                          X
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
