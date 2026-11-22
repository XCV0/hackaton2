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
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const rows = useAsync(() => api(`/api/results${qs({ domain, split, verification: filter, limit: 300 })}`), [domain, split, filter]);
  const toggle = (id: number) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n); };
  const runCheck = async (ocr: boolean) => {
    setBusy(true); setErr(""); setCheck(null);
    try { setCheck(await post("/api/admin/check", { domain, split, ocr })); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="topbar"><div><div className="crumbs">{DOMAIN_LONG[domain]} · {split}</div><h1>Экспорт</h1>
        <div className="muted">Экспорт строится из тех же записей, что показывает интерфейс. Отклонённые записи не экспортируются. Каждая выгрузка записывается в аудит.</div></div></div>
      <div className="grid g3">
        <div className="card card-b stack"><h3>Официальные CSV</h3>
          <div className="small muted">{domain === "rag" ? "7 таблиц по schema.json комплекта RAG" : "7 таблиц по шаблону области 1"}; строка publications для каждого PDF набора.</div>
          <a className="btn primary" href={`/api/export/${domain}/${split}.zip`}>Скачать {domain}_{split}.zip</a></div>
        <div className="card card-b stack"><h3>Отчёт по замечаниям</h3>
          <div className="small muted">Все замечания с правилом, формулой, связанными записями, статусом и местом в статье.</div>
          <a className="btn" href={`/api/export/${domain}/${split}/issues_report.csv`}>Скачать issues_report.csv</a></div>
        <div className="card card-b stack"><h3>Официальный проверщик</h3>
          <div className="small muted">Запускает неизменённый tools/check_submission.py на свежем экспорте. Код 0 — проверки прошли, 1 — ошибки, 2 — нужна проверка источников.</div>
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
