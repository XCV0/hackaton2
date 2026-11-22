import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, DOMAIN_LONG, ISSUE_LABEL, post, put, qs } from "../api";
import SourceViewer from "../components/SourceViewer";
import { Badge, Empty, ErrorState, IssueTag, Kpi, Loading, pct, QuoteBadge, ReviewBadge, Toast, useAsync, useUrlState, VerBadge } from "../components/ui";
import { useScope } from "../main";

const TABS: [string, string][] = [["review", "Очередь проверки"], ["issues", "Замечания"], ["corpus", "Корпус и задачи"], ["metrics", "Метрики качества"],
  ["llm", "LLM и ноды"], ["config", "Схемы и правила"], ["audit", "Аудит"]];

export default function Admin() {
  const { tab = "review" } = useParams();
  const { domain, split } = useScope();
  const nav = useNavigate();
  return (
    <div className="stack">
      <div className="topbar"><div><div className="crumbs">Администрирование · {DOMAIN_LONG[domain]} · {split}</div><h1>{TABS.find((t) => t[0] === tab)?.[1] || "Администрирование"}</h1></div></div>
      <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => nav(`/admin/${k}?domain=${domain}&split=${split}`)}>{l}</button>)}</div>
      {tab === "review" && <ReviewQueue />}
      {tab === "issues" && <Issues />}
      {tab === "corpus" && <Corpus />}
      {tab === "metrics" && <Metrics />}
      {tab === "llm" && <LLM />}
      {tab === "config" && <Config />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

function ReviewQueue() {
  const { domain, split } = useScope();
  const nav = useNavigate();
  const [f, set] = useUrlState({ verification: "flagged,needs_review", review: "pending", issue: "", kind: "", scan: "", sel: "" });
  const { data, error, loading, reload } = useAsync(() => api(`/api/results${qs({ domain, split, verification: f.verification, review: f.review, issue: f.issue, kind: f.kind, scan: f.scan, limit: 200 })}`),
    [domain, split, f.verification, f.review, f.issue, f.kind, f.scan]);
  const [toast, setToast] = useState("");
  const [comment, setComment] = useState("");
  const rows = data?.rows || [];
  const cur = rows.find((r: any) => String(r.id) === f.sel) || rows[0];
  const idx = cur ? rows.indexOf(cur) : -1;
  const act = async (action: string) => {
    if (!cur) return;
    if (action === "reject" && !comment.trim()) { setToast("Для отклонения нужен комментарий"); return; }
    try {
      await post(`/api/records/${cur.id}/review`, { action, comment, actor: localStorage.getItem("actor") || "reviewer" });
      setToast(action === "confirm" ? `${cur.pub_id}/${cur.rec_id}: подтверждено` : `${cur.pub_id}/${cur.rec_id}: отклонено`);
      setComment("");
      const next = rows[idx + 1];
      set({ sel: next ? String(next.id) : "" });
      reload();
    } catch (e: any) { setToast(e.message); }
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (!cur || (t && ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName)) || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "j" || e.key === "ArrowDown") { e.preventDefault(); const n = rows[idx + 1]; if (n) set({ sel: String(n.id) }); }
      else if (k === "k" || e.key === "ArrowUp") { e.preventDefault(); const n = rows[idx - 1]; if (n) set({ sel: String(n.id) }); }
      else if (k === "a" || k === "ф") act("confirm");
      else if (k === "r" || k === "к") { if (comment.trim()) act("reject"); else { (document.getElementById("rq-comment") as HTMLTextAreaElement | null)?.focus(); setToast("Напишите причину и нажмите «Отклонить»"); } }
      else if (k === "e" || k === "у") nav(`/record/${cur.id}`);
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  });
  return (
    <div className="stack">
      <div className="card"><div className="filters">
        <label>Статус проверки<select className="input" value={f.verification} onChange={(e) => set({ verification: e.target.value, sel: "" })}>
          <option value="flagged,needs_review">все проблемные</option><option value="flagged">противоречие правилу</option><option value="needs_review">нужна проверка</option><option value="verified">подтверждённые (выборочно)</option></select></label>
        <label>Ручная проверка<select className="input" value={f.review} onChange={(e) => set({ review: e.target.value, sel: "" })}>
          <option value="pending">в очереди</option><option value="">все</option><option value="confirmed">подтверждено</option><option value="corrected">исправлено</option><option value="rejected">отклонено</option></select></label>
        <label>Тип замечания<select className="input" value={f.issue} onChange={(e) => set({ issue: e.target.value, sel: "" })}>
          <option value="">любой</option>{Object.entries(ISSUE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Источник<select className="input" value={f.kind} onChange={(e) => set({ kind: e.target.value, sel: "" })}>
          <option value="">любой</option><option value="table">таблица</option><option value="text">текст</option><option value="figure">рисунок</option></select></label>
        <label>PDF<select className="input" value={f.scan} onChange={(e) => set({ scan: e.target.value, sel: "" })}>
          <option value="">все</option><option value="true">сканы</option><option value="false">текстовые</option></select></label>
        <span className="small muted" style={{ alignSelf: "center" }}>{data ? `${data.total} в выборке` : ""}</span>
      </div></div>
      {loading && !data && <Loading rows={8} />}
      {error && <ErrorState error={error} retry={reload} />}
      {data && rows.length === 0 && <Empty title="Очередь пуста">По этим фильтрам нет записей, ожидающих проверки.</Empty>}
      {cur && (
        <div className="split">
          <div className="card" style={{ minWidth: 0 }}>
            <div className="tbl-wrap" style={{ maxHeight: "78vh" }}><table className="tbl"><thead><tr><th>Запись</th><th>Значение</th><th>Статус</th><th>Причины</th></tr></thead>
              <tbody>{rows.map((r: any) => <tr key={r.id} className={`rowlink ${r.id === cur.id ? "sel" : ""}`} onClick={() => set({ sel: String(r.id) })} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && set({ sel: String(r.id) })}>
                <td className="nowrap"><span className="mono">{r.pub_id}/{r.rec_id}</span><div className="small faint">с. {r.data.source_page} · {r.evidence?.kind}</div></td>
                <td><b>{r.data.metric_name}</b> <span className="mono">{r.data.raw_value}</span></td>
                <td><div className="stack" style={{ gap: 3 }}><VerBadge v={r.verification_status} /><ReviewBadge v={r.review_status} /></div></td>
                <td><div className="row" style={{ gap: 3 }}>{(r.issue_types || []).map((t: string, i: number) => <IssueTag key={i} t={t} />)}</div></td></tr>)}</tbody></table></div>
          </div>
          <div className="sticky-col card card-b stack">
            <div className="row between"><div><b>{cur.data.metric_name} = <span className="mono">{cur.data.raw_value} {cur.data.raw_unit}</span></b>
              <div className="small muted">{cur.pub_id} · {cur.rec_id} · {cur.data.source_table || cur.data.source_figure || "текст"} · {(cur.evidence?.reasons || []).join(", ")}</div></div>
              <Link className="btn sm" to={`/record/${cur.id}`}>Полная карточка / исправить</Link></div>
            <div className="row"><VerBadge v={cur.verification_status} /><QuoteBadge v={cur.quote_outcome} />{cur.data.note && <span className="small muted clip2">{cur.data.note}</span>}</div>
            {cur.data.source_fragment && <div className="quote">«{cur.data.source_fragment}»</div>}
            <SourceViewer domain={cur.domain} split={cur.split} pid={cur.pub_id} page={Number(cur.data.source_page) || 1} fragment={cur.data.source_fragment} value={cur.data.raw_value}
              cell={cur.evidence?.cell_bbox || cur.evidence?.row_bbox || null} figure={cur.data.source_figure && !cur.data.source_table ? cur.data.source_figure : undefined} />
            <textarea id="rq-comment" className="input" rows={2} placeholder="Комментарий (обязателен для отклонения)" value={comment} onChange={(e) => setComment(e.target.value)} aria-label="Комментарий проверяющего" />
            <div className="row"><button className="btn teal" onClick={() => act("confirm")}>✓ Подтвердить и дальше</button><button className="btn danger" onClick={() => act("reject")}>✕ Отклонить</button>
              <button className="btn ghost" disabled={idx < 0 || idx + 1 >= rows.length} onClick={() => set({ sel: String(rows[idx + 1].id) })}>Пропустить →</button></div>
            <div className="small faint kbd-hint">Клавиши: <kbd>J</kbd>/<kbd>↓</kbd> следующая · <kbd>K</kbd>/<kbd>↑</kbd> предыдущая · <kbd>A</kbd> подтвердить · <kbd>R</kbd> отклонить · <kbd>E</kbd> открыть карточку</div>
          </div>
        </div>
      )}
      {toast && <Toast msg={toast} onDone={() => setToast("")} />}
    </div>
  );
}

