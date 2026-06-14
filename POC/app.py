"""
Streamlit "x-ray panel" for the [AI]mbassy RAG baseline: a question goes in, the
grounded answer comes out, and — crucially for debugging — you see exactly which
chunks the retriever pulled and from which sources. This is both the live demo
and the tool we use on Days 3-4 to see why an answer is good or bad.

Run inside the venv:
    ~/venvs/ambassy-poc/bin/streamlit run app.py
"""
import time
import uuid

import streamlit as st

import prompts
import graph as g

st.set_page_config(page_title="[AI]mbassy — рентген-панель", layout="wide")


@st.cache_resource
def get_graph():
    """Compile the LangGraph once per process (heavy: opens Chroma, loads model
    config). Cached across reruns/sessions per Streamlit guidance."""
    return g.build_graph()


def render_sources(hits):
    st.caption("Дистанция: меньше = ближе по смыслу (косинус).")
    for i, h in enumerate(hits, 1):
        m = h["meta"]
        if m.get("doc_type") == "case":
            label = f"{i}. {h['id']} — {m.get('title', '')}"
        else:
            para = (m.get("paragraph") or "").replace("§", "").strip()
            label = f"{i}. {m.get('law_code', '')} § {para} — {m.get('title', '')}"
        with st.expander(f"[{h['distance']:.3f}]  {label}".rstrip(" —")):
            if m.get("section"):
                st.caption(m["section"])
            if m.get("source_url"):
                st.markdown(f"[Открыть источник]({m['source_url']})")
            st.text(h["text"][:1800] + ("…" if len(h["text"]) > 1800 else ""))


def _trace_summary(ev):
    """One human line per node for the trace panel (non-technical demo)."""
    d = ev.get("detail", {})
    n = ev["node"]
    if n == "guardrail":
        pii = ", ".join(d.get("pii_types") or []) or "нет"
        return f"тема: {'да' if d.get('on_topic') else 'нет'} · PII: {pii} · действие: {d.get('action')}"
    if n == "rewrite":
        return f"DE-запрос: {d['query_de']}" if d.get("rewritten") else "пропущен (rewrite выкл. или сбой → ищем по RU)"
    if n == "retrieve":
        return f"{d.get('n_hits', 0)} кусков: " + ", ".join(d.get("top") or [])
    if n == "generate":
        return f"ответ {d.get('answer_chars', 0)} символов"
    if n == "router":
        return f"решение: {d.get('decision')} · отвечаемо: {d.get('answerable')} · уверенность {d.get('confidence')}/5"
    return ""


def render_trace(trace):
    st.caption("Сколько занял каждый узел графа и что он решил. Латентность — для отладки/прода.")
    for ev in trace:
        st.text(f"{ev['node']:9} · {ev['status']:8} · {ev['latency_ms']:7.0f} мс  —  {_trace_summary(ev)}")


st.title("[AI]mbassy — рентген-панель")
st.write(
    "Задай вопрос про легализацию/убежище в Австрии. Слева — ответ со ссылками на "
    "параграфы, справа — что именно нашёл поиск (для отладки)."
)

with st.sidebar:
    st.header("Настройки")
    countries = list(prompts.COUNTRY_NAMES.keys())
    country = st.selectbox(
        "Страна", options=countries,
        format_func=lambda c: f"{prompts.COUNTRY_NAMES.get(c, c)} ({c})",
    )
    k = st.slider("Сколько кусков искать (top-k)", min_value=3, max_value=10, value=5)
    use_rewrite = st.toggle(
        "Переписывать запрос в немецкий (rewrite)", value=True,
        help="Day-4 рычаг: бытовой RU-вопрос → формальный DE-запрос для поиска. "
             "Выключи, чтобы увидеть baseline-поиск по исходному тексту.",
    )
    st.caption("POC: корпус пока только по Австрии (NAG, StbG, FPG).")

with st.form("ask"):
    question = st.text_area(
        "Вопрос", height=90,
        placeholder="Например: Можно ли продлить вид на жительство без действующего паспорта?",
    )
    submitted = st.form_submit_button("Спросить")

if submitted and question.strip():
    graph = get_graph()
    try:
        with st.spinner("Ищу в законах и формулирую ответ…"):
            t0 = time.perf_counter()
            out = graph.invoke({"question": question.strip(), "country": country, "k": k,
                                "use_rewrite": use_rewrite,
                                "request_id": uuid.uuid4().hex, "trace": []})
            dt = time.perf_counter() - t0
        st.session_state["result"] = {"out": out, "dt": dt}
    except Exception as e:  # noqa: BLE001 — surface any pipeline error to the panel
        st.session_state.pop("result", None)
        st.error(f"Ошибка пайплайна: {e}")

res = st.session_state.get("result")
if res:
    out, dt = res["out"], res["dt"]
    gv = out.get("guard", {})
    rv = out.get("router", {})
    hits = out.get("hits", [])
    st.caption(f"Готово за {dt:.1f} c · страна: {out.get('country')} · найдено кусков: {len(hits)}")

    # Verdict strip — the guardrail + router "x-ray" for the demo.
    badges = []
    if gv:
        pii = ", ".join(gv["pii_types"]) if gv.get("pii_types") else "нет"
        badges.append(f"guardrail: **{gv['action']}** · PII: {pii}")
    if rv:
        badges.append(f"router: **{rv['decision']}** (уверенность {rv['confidence']}/5)")
    if badges:
        st.info("  |  ".join(badges))
        if rv.get("reason"):
            st.caption(f"router-обоснование: {rv['reason']}")

    trace = out.get("trace") or []
    if trace:
        with st.expander(f"Трейс пайплайна по узлам ({len(trace)}) · те же строки пишутся в BigQuery flow_events"):
            render_trace(trace)

    col_ans, col_ctx = st.columns([3, 2])
    with col_ans:
        st.subheader("Что увидит пользователь")
        st.markdown(out.get("final") or out.get("answer") or "(пусто)")
    with col_ctx:
        st.subheader("Рентген: что нашёл поиск")
        if out.get("rewritten"):
            st.caption(f"Поисковый запрос (DE): {out['rewritten']}")
        elif hits:
            st.caption("Поиск по исходному тексту (rewrite выкл.).")
        if hits:
            render_sources(hits)
        else:
            st.caption("Сообщение отклонено на входном фильтре — поиск и генерация не выполнялись.")
