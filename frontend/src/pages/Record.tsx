import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, DOMAIN_LONG, post } from "../api";
import SourceViewer from "../components/SourceViewer";
import { Badge, ErrorState, IssueTag, Loading, OriginBadge, QuoteBadge, ReviewBadge, Toast, useAsync, VerBadge } from "../components/ui";

const LINK_TITLE: Record<string, string> = { experiment_id: "Эксперимент", config_id: "Конфигурация", dataset_id: "Набор данных", task_id: "Задача",
  device_id: "Прибор", measurement_id: "Измерение", material_id: "Материал" };

function Chain({ r }: { r: any }) {
  const q = (r.checks || []).find((c: any) => c.check === "quote") || {};
  const rules = (r.checks || []).filter((c: any) => !["quote", "table_cell"].includes(c.check));
  const qo = r.quorum?.outcome;
  const ev = r.evidence || {};
  const st = (ok: boolean | null, warn = false) => (ok === null ? "" : ok ? "ok" : warn ? "warn" : "err");
  return (
    <div className="chain" aria-label="Цепочка обработки">
      <span className="step ok">PDF {r.pub_id}{r.is_scan ? " (скан)" : ""}</span><span className="arr">→</span>
      <span className={`step ${r.is_scan ? "warn" : "ok"}`}>{r.is_scan ? "OCR Tesseract" : "текстовый слой"}</span><span className="arr">→</span>
      <span className="step ok">нода {r.node} · {ev.kind || "?"}</span><span className="arr">→</span>
      <span className={`step ${st(!!ev.norm?.output?.[0], true)}`}>нормализация</span><span className="arr">→</span>
      <span className={`step ${st(q.outcome === "matched", q.outcome === "matched_ocr_only" || q.outcome === "no_fragment")}`}>источник: {q.outcome || "—"}</span><span className="arr">→</span>
      <span className={`step ${qo === "agree" || qo === "resolved_by_C" ? "ok" : qo === "disagree" || qo === "unresolved" ? "err" : ""}`}>кворум: {qo || "—"}</span><span className="arr">→</span>
      <span className={`step ${rules.some((x: any) => x.outcome === "fail") ? "err" : rules.length ? "ok" : ""}`}>правила: {rules.length ? (rules.some((x: any) => x.outcome === "fail") ? "нарушение" : "пройдены") : "не применимы"}</span><span className="arr">→</span>
      <span className={`step ${r.verification_status === "verified" ? "ok" : r.verification_status === "flagged" ? "err" : "warn"}`}>{r.verification_status}</span>
      {r.review_status !== "none" && <><span className="arr">→</span><span className={`step ${r.review_status === "confirmed" || r.review_status === "corrected" ? "ok" : r.review_status === "rejected" ? "err" : "warn"}`}>человек: {r.review_status}</span></>}
    </div>
  );
}