function Issues() {
  const { domain, split } = useScope();
  const [f, set] = useUrlState({ check: "", status: "", pub: "" });
  const { data, error, loading, reload } = useAsync(() => api(`/api/issues${qs({ domain, split, ...f })}`), [domain, split, f.check, f.status, f.pub]);
  const [toast, setToast] = useState("");
  const setStatus = async (id: number, status: string) => {
    const comment = window.prompt("Комментарий к решению по замечанию (обязателен):") || "";
    if (!comment.trim()) return;
    try { await post(`/api/issues/${id}/status`, { status, comment, actor: localStorage.getItem("actor") || "reviewer" }); setToast("Статус замечания обновлён"); reload(); } catch (e: any) { setToast(e.message); }
  };
  return (
    <div className="card">
      <div className="filters">
        <label>Правило<select className="input" value={f.check} onChange={(e) => set({ check: e.target.value })}><option value="">все</option>
          {(data?.facets || []).map(([k, n]: any) => <option key={k} value={k}>{ISSUE_LABEL[k] || k} ({n})</option>)}</select></label>
        <label>Статус<select className="input" value={f.status} onChange={(e) => set({ status: e.target.value })}><option value="">все</option><option value="open">открытые</option><option value="resolved">решённые</option><option value="wont_fix">не исправлять</option></select></label>
        <label>Публикация<input className="input" style={{ width: 90 }} value={f.pub} onChange={(e) => set({ pub: e.target.value.toUpperCase() })} /></label>
        <a className="btn" href={`/api/export/${domain}/${split}/issues_report.csv`}>Отчёт CSV</a>
      </div>
      {loading && !data && <Loading rows={8} />}
      {error && <ErrorState error={error} retry={reload} />}
      {data && data.total === 0 && <Empty title="Замечаний нет" />}
      {data && data.total > 0 && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Публ.</th><th>ID</th><th>Правило</th><th>Описание</th><th>Записи</th><th>Статус</th><th /></tr></thead>
        <tbody>{data.rows.map((i: any) => <tr key={i.id}><td><Link className="mono" to={`/pub/${domain}/${split}/${i.pub_id}`}>{i.pub_id}</Link></td><td className="mono">{i.data.issue_id}</td>
          <td><IssueTag t={i.data.check_name} /></td><td><div className="clip2 small" title={i.data.description}>{i.data.description}</div>{i.evidence?.formula && <div className="small faint mono">{i.evidence.formula}</div>}</td>
          <td><div className="row" style={{ gap: 4 }}>{i.record_links.slice(0, 6).map((l: any) => l.id ? <Link key={l.rec_id} className="mono small" to={`/record/${l.id}`}>{l.rec_id}</Link> : <span key={l.rec_id} className="mono small">{l.rec_id}</span>)}{i.record_links.length > 6 ? "…" : ""}</div></td>
          <td><Badge cls={i.verification_status === "open" ? "b-warn" : "b-ok"}>{i.verification_status}</Badge></td>
          <td className="nowrap">{i.verification_status === "open" ? <><button className="btn sm" onClick={() => setStatus(i.id, "resolved")}>Решено</button> <button className="btn sm ghost" onClick={() => setStatus(i.id, "wont_fix")}>Оставить</button></> : <button className="btn sm ghost" onClick={() => setStatus(i.id, "open")}>Открыть</button>}</td></tr>)}</tbody></table></div>}
      {toast && <Toast msg={toast} onDone={() => setToast("")} />}
    </div>
  );
}

