export function Monogram({ answer = false }: { answer?: boolean }) {
  return <span className={answer ? 'monogram answer-monogram' : 'monogram'} aria-hidden="true">P</span>
}

export function Brand() {
  return <span className="brand"><Monogram /><span className="rail-label">PolicyDesk RAG</span></span>
}
