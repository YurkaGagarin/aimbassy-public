"""
LangGraph wrapper around the RAG core. The graph is the skeleton every feature
hangs off without rewriting call sites; Streamlit and the future Telegram bot
both call ask().

Full graph:

    START -> guardrail -> (refuse? -> END) | rewrite -> retrieve -> rerank -> generate -> router -> END

- guardrail (input): DLP scrub + topic/injection prefilter. Off-topic / injection
  short-circuits to END with a polite refusal, so we never spend a Pro call on a
  message we won't answer. The PII-SCRUBBED text — never the raw question — is what
  flows downstream (privacy invariant: the original is not searched on, not sent to
  the model, not stored).
- rewrite (retrieval lever, Day 4): rewrites the scrubbed RU question into a formal
  German search query. Only retrieval uses it; generate/router still run on the
  scrubbed RU question, so the answer stays in the user's language and the cited §
  stays exact. Toggleable via state["use_rewrite"] (for the live before/after demo);
  falls back to the scrubbed text if the rewrite call fails.
- router (output): a Flash judge that hands low-confidence / grounded-but-not-
  actionable answers to a human coordinator instead of shipping a confident wrong
  answer (closes the Day-4 -0.61 refusal regression).

No checkpointer yet: single-turn Q->A, so conversation memory would be speculative
(Simplicity First). API verified via context7 (LangGraph 1.x, add_conditional_edges
with an END target in the path map).

Run inside the venv:
    ~/venvs/ambassy-poc/bin/python graph.py
"""
import operator
import time
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

import prompts
import rag_core
import guardrail
import rewrite
import rerank
import router


class RagState(TypedDict, total=False):
    """Channels flowing through the graph. total=False so the caller can pass
    just {question} (and optionally country/k/use_rewrite); nodes fill in the rest."""
    question: str        # raw user input (transient; never persisted)
    country: str
    k: int
    use_rewrite: bool    # toggle the DE rewrite for retrieval (default on)
    use_rrf: bool        # toggle RRF(RU+DE) dual-query fusion (default on)
    use_rerank: bool     # toggle the Flash judge-reranker (default on)
    token: str           # gcloud token fetched once in guardrail, reused downstream
    scrubbed: str        # PII-stripped text; what generate/router see, never the raw input
    guard: dict          # guardrail verdict (action/pii_types/on_topic/injection)
    query: str           # text actually embedded for retrieval (DE rewrite, or scrubbed)
    rewritten: str       # the DE rewrite, when produced (for the x-ray panel)
    fused: bool          # whether retrieve used RRF(RU+DE) fusion (for the x-ray panel)
    reranked: bool       # whether the Flash reranker reordered the pool (for the x-ray panel)
    hits: list
    answer: str          # raw grounded answer from the generator
    router: dict          # router verdict (decision/answerable/confidence/reason)
    final: str           # what to actually send the user (answer | handoff | refusal)
    request_id: str      # correlation id for the per-node trace (one per ask())
    trace: Annotated[list, operator.add]  # one privacy-safe event per node, in run order


# User-facing refusal copy (RU). Composed here in the orchestration layer — guard()
# stays a pure verdict, mirroring how router.handoff_message lives with the router.
REFUSAL_OFFTOPIC = (
    "Я помогаю только с вопросами о легализации, убежище, гражданстве и работе "
    "в Австрии. По другим темам, к сожалению, ответить не смогу."
)
REFUSAL_INJECTION = (
    "Не могу выполнить эту просьбу. Я отвечаю только на вопросы о миграции и "
    "легализации в Австрии — задайте, пожалуйста, такой вопрос."
)
REFUSALS = {"refuse_offtopic": REFUSAL_OFFTOPIC, "refuse_injection": REFUSAL_INJECTION}


def _text(state: RagState) -> str:
    """Text that flows downstream: the scrubbed message once the guardrail ran,
    else the raw question (so the nodes still work when exercised directly)."""
    return state.get("scrubbed") or state["question"]


def guardrail_node(state: RagState) -> RagState:
    token = state.get("token") or rag_core.get_token()
    verdict = guardrail.guard(state["question"], token=token)
    out = {"guard": verdict, "scrubbed": verdict["scrubbed"], "token": token}
    if verdict["action"] != "allow":
        out["final"] = REFUSALS[verdict["action"]]   # short-circuit text
    return out