function Corpus() {
  const { domain, split } = useScope();
  const corp = useAsync(() => api<any[]>(`/api/corpus${qs({ domain, split })}`), [domain, split]);
  const jobs = useAsync(() => api<any[]>("/api/jobs"), []);
  const [mode, setMode] = useState("default");
  const [pubs, setPubs] = useState("");
  const [toast, setToast] = useState("");
  const running = (jobs.data || []).some((j) => j.status === "running" || j.status === "queued");
  useEffect(() => { if (!running) return; const t = setInterval(() => { jobs.reload(); corp.reload(); }, 4000); return () => clearInterval(t); }, [running]);
  const start = async (ids?: string[]) => {
    try {
      const r = await post("/api/jobs", { domains: [domain], splits: [split], pub_ids: ids && ids.length ? ids : null, mode, actor: localStorage.getItem("actor") || "admin" });
      setToast(`Задача #${r.job_id} запущена`); jobs.reload();
    } catch (e: any) { setToast(e.message); }
  };
  const c = corp.data || [];
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="grid g4">
        <Kpi l="PDF в наборе" v={c.length} s={`сканов: ${c.filter((x) => x.is_scan).length}`} />
        <Kpi l="Обработано" v={c.filter((x) => x.status === "done").length} tone="ok" />
        <Kpi l="Ошибки" v={c.filter((x) => x.status === "error").length} tone={c.some((x) => x.status === "error") ? "err" : undefined} />
        <Kpi l="Страниц OCR" v={c.reduce((a, x) => a + (x.stats?.ocr_pages || 0), 0)} s="Tesseract, только страницы без текстового слоя" />
      </div>
      <div className="card card-b stack">
        <h3>Запуск обработки</h3>
        <div className="row">
          <div className="seg" role="radiogroup" aria-label="Режим"><button className={mode === "default" ? "on" : ""} onClick={() => setMode("default")}>Обычный: нода A + проверки</button>
            <button className={mode === "extended" ? "on" : ""} onClick={() => setMode("extended")}>Расширенный: A + B + C</button></div>
          <input className="input" value={pubs} onChange={(e) => setPubs(e.target.value)} placeholder="ID через запятую (пусто = весь набор)" style={{ minWidth: 260 }} aria-label="Публикации" />
          <button className="btn primary" disabled={running} onClick={() => start(pubs.split(",").map((x) => x.trim().toUpperCase()).filter(Boolean))}>Запустить для {domain}/{split}</button>
        </div>
        <div className="small muted">Без настроенного LLM работает только детерминированная нода R (таблицы по геометрии + текстовые шаблоны). Ручные решения при повторном запуске сохраняются.</div>
      </div>
      <div className="card"><div className="card-h"><b>Задачи</b>{running && <Badge cls="b-warn">выполняется…</Badge>}</div>
        {jobs.data && jobs.data.length === 0 && <Empty title="Задач ещё не было" />}
        {jobs.data && jobs.data.length > 0 && <div className="tbl-wrap" style={{ maxHeight: 300 }}><table className="tbl"><thead><tr><th>#</th><th>Параметры</th><th>Статус</th><th>Прогресс</th><th>Создана</th><th>Журнал</th></tr></thead>
          <tbody>{jobs.data.map((j) => <tr key={j.id}><td className="num">{j.id}</td><td className="small mono">{JSON.stringify(j.params)}</td>
            <td><Badge cls={j.status === "done" ? "b-ok" : j.status.includes("error") ? "b-err" : "b-warn"}>{j.status}</Badge></td><td className="num">{j.done}/{j.total}</td><td className="small">{j.created}</td>
            <td><details className="more"><summary>журнал</summary><pre className="code">{j.log || "—"}</pre></details></td></tr>)}</tbody></table></div>}</div>
      <div className="card"><div className="card-h"><b>Состояние публикаций</b></div>
        {corp.loading && !corp.data && <Loading />}
        {corp.error && <ErrorState error={corp.error} retry={corp.reload} />}
        {c.length > 0 && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>ID</th><th>Статус</th><th>Стр.</th><th>Текст</th><th>OCR</th><th>Значений</th><th>Подтв.</th><th>На пров.</th><th>Время</th><th>Токены</th><th>SHA-256</th><th /></tr></thead>
          <tbody>{c.map((x) => <tr key={x.pub_id}><td><Link className="mono" to={`/pub/${domain}/${split}/${x.pub_id}`}>{x.pub_id}</Link></td>
            <td><Badge cls={x.status === "done" ? "b-ok" : x.status === "error" ? "b-err" : "b-plain"} title={x.error || ""}>{x.stage || x.status}</Badge></td>
            <td className="num">{x.pages ?? "—"}</td><td className="num">{x.text_pages ?? "—"}</td><td className="num">{x.stats?.ocr_pages ?? (x.is_scan ? "?" : 0)}</td>
            <td className="num">{x.stats?.results ?? "—"}</td><td className="num">{x.stats?.verified ?? "—"}</td><td className="num">{x.stats ? (x.stats.needs_review || 0) + (x.stats.flagged || 0) : "—"}</td>
            <td className="num">{x.stats?.seconds ?? "—"}</td><td className="num">{x.stats ? `${x.stats.tokens_in || 0}/${x.stats.tokens_out || 0}` : "—"}</td>
            <td className="mono small faint">{(x.sha256 || "").slice(0, 12)}</td>
            <td><button className="btn sm" disabled={running} onClick={() => start([x.pub_id])}>Перезапустить</button></td></tr>)}</tbody></table></div>}</div>
      {toast && <Toast msg={toast} onDone={() => setToast("")} />}
    </div>
  );
}

