import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, DOMAIN_LONG, qs } from "../api";
import { Badge, Empty, ErrorState, Loading, SortTh, useAsync, useUrlState } from "../components/ui";
import { useScope } from "../main";
import UploadPanel from "../components/UploadPanel";

export default function Catalog() {
  const { domain, split } = useScope();
  const [f, set] = useUrlState({ q: "", status: "", scope: "", scan: "", sort: "pub_id", metric: "", material_class: "", domain, split });
  const [q, setQ] = useState(f.q);
  const [showUpload, setShowUpload] = useState(split === "demo");
  useEffect(() => setQ(f.q), [f.q]);
  const nav = useNavigate();
  const { data, error, loading, reload } = useAsync(() => api<any[]>(`/api/publications${qs({ ...f, domain, split })}`),
    [domain, split, f.q, f.status, f.scope, f.scan, f.sort, f.metric, f.material_class]);
  const metrics = useAsync(() => api<any[]>(`/api/metric_names${qs({ domain, split })}`), [domain, split]);
  return (
    <div className="stack">
      <div className="topbar">
        <div><div className="crumbs">{DOMAIN_LONG[domain]} · {split}</div><h1>Публикации</h1>
          <div className="muted">Каждый PDF корпуса, включая исключённые по области. Фильтры сохраняются в адресе страницы.</div></div>
        <button className="btn primary" onClick={() => setShowUpload(!showUpload)}>{showUpload ? "Скрыть загрузку" : "⇪ Загрузить PDF"}</button>
      </div>
      {showUpload && <UploadPanel domain={domain} onDone={reload} />}
      <div className="card">
        <form className="filters" onSubmit={(e) => { e.preventDefault(); set({ q }); }}>
          <label style={{ flex: "1 1 240px" }}>Поиск (название, DOI, авторы, полный текст)
            <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="напр. HotpotQA, perovskite, 10.1021/…" /></label>
          <label>Статус
            <select className="input" value={f.status} onChange={(e) => set({ status: e.target.value })}>
              <option value="">все</option><option value="problem">с проблемами</option><option value="done">обработаны</option>
              <option value="registered">не обработаны</option><option value="error">ошибка обработки</option></select></label>
          <label>Область
            <select className="input" value={f.scope} onChange={(e) => set({ scope: e.target.value })}>
              <option value="">все</option><option value="true">в области</option><option value="false">исключены</option></select></label>
          <label>Тип PDF
            <select className="input" value={f.scan} onChange={(e) => set({ scan: e.target.value })}>
              <option value="">все</option><option value="true">скан (OCR)</option><option value="false">текстовый слой</option></select></label>
          <label>Показатель
            <select className="input" value={f.metric} onChange={(e) => set({ metric: e.target.value })}>
              <option value="">любой</option>{(metrics.data || []).map((m) => <option key={m.name} value={m.name}>{m.name} ({m.n})</option>)}</select></label>
          {domain === "solar" && <label>Класс материала
            <select className="input" value={f.material_class} onChange={(e) => set({ material_class: e.target.value })}>
              <option value="">любой</option>{["perovskite", "CIGS", "CdTe", "kesterite", "Sb2Se3", "thin-film Si", "other"].map((m) => <option key={m}>{m}</option>)}</select></label>}
          <button className="btn primary" type="submit">Найти</button>
          {(f.q || f.status || f.scope || f.scan || f.metric || f.material_class) && <button type="button" className="btn ghost" onClick={() => { setQ(""); set({ q: "", status: "", scope: "", scan: "", metric: "", material_class: "" }); }}>Сбросить</button>}
        </form>
        {loading && !data && <Loading rows={8} />}
        {error && <ErrorState error={error} retry={reload} />}
        {data && data.length === 0 && <Empty title="Ничего не найдено">Измените условия поиска или сбросьте фильтры.</Empty>}
        {data && data.length > 0 && (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr>
                <SortTh k="pub_id" label="ID" sort={f.sort} onSort={(s) => set({ sort: s })} />
                <SortTh k="title" label="Публикация" sort={f.sort} onSort={(s) => set({ sort: s })} />
                <SortTh k="year" label="Год" sort={f.sort} onSort={(s) => set({ sort: s })} />
                <th>Состояние</th>
                <SortTh k="results" label="Значений" sort={f.sort} onSort={(s) => set({ sort: s })} />
                <SortTh k="verified" label="Подтв." sort={f.sort} onSort={(s) => set({ sort: s })} title="Подтверждено источником" />
                <SortTh k="needs_review" label="На проверку" sort={f.sort} onSort={(s) => set({ sort: s })} />
                <SortTh k="issues" label="Замечаний" sort={f.sort} onSort={(s) => set({ sort: s })} />
              </tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.pub_id} className="rowlink" onClick={() => nav(`/pub/${domain}/${split}/${r.pub_id}`)}>
                    <td><Link to={`/pub/${domain}/${split}/${r.pub_id}`} className="mono" onClick={(e) => e.stopPropagation()}>{r.pub_id}</Link></td>
                    <td><div className="clip2" title={r.title}>{r.title || <span className="faint">название не извлечено</span>}</div>
                      <div className="small faint clip">{r.doi}</div></td>
                    <td className="num">{r.year}</td>
                    <td><div className="row" style={{ gap: 4 }}>
                      {r.status !== "done" && <Badge cls={r.status === "error" ? "b-err" : "b-plain"}>{r.status === "error" ? "ошибка" : r.status === "running" ? "в работе" : "не обработан"}</Badge>}
                      {r.in_scope === "false" && <Badge cls="b-plain" title={r.exclusion_reason}>исключена</Badge>}
                      {r.is_scan && <Badge cls="b-warn">скан</Badge>}
                      {r.primary_node && <span className="tag" title="Основная нода извлечения">нода {r.primary_node}</span>}
                    </div></td>
                    <td className="num">{r.results}</td>
                    <td className="num" style={{ color: "var(--teal)" }}>{r.verified}</td>
                    <td className="num" style={{ color: r.needs_review + r.flagged ? "var(--amber)" : undefined }}>{r.needs_review + r.flagged}</td>
                    <td className="num">{r.issues}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
