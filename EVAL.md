# Golden Set

The [golden set](evals/golden_set.json) pairs questions with reference answers and evidence substrings from the fictional Tarnwick corpus. It covers direct lookups, rewordings, compound and cross-document questions, conflicting policy versions, Urdu questions, and questions outside the indexed evidence. There are 40 items, including 30 answerable English items, three answerable Urdu items, and seven unanswerable English items.

Types include `contradiction` (2), `single` (19), `reworded` (2), `multi_part` (4), `multi_doc` (3), `unanswerable` (7), `multilingual` (3).

A passage counts for an expected source when its filename matches exactly and its text contains at least one of that source’s literal evidence substrings. Only answerable items enter retrieval denominators. Each answerable entry also defines the must-have `key_facts` used by the correctness judge.

| ID | Type | Question | Expected file |
|---|---|---|---|
| q01 | contradiction | How many annual leave days do employees get? | `leave_policy_v2_2026.pdf` |
| q02 | contradiction | How many unused annual leave days can be carried over to next year? | `leave_policy_v2_2026.pdf` |
| q03 | single | What is the hotel limit per night in Karachi? | `expense_policy.pdf` |
| q04 | reworded | If I'm sent to Islamabad, what is the most I can spend on a hotel each night? | `expense_policy.pdf` |
| q05 | single | Who approves expense claims above PKR 50,000? | `expense_policy.pdf` |
| q06 | single | When am I allowed to travel by air for work? | `expense_policy.pdf` |
| q07 | multi_part | How long do I have to submit an expense claim, and when do I need receipts? | `expense_policy.pdf` |
| q08 | single | Which days are mandatory office days? | `remote_work_policy.docx` |
| q09 | single | What are the core collaboration hours? | `remote_work_policy.docx` |
| q10 | single | How long can I work from outside Pakistan? | `remote_work_policy.docx` |
| q11 | multi_part | How much does the RevOps Audit cost and how long does it take? | `service_catalogue_pricing.pdf` |
| q12 | multi_part | What does the Pro support retainer include: fee, hours and response time? | `service_catalogue_pricing.pdf` |
| q13 | single | What are the payment terms for projects? | `service_catalogue_pricing.pdf` |
| q14 | single | How long is the probation period? | `onboarding_guide.docx` |
| q15 | single | When is salary paid? | `onboarding_guide.docx` |
| q16 | single | What is the minimum password length? | `security_it_policy.md` |
| q17 | multi_part | Who do I report a security incident to, and how quickly? | `security_it_policy.md` |
| q18 | single | What is the maximum value of a gift I can accept from a client? | `code_of_conduct.docx` |
| q19 | single | How far in advance must flights be requested? | `travel_policy.md` |
| q20 | single | What daily allowance do I get on an international trip? | `travel_policy.md` |
| q21 | single | What does a performance rating of 3 mean? | `performance_review_policy.md` |
| q22 | single | What is the yearly learning budget per employee? | `learning_and_development_policy.md` |
| q23 | single | How quickly does IT respond to a P2 ticket? | `it_helpdesk_guide.md` |
| q24 | reworded | Do we get a day off on 23 March? | `public_holidays_2026.md` |
| q25 | single | How many days does a client have to accept a delivery after UAT? | `client_project_delivery_process.md` |
| q26 | single | What is the outpatient (OPD) insurance limit? | `health_and_wellbeing_benefits.md` |
| q27 | single | What notice period do I need to give if I resign? | `resignation_and_offboarding_policy.md` |
| q28 | multi_doc | Is unused annual leave paid out in cash when I resign? | `leave_policy_v2_2026.pdf`, `resignation_and_offboarding_policy.md` |
| q29 | multi_doc | What can I claim for working from home? | `remote_work_policy.docx`, `expense_policy.pdf` |
| q30 | multi_doc | My laptop broke. How fast will it be replaced? | `it_helpdesk_guide.md`, `employee_faq.txt` |
| u01 | unanswerable | What is the name of Tarnwick's CEO? | None |
| u02 | unanswerable | What is the company parking policy? | None |
| u03 | unanswerable | What is the capital of France? | None |
| u04 | unanswerable | What was Tarnwick's annual revenue last year? | None |
| u05 | unanswerable | Does Tarnwick offer stock options to employees? | None |
| u06 | unanswerable | What is the office dress code? | None |
| u07 | unanswerable | Where is the office moving on 1 December 2026? | None |
| m01 | multilingual | ملازمین کو سالانہ کتنی چھٹیاں ملتی ہیں؟ | `leave_policy_v2_2026.pdf` |
| m02 | multilingual | کراچی میں ہوٹل کی ایک رات کی حد کتنی ہے؟ | `expense_policy.pdf` |
| m03 | multilingual | پاس ورڈ کم از کم کتنے حروف کا ہونا چاہیے؟ | `security_it_policy.md` |

# Metrics

