import { motion, useReducedMotion } from 'motion/react'

const stages: Record<string, string> = {
  guard_input: 'Checking the question',
  check_corpus: 'Checking documents',
  retrieve: 'Searching documents',
  check_relevance: 'Checking relevance',
  generate: 'Writing the answer',
  validate_output: 'Verifying citations',
  refuse: 'Preparing the response',
}
const route = Object.keys(stages).filter((stage) => stage !== 'refuse')

export function PipelineProgress({ completed }: { completed: string[] }) {
  const reduced = useReducedMotion()
  const current = completed.at(-1)
  const done = completed.slice(0, -1)
  const label = current ? stages[current] ?? 'Working on the question' : 'Sending the question'
  return (
    <div className="pipeline-progress" role="status" aria-label={label}>
      <div className="pipeline-steps" aria-hidden="true">
        {route.map((stage) => (
          <motion.span key={stage} title={stages[stage]} className={done.includes(stage)
            ? 'pipeline-dot complete' : stage === current ? 'pipeline-dot current' : 'pipeline-dot'}
          initial={false} animate={{ opacity: done.includes(stage) || stage === current ? 1 : 0.55 }}
          transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}>
            {done.includes(stage) ? '✓' : ''}
          </motion.span>
        ))}
      </div>
      <span>{label}</span>
    </div>
  )
}
