// src/components/ExamGenerator.jsx
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase';

export default function ExamGenerator() {
  const navigate = useNavigate();

  // --- Logout handler ---
  const handleLogout = async () => {
    try {
      await signOut(auth);
      navigate('/');
    } catch (e) {
      console.error('Logout failed:', e);
    }
  };

  // Exam settings
  const [examTitle, setExamTitle] = useState('');
  const [duration, setDuration] = useState(60);
  const [totalMarks, setTotalMarks] = useState(0);
  const [questionTypes, setQuestionTypes] = useState({
    mcq: true,
    shortAnswer: true,
    longAnswer: false
  });
  const [numQuestions, setNumQuestions] = useState(5);

  // Mode: 'manual', 'paste', or 'multi'
  const [mode, setMode] = useState('paste');

  // Manual topics
  const [topics, setTopics] = useState([
    { id: Date.now(), name: '', marks: '' }
  ]);

  // NLP paste text
  const [pasteText, setPasteText] = useState('');

  // Upload file & multi-chapter
  const [syllabusFile, setSyllabusFile] = useState(null);
  const [chapterRequests, setChapterRequests] = useState([
    { id: Date.now(), chapter: '', numQuestions: 5, marks: 5, selected: true }
  ]);

  // Outputs
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Helpers for manual topics
  const addTopic = () => setTopics(prev => [...prev, { id: Date.now(), name: '', marks: '' }]);
  const updateTopic = (id, field, value) =>
    setTopics(prev => prev.map(t => t.id === id ? { ...t, [field]: value } : t));
  const removeTopic = id =>
    setTopics(prev => prev.filter(t => t.id !== id));

  // Helpers for multi-chapter
  const addChapter = () => setChapterRequests(prev => [
    ...prev,
    { id: Date.now(), chapter: '', numQuestions: 5, marks: 5, selected: true }
  ]);
  const updateChapter = (id, field, value) =>
    setChapterRequests(prev => prev.map(c => c.id === id ? { ...c, [field]: value } : c));
  const removeChapter = id =>
    setChapterRequests(prev => prev.filter(c => c.id !== id));

  // Upload syllabus
  const handleUpload = async () => {
    if (!syllabusFile) throw new Error('Please upload a syllabus PDF.');
    const fd = new FormData();
    fd.append('file', syllabusFile);
    const res = await fetch('http://localhost:8001/api/upload-syllabus', {
      method: 'POST',
      body: fd
    });
    if (!res.ok) throw new Error('Upload failed');
    await res.json();
  };

  // Generate questions
  const generate = async () => {
    setLoading(true);
    setError('');
    setQuestions([]);
    try {
      // Build types array
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
        const res = await fetch('http://localhost:8001/api/nlp-generate-questions', {
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
        const res = await fetch('http://localhost:8001/api/nlp-generate-questions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error('Generation failed');
        const { questions } = await res.json();
        setQuestions(questions.map(q => ({ question: q, marks: null })));
        return;
      }

      // Multiple chapters flow
      if (mode === 'multi') {
        await handleUpload();
        const aggregated = [];
        for (const c of chapterRequests.filter(x => x.selected && x.chapter.trim())) {
          const res = await fetch('http://localhost:8001/api/nlp-generate-questions-by-chapter', {
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
    } catch (e) {
      console.error(e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // Download PDF
  const downloadPdf = async () => {
    try {
      const res = await fetch('http://localhost:8001/api/export-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ questions })
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
    <div className="relative max-w-3xl mx-auto bg-white p-6 rounded-2xl shadow">
      {/* Logout Button */}
      <button
        onClick={handleLogout}
        className="absolute top-4 right-4 bg-red-500 text-white px-3 py-1 rounded hover:bg-red-600"
      >
        Logout
      </button>

      <h1 className="text-2xl font-semibold mb-4">Exam & Question Generator</h1>

      {/* --- Settings --- */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <input
          type="text"
          placeholder="Title"
          value={examTitle}
          onChange={e => setExamTitle(e.target.value)}
          className="border p-2 rounded"
        />
        <input
          type="number"
          placeholder="Duration (mins)"
          value={duration}
          onChange={e => setDuration(e.target.value)}
          className="border p-2 rounded"
        />
        <input
          type="number"
          placeholder="#Questions"
          value={numQuestions}
          onChange={e => setNumQuestions(e.target.value)}
          className="border p-2 rounded"
        />
      </div>

      {/* --- Types --- */}
      <div className="flex space-x-6 mb-6">
        {['mcq','shortAnswer','longAnswer'].map(k => (
          <label key={k} className="inline-flex items-center">
            <input
              type="checkbox"
              checked={questionTypes[k]}
              onChange={e => setQuestionTypes(prev => ({
                ...prev,
                [k]: e.target.checked
              }))}
            />
            <span className="ml-2">
              {k==='shortAnswer' ? 'Short Answer' : k==='longAnswer' ? 'Long Answer' : 'MCQ'}
            </span>
          </label>
        ))}
      </div>

      {/* --- Mode --- */}
      <div className="flex space-x-6 mb-6">
        {['manual','paste','multi'].map(m => (
          <label key={m} className="inline-flex items-center">
            <input
              type="radio"
              value={m}
              checked={mode===m}
              onChange={() => setMode(m)}
            />
            <span className="ml-2">
              {m==='manual' ? 'Manual' : m==='paste' ? 'Paste Text' : 'Multiple Chapters'}
            </span>
          </label>
        ))}
      </div>

      {/* --- Manual Topics --- */}
      {mode==='manual' && (
        <>
          <table className="w-full table-auto mb-4">
            <thead>
              <tr><th>Topic</th><th/></tr>
            </thead>
            <tbody>
              {topics.map(t => (
                <tr key={t.id}>
                  <td>
                    <input
                      type="text"
                      value={t.name}
                      onChange={e => updateTopic(t.id,'name',e.target.value)}
                      placeholder="Topic"
                      className="w-full p-1 border rounded"
                    />
                  </td>
                  <td className="text-center">
                    <button onClick={()=>removeTopic(t.id)} className="text-red-500">X</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={addTopic} className="px-4 py-2 bg-green-500 text-white rounded">
            + Add Topic
          </button>
        </>
      )}

      {/* --- Paste Text --- */}
      {mode==='paste' && (
        <textarea
          rows={6}
          className="w-full p-2 border rounded mb-4"
          placeholder="Enter text..."
          value={pasteText}
          onChange={e=>setPasteText(e.target.value)}
        />
      )}

      {/* --- Multiple Chapters --- */}
      {mode==='multi' && (
        <>
          <input
            type="file"
            accept=".pdf"
            className="mb-3"
            onChange={e=>setSyllabusFile(e.target.files[0])}
          />
          <table className="w-full table-auto mb-4">
            <thead>
              <tr><th/><th>Chapter</th><th>#Q</th><th>Marks</th><th/></tr>
            </thead>
            <tbody>
              {chapterRequests.map(c => (
                <tr key={c.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={c.selected}
                      onChange={e => updateChapter(c.id,'selected',e.target.checked)}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={c.chapter}
                      onChange={e => updateChapter(c.id,'chapter',e.target.value)}
                      placeholder="Chapter"
                      className="w-full p-1 border rounded"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={c.numQuestions}
                      onChange={e => updateChapter(c.id,'numQuestions',e.target.value)}
                      className="w-full p-1 border rounded"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      value={c.marks}
                      onChange={e => updateChapter(c.id,'marks',e.target.value)}
                      className="w-full p-1 border rounded"
                    />
                  </td>
                  <td className="text-center">
                    <button onClick={()=>removeChapter(c.id)} className="text-red-500">X</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={addChapter} className="px-4 py-2 bg-green-500 text-white rounded">
            + Add Chapter
          </button>  
        </>
      )}

      {/* --- Actions --- */}
      <div className="flex space-x-4 mt-6">
        <button
          onClick={generate}
          disabled={loading}
          className="bg-blue-600 text-white px-6 py-2 rounded"
        >
          {loading ? 'Generating...' : 'Generate Questions'}
        </button>
        {questions.length > 0 && (
          <button
            onClick={downloadPdf}
            className="bg-green-600 text-white px-6 py-2 rounded"
          >
            Download PDF
          </button>
        )}
      </div>

      {error && <p className="text-red-600 mt-4">{error}</p>}

      {questions.length > 0 && (
        <div className="mt-6">
          <h2 className="text-xl font-medium mb-2">Generated Questions</h2>
          <ul className="list-disc pl-5 space-y-2">
            {questions.map((q, i) => (
              <li key={i}>
                {q.question} {q.marks ? `(${q.marks} marks)` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