export default function RecordPage() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api(`/api/records/${id}`), [id]);
  const [toast, setToast] = useState("");
  if (loading && !data) return <Loading rows={12} />;
  if (error) return <ErrorState error={error} retry={reload} />;
  const r = data;
  const d = r.data;
  const isResult = r.tbl === "results";
  const q = (r.checks || []).find((c: any) => c.check === "quote") || {};
  const cell = r.evidence?.cell_bbox || r.evidence?.row_bbox || null;
  const page = Number(d.source_page) || 1;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="topbar">
        <div style={{ minWidth: 0 }}>
          <div className="crumbs"><Link to={`/catalog?domain=${r.domain}&split=${r.split}`}>{DOMAIN_LONG[r.domain]} · {r.split}</Link> / <Link to={`/pub/${r.domain}/${r.split}/${r.pub_id}`}>{r.pub_id}</Link> / {r.rec_id}</div>
          <h1>{isResult ? <>{d.metric_name || "Показатель"} <span className="mono" style={{ fontWeight: 500 }}>= {d.raw_value} {d.raw_unit}</span></> : `${r.tbl} ${r.rec_id}`}</h1>
          <div className="muted small wrap-any">{r.publication?.title}</div>
          {isResult && <div className="row" style={{ marginTop: 8 }}><VerBadge v={r.verification_status} /><QuoteBadge v={q.outcome} /><ReviewBadge v={r.review_status} /><OriginBadge o={d.result_origin} />
            {d.extraction_status && <Badge cls="b-plain">извлечение: {d.extraction_status}</Badge>}
            {d.duplicate_of && <Link className="tag" to={r.duplicate_record ? `/record/${r.duplicate_record}` : "#"}>повтор записи {d.duplicate_of}</Link>}</div>}
        </div>
      </div>
      {isResult && <Chain r={r} />}
      <div className="split">
        <div className="stack" style={{ gap: 14, minWidth: 0 }}>
          {isResult && (
            <section className="card card-b stack">
              <h3>Значение: опубликовано · нормализовано · проверено</h3>
              <div className="triple">
                <div><div className="t">Опубликовано (raw)</div><div className="v">{d.raw_value || "—"}</div><div className="small muted">{d.raw_unit || "единица не указана"}</div></div>
                <div><div className="t">Нормализовано</div><div className="v">{d.normalized_value || "—"}</div><div className="small muted">{d.normalized_unit || "без пересчёта"}</div>
                  {r.evidence?.norm?.rule && <div className="small faint">{r.evidence.norm.rule}</div>}</div>
                <div><div className="t">Проверено</div><div style={{ marginTop: 4 }}><VerBadge v={r.verification_status} /></div>
                  <div className="small muted" style={{ marginTop: 4 }}>{(r.evidence?.reasons || []).join(", ") || "все машинные проверки пройдены"}</div></div>
              </div>
              <dl className="kv">
                <dt>Показатель</dt><dd><b>{d.metric_name}</b>{d.metric_variant ? ` · ${d.metric_variant}` : ""}{d.metric_k ? ` · k=${d.metric_k}` : ""}{d.metric_direction ? ` · ${d.metric_direction}` : ""}</dd>
                {d.aggregation !== undefined && <><dt>Агрегация</dt><dd>{d.aggregation || <span className="faint">в статье не указано (пусто, не угадывается)</span>}</dd></>}
                {d.spread_value && <><dt>Разброс / n</dt><dd>{d.spread_value} / {d.n_devices}</dd></>}
                {d.time_point && <><dt>Момент времени</dt><dd>{d.time_point} {d.time_unit}</dd></>}
                {d.sample_size && <><dt>Размер выборки</dt><dd>{d.sample_size}</dd></>}
                {d.baseline_value && <><dt>Baseline</dt><dd>{d.baseline_value}</dd></>}
                <dt>Происхождение</dt><dd><OriginBadge o={d.result_origin} /> {d.cited_publication_id && <span className="mono">ссылка в статье: {d.cited_publication_id}</span>}</dd>
                {d.note && <><dt>Примечание</dt><dd className="small">{d.note}</dd></>}
              </dl>
            </section>
          )}
          {isResult && (
            <section className="card card-b stack">
              <h3>Источник</h3>
              <dl className="kv">
                <dt>Страница PDF</dt><dd><b>{d.source_page || "—"}</b> из {r.page_count}</dd>
                <dt>Раздел</dt><dd>{d.source_section || <span className="faint">не определён</span>}</dd>
                {d.source_table && <><dt>Таблица</dt><dd>{d.source_table}{r.evidence?.row_label ? ` · строка «${r.evidence.row_label}»` : ""}{r.evidence?.col_label ? ` · столбец «${r.evidence.col_label}»` : ""}</dd></>}
                {d.source_figure && <><dt>Рисунок</dt><dd>{d.source_figure} <Badge cls="b-warn">требует визуальной проверки</Badge></dd></>}
              </dl>
              {d.source_fragment ? <div className={`quote ${q.outcome === "matched" ? "" : "bad"}`}>«{d.source_fragment}»</div> : <div className="notice">Дословной цитаты нет — только указатель на таблицу/рисунок; нужна визуальная проверка.</div>}
              {r.evidence?.failed_fragment && <div className="small muted">Цитата, предложенная нодой и не найденная: «{r.evidence.failed_fragment}»</div>}
              <div className="row small">
                {q.engines?.length ? <span>Найдена движками: {q.engines.map((e: string) => <span key={e} className="tag">{e}</span>)}</span> : null}
                {q.value_in_fragment === true && <Badge cls="b-ok">число есть в цитате</Badge>}
                {q.value_in_fragment === false && <Badge cls="b-warn">числа нет в цитате{cell ? " — подтверждено ячейкой таблицы" : ""}</Badge>}
                {q.other_pages?.length ? <Badge cls="b-err">найдена на с. {q.other_pages.join(", ")}</Badge> : null}
                {q.paraphrase_suspect && <Badge cls="b-err">похоже на пересказ, а не цитату</Badge>}
              </div>
            </section>
          )}
          {isResult && Object.keys(r.linked || {}).length > 0 && (
            <section className="card card-b stack"><h3>Связанные записи (условия)</h3>
              {Object.entries(r.linked).map(([k, e]: any) => (
                <details key={k} className="more"><summary>{LINK_TITLE[k] || k}: <span className="mono">{d[k]}</span> {e ? <span className="muted">{e.data.rag_variant || e.data.dataset_name || e.data.task_type || e.data.device_label || e.data.material_name_raw || e.data.measurement_type || (e.data.evaluation_protocol || "").slice(0, 80)}</span> : <Badge cls="b-err">связь разорвана</Badge>}</summary>
                  {e && <dl className="kv">{Object.entries(e.data).filter(([kk, vv]) => vv && kk !== "publication_id").map(([kk, vv]: any) => <><dt key={kk + "t"}>{kk}</dt><dd key={kk}>{vv}</dd></>)}</dl>}
                </details>))}
            </section>
          )}
          {isResult && (
            <section className="card card-b stack"><h3>Проверки</h3>
              {(r.checks || []).map((c: any, i: number) => (
                <div key={i} className="stack" style={{ gap: 4, borderBottom: "1px solid var(--line)", paddingBottom: 8 }}>
                  <div className="row between"><b>{c.check}</b><span className="row small"><Badge cls={["matched", "pass", "value_at_cell"].includes(c.outcome) ? "b-ok" : c.outcome === "fail" || c.outcome === "not_found" || c.outcome === "wrong_page" ? "b-err" : "b-warn"}>{c.outcome}</Badge><span className="faint">{c.ts}</span></span></div>
                  {c.formula && <div className="formula">{c.formula}{c.computed !== undefined ? ` → расчёт ${c.computed}` : ""}{c.rel_diff !== undefined ? `, отклонение ${(c.rel_diff * 100).toFixed(2)} % (порог ${(c.threshold ?? 0) * 100} %)` : ""}<br />входные: {JSON.stringify(c.inputs)}</div>}
                  {c.detail && <div className="small muted">{c.detail}</div>}
                  {c.action && <div className="small"><Badge cls="b-violet">{c.action}</Badge></div>}
                </div>))}
            </section>
          )}
          {isResult && (
            <section className="card card-b stack"><h3>Кворум нод</h3>
              <dl className="kv">
                <dt>Режим</dt><dd>{r.quorum?.mode || "—"} · ноды: {(r.quorum?.nodes || []).join(", ") || "—"}</dd>
                <dt>Исход</dt><dd><Badge cls={r.quorum?.outcome === "agree" ? "b-ok" : r.quorum?.outcome === "disagree" || r.quorum?.outcome === "unresolved" ? "b-err" : "b-plain"}>{({ agree: "ноды совпали", disagree: "ноды разошлись", single: "значение нашла одна нода", single_node: "работала одна нода", resolved_by_C: "C перечитала и поддержала одну версию", unresolved: "не разрешено — к человеку" } as any)[r.quorum?.outcome] || "—"}</Badge></dd>
                {r.quorum?.other_value && <><dt>Другая нода прочла</dt><dd className="mono">{r.quorum.other_value}</dd></>}
                {r.quorum?.C && <><dt>Нода C</dt><dd className="small">{JSON.stringify(r.quorum.C)}</dd></>}
                {r.quorum?.limitation && <><dt>Ограничение</dt><dd className="small">{r.quorum.limitation}</dd></>}
                {r.quorum?.same_model_limitation && <><dt>Ограничение</dt><dd className="small">A и B — одна модель: это повторный запуск, а не независимые модели.</dd></>}
              </dl>
            </section>
          )}
          {r.issues?.length > 0 && <section className="card card-b stack"><h3>Замечания</h3>{r.issues.map((i: any) => (
            <div key={i.id} className="stack" style={{ gap: 4 }}><div className="row"><span className="mono small">{i.data.issue_id}</span><IssueTag t={i.data.check_name} /><Badge cls={i.verification_status === "open" ? "b-warn" : "b-ok"}>{i.verification_status}</Badge></div>
              <div className="wrap-any">{i.data.description}</div>{i.evidence?.formula && <div className="formula">{i.evidence.formula} · {JSON.stringify(i.evidence.inputs)}</div>}</div>))}</section>}
          <ReviewPanel r={r} onDone={(m) => { setToast(m); reload(); }} />
          <section className="card card-b"><details className="more"><summary>История изменений ({r.history?.length || 0})</summary>
            <div className="stack">{(r.history || []).map((h: any) => <div key={h.id} className="small"><span className="faint">{h.ts}</span> · <b>{h.actor}</b> · {h.action}{h.rec_id ? ` · ${h.rec_id}` : ""}{h.reason ? ` — «${h.reason}»` : ""}</div>)}</div></details></section>
        </div>
        <div className="sticky-col card card-b">
          {isResult ? <SourceViewer domain={r.domain} split={r.split} pid={r.pub_id} page={page} fragment={d.source_fragment} value={d.raw_value}
            cell={cell} pageCount={r.page_count} figure={d.source_figure && !d.source_table ? d.source_figure : undefined} /> :
            <SourceViewer domain={r.domain} split={r.split} pid={r.pub_id} page={1} pageCount={r.page_count} />}
        </div>
      </div>
      {toast && <Toast msg={toast} onDone={() => setToast("")} />}
    </div>
  );
}

