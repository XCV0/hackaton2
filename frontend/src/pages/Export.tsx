import { useState } from "react";
import { Link } from "react-router-dom";
import { api, DOMAIN_LONG, post, qs } from "../api";
import { Badge, ErrorState, Loading, useAsync } from "../components/ui";
import { useScope } from "../main";
import { ResultsTable } from "./Results";

export default function ExportPage() {
  const { domain, split } = useScope();
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("verified");
  const [check, setCheck] = useState<any>(null);
  const [conf, setConf] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const rows = useAsync(() => api(`/api/results${qs({ domain, split, verification: filter, limit: 300 })}`), [domain, split, filter]);
  const toggle = (id: number) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n); };
  const runCheck = async (ocr: boolean) => {
    setBusy(true); setErr(""); setCheck(null);
    try { setCheck(await post("/api/admin/check", { domain, split, ocr })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const runConf = async () => {
    setBusy(true); setErr(""); setConf(null);
    try { setConf(await post("/api/admin/conformance", { domain, split })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="topbar"><div><div className="crumbs">{DOMAIN_LONG[domain]} · {split}</div><h1>Экспорт</h1>
        <div className="muted">Экспорт строится из тех же записей, что показывает интерфейс. Отклонённые записи не экспортируются. Каждая выгрузка записывается в аудит.</div></div></div>
      <div className="card card-b stack">
        <div className="row between"><h3 style={{ margin: 0 }}>Проверка по шаблону сдачи</h3>
          <button className="btn primary" disabled={busy} onClick={runConf}>Проверить соответствие шаблону</button></div>
        <div className="small muted">Наша независимая проверка свежего экспорта по шаблону комплекта: имена файлов, заголовки и порядок колонок, словари
          {domain === "rag" ? " (schema.json)" : " (README шаблона)"}, ключи внутри публикации, связи, страница ≥ 1 и место извлечения, cited, повторы, нормализация, пустые ячейки без NaN/null/unknown.
          Отдельно показывает «структура валидна» и «сколько обработано» — пустой шаблон успехом не считается.</div>
        {conf && <div className="stack">
          <div className="row"><Badge cls={conf.structure_valid ? "b-ok" : conf.header_only ? "b-warn" : "b-err"}>{conf.structure_valid ? "структура валидна" : conf.header_only ? "пустой набор" : "структура не валидна"}</Badge>
            <span>{conf.verdict}</span></div>
          <div className="small">Шаблон: {conf.template.official ? "официальный (область 1)" : "рекомендуемый формат RAG — не официальный шаблон"} · ошибок {conf.counts.errors}, предупреждений {conf.counts.warnings}
            · публикаций {conf.content.publications} (PDF в наборе {conf.content.pdfs_in_set}), результатов {conf.content.results}, извлечено {conf.content.extracted}, повторов {conf.content.duplicates}, cited {conf.content.cited}, замечаний {conf.content.issues}</div>
          {conf.withheld?.length > 0 && <details className="more"><summary className="small">Не выгружено по правилам формата: {conf.withheld.length}</summary><pre className="code">{conf.withheld.join("\n")}</pre></details>}
          {conf.findings?.length > 0 && <details className="more"><summary className="small">Находки ({conf.counts.errors + conf.counts.warnings})</summary>
            <div className="tbl-wrap" style={{ maxHeight: 320 }}><table className="tbl"><thead><tr><th>Уровень</th><th>Правило</th><th>Где</th><th>Что</th></tr></thead>
              <tbody>{conf.findings.map((f: any, i: number) => <tr key={i}><td><Badge cls={f.severity === "error" ? "b-err" : "b-warn"}>{f.severity}</Badge></td><td>{f.rule}</td><td className="mono small">{f.where}</td><td className="small">{f.message}</td></tr>)}</tbody></table></div></details>}
        </div>}
      </div>
      <div className="grid g3">
        <div className="card card-b stack"><h3>CSV по шаблону сдачи</h3>
          <div className="small muted">{domain === "rag" ? "7 таблиц по schema.json комплекта RAG" : "7 таблиц по шаблону области 1"}; строка publications для каждого PDF набора.</div>
          <a className="btn primary" href={`/api/export/${domain}/${split}.zip`}>Скачать {domain}_{split}.zip</a></div>
        <div className="card card-b stack"><h3>Отчёт по замечаниям</h3>
          <div className="small muted">Все замечания с правилом, формулой, связанными записями, статусом и местом в статье.</div>
          <a className="btn" href={`/api/export/${domain}/${split}/issues_report.csv`}>Скачать issues_report.csv</a></div>
        <div className="card card-b stack"><h3>Проверщик комплекта</h3>
          <div className="small muted">Запускает неизменённый tools/check_submission.py из комплекта на свежем экспорте{domain === "rag" ? " (для RAG это проверка рекомендуемого формата, не официальный скорер)" : " (официальный проверщик области 1)"}. Код 0 — проверки прошли, 1 — ошибки, 2 — нужна проверка источников.</div>
          <div className="row"><button className="btn" disabled={busy} onClick={() => runCheck(false)}>Проверить</button>
            {domain === "rag" && <button className="btn" disabled={busy} onClick={() => runCheck(true)}>Проверить с OCR</button>}</div></div>
      </div>
      {busy && <div className="card"><Loading rows={3} /><div className="small muted" style={{ padding: "0 16px 12px" }}>Проверщик читает все PDF набора — это может занять несколько минут (с OCR — дольше).</div></div>}
      {err && <ErrorState error={err} />}
      {check && (
        <div className="card card-b stack">
          <div className="row between"><b>Результат проверщика</b><Badge cls={check.exit_code === 0 ? "b-ok" : check.exit_code === 1 ? "b-err" : "b-warn"}>код выхода {check.exit_code}</Badge></div>
          <div className="small mono wrap-any">{check.cmd}</div>
          {check.report && <div className="small">Строки: {JSON.stringify(check.report.rows)} · цитаты: {JSON.stringify(check.report.quotes)} · ошибок {check.n_errors}, на проверку {check.n_warnings}</div>}
          <details className="more"><summary>Вывод</summary><pre className="code">{check.stdout_tail}</pre></details>
          <div className="small muted">Успешная техническая проверка не подтверждает научную правильность и полноту разметки.</div>
        </div>
      )}
      <div className="card">
        <div className="card-h"><div><b>Экспорт выбранных записей</b><div className="small muted">Отметьте записи — в архив попадут они, их публикации и связанные сущности.</div></div>
          <div className="row"><select className="input" value={filter} onChange={(e) => { setFilter(e.target.value); setSel(new Set()); }} aria-label="Фильтр по проверке">
            <option value="verified">подтверждённые</option><option value="flagged,needs_review">проблемные</option><option value="">все</option></select>
            <a className={`btn primary ${sel.size ? "" : "disabled"}`} aria-disabled={!sel.size} href={sel.size ? `/api/export/${domain}/${split}.zip?ids=${[...sel].join(",")}` : undefined}
              onClick={(e) => { if (!sel.size) e.preventDefault(); }}>Скачать выбранные ({sel.size})</a></div></div>
        {rows.loading && !rows.data && <Loading />}
        {rows.error && <ErrorState error={rows.error} />}
        {rows.data && <ResultsTable rows={rows.data.rows} domain={domain} selectable selected={sel} onSelect={toggle} />}
        {rows.data && rows.data.total > 300 && <div className="pager small muted">Показаны первые 300 из {rows.data.total}. Уточните выбор в <Link to={`/results?domain=${domain}&split=${split}`}>Результатах</Link>.</div>}
      </div>
    </div>
  );
}
