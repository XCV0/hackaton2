import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, DOMAIN_LONG, ISSUE_LABEL, qs } from "../api";
import { Empty, ErrorState, IssueTag, Loading, OriginBadge, QuoteBadge, ReviewBadge, SortTh, useAsync, useUrlState, VerBadge } from "../components/ui";
import { useScope } from "../main";

export function ResultsTable({ rows, domain, sort, onSort, selectable, selected, onSelect }:
  { rows: any[]; domain: string; sort?: string; onSort?: (s: string) => void; selectable?: boolean; selected?: Set<number>; onSelect?: (id: number) => void }) {
  const nav = useNavigate();
  const S = (k: string, l: string) => (onSort ? <SortTh k={k} label={l} sort={sort || ""} onSort={onSort} /> : <th>{l}</th>);
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr>
          {selectable && <th aria-label="Выбор" />}
          {S("pub_id", "Публ.")}{S("result_id", "ID")}{S("metric_name", "Показатель")}
          <th>Опубликовано</th>{S("metric_value", "Норм.")}
          <th>{domain === "rag" ? "Конфиг. / набор" : "Прибор / агрег."}</th>
          {S("source_page", "Стр.")}<th>Источник</th><th>Проверка</th><th>Замечания</th>
        </tr></thead>
        <tbody>
          {rows.map((r) => {
            const d = r.data;
            return (
              <tr key={r.id} className={`rowlink ${selected?.has(r.id) ? "sel" : ""}`} onClick={() => nav(`/record/${r.id}`)}>
                {selectable && <td onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected?.has(r.id)} onChange={() => onSelect?.(r.id)} aria-label={`Выбрать ${d.result_id}`} /></td>}
                <td><Link className="mono" to={`/pub/${r.domain}/${r.split}/${r.pub_id}`} onClick={(e) => e.stopPropagation()}>{r.pub_id}</Link></td>
                <td className="mono"><Link to={`/record/${r.id}`} onClick={(e) => e.stopPropagation()}>{d.result_id}</Link></td>
                <td><div className="clip" title={d.metric_name}><b>{d.metric_name}</b>{d.metric_k ? <span className="faint"> k={d.metric_k}</span> : null}</div>
                  <div className="row" style={{ gap: 4 }}><OriginBadge o={d.result_origin} />{d.duplicate_of && <span className="tag">повтор {d.duplicate_of}</span>}</div></td>
                <td className="num">{d.raw_value} <span className="faint">{d.raw_unit}</span></td>
                <td className="num">{d.metric_value} <span className="faint">{d.metric_unit}</span></td>
                <td className="small"><div className="clip">{domain === "rag" ? `${d.config_id || "—"} · ${d.dataset_id || "—"}` : `${d.device_id || "—"} · ${d.aggregation || "агрегация не указана"}`}</div></td>
                <td className="num">{d.source_page}</td>
                <td className="small"><div className="clip" title={d.source_fragment}>{d.source_table || d.source_figure || ""} {d.source_fragment ? <span className="faint">«{d.source_fragment.slice(0, 60)}»</span> : ""}</div></td>
                <td><div className="stack" style={{ gap: 3 }}><VerBadge v={r.verification_status} /><QuoteBadge v={r.quote_outcome} />{r.review_status !== "none" && <ReviewBadge v={r.review_status} />}</div></td>
                <td><div className="row" style={{ gap: 3 }}>{(r.issue_types || []).slice(0, 3).map((t: string, i: number) => <IssueTag key={i} t={t} />)}</div></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function Results() {
  const { domain, split } = useScope();
  const [f, set] = useUrlState({ q: "", pub: "", metric: "", verification: "", review: "", origin: "", kind: "", issue: "", scan: "", sort: "pub_id", offset: "0" });
  const [q, setQ] = useState(f.q);
  useEffect(() => setQ(f.q), [f.q]);
  const limit = 100;
  const { data, error, loading, reload } = useAsync(() => api(`/api/results${qs({ ...f, domain, split, limit })}`),
    [domain, split, f.q, f.pub, f.metric, f.verification, f.review, f.origin, f.kind, f.issue, f.scan, f.sort, f.offset]);
  const off = Number(f.offset) || 0;
  return (
    <div className="stack">
      <div className="topbar"><div><div className="crumbs">{DOMAIN_LONG[domain]} · {split}</div><h1>Результаты</h1>
        <div className="muted">Каждая строка — одно значение одного показателя с источником и статусами извлечения и проверки.</div></div></div>
      <div className="card">
        <form className="filters" onSubmit={(e) => { e.preventDefault(); set({ q, offset: "0" }); }}>
          <label style={{ flex: "1 1 200px" }}>Поиск<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="значение, метрика, цитата…" /></label>
          <label>Публикация<input className="input" style={{ width: 90 }} value={f.pub} onChange={(e) => set({ pub: e.target.value.toUpperCase(), offset: "0" })} placeholder="D001" /></label>
          <label>Показатель<select className="input" value={f.metric} onChange={(e) => set({ metric: e.target.value, offset: "0" })}>
            <option value="">любой</option>{(data?.facets?.metric || []).map(([m, n]: any) => m && <option key={m} value={m}>{m} ({n})</option>)}</select></label>
          <label>Проверка<select className="input" value={f.verification} onChange={(e) => set({ verification: e.target.value, offset: "0" })}>
            <option value="">все</option><option value="verified">подтверждено</option><option value="flagged">противоречие правилу</option>
            <option value="needs_review">нужна проверка</option><option value="flagged,needs_review">все проблемные</option></select></label>
          <label>Ручная проверка<select className="input" value={f.review} onChange={(e) => set({ review: e.target.value, offset: "0" })}>
            <option value="">все</option><option value="pending">в очереди</option><option value="confirmed">подтверждено</option><option value="corrected">исправлено</option><option value="rejected">отклонено</option></select></label>
          <label>Происхождение<select className="input" value={f.origin} onChange={(e) => set({ origin: e.target.value, offset: "0" })}>
            <option value="">все</option><option value="primary">primary</option><option value="cited">cited</option></select></label>
          <label>Откуда<select className="input" value={f.kind} onChange={(e) => set({ kind: e.target.value, offset: "0" })}>
            <option value="">всё</option><option value="table">таблица</option><option value="text">текст</option><option value="figure">рисунок</option></select></label>
          <label>PDF<select className="input" value={f.scan} onChange={(e) => set({ scan: e.target.value, offset: "0" })}>
            <option value="">все</option><option value="true">сканы</option><option value="false">текстовые</option></select></label>
          <label>Замечание<select className="input" value={f.issue} onChange={(e) => set({ issue: e.target.value, offset: "0" })}>
            <option value="">любое</option>{Object.entries(ISSUE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <button className="btn primary" type="submit">Применить</button>
        </form>
        {loading && !data && <Loading rows={10} />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && data.total === 0 && <Empty title="Нет значений по этим условиям">Если набор не обработан, запустите обработку в «Корпус и задачи».</Empty>}
        {data && data.total > 0 && <>
          <ResultsTable rows={data.rows} domain={domain} sort={f.sort} onSort={(s) => set({ sort: s, offset: "0" })} />
          <div className="pager">
            <span className="small muted">{off + 1}–{Math.min(off + limit, data.total)} из {data.total}{loading ? " · обновление…" : ""}</span>
            <div className="row"><button className="btn sm" disabled={off === 0} onClick={() => set({ offset: String(Math.max(0, off - limit)) })}>← Назад</button>
              <button className="btn sm" disabled={off + limit >= data.total} onClick={() => set({ offset: String(off + limit) })}>Вперёд →</button></div>
          </div>
        </>}
      </div>
    </div>
  );
}
