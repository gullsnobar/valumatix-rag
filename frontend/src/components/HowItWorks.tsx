import { ExternalLink } from 'lucide-react'
import { API_DOCS_URL } from '../api/client.ts'
import { exampleQuestions } from '../questions.ts'

export function HowItWorks({ chooseQuestion }: { chooseQuestion: (question: string) => void }) {
  return <div className="guide-content">
    <section>
      <h3>What PolicyDesk RAG does</h3>
      <p>PolicyDesk RAG answers questions about the company policies you add. Every answer shows the passage it came from.</p>
    </section>
    <section>
      <h3>How to use it</h3>
      <ol className="numbered-steps">
        <li>Add your documents or load the samples.</li>
        <li>Ask a question in everyday words.</li>
        <li>Read the answer. The small numbers are sources.</li>
        <li>Click a number to see the exact passage.</li>
      </ol>
    </section>
    <section>
      <h3>How to read a source</h3>
      <p>Match is a score from 0 to 1 for how closely a passage matches your question. Use the file and page, when available, to find the passage in the original document.</p>
    </section>
    <section>
      <h3>When PolicyDesk RAG says it can’t answer</h3>
      <p>PolicyDesk RAG only answers from your documents, by design. If the documents don’t support an answer, it gives you a reason so you can check what’s missing.</p>
    </section>
    <section>
      <h3>What you can try</h3>
      <p>Load the sample documents and pick a question to fill the composer. The France question is there to try a refusal.</p>
      <ul className="guide-questions">
        {[...exampleQuestions, 'What is the capital of France?'].map((question) =>
          <li key={question}><button type="button" className="button ghost" onClick={() => chooseQuestion(question)}>
            {question}
          </button></li>)}
      </ul>
    </section>
    <section>
      <h3>For developers</h3>
      <p>React and FastAPI run the app, with LangGraph, PostgreSQL and pgvector, Ollama, and Groq for answers.</p>
      <a href={API_DOCS_URL} target="_blank" rel="noopener noreferrer" className="guide-link text-link">
        API documentation <ExternalLink aria-hidden="true" />
      </a>
    </section>
  </div>
}