- **Hit@k** measures the fraction of answerable questions with any relevant passage among the first k results.
- **Recall@k** averages the fraction of each question’s expected sources covered by relevant top-k passages.
- **MRR** averages the reciprocal rank of the first relevant passage, assigning zero when none appears in the first eight results.
- **Faithfulness** is the fraction of graded answers whose factual claims are all supported by the cited passages alone.
- **Correctness** is the fraction of graded answerable items that include all annotated key facts with matching numbers and contain no contradiction of the reference.
- **Refusal accuracy** is the fraction of unanswerable items the service refused.
- **Hallucination rate** is the fraction of unanswerable items the service answered.

# Evaluation Frameworks

The suite uses deterministic retrieval metrics and an LLM judge. This keeps the dependency footprint small and makes the request count and 200-token judge budget explicit for the configured Groq free-tier workload. The [judge prompts](evals/judge.py) implement RAGAS-style faithfulness and answer-correctness checks. Their full inputs and binary scoring rules are visible in the repository.

Request telemetry comes from the service’s own `ask_logs`. The evaluation reads each completed request’s logged latency, uses the same prompt and completion token counts, and estimates cost at the configured token prices. Reported percentiles cover completed answer and refusal requests, including early refusals. They exclude the eight-second pauses, retries before a successful request, and judge calls.

# Judge Reliability

The judge is from the Qwen family and the answer model is from the gpt-oss family. The [review worksheet](evals/results/judge_review.csv) samples 12 answered items, mixing judge scores of 1 and 0 where available. This export contains 9 scores of 1 and 3 scores of 0. A human assigns an independent binary correctness label to each answer against its question and reference. `judge_check --score` reports exact agreement and Cohen’s kappa, which adjusts for agreement expected from the label frequencies.

**PENDING HUMAN LABELS** for agreement rate and Cohen’s kappa.

# Configuration Comparison

The run indexed 18 documents per strategy with `bge-m3` and skipped `scanned_office_notice.pdf` for both strategies because it has no extractable text. It scored the first one, four, and eight entries of the same retrieved ranking, reusing an identical embedding for each question across configurations.

| Configuration | Hit@1 | Hit@4 | Recall@4 | Recall@8 | MRR |
|---|---:|---:|---:|---:|---:|
| fixed+dense | 0.8485 | 0.9091 | 0.8939 | 1.0000 | 0.8854 |
| fixed+hybrid | 0.8788 | 0.9091 | 0.9091 | 1.0000 | 0.9005 |
| structure+dense | 0.8485 | 0.9091 | 0.8939 | 1.0000 | 0.8902 |
| structure+hybrid | 0.8485 | 0.9091 | 0.9091 | 1.0000 | 0.8952 |

**Fixed + hybrid** advanced to answer evaluation with the highest MRR (0.9005). The recall@4 tiebreaker was unnecessary. Every configuration covered all annotated sources within eight results. Retrieval scores matched the baseline across all configurations and languages.

| Language | Configuration | Hit@1 | Hit@4 | Recall@4 | Recall@8 | MRR |
|---|---|---:|---:|---:|---:|---:|
| English (30) | fixed+dense | 0.8667 | 0.9333 | 0.9167 | 1.0000 | 0.9031 |
| English (30) | fixed+hybrid | 0.9000 | 0.9333 | 0.9333 | 1.0000 | 0.9198 |
| English (30) | structure+dense | 0.8667 | 0.9333 | 0.9167 | 1.0000 | 0.9078 |
| English (30) | structure+hybrid | 0.8667 | 0.9333 | 0.9333 | 1.0000 | 0.9133 |
| Urdu (3) | fixed+dense | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.7083 |
| Urdu (3) | fixed+hybrid | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.7083 |
| Urdu (3) | structure+dense | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.7143 |
| Urdu (3) | structure+hybrid | 0.6667 | 0.6667 | 0.6667 | 1.0000 | 0.7143 |

# Results

The uncached Stage B run evaluated all 40 items on fixed + hybrid using four retrieved passages and Groq fallback disabled. The answer model was `openai/gpt-oss-20b` and the judge was `qwen/qwen3.8-27b`. The run recorded 0 request errors.

Full per-item artifacts are available for [retrieval](evals/results/retrieval_20261125_070715_670686Z.json) and [answers](evals/results/answers_20261125_070715_670686Z.json). The aggregate data is in [latest_summary.json](evals/results/latest_summary.json).

| Language | Items | Answered / answerable | Correctness | Faithfulness | Correct refusals | Hallucinations | False refusals |
|---|---:|---:|---:|---:|---:|---:|---:|
| Overall | 40 | 32/33 | 29/33 (87.9%) | 32/32 (100.0%) | 7/7 | 0 | 1 |
| English | 37 | 29/30 | 27/30 (90.0%) | 29/29 (100.0%) | 7/7 | 0 | 1 |
| Urdu | 3 | 3/3 | 2/3 (66.7%) | 3/3 (100.0%) | N/A | 0 | 0 |

Correctness includes the 1 false refusal. Faithfulness covers the 32 returned answers. On the seven unanswerable items, refusal accuracy was 100% and hallucination rate was 0%.