function PRF({ t, x }: { t: string; x: any }) {
  if (!x) return null;
  return <tr><td>{t}</td><td className="num">{x.matched}</td><td className="num">{x.pred}</td><td className="num">{x.gold}</td><td className="num">{pct(x.precision)}</td><td className="num">{pct(x.recall)}</td><td className="num"><b>{pct(x.f1)}</b></td></tr>;
}

function Metrics() {
  const { domain, split } = useScope();
  const [refresh, setRefresh] = useState(0);
  const { data, error, loading, reload } = useAsync(() => api(`/api/metrics/${domain}/${split}${refresh ? "?refresh=true" : ""}`), [domain, split, refresh]);
  const t = data?.technical || data;
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row between"><div className="small muted">{split === "dev" ? "Сравнение с dev_gold выполняется только после извлечения; конвейер не читает эталон." : "Для test эталона нет: показываются только технические показатели."}</div>
        <button className="btn sm" onClick={() => setRefresh((x) => x + 1)}>Пересчитать</button></div>
      {loading && !data && <Loading rows={8} />}
      {error && <ErrorState error={error} retry={reload} />}
      {data && split === "dev" && data.headline_strict_L3 && (
        <div className="card"><div className="card-h"><b>Качество извлечения vs dev_gold</b><span className="small muted">доля оцифрованных графиков в эталоне: {pct(data.gold_digitised_share)} (их мы по ТЗ не оцифровываем)</span></div>
          <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Срез / уровень сопоставления</th><th>Совпало</th><th>Извлечено</th><th>Эталон</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>
            <PRF t="L3 строгий (основной): страница+значение+метрика+k+набор/конфигурация" x={data.headline_strict_L3} />
            <PRF t="L2: страница+значение+метрика+k" x={data.L2_value_metric} />
            <PRF t="L1: страница+значение" x={data.L1_value_page} />
            <PRF t="L3, только напечатанные значения эталона" x={data.printed_subset_L3} />
            <PRF t="L2, только напечатанные значения эталона" x={data.printed_subset_L2} />
            {Object.entries(data.slices_L2 || {}).map(([k, v]) => <PRF key={k} t={`L2 · срез: ${k}`} x={v} />)}
          </tbody></table></div>
          <div className="card-b small muted">Правило: {data.matching_rule}</div>
          <div className="card-b small">Совпадение области (in_scope): {data.scope_agreement?.agree}/{data.scope_agreement?.total} {Object.keys(data.scope_agreement?.disagreements || {}).length ? `— расхождения: ${JSON.stringify(data.scope_agreement.disagreements)}` : ""}</div>
        </div>)}
      {t && t.results !== undefined && (
        <div className="grid g4">
          <Kpi l="Покрытие публикаций" v={`${t.coverage_pubs_with_results}/${t.publications}`} s={`исключено: ${t.excluded}, ошибок: ${t.errors}`} />
          <Kpi l="Буквально подтверждённые цитаты" v={pct(t.quote_literal_share)} tone="ok" s={`только OCR: ${pct(t.quote_ocr_only_share)}`} />
          <Kpi l="С ручной проверкой" v={pct(t.manual_review_share)} />
          <Kpi l="Время / стоимость" v={`${t.processing_seconds} с`} s={`$${t.cost_usd} · OCR стр.: ${t.ocr_pages}`} />
        </div>)}
      {t && t.results !== undefined && (
        <div className="grid g3">
          <div className="card card-b"><h3>Проверка цитат</h3><dl className="kv">{Object.entries(t.quote_outcomes).map(([k, v]: any) => <><dt key={k}>{k}</dt><dd key={k + "v"}>{v}</dd></>)}</dl></div>
          <div className="card card-b"><h3>Кворум</h3><dl className="kv">{Object.entries(t.quorum).map(([k, v]: any) => <><dt key={k}>{k}</dt><dd key={k + "v"}>{v}</dd></>)}</dl></div>
          <div className="card card-b"><h3>Замечания по типам</h3><dl className="kv">{Object.entries(t.issues_by_type).map(([k, v]: any) => <><dt key={k}>{ISSUE_LABEL[k] || k}</dt><dd key={k + "v"}>{v}</dd></>)}</dl></div>
        </div>)}
      {data?.per_publication && <div className="card"><div className="card-h"><b>По публикациям (dev)</b></div><div className="tbl-wrap" style={{ maxHeight: 380 }}><table className="tbl"><thead><tr><th>Публ.</th><th>Эталон</th><th>из них напечатано</th><th>Извлечено</th><th>L2</th><th>L3</th><th>Скан</th></tr></thead>
        <tbody>{Object.entries(data.per_publication).map(([k, v]: any) => <tr key={k}><td><Link className="mono" to={`/pub/${domain}/${split}/${k}`}>{k}</Link></td><td className="num">{v.gold}</td><td className="num">{v.gold_printed}</td><td className="num">{v.pred}</td><td className="num">{v.match_L2}</td><td className="num">{v.match_L3}</td><td>{v.scan ? <Badge cls="b-warn">скан</Badge> : ""}</td></tr>)}</tbody></table></div></div>}
    </div>
  );
}