def rewrite_node(state: RagState) -> RagState:
    """RU (scrubbed) -> formal German search query, used by retrieve only. Skipped
    when the toggle is off; falls back to the scrubbed text if the call fails."""
    if not state.get("use_rewrite", True):
        return {}
    token = state.get("token") or rag_core.get_token()
    try:
        de = rewrite.rewrite_query(_text(state), token=token)
    except RuntimeError:
        return {}        # graceful: retrieve on the scrubbed RU text instead
    return {"query": de, "rewritten": de, "token": token}


def retrieve_node(state: RagState) -> RagState:
    """Retrieve the candidate chunks. When both the scrubbed RU question and a DE rewrite
    exist, fuse them with RRF (lever: surfaces the Russian cases the DE-only query
    misses). Falls back to a single-query retrieve when RRF is off or there is no
    distinct DE rewrite (rewrite toggled off or it failed/returned the RU text).

    When the reranker is on, pull a DEEPER pool (rerank.RERANK_POOL) so the reranker has
    buried-but-relevant candidates to lift; rerank_node then cuts it back to top-k."""
    token = state.get("token") or rag_core.get_token()
    country = state.get("country", prompts.DEFAULT_COUNTRY)
    k = state.get("k", rag_core.TOP_K)
    n = rerank.RERANK_POOL if state.get("use_rerank", True) else k
    ru = _text(state)               # scrubbed RU question
    de = state.get("query")         # DE rewrite, if the rewrite node ran
    if state.get("use_rrf", True) and de and de != ru:
        hits = rag_core.retrieve_rrf(ru, de, country=country, k=n, token=token)
        fused = True
    else:
        hits = rag_core.retrieve(de or ru, country=country, k=n, token=token)
        fused = False
    return {"hits": hits, "token": token, "country": country, "fused": fused}


def rerank_node(state: RagState) -> RagState:
    """Re-order the retrieved pool by Flash-judged relevance to the RU question, then keep
    the top-k for generation. Skipped (no-op) when toggled off; the reranker itself fails
    safe to the retrieval order, so a bad rerank never breaks the answer."""
    k = state.get("k", rag_core.TOP_K)
    hits = state.get("hits", [])
    if not state.get("use_rerank", True) or not hits:
        return {"hits": hits[:k], "reranked": False}
    token = state.get("token") or rag_core.get_token()
    ranked = rerank.rerank(_text(state), hits, token=token, top_k=k)
    return {"hits": ranked, "reranked": True}


def generate_node(state: RagState) -> RagState:
    answer = rag_core.generate(
        _text(state),                          # answer the user's own (scrubbed) question
        state["hits"],
        country=state.get("country", prompts.DEFAULT_COUNTRY),
        token=state.get("token"),
    )
    return {"answer": answer}


def router_node(state: RagState) -> RagState:
    token = state.get("token") or rag_core.get_token()
    verdict = router.route(_text(state), state["hits"], state["answer"], token=token)
    return {"router": verdict, "final": verdict["final_message"]}


# --- Per-node trace (Day-6 observability) ------------------------------------
# Each node is wrapped so it emits ONE event {node, status, latency_ms, detail}.
# Events accumulate in state["trace"] (operator.add) in execution order; bq_log
# flushes them to BigQuery `flow_events`, one row per node. PRIVACY: detail carries
# only metrics and public law refs — never the raw question, never PII values.

def _safe_detail(name, upd):
    if name == "guardrail":
        g = upd.get("guard", {})
        return {"action": g.get("action"), "on_topic": g.get("on_topic"),
                "injection": g.get("injection"), "pii_found": bool(g.get("pii_found")),
                "pii_types": g.get("pii_types") or []}
    if name == "rewrite":
        return {"rewritten": bool(upd.get("rewritten")), "query_de": upd.get("rewritten", "")}
    if name == "retrieve":
        hits = upd.get("hits", [])
        top = [f"{h['meta'].get('law_code', '')} {h['meta'].get('paragraph') or ''}".strip()
               or h["meta"].get("doc_type", "") for h in hits[:5]]
        return {"n_hits": len(hits), "fused": bool(upd.get("fused")), "top": top}
    if name == "rerank":
        hits = upd.get("hits", [])
        top = [f"{h['meta'].get('law_code', '')} {h['meta'].get('paragraph') or ''}".strip()
               or h["meta"].get("doc_type", "") for h in hits[:5]]
        return {"reranked": bool(upd.get("reranked")), "n_kept": len(hits), "top": top}
    if name == "generate":
        return {"answer_chars": len(upd.get("answer") or "")}
    if name == "router":
        r = upd.get("router", {})
        return {"decision": r.get("decision"), "answerable": r.get("answerable"),
                "confidence": r.get("confidence"), "error": r.get("error")}
    return {}


