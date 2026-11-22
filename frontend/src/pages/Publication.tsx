import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, DOMAIN_LONG, quoteOutcome } from "../api";
import { Badge, Empty, ErrorState, IssueTag, Kpi, Loading, Term, useAsync } from "../components/ui";
import SourceViewer from "../components/SourceViewer";
import { ResultsTable } from "./Results";

const ENT_TITLE: Record<string, string> = { configurations: "Конфигурации", datasets: "Наборы данных", tasks: "Задачи", experiments: "Эксперименты",
  materials: "Материалы", devices: "Приборы", layers: "Слои", measurements: "Условия измерения" };

export default function Publication() {
  const { domain = "rag", split = "dev", pid = "" } = useParams();
  const { data, error, loading, reload } = useAsync(() => api(`/api/publications/${domain}/${split}/${pid}`), [domain, split, pid]);
  const [tab, setTab] = useState("results");
  if (loading && !data) return <Loading rows={10} />;
  if (error) return <ErrorState error={error} retry={reload} />;
  const p = data.publication?.data || {};
  const corp = data.corpus;
  const st = corp.stats || {};
  const res = data.results.map((r: any) => ({ ...r, quote_outcome: quoteOutcome(r.checks),
    issue_types: data.issues.filter((i: any) => (i.data.record_ids || "").split(";").includes(r.rec_id)).map((i: any) => i.data.check_name) }));
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="topbar">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="crumbs"><Link to={`/catalog?domain=${domain}&split=${split}`}>{DOMAIN_LONG[domain]} · {split}</Link> / {pid}</div>
          <h1 className="wrap-any">{p.title || <span className="faint">Название не извлечено</span>}</h1>
          <div className="muted small wrap-any">{(p.authors || "").split(";").filter(Boolean).slice(0, 8).join(", ")}{(p.authors || "").split(";").length > 8 ? " и др." : ""}</div>
          <div className="row small" style={{ marginTop: 6 }}>
            {p.year && <span className="tag">{p.year}</span>}
            {p.DOI && <span className="tag mono">DOI {p.DOI}</span>}
            {p.in_scope === "false" ? <Badge cls="b-plain">Исключена: {p.exclusion_reason}</Badge> : p.in_scope === "true" ? <Badge cls="b-ok">В предметной области</Badge> : null}
            {corp.is_scan ? <Badge cls="b-warn">Скан · OCR {st.ocr_pages} стр.{st.ocr_conf_mean ? ` · ср. уверенность ${st.ocr_conf_mean}` : ""}</Badge> : <Badge cls="b-info">Текстовый слой</Badge>}
            <Badge cls={corp.status === "done" ? "b-ok" : corp.status === "error" ? "b-err" : "b-plain"}>Обработка: {corp.status}</Badge>
            {st.primary_node && <span className="tag">основная нода {st.primary_node}</span>}
          </div>
        </div>
        <div className="row">
          <a className="btn" href={`/api/pdf/${domain}/${split}/${pid}.pdf`} target="_blank" rel="noreferrer">PDF ↗</a>
          <a className="btn" href={`/api/export/${domain}/${split}.zip?pub=${pid}`}>Экспорт CSV</a>
          <a className="btn teal" href={`/api/passport/${domain}/${split}/${pid}.pdf`} target="_blank" rel="noreferrer" title="PDF-отчёт: каждое значение с вырезкой страницы и цитатой, проблемные — первыми">Паспорт доказательств</a>
        </div>
      </div>
      {corp.status === "error" && <div className="notice err">Обработка завершилась ошибкой. Подробности — в «Корпус и задачи». <pre className="code">{(corp.error || "").slice(-800)}</pre></div>}
      <div className="grid g4">
        <Kpi l="Страниц / с текстом" v={`${corp.pages ?? "—"} / ${corp.text_pages ?? "—"}`} />
        <Kpi l="Значений" v={data.results.length} s={`подтверждено ${st.verified ?? 0}`} tone="ok" />
        <Kpi l="На проверку" v={(st.needs_review ?? 0) + (st.flagged ?? 0)} tone={(st.needs_review ?? 0) + (st.flagged ?? 0) ? "warn" : undefined} s={`из них противоречий правилу: ${st.flagged ?? 0}`} />
        <Kpi l="Замечаний" v={data.issues.length} s={st.seconds ? `обработка ${st.seconds} с` : undefined} />
      </div>
      <div className="card">
        <div className="card-b">
          <div className="tabs" role="tablist">
            <button className={tab === "results" ? "on" : ""} onClick={() => setTab("results")}>Результаты ({data.results.length})</button>
            {data.entity_tables.map((t: string) => <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>{ENT_TITLE[t] || t} ({data.entities[t]?.length || 0})</button>)}
            <button className={tab === "pages" ? "on" : ""} onClick={() => setTab("pages")}>Рентген страниц</button>
            <button className={tab === "issues" ? "on" : ""} onClick={() => setTab("issues")}>Замечания ({data.issues.length})</button>
            <button className={tab === "nodes" ? "on" : ""} onClick={() => setTab("nodes")}>Ноды ({data.node_runs.length})</button>
          </div>
          {tab === "results" && (res.length ? <ResultsTable rows={res} domain={domain} /> : <Empty title={p.in_scope === "false" ? "Публикация исключена — значений нет" : "Значения не извлечены"}>{p.in_scope === "false" ? p.exclusion_reason : "Нода не нашла значений с проверяемым источником."}</Empty>)}
          {data.entity_tables.includes(tab) && <EntityTable rows={data.entities[tab] || []} cols={data.tables[tab]} />}
          {tab === "pages" && <div className="stack"><div className="small muted"><Term k="рентген">Все числа страницы поверх PDF</Term>: цветная рамка — извлечённое значение (клик откроет его), пунктир — напечатанное число, которое никто не извлёк (клик — добавить вручную).</div>
            <SourceViewer domain={domain} split={split} pid={pid} page={1} pageCount={corp.pages} xrayDefault /></div>}
          {tab === "issues" && <IssueList issues={data.issues} results={data.results} />}
          {tab === "nodes" && <NodeRuns runs={data.node_runs} />}
        </div>
      </div>
    </div>
  );
}