function LLM() {
  const { data, error, loading, reload } = useAsync(() => api("/api/admin/llm"), []);
  const [form, setForm] = useState<any>({});
  const [key, setKey] = useState("");
  const [backupKey, setBackupKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [test, setTest] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => { if (data) setForm(data); }, [data]);
  const save = async () => {
    setBusy(true); setMsg("");
    try { const r = await post("/api/admin/llm", { ...form, api_key: key || undefined, actor: localStorage.getItem("actor") || "admin" }); setForm(r); setKey(""); setMsg("Настройки сохранены"); reload(); }
    catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };
  const loadModels = async () => { setBusy(true); try { const r = await api("/api/admin/llm/models"); setModels(r.models || []); setMsg(r.error ? `Список моделей: ${r.error}` : `Моделей: ${r.models.length}`); } finally { setBusy(false); } };
  const runTest = async () => { setBusy(true); setTest(null); try { setTest(await post("/api/admin/llm/test", {})); } catch (e: any) { setTest({ probe_error: e.message }); } finally { setBusy(false); } };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} retry={reload} />;
  const F = (k: string, label: string, type = "text", hint?: string) => (
    <label className="small muted" style={{ display: "grid", gap: 3 }}>{label}
      <input className="input" type={type} value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: type === "number" ? Number(e.target.value) : e.target.value })} list={k.startsWith("model") ? "models" : undefined} />
      {hint && <span className="faint">{hint}</span>}</label>);
  return (
    <div className="grid g2" style={{ alignItems: "start" }}>
      <div className="card card-b stack">
        <h3>Подключение к LLM-шлюзу</h3>
        <div className="row">{data.api_key_set ? <Badge cls="b-ok">Ключ сохранён: {data.api_key_hint}</Badge> : <Badge cls="b-warn">Ключ не задан</Badge>}</div>
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Провайдер
          <select className="input" value={form.provider || "agentrouter"} onChange={(e) => { const p = e.target.value; const pr = data.presets?.[p] || {}; setForm({ ...form, provider: p, base_url: pr.base_url, model_a: pr.model }); }}>
            {Object.keys(data.presets || {}).map((p) => <option key={p} value={p}>{p}{data.presets[p].api === "responses" ? " (Responses API)" : ""}</option>)}</select>
          <span className="faint">AgentRouter: /v1/responses с идентификацией клиента; остальные — OpenAI-совместимый /chat/completions.</span></label>
        {F("base_url", "Base URL", "text")}
        <label className="small muted" style={{ display: "grid", gap: 3 }}>API-ключ
          <input className="input" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={data.api_key_set ? "оставьте пустым, чтобы не менять" : "вставьте ключ"} />
          <span className="faint">Хранится только локально в базе приложения, не попадает в экспорт и журналы.</span></label>
        <div className="row"><button className="btn primary" disabled={busy} onClick={save}>Сохранить</button><button className="btn" disabled={busy || !data.api_key_set} onClick={loadModels}>Загрузить список моделей</button>
          <button className="btn" disabled={busy || !data.api_key_set} onClick={runTest}>Проверить соединение</button>
          {data.api_key_set && <button className="btn ghost danger" disabled={busy} onClick={async () => { await post("/api/admin/llm", { clear_key: true }); reload(); }}>Удалить ключ</button>}</div>
        <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          <b className="small">Ключи провайдера {form.provider} (по порядку)</b>
          <div className="small muted">Если на ключе кончилась квота или он отклонён, запрос повторяется со следующим ключом этого провайдера и только потом идёт дальше по цепочке резервов.</div>
          {(data.key_pools?.[form.provider] || []).length === 0 && <span className="small faint">Ключей нет</span>}
          {(data.key_pools?.[form.provider] || []).map((h: string, i: number) => (
            <div key={i} className="row small"><span className="tag mono">{i === 0 ? "основной" : `резерв ${i}`}: {h}</span>
              {data.breaker?.[`${form.provider}/${form.model_a}#${i + 1}`] ? <Badge cls="b-err">квота: пауза {data.breaker[`${form.provider}/${form.model_a}#${i + 1}`]} мин</Badge> : null}
              <button className="btn sm ghost danger" disabled={busy} onClick={async () => { await post("/api/admin/llm", { provider: form.provider, remove_key_index: i }); reload(); }}>Удалить</button></div>))}
          <label className="small muted" style={{ display: "grid", gap: 3 }}>Добавить резервный ключ
            <div className="row"><input className="input" style={{ flex: 1 }} type="password" autoComplete="off" value={backupKey} onChange={(e) => setBackupKey(e.target.value)} placeholder="вставьте резервный ключ" aria-label="Резервный ключ" />
              <button className="btn" disabled={busy || !backupKey.trim()} onClick={async () => { setBusy(true); try { await post("/api/admin/llm", { provider: form.provider, add_key: backupKey }); setBackupKey(""); setMsg("Резервный ключ добавлен"); reload(); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); } }}>Добавить</button></div></label>
        </div>
        {msg && <div className="notice info small">{msg}</div>}
        {test &&<div className={`notice ${test.ok ? "ok" : "err"} small`}><div>{test.message}</div><div>Провайдер: {test.provider} · {test.base_url} · модель {test.model} · ключ: {test.key_source || "нет"}</div>
          {test.models && <div>Модели доступны: {test.models.length}</div>}{test.models_error && <div>Список моделей: {test.models_error}</div>}
          {test.probe && <div>Проба модели {test.probe.model}: «{test.probe.reply}» за {test.probe.seconds} с</div>}{test.probe_error && <div>Проба: {test.probe_error}</div>}</div>}
      </div>
      <div className="card card-b stack">
        <h3>Модели нод</h3>
        <datalist id="models">{models.map((m) => <option key={m} value={m} />)}</datalist>
        {F("model_a", "Нода A — основное извлечение (весь корпус)", "text", "По умолчанию — модель пресета провайдера.")}
        {F("model_b", "Нода B — независимое извлечение (расширенный режим)", "text", "Лучше другая модель: одна и та же модель даёт повторный запуск, а не независимость.")}
        {F("model_c", "Нода C — точечное перечитывание при расхождении")}
        {F("model_vision", "Vision — чтение напечатанных чисел на рисунках")}
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Reasoning effort (Responses API)
          <select className="input" value={form.reasoning_effort || "low"} onChange={(e) => setForm({ ...form, reasoning_effort: e.target.value })}>
            {["minimal", "low", "medium", "high", "default"].map((x) => <option key={x}>{x}</option>)}</select><span className="faint">Замер 21.11: AgentRouter фактически игнорирует этот параметр (~20 тыс. reasoning-токенов при любом значении).</span></label>
        <div className="grid g2">{F("page_workers", "Параллельных запросов (страниц)", "number")}{F("max_tokens", "Max tokens", "number")}{F("timeout_s", "Таймаут, с", "number")}{F("price_in_per_mtok", "Цена вход, $/1M ток.", "number")}{F("price_out_per_mtok", "Цена выход, $/1M ток.", "number")}</div>
        <button className="btn primary" disabled={busy} onClick={save}>Сохранить модели</button>
        <div className="small muted">Нода R (правила) работает всегда и служит независимой второй нодой для кворума, если B не задана. C не является безусловным судьёй: неразрешённые расхождения уходят человеку; число перечитываний ограничено.</div>
      </div>
      <div className="card card-b stack" style={{ gridColumn: "1 / -1" }}>
        <h3>Цепочка резервов</h3>
        <div className="small muted">Если основной провайдер вернул «квота исчерпана», ошибку ключа, «модель недоступна» или не ответил после повторов, запрос уходит дальше по списку.
          Провайдер с исчерпанной квотой пропускается {form.breaker_minutes || 30} мин. Локальный Claude Code (claude-cli) изображения не принимает — для Vision он пропускается.
          Кто фактически ответил, записывается в журнал нод (served_by).</div>
        <ol className="stack" style={{ margin: 0, paddingLeft: 20 }}>
          <li className="small"><b>{form.provider}</b> / модель ноды (основной)</li>
          {(form.fallback_chain || []).map((st: any, i: number) => (
            <li key={i}><div className="row">
              <select className="input" value={st.provider} aria-label={`Провайдер шага ${i + 1}`}
                onChange={(e) => { const c = [...form.fallback_chain]; c[i] = { ...st, provider: e.target.value }; setForm({ ...form, fallback_chain: c }); }}>
                {Object.keys(data.presets || {}).map((p) => <option key={p} value={p}>{p}</option>)}</select>
              <input className="input" value={st.model} list="models" aria-label={`Модель шага ${i + 1}`}
                onChange={(e) => { const c = [...form.fallback_chain]; c[i] = { ...st, model: e.target.value }; setForm({ ...form, fallback_chain: c }); }} />
              {(data.keys_set || []).includes(st.provider) ? <Badge cls="b-ok">ключ есть</Badge> : <Badge cls="b-warn">нет ключа — шаг пропустится</Badge>}
              {data.breaker?.[`${st.provider}/${st.model}`] ? <Badge cls="b-err">квота: пауза {data.breaker[`${st.provider}/${st.model}`]} мин</Badge> : null}
              <button className="btn sm ghost" disabled={i === 0} onClick={() => { const c = [...form.fallback_chain]; [c[i - 1], c[i]] = [c[i], c[i - 1]]; setForm({ ...form, fallback_chain: c }); }} aria-label="Выше">↑</button>
              <button className="btn sm ghost danger" onClick={() => setForm({ ...form, fallback_chain: form.fallback_chain.filter((_: any, j: number) => j !== i) })} aria-label="Удалить шаг">✕</button>
            </div></li>))}
        </ol>
        <div className="row"><button className="btn sm" onClick={() => setForm({ ...form, fallback_chain: [...(form.fallback_chain || []), { provider: "claude-cli", model: "haiku" }] })}>+ Добавить шаг</button>
          <button className="btn primary" disabled={busy} onClick={save}>Сохранить цепочку</button></div>
      </div>
    </div>
  );
}

