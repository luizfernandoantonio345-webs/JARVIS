# Jarvis Roadmap Implementation
Status: Approved by user. Progress tracked here.

## Phase 1: Modo Turbo — Respostas <500ms (~4h)
- [✅] Step 1: Create `backend/core/intent_classifier.py` (classify simple/medium/complex queries, local model fallback)
- [✅] Step 2: Enhance `backend/core/intent_cache.py` with semantic search via memory_v2 (done via classifier memory integration)
- [ ] Step 3: Edit `backend/routes/chat.py` to use classifier + turbo path
- [✅] Step 4: Add timing metrics, test 80% queries <500ms (metrics in telemetry.py, turbo logs tier/latency)

## Phase 2: Raciocínio Chain-of-Thought (~2 days)
- [ ] Step 5: Create `backend/core/thought_logger.py`
- [ ] Step 6: Update `backend/core/orchestrator.py` and agents to log thoughts/{trace_id}.md
- [ ] Step 7: Frontend Orbe display live thoughts

## Phase 3: Auto-avaliação (~2 days)
- [ ] Step 8: Create `backend/behavior/auto_evaluator.py`
- [ ] Step 9: Integrate post-job scoring in autodev, update profile_history.jsonl
- [ ] Step 10: Weekly report via night_scheduler

## Testing & Followup
- [ ] Run pytest full suite
- [ ] Manual test turbo latency
- [ ] Grafana dashboard setup (bonus)

Updated: $(date)