function ReviewPanel({ r, onDone }: { r: any; onDone: (m: string) => void }) {
  const [mode, setMode] = useState<"" | "correct">("");
  const [comment, setComment] = useState("");
  const [actor, setActor] = useState(() => { try { return localStorage.getItem("actor") || ""; } catch { return ""; } });
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setEdit({}); setMode(""); setComment(""); }, [r.id]);
  const editable = (r.columns || []).filter((c: string) => !["publication_id", "result_id"].includes(c));
  const send = async (action: string) => {
    setErr("");
    if ((action === "correct" || action === "reject") && !comment.trim()) { setErr("Укажите причину решения — это требование аудита."); return; }
    setBusy(true);
    try { localStorage.setItem("actor", actor); } catch { /* ignore */ }
    try {
      await post(`/api/records/${r.id}/review`, { action, comment, actor: actor || "reviewer", data: action === "correct" ? edit : undefined });
      onDone({ confirm: "Запись подтверждена", correct: "Исправление сохранено и перепроверено", reject: "Запись отклонена и исключена из экспорта", reopen: "Запись возвращена в очередь" }[action] || "Сохранено");
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const rawChanged = edit.raw_value !== undefined && edit.raw_value !== r.data.raw_value;
  return (
    <section className="card card-b stack">
      <h3>Решение проверяющего</h3>
      <div className="row">
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Кто проверяет<input className="input" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="имя/логин" /></label>
      </div>
      <label className="small muted" style={{ display: "grid", gap: 3 }}>Комментарий (обязателен для исправления и отклонения)
        <textarea className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Например: сверено с таблицей 2, строка ThreadRAG" /></label>
      {mode === "correct" && (
        <div className="stack">
          <div className="notice info small">Исправляется <b>извлечение</b> (ошибка чтения). Исходный ответ ноды сохраняется в истории; опубликованное значение статьи не «улучшается» — если статья сама противоречива, оставьте значение и создайте замечание.</div>
          <div className="grid g2">{editable.map((c: string) => (
            <label key={c} className="small muted" style={{ display: "grid", gap: 3 }}>{c}
              <input className="input mono" value={edit[c] ?? r.data[c] ?? ""} onChange={(e) => setEdit({ ...edit, [c]: e.target.value })} /></label>))}</div>
          {rawChanged && <div className="notice">Вы меняете raw_value. Это допустимо только если нода неверно прочитала напечатанное число. Изменение будет явно отражено в аудите.</div>}
        </div>
      )}
      {err && <div className="notice err" role="alert">{err}</div>}
      <div className="row">
        <button className="btn teal" disabled={busy} onClick={() => send("confirm")}>✓ Подтвердить</button>
        {mode !== "correct" ? <button className="btn" disabled={busy} onClick={() => setMode("correct")}>✎ Исправить извлечение</button>
          : <button className="btn primary" disabled={busy} onClick={() => send("correct")}>Сохранить исправление</button>}
        <button className="btn danger" disabled={busy} onClick={() => send("reject")}>✕ Отклонить</button>
        {r.review_status !== "none" && r.review_status !== "pending" && <button className="btn ghost" disabled={busy} onClick={() => send("reopen")}>Вернуть в очередь</button>}
      </div>
    </section>
  );
}