function Config() {
  const { domain } = useScope();
  const { data, error, loading, reload } = useAsync(() => api(`/api/admin/config/${domain}`), [domain]);
  const [text, setText] = useState("");
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState<{ t: string; ok: boolean } | null>(null);
  useEffect(() => { if (data) setText(data.yaml); }, [data]);
  const save = async () => {
    setMsg(null);
    try { await put(`/api/admin/config/${domain}`, { yaml: text, comment, actor: localStorage.getItem("actor") || "admin" }); setMsg({ t: "Конфигурация сохранена и загружена. Изменения применятся при следующей обработке.", ok: true }); reload(); }
    catch (e: any) { setMsg({ t: e.message, ok: false }); }
  };
  if (loading && !data) return <Loading />;
  if (error) return <ErrorState error={error} retry={reload} />;
  return (
    <div className="grid g2" style={{ alignItems: "start" }}>
      <div className="card card-b stack"><h3>domains/{domain}.yaml — словари, нормализация, правила</h3>
        <textarea className="input mono" rows={28} value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label="YAML конфигурации" />
        <input className="input" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Причина изменения (попадёт в аудит)" />
        <div className="row"><button className="btn primary" onClick={save} disabled={text === data.yaml}>Сохранить</button><button className="btn ghost" onClick={() => setText(data.yaml)}>Отменить правки</button></div>
        {msg && <div className={`notice ${msg.ok ? "ok" : "err"}`}>{msg.t}</div>}
      </div>
      <div className="card card-b stack"><h3>Официальная схема (из шаблонов комплекта, только чтение)</h3>
        {Object.entries(data.tables).map(([t, cols]: any) => <details key={t} className="more"><summary>{t}.csv · {cols.length} колонок</summary><div className="row" style={{ gap: 4 }}>{cols.map((c: string) => <span key={c} className="tag mono">{c}</span>)}</div></details>)}
        <h3 style={{ marginTop: 10 }}>Закрытые словари</h3>
        {Object.entries(data.closed_enums).map(([k, v]: any) => <div key={k} className="small"><span className="mono">{k}</span>: {v.join(", ")}</div>)}
      </div>
    </div>
  );
}

