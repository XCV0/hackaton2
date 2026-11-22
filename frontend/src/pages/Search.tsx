import { Link, useSearchParams } from "react-router-dom";
import { api, qs } from "../api";
import { Empty, ErrorState, Loading, useAsync, VerBadge } from "../components/ui";

function Snip({ s }: { s: string }) {
  const parts = s.split(/(\[\[.*?\]\])/g);
  return <>{parts.map((p, i) => p.startsWith("[[") ? <mark key={i}>{p.slice(2, -2)}</mark> : <span key={i}>{p}</span>)}</>;
}

export default function SearchPage() {
  const [sp] = useSearchParams();
  const q = sp.get("q") || "";
  const domain = sp.get("domain") || "";
  const split = sp.get("split") || "";
  const { data, error, loading, reload } = useAsync(() => (q ? api(`/api/search${qs({ q, domain, split })}`) : Promise.resolve(null)), [q, domain, split]);
  return (
    <div className="stack">
      <div className="topbar"><div><h1>Поиск: «{q}»</h1><div className="muted">Полнотекстовый поиск по страницам PDF (текстовый слой или OCR) и по извлечённым значениям.</div></div></div>
      {!q && <Empty title="Введите запрос в поле поиска слева" />}
      {loading && !data && <Loading rows={6} />}
      {error && <ErrorState error={error} retry={reload} />}
      {data?.error && <div className="notice err">{data.error}</div>}
      {data && <div className="grid g2">
        <div className="card"><div className="card-h"><b>Страницы PDF ({data.pages.length})</b></div>
          {data.pages.length === 0 ? <Empty title="Совпадений в тексте нет" /> : <div className="tbl-wrap"><table className="tbl"><tbody>
            {data.pages.map((h: any, i: number) => <tr key={i}><td className="nowrap"><Link className="mono" to={`/pub/${h.domain}/${h.split}/${h.pub_id}`}>{h.pub_id}</Link><div className="small faint">{h.domain}/{h.split} · с. {h.page}{h.engine === "ocr" ? " · OCR" : ""}</div></td>
              <td className="small wrap-any"><Snip s={h.snip} /></td></tr>)}</tbody></table></div>}</div>
        <div className="card"><div className="card-h"><b>Значения ({data.results.length})</b></div>
          {data.results.length === 0 ? <Empty title="Совпадений среди значений нет" /> : <div className="tbl-wrap"><table className="tbl"><tbody>
            {data.results.map((r: any) => <tr key={r.id}><td className="nowrap"><Link to={`/record/${r.id}`} className="mono">{r.pub_id}/{r.rec_id}</Link><div className="small faint">{r.domain}/{r.split} · с. {r.source_page}</div></td>
              <td><b>{r.metric_name}</b> = <span className="mono">{r.raw_value}</span><div className="small muted clip2">{r.fragment}</div></td><td><VerBadge v={r.verification_status} /></td></tr>)}</tbody></table></div>}</div>
      </div>}
    </div>
  );
}
