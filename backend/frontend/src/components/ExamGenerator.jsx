import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { doc, getDoc, setDoc, updateDoc } from 'firebase/firestore';
import { db, auth } from '../firebase';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  const [syllabusmode, setSyllabusMode] = useState('chapter');
  const [topics, setTopics] = useState([{ id: Date.now(), name: '', marks: '' }]);
  const [pasteText, setPasteText] = useState('');
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [chapterRequests, setChapterRequests] = useState([
    { id: Date.now(), chapter: '', numQuestions: 5, marks: 5, selected: true },
  ]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingAnswers, setLoadingAnswers] = useState(false);
  const [error, setError] = useState('');
  const [loginPrompt, setLoginPrompt] = useState(false);
  const [answers, setAnswers] = useState([]);
  const navigate = useNavigate();
  const [credits, setCredits] = useState(null);
  const [subscriptionExpires, setSubscriptionExpires] = useState(null);
  const [questionPaperFile, setQuestionPaperFile] = useState(null);
  const [questionRequests, setQuestionRequests] = useState([
    { id: Date.now(), question: '', selected: true },
  ]);

  //const API_URL = "http://localhost:8001";
  const API_URL = "https://www.qnagenai.com";

  // Reset prompt if user logs in
  useEffect(() => {
    if (user && loginPrompt) {
      setLoginPrompt(false);
    }
  }, [user, loginPrompt]);

  // Reset syllabusmode if we leave multi
  useEffect(() => {
    if (mode !== 'multi') setSyllabusMode('chapter');
  }, [mode]);

  // Compute whether to show the main "Generate Questions" button
  const showGenerate = !(mode === 'multi' && syllabusmode === 'question');

  // On mount: fetch (or init) your free credit
  useEffect(() => {
    const loadCredits = async () => {
      const ref = doc(db, 'users', user.uid);
      const snap = await getDoc(ref);
      if (snap.exists()) {
        setCredits(snap.data().credits);
        const expires = snap.data().subscriptionExpires;
        setSubscriptionExpires(expires ? new Date(expires.seconds * 1000) : null);
      } else {
        const expiryDate = new Date();
        const expiryDate1 = expiryDate.getMonth() + 1;
        await setDoc(ref, { credits: 10, subscriptionExpires: expiryDate1 });
        setCredits(10);
      }
    };
    if (user) loadCredits();
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

  const addQuestion = () =>
    setQuestionRequests(prev => [
      ...prev,
      { id: Date.now(), question: '', selected: true },
    ]);

  const updateQuestion = (id, field, value) =>
    setQuestionRequests(prev =>
      prev.map(c => (c.id === id ? { ...c, [field]: value } : c))
    );

  const removeQuestion = id =>
    setQuestionRequests(prev => prev.filter(c => c.id !== id));

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
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error('Upload failed: ' + errorText);
    }
    await res.json();
  };

  // --- Handle question type selection ---
  const handleQuestionTypeChange = (type) => {
    setQuestionTypes({
      mcq: type === 'mcq',
      shortAnswer: type === 'shortAnswer',
      longAnswer: type === 'longAnswer',
    });
  };

  // --- Generate Questions ---
  const generate = async () => {
    setLoading(true);
    setError('');
    setQuestions([]);
    try {
      if (!user) {
        setLoginPrompt(true);
        return;
      }

      if (credits <= 0) {
        throw new Error('You have no credits left. Please subscribe for ₹49/month.');
        return;
      }

      const ref = doc(db, 'users', user.uid);
      await updateDoc(ref, { credits: credits - 1 });
      setCredits(credits - 1);

      if (subscriptionExpires && subscriptionExpires < new Date()) {
        await updateDoc(ref, { credits: 0 });
        setCredits(0);
        throw new Error('Your subscription has expired.');
      }

      const types = [];
      if (questionTypes.mcq) types.push('MCQ');
      if (questionTypes.shortAnswer) types.push('short answer');
      if (questionTypes.longAnswer) types.push('long answer');
      if (!types.length) throw new Error('Select a question type.');

      if (mode === 'manual') {
        const listText = topics
          .filter(t => t.name.trim() && t.marks)
          .map(t => `${t.name} (${t.marks} marks)`)
          .join('\n');
        if (!listText) throw new Error('Please provide at least one valid topic with marks.');
        if (numQuestions <= 0) throw new Error('Number of questions must be greater than 0.');
        const payload = {
          text: `Exam: ${examTitle}\nDuration: ${duration} mins\n${listText}`,
          numQuestions,
          mcq: questionTypes.mcq,
          shortAnswer: questionTypes.shortAnswer,
          longAnswer: questionTypes.longAnswer
        };
        console.log('Manual Mode Payload:', payload);
        const res = await fetch(`${API_URL}/api/nlp-generate-questions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) {
          const errorText = await res.text();
          console.error('API Error:', errorText);
          throw new Error('Generation failed: ' + errorText);
        }
        const { questions } = await res.json();
        setQuestions(questions.map(q => ({ question: q, marks: null })));
        return;
      }

      if (mode === 'paste') {
        if (!pasteText.trim()) throw new Error('Please enter text to generate questions.');
        if (numQuestions <= 0) throw new Error('Number of questions must be greater than 0.');
        const payload = {
          text: pasteText,
          numQuestions,
          mcq: questionTypes.mcq,
          shortAnswer: questionTypes.shortAnswer,
          longAnswer: questionTypes.longAnswer
        };
        console.log('Paste Mode Payload:', payload);
        const res = await fetch(`${API_URL}/api/nlp-generate-questions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) {
          const errorText = await res.text();
          console.error('API Error:', errorText);
          throw new Error('Generation failed: ' + errorText);
        }
        const { questions } = await res.json();
        setQuestions(questions.map(q => ({ question: q, marks: null, showAnswer: false, answer: null })));
        return;
      }

      if (mode === 'multi') {
        await handleUpload();
        const aggregated = [];
        const validChapters = chapterRequests.filter(x => x.selected && x.chapter.trim() && x.numQuestions > 0);
        if (!validChapters.length) throw new Error('Please provide at least one valid chapter.');
        for (const c of validChapters) {
          const payload = {
            chapter: c.chapter,
            numQuestions: c.numQuestions,
            mcq: questionTypes.mcq,
            shortAnswer: questionTypes.shortAnswer,
            longAnswer: questionTypes.longAnswer
          };
          console.log('Multi Mode Payload for Chapter:', payload);
          const res = await fetch(`${API_URL}/api/nlp-generate-questions-by-chapter`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          if (!res.ok) {
            const errorText = await res.text();
            console.error('API Error:', errorText);
            throw new Error(`Generation failed for ${c.chapter}: ${errorText}`);
          }
          const { questions } = await res.json();
          questions.forEach(q => aggregated.push({ question: q, marks: c.marks }));
        }
        setQuestions(aggregated);
        return;
      }

      if (mode === 'questionPaper') {
        if (!questionPaperFile) {
          throw new Error('Please upload a question paper PDF first.');
        }
        const fd = new FormData();
        fd.append('file', questionPaperFile);
        const res = await fetch(`${API_URL}/api/upload-question-paper`, {
          method: 'POST',
          body: fd,
        });
        if (!res.ok) {
          const errorText = await res.text();
          console.error('API Error:', errorText);
          throw new Error('Failed to extract questions from paper: ' + errorText);
        }
        const { questions: qs } = await res.json();
        setQuestions(qs.map(q => ({
          question: q,
          showAnswer: false,
          answer: '',
          loadingAnswer: false
        })));
        return;
      }
    } catch (e) {
      console.error('Generate Error:', e);
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
      if (!res.ok) {
        const errorText = await res.text();
        console.error('API Error:', errorText);
        throw new Error('Answer generation failed: ' + errorText);
      }
      const { answer } = await res.json();
      setQuestions(q =>
        q.map((item, i) =>
          i === idx
            ? { ...item, answer, showAnswer: true, loadingAnswer: false }
            : item
        )
      );
    } catch (e) {
      console.error('Generate Answer Error:', e);
      setError('Failed to generate answer: ' + e.message);
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
      if (!res.ok) {
        const errorText = await res.text();
        console.error('API Error:', errorText);
        throw new Error('PDF export failed: ' + errorText);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'questions.pdf';
      a.click();
    } catch (e) {
      console.error('Download PDF Error:', e);
      setError('Failed to download PDF: ' + e.message);
    }
  };

  const Answergenerate = async () => {
    setAnswers([]);
    setLoadingAnswers(true);

    try {
      await handleUpload();

      if (mode === 'multi') {
        if (syllabusmode === 'question') {
          const selectedQuestions = questionRequests.filter(x => x.selected && x.question.trim());
          console.log('Selected questions:', selectedQuestions);

          if (selectedQuestions.length === 0) {
            throw new Error('Please select at least one question.');
          }

          const aggregated = [];

          for (const c of selectedQuestions) {
            console.log(`Sending API call for question: "${c.question}"`);
            const res = await fetch(`${API_URL}/api/nlp-generate-answer-to-question`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ question: c.question })
            });

            if (!res.ok) {
              const errorText = await res.text();
              console.error(`API Error: ${errorText}`);
              throw new Error(`Answer generation failed for question: "${c.question}"`);
            }

            const { answer } = await res.json();
            aggregated.push({ question: c.question, answer });
          }

          setAnswers(aggregated);
        }
      }
    } catch (err) {
      console.error('Answer Generate Error:', err);
      setError(err.message || 'An error occurred');
    } finally {
      setLoadingAnswers(false);
    }
  };

  return (
    <div className="exam-generator-container container my-5 pt-5">
      <div className="card shadow-lg border-0">
        <div className="card-header text-white">
          <h4 className="mb-0">Generate Questions & Answers</h4>
        </div>
        <div className="card-body p-4">
          {/* Settings */}
          <div className="row g-3 mb-4">
            <div className="col-md-4" style={{ display: 'none' }}>
              <label className="form-label text-accent">Title</label>
              <input
                type="text"
                className="form-control"
                value={examTitle}
                onChange={e => setExamTitle(e.target.value)}
                placeholder="Title (Optional)"
              />
            </div>
            <div className="col-md-4" style={{ display: 'none' }}>
              <label className="form-label text-accent">Duration (mins)</label>
              <input
                type="number"
                className="form-control"
                value={duration}
                onChange={e => setDuration(+e.target.value)}
              />
            </div>
          </div>

          {/* Mode Selection */}
          <div className="mb-5 text-center">
            <h5 className="mb-3 text-accent">Select Input Method</h5>
            <div className="d-flex flex-column flex-md-row justify-content-center gap-2">
              {['paste', 'multi', 'questionPaper'].map(m => (
                <button
                  key={m}
                  className={`input-method-btn ${mode === m ? 'active' : 'btn-outline-primary'} w-100 w-md-auto`}
                  onClick={() => setMode(m)}
                >
                  {m === 'paste' ? 'Enter Your Text' : m === 'multi' ? 'Upload Syllabus' : 'Upload Question Paper'}
                </button>
              ))}
            </div>
          </div>

          {/* Question Type Dropdown and Number of Questions */}
          {mode !== 'questionPaper' && (
            <div className="mb-5 text-center">
              <h5 className="mb-3 text-accent">Select Question Type</h5>
              <div className="d-flex justify-content-center">
                <select
                  className="form-select w-50"
                  value={Object.keys(questionTypes).find(key => questionTypes[key]) || 'shortAnswer'}
                  onChange={e => handleQuestionTypeChange(e.target.value)}
                  style={{ maxWidth: '300px' }}
                >
                  <option value="mcq">Multiple Choice (MCQ)</option>
                  <option value="shortAnswer">Short Answer</option>
                  <option value="longAnswer">Long Answer</option>
                </select>
              </div>
              <div className="mt-3">
                <label className="form-label fw-bold text-accent">Number of Questions</label>
                <input
                  type="number"
                  className="form-control w-50 mx-auto"
                  value={numQuestions}
                  onChange={e => setNumQuestions(+e.target.value)}
                  style={{ maxWidth: '300px' }}
                />
              </div>
            </div>
          )}

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
              <div className="mb-4">
                <label className="form-label text-accent">Upload Syllabus pdf/jpg/jpeg</label>
                <input
                  type="file"
                  accept=".pdf, .jpg, .jpeg"
                  className="form-control"
                  onChange={e => setSyllabusFile(e.target.files[0])}
                />
              </div>

              <div className="mb-4">
                {['chapter', 'question'].map(m => (
                  <div className="form-check form-check-inline" key={m}>
                    <input
                      className="form-check-input"
                      type="radio"
                      name="syllabusmode"
                      id={m}
                      value={m}
                      checked={syllabusmode === m}
                      onChange={() => setSyllabusMode(m)}
                    />
                    <label className="form-check-label text-accent" htmlFor={m}>
                      {m === 'chapter' ? 'Topic' : 'Question'}
                    </label>
                  </div>
                ))}
              </div>

              {syllabusmode === 'question' && (
                <div>
                  <table className="table table-bordered mb-3">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Questions</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {questionRequests.map(c => (
                        <tr key={c.id}>
                          <td className="text-center" style={{ width: '10%' }}>
                            <input
                              type="checkbox"
                              className="form-check-input"
                              checked={c.selected}
                              onChange={e => updateQuestion(c.id, 'selected', e.target.checked)}
                            />
                          </td>
                          <td style={{ width: '90%' }}>
                            <textarea
                              rows={1}
                              className="form-control"
                              placeholder="Enter Question..."
                              value={c.question}
                              onChange={e => updateQuestion(c.id, 'question', e.target.value)}
                            />
                          </td>
                          <td className="text-center" style={{ width: '10%' }}>
                            <button
                              className="btn btn-sm btn-outline-danger"
                              onClick={() => removeQuestion(c.id)}
                            >
                              ×
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="d-flex gap-2 mb-4">
                    <button className="btn btn-sm btn-primary" onClick={addQuestion}>
                      + Add Question
                    </button>
                    <button className="btn btn-sm btn-success" onClick={Answergenerate}>
                      {loadingAnswers ? 'Generating...' : 'Get Answer'}
                    </button>
                  </div>
                </div>
              )}

              {answers.length > 0 && syllabusmode !== 'chapter' && (
                <div className="card question-card mt-4">
                  <div className="card-header bg-success text-white">
                    <strong>Generated Q&A</strong>
                  </div>
                  <div className="card-body">
                    <div className="list-group">
                      {answers.map((item, index) => (
                        <div key={index} className="list-group-item">
                          <h6 className="mb-2">Q: {item.question}</h6>
                          <div className="ps-3">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {item.answer}
                            </ReactMarkdown>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {syllabusmode === 'chapter' && (
                <div>
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
                          <td style={{ width: '20%', display: 'none' }}>
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
                              ×
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button className="btn btn-sm btn-success mb-4" onClick={addChapter}>
                    + Add Chapter
                  </button>
                </div>
              )}
            </>
          )}

          {/* Upload Question Paper */}
          {mode === 'questionPaper' && (
            <div className="mb-4">
              <label className="form-label text-accent">Upload Question Paper pdf/jpg/jpeg</label>
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
            {showGenerate && (
              <button className="btn btn-primary" onClick={generate} disabled={loading}>
                {loading ? 'Generating...' : 'Generate Questions'}
              </button>
            )}
            {questions.length > 0 && showGenerate && (
              <button className="btn btn-success" onClick={downloadPdf}>
                Download PDF
              </button>
            )}
          </div>

          {questions.length > 0 && syllabusmode !== 'question' && (
            <div className="mt-5">
              <h5 className="text-accent">Generated Questions:</h5>
               
              {questions.map((q, idx) => {
                const lines = q.question.split('\n');
                const isMCQ = lines.some(line => /^[-\s]*[A-Za-z0-9][).]\s+/.test(line.trim()));
                return (
                  <div key={idx} className="card question-card mb-3">
                    <div className="card-body">
                      
                      {isMCQ ? (
                        <h6>{lines[0]}</h6>                         
                      ) : (
                        <h6>Q{idx+1}. {lines[0]}</h6>
                      )}

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

                      {!isMCQ && !q.showAnswer && (
                        <button
                          className="btn btn-sm btn-primary mt-2"
                          onClick={() => generateAnswer(idx)}
                          disabled={q.loadingAnswer}
                        >
                          {q.loadingAnswer ? 'Generating...' : 'Generate Answer'}
                        </button>
                      )}

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
                    {!isMCQ && q.showAnswer && (
                      <button
                        className="btn btn-sm position-absolute close-answer-btn"
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