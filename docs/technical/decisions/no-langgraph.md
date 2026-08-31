# ADR: bez LangGraph (OSS i Cloud)

**Data:** 2026-08-31  
**Status:** zaakceptowany

## Kontekst

Orchestrator czatu (`chat_orchestrator.py`, ~3000 linii, 17 narzędzi) działa jako custom Python z jedną rundą tool callingu, jobami w procesie uvicorn i limitami kosztu LLM. LangGraph Cloud (LangSmith Plus ~$39/mc) oferuje agent loop, checkpoints i streaming, ale wymaga dużej migracji i osobnej infrastruktury (własna Postgres na checkpoints w Cloud).

Obserwowalność rozmów: Langfuse z `session_id = conversation_id` (Faza A, 2026-08-31).

## Decyzja

**Nie wdrażamy LangGraph** — ani Cloud, ani OSS w najbliższej iteracji.

Kierunek rozwoju orchestratora:

- inkrementalne ulepszenia obecnego `ChatOrchestratorUseCase` (np. pętla agenta 2–3 rundy tool calling),
- Langfuse dla debugu sesji rozmowy,
- opcjonalnie SSE / streaming w API czatu,
- bez czwartego vendora i bez dual DB.

## Uzasadnienie

- Profil ruchu (sporadyczny, Render Free) — koszt LangSmith Plus bez wyraźnej korzyści.
- Stack: Vercel + Render + Supabase — LangGraph Cloud to dodatkowy vendor i synchronizacja stanu z `conversations` / `messages`.
- Duży rewrite orchestratora vs zysk przy obecnym zakresie produktu.
- Langfuse pokrywa główną potrzebę insightów z rozmów (Sessions per `conversation_id`).

## Konsekwencje

- Placeholder „LangGraph w przyszłości” w panelu admina usunięty / zastąpiony opisem obecnego orchestratora.
- Powrót do LangGraph tylko jeśli pojawi się silna potrzeba: długie HITL workflow z checkpointami, LangSmith Studio dla wielu edytorów grafu, lub skala wymagająca oddzielnego agent hosta.

## Powiązane

- `docs/superpowers/specs/2026-08-31-langfuse-conversation-sessions-design.md`
- Feasibility LangGraph Cloud — odrzucone w sesji 2026-08-31 (opcja D: status quo + inkrement).