function EntityTable({ rows, cols }: { rows: any[]; cols: string[] }) {
  if (!rows.length) return <Empty title="Записей нет">Пустая таблица означает, что сведения не извлечены — они не заполняются по догадке.</Empty>;
  const used = cols.filter((c) => c !== "publication_id" && rows.some((r) => r.data[c]));
  return (
    <div className="tbl-wrap"><table className="tbl"><thead><tr>{used.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r) => <tr key={r.id}>{used.map((c) => <td key={c}><div className="clip2" title={r.data[c]}>{r.data[c]}</div></td>)}</tr>)}</tbody></table>
      <div className="small faint" style={{ padding: 8 }}>Пустые колонки скрыты: {cols.filter((c) => c !== "publication_id" && !used.includes(c)).join(", ") || "нет"}</div></div>
  );
}

export function IssueList({ issues, results }: { issues: any[]; results: any[] }) {
  if (!issues.length) return <Empty title="Замечаний нет" />;
  const idOf = (rid: string) => results.find((r: any) => r.rec_id === rid)?.id;
  return (
    <div className="stack">
      {issues.map((i) => (
        <div key={i.id} className="card pad stack" style={{ gap: 6 }}>
          <div className="row between"><div className="row"><span className="mono small">{i.data.issue_id}</span><IssueTag t={i.data.check_name} />
            <Badge cls={i.verification_status === "open" ? "b-warn" : "b-ok"}>{i.verification_status === "open" ? "открыто" : i.verification_status}</Badge></div>
            <div className="row small">{(i.data.record_ids || "").split(";").filter(Boolean).map((rid: string) => idOf(rid) ? <Link key={rid} className="mono" to={`/record/${idOf(rid)}`}>{rid}</Link> : <span key={rid} className="mono">{rid}</span>)}</div></div>
          <div className="wrap-any">{i.data.description}</div>
          {i.evidence?.formula && <div className="formula">{i.evidence.formula} · входные данные: {JSON.stringify(i.evidence.inputs)}</div>}
          {i.data.source_fragment && <div className="quote">с. {i.data.source_page}: {i.data.source_fragment}</div>}
        </div>
      ))}
    </div>
  );
}

function NodeRuns({ runs }: { runs: any[] }) {
  const [open, setOpen] = useState<any>(null);
  if (!runs.length) return <Empty title="Запусков нод нет" />;
  return (
    <div className="stack">
      <div className="tbl-wrap"><table className="tbl"><thead><tr><th>#</th><th>Нода</th><th>Назначение</th><th>Модель / версия</th><th>Вход</th><th>Время</th><th>Токены</th><th>Статус</th><th /></tr></thead>
        <tbody>{runs.map((r) => <tr key={r.id}><td className="num">{r.id}</td><td><b>{r.node}</b></td><td>{r.purpose}</td><td className="mono small">{r.model}</td><td className="small">{r.input_ref}</td>
          <td className="num">{r.seconds}s</td><td className="num">{r.tokens_in || 0}/{r.tokens_out || 0}</td>
          <td>{r.error ? <Badge cls="b-err" title={r.error}>ошибка</Badge> : <Badge cls="b-ok">ok</Badge>}</td>
          <td><button className="btn sm" onClick={() => api(`/api/node_runs/${r.id}`).then(setOpen)}>Ответ</button></td></tr>)}</tbody></table></div>
      {open && <div className="card pad stack"><div className="row between"><b>Запуск #{open.id}: нода {open.node}, {open.model}</b><button className="btn sm" onClick={() => setOpen(null)}>Закрыть</button></div>
        {open.error && <div className="notice err">{open.error}</div>}
        <div className="small muted">Параметры: {JSON.stringify(open.params)}</div>
        <details className="more"><summary>Промпт</summary><pre className="code">{open.prompt || "детерминированная нода: промпта нет"}</pre></details>
        <details className="more" open><summary>Сырой ответ модели / результат</summary><pre className="code">{open.raw_response || JSON.stringify(open.parsed, null, 1)}</pre></details></div>}
    </div>
  );
}