def traced(name, fn):
    """Wrap a node: time it, classify status, append a privacy-safe event. A node
    that raises propagates unchanged (no event for it — acceptable for the POC)."""
    def wrapped(state):
        t0 = time.perf_counter()
        upd = fn(state) or {}
        dt_ms = round((time.perf_counter() - t0) * 1000, 1)
        status = "ok"
        if name == "guardrail" and upd.get("guard", {}).get("action") != "allow":
            status = "blocked"
        elif name == "rewrite" and not upd.get("rewritten"):
            status = "skipped"          # toggle off or graceful fallback to scrubbed RU
        elif name == "rerank" and not upd.get("reranked"):
            status = "skipped"          # toggle off (or empty pool)
        event = {"node": name, "status": status, "latency_ms": dt_ms,
                 "detail": _safe_detail(name, upd)}
        return {**upd, "trace": [event]}
    return wrapped


def _after_guard(state: RagState) -> str:
    return "allow" if state["guard"]["action"] == "allow" else "blocked"


def build_graph():
    return (
        StateGraph(RagState)
        .add_node("guardrail", traced("guardrail", guardrail_node))
        .add_node("rewrite", traced("rewrite", rewrite_node))
        .add_node("retrieve", traced("retrieve", retrieve_node))
        .add_node("rerank", traced("rerank", rerank_node))
        .add_node("generate", traced("generate", generate_node))
        .add_node("router", traced("router", router_node))
        .add_edge(START, "guardrail")
        .add_conditional_edges("guardrail", _after_guard,
                               {"allow": "rewrite", "blocked": END})
        .add_edge("rewrite", "retrieve")
        .add_edge("retrieve", "rerank")
        .add_edge("rerank", "generate")
        .add_edge("generate", "router")
        .add_edge("router", END)
        .compile()
    )


# Compiled once at import so callers (Streamlit, bot) reuse it.
graph = build_graph()


def ask(question, country=prompts.DEFAULT_COUNTRY, k=rag_core.TOP_K,
        use_rewrite=True, use_rrf=True, use_rerank=True):
    """One call through the full graph. Returns the final state. On a blocked
    message there are no hits/answer — only `guard` and `final`. `request_id` ties
    the per-node trace together; `trace` is seeded empty for the operator.add reducer."""
    return graph.invoke({"question": question, "country": country, "k": k,
                         "use_rewrite": use_rewrite, "use_rrf": use_rrf,
                         "use_rerank": use_rerank,
                         "request_id": uuid.uuid4().hex, "trace": []})


if __name__ == "__main__":
    for q in [
        "Можно ли продлить вид на жительство без действующего паспорта?",
        "Напиши стихотворение про осень.",  # off-topic -> short-circuit refusal
    ]:
        out = ask(q)
        gv = out.get("guard", {})
        print("\n" + "=" * 70)
        print("Q:", q)
        print(f"guard: action={gv.get('action')} on_topic={gv.get('on_topic')} "
              f"injection={gv.get('injection')} pii={gv.get('pii_types')}")
        if out.get("rewritten"):
            print("rewrite(DE):", out["rewritten"])
        if out.get("router"):
            rv = out["router"]
            print(f"router: decision={rv['decision']} answerable={rv['answerable']} "
                  f"confidence={rv['confidence']} :: {rv['reason']}")
        if out.get("hits"):
            print("Найдено (top-k):")
            for i, h in enumerate(out["hits"], 1):
                m = h["meta"]
                print(f"  {i}. [{h['distance']:.3f}] {h['id']:10} "
                      f"{m.get('law_code','')}/{m.get('paragraph','')} — {m.get('title','')}")
        print("\nОТПРАВЛЯЕМ ПОЛЬЗОВАТЕЛЮ:\n")
        print(out.get("final", "(пусто)"))