function Audit() {
  const { domain } = useScope();
  const [f, set] = useUrlState({ pub: "", action: "" });
  const { data, error, loading, reload } = useAsync(() => api<any[]>(`/api/audit${qs({ domain: f.action.startsWith("llm") ? "" : domain, ...f })}`), [domain, f.pub, f.action]);
  return (
    <div className="card">
      <div className="filters">
        <label>Публикация<input className="input" style={{ width: 90 }} value={f.pub} onChange={(e) => set({ pub: e.target.value.toUpperCase() })} /></label>
        <label>Действие<select className="input" value={f.action} onChange={(e) => set({ action: e.target.value })}><option value="">все</option><option value="review">ручные решения</option>
          <option value="export">экспорт</option><option value="process">автоматическая обработка</option><option value="config">конфигурации</option><option value="official_check">официальный проверщик</option><option value="issue">замечания</option><option value="job">задачи</option></select></label>
      </div>
      {loading && !data && <Loading />}
      {error && <ErrorState error={error} retry={reload} />}
      {data && data.length === 0 && <Empty title="Событий нет" />}
      {data && data.length > 0 && <div className="tbl-wrap"><table className="tbl"><thead><tr><th>Когда</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Почему</th><th>Что изменилось</th></tr></thead>
        <tbody>{data.map((a) => <tr key={a.id}><td className="small nowrap">{a.ts}</td><td>{a.actor}</td><td><span className="tag">{a.action}</span></td>
          <td className="mono small">{[a.domain, a.split, a.pub_id, a.tbl, a.rec_id].filter(Boolean).join("/")}</td><td className="small"><div className="clip2">{a.reason}</div></td>
          <td>{(a.before || a.after) && <details className="more"><summary className="small">diff</summary><pre className="code">{JSON.stringify({ before: a.before, after: a.after }, null, 1).slice(0, 4000)}</pre></details>}</td></tr>)}</tbody></table></div>}
    </div>
  );
}