Across 40 requests, latency was **1,001.08 ms p50** and **1,849.71 ms p95**. English was 1,013.46 ms p50 and 2,351.05 ms p95. Urdu was 945.76 ms p50 and 1,038.46 ms p95. The full sample includes two unusually slow requests, `u02` (127,965.90 ms) and `u03` (5,024.84 ms).

Groq generated responses for 39 requests. `u03` ended at the relevance check before generation. The service recorded 42,965 prompt tokens and 1,952 completion tokens at a configured estimated generation cost of $0.00.

# Iteration: Before and After

The [baseline summary](evals/results/baseline_summary.json) and [baseline answers](evals/results/baseline_answers.json) preserve the first run. The [re-judged baseline](evals/results/baseline_rejudged.json) scores those same answers against the updated checklist. Its faithfulness, refusal outcomes, and request timings carry over from the first run.

| Metric | Baseline | Baseline (re-judged with `key_facts`) | Improved |
|---|---:|---:|---:|
| Correctness | 18/33 (54.5%) | 19/33 (57.6%) | 29/33 (87.9%) |
| Faithfulness | 20/20 (100.0%) | 20/20 (100.0%) | 32/32 (100.0%) |
| False refusals | 13 | 13 | 1 |
| Correct refusals | 7/7 | 7/7 | 7/7 |
| Hallucinations | 0 | 0 | 0 |
| Urdu correctness | 1/3 (33.3%) | 2/3 (66.7%) | 2/3 (66.7%) |
| p50 latency | 1,000.78 ms | 1,000.78 ms | 1,001.08 ms |
| p95 latency | 1,127.46 ms | 1,127.46 ms | 1,849.71 ms |

- **Tolerant citation parsing** converts grouped references, parenthesized IDs, corner brackets, standalone bracketed IDs, and trailing source lines into separate `[C1]` markers and removes unavailable IDs.
- **Version-aware context** adds the first two non-empty extracted lines, up to 200 characters, so the generation prompt can compare versions and effective dates.
- **Explicit citation rule** requires at least one citation in every substantive answer and shows how to append separate canonical markers.
- **Key-facts judging** requires every listed fact and checks for contradictions with the reference, while allowing alternate wording and extra correct detail.

The saved baseline text for `q01`, `q02`, `q03`, `q04`, `q06`, `q11`, `q12`, `q14`, `q16`, `q23`, `q26`, and `q30` was “I couldn't produce an answer that is backed by your documents.” These rows contain zero validated citations. The baseline discarded the generation drafts, so their exact citation formats are unavailable.

The twelve `ungrounded` refusals fell to zero in the improved run. The only change from re-judging the baseline was `m02`. Its answer already gave PKR 15,000, and pre-approval is optional under that item's key-facts checklist. Urdu correctness is therefore unchanged under the matched rubric. The run measures the combined generation and citation changes.

# Failure Analysis

| Item | Remaining failure | Evidence and likely cause |
|---|---|---|
| q01 | Top-four retrieval miss and incorrect answer | The current 21-day evidence ranked fifth. The answer gave 18 days using the old FAQ and v1.0, even though a different v2.0 passage and the newer header were in context. |
| q24 | Top-four retrieval miss and false refusal | Pakistan Day evidence ranked seventh. The model received leave and FAQ passages and returned `NOT_IN_DOCUMENTS`. |
| q29 | Incomplete answer | Both policy sources made the winner’s top four. The answer gave the PKR 3,000 monthly internet allowance and omitted the PKR 15,000 one-time stipend. Dense retrieval still misses the expense-policy evidence at four. |
| m01 | Top-four retrieval miss and incorrect answer | The newer entitlement passage ranked eighth. The Urdu answer cited the FAQ and v1.0 and gave 18 days instead of 21 working days. |

- Test an evidence expansion to eight candidates with date- and version-aware reranking. All expected sources were covered by rank eight in this run.
- Match exact calendar dates and holiday-name aliases to improve `q24` without widening every answer prompt.
- For multi-document questions, check that the draft addresses each supported source before returning it. `q29` had both pieces of evidence available.
- Add more Urdu cases and test bilingual query expansion on versioned policies. The three-item slice includes one stale-source answer.

# How to Reproduce

From the repository root, activate the project’s Python 3.12 environment, start PostgreSQL, and ensure Ollama is running with `bge-m3`. Set `GROQ_API_KEY` in `.env`.

```powershell
docker compose up -d
python -m evals.run --no-cache
python -m evals.run --retrieval-only
python -m evals.judge_check --export
python -m evals.rejudge
# Fill human_correctness with 0 or 1 in evals/results/judge_review.csv.
python -m evals.judge_check --score
```

`evals.rejudge` uses the saved `evals/results/baseline_answers.json` snapshot. Use `--configs fixed+dense structure+hybrid` to compare a subset and `--no-cache` for fresh model calls. A full run uses the reserved `eval-fixed` and `eval-structure` owners and removes their documents when it finishes.
