import { Link } from "react-router-dom";
import { api, DOMAIN_LONG } from "../api";
import { Badge, ErrorState, Kpi, Loading, pct, Term, useAsync } from "../components/ui";

function VerBar({ v }: { v: Record<string, number> }) {
  const total = Object.values(v || {}).reduce((a, b) => a + b, 0);
  if (!total) return <div className="bar" />;
  const seg = (k: string, c: string) => <span key={k} style={{ width: `${((v[k] || 0) / total) * 100}%`, background: c }} title={`${k}: ${v[k] || 0}`} />;
  return <div className="bar" aria-label="Распределение статусов проверки">{seg("verified", "var(--teal)")}{seg("flagged", "var(--red)")}{seg("needs_review", "#e0a11b")}{seg("not_applicable", "var(--line-2)")}</div>;
}

function Attention() {
  const { data } = useAsync(async () => {
    const all: any[] = [];
    for (const d of ["rag", "solar"]) for (const s of ["demo", "dev", "test"]) {
      try { (await api(`/api/publications?domain=${d}&split=${s}&status=problem&sort=-needs_review`)).slice(0, 6).forEach((r: any) => all.push({ ...r, d, s })); } catch { /* skip */ }
    }
    return all.map((r) => ({ ...r, score: r.flagged * 3 + r.needs_review + (r.status === "error" ? 50 : 0) + (r.s === "demo" ? 20 : 0) }))
      .sort((a, b) => b.score - a.score).slice(0, 6);
  }, []);
  if (!data?.length) return null;
  return (
    <section className="card">
      <div className="card-h"><div><h2 style={{ margin: 0 }}>Требует внимания</h2><span className="muted small">публикации, где больше всего значений ждут человека; свои загрузки (demo) — выше</span></div>
        <Link className="btn sm teal" to="/admin/review">Открыть очередь проверки</Link></div>
      <div className="card-b attention">
        {data.map((r: any) => (
          <Link key={`${r.d}${r.s}${r.pub_id}`} className="att-item" to={`/pub/${r.d}/${r.s}/${r.pub_id}`}>
            <div className="row between"><span className="mono">{r.pub_id}</span><span className="small faint">{DOMAIN_LONG[r.d]} · {r.s}</span></div>
            <div className="small clip2">{r.title || "без названия"}</div>
            <div className="row" style={{ gap: 4 }}>
              {r.status === "error" && <Badge cls="b-err">ошибка обработки</Badge>}
              {r.flagged > 0 && <Badge cls="b-err">противоречий: {r.flagged}</Badge>}
              {r.needs_review > 0 && <Badge cls="b-warn">на проверку: {r.needs_review}</Badge>}
              <span className="small muted">из {r.results}</span>
            </div>
          </Link>))}
      </div>
    </section>
  );
}

export default function Overview() {
  const { data, error, loading, reload } = useAsync(() => api("/api/overview"), []);
  if (loading && !data) return <Loading rows={8} />;
  if (error) return <ErrorState error={error} retry={reload} />;
  const llm = data._llm;
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="topbar">
        <div>
          <h1>Обзор корпуса</h1>
          <div className="muted">Доказуемое извлечение: публикация → страница PDF → таблица/рисунок → дословная цитата → проверка.</div>
        </div>
        <div className="row">
          {llm?.available ? <Badge cls="b-ok">LLM-нода A: {llm.model_a}</Badge> : <Badge cls="b-warn">LLM не настроен — работает только детерминированная нода R</Badge>}
          <Link className="btn sm" to="/admin/llm">Настроить LLM</Link>
        </div>
      </div>
      <Attention />
      <div className="notice info">
        Показатели ниже — <b>технические</b>: сколько значений подтверждено буквальной цитатой и сколько требует человека.
        Это не точность извлечения. Precision/recall считаются только на dev по эталону — см. <Link to="/admin/metrics">Метрики качества</Link>; для test эталона нет.
      </div>
      {(["rag", "solar"] as const).map((d) => (
        <section key={d} className="card">
          <div className="card-h">
            <div><h2 style={{ margin: 0 }}>{DOMAIN_LONG[d]}</h2><span className="muted small">{d === "rag" ? "Область 2" : "Область 1"} · обязательная</span></div>
            <div className="row">
              <Link className="btn sm" to={`/catalog?domain=${d}&split=dev`}>Публикации</Link>
              <Link className="btn sm" to={`/admin/review?domain=${d}&split=dev`}>Очередь проверки</Link>
            </div>
          </div>
          <div className="card-b grid g2">
            {(["dev", "test", "demo"] as const).map((s) => {
              const x = data[d].splits[s];
              return (
                <div key={s} className="stack">
                  <div className="row between"><b>{s === "dev" ? "dev — с открытым эталоном" : "test — без эталона"}</b>
                    <span className="small muted">{x.processed}/{x.pdfs} обработано{x.errors ? ` · ошибок ${x.errors}` : ""}</span></div>
                  <div className="grid g4">
                    <Kpi l="PDF / сканы" v={<>{x.pdfs}<span className="faint" style={{ fontSize: 15 }}> / {x.scans}</span></>} s={`исключено по области: ${x.excluded}`} />
                    <Kpi l="Значений" v={x.results} s={`публикаций с проблемами: ${x.problem_publications}`} />
                    <Kpi l="Подтверждено цитатой" v={pct(x.verified_share)} tone="ok" s={`${x.verification.verified || 0} значений`} />
                    <Kpi l="Открытых замечаний" v={x.open_issues} tone={x.open_issues ? "warn" : undefined} s={`на проверке: ${(x.verification.needs_review || 0) + (x.verification.flagged || 0)}`} />
                  </div>
                  <VerBar v={x.verification} />
                  <div className="legend">
                    <span><i style={{ background: "var(--teal)" }} />Подтверждено {x.verification.verified || 0}</span>
                    <span><i style={{ background: "var(--red)" }} />Противоречие правилу {x.verification.flagged || 0}</span>
                    <span><i style={{ background: "#e0a11b" }} />Нужна проверка {x.verification.needs_review || 0}</span>
                    <span>Проверено человеком: {(x.review.confirmed || 0) + (x.review.corrected || 0) + (x.review.rejected || 0)}</span>
                  </div>
                  {x.processed === 0 && <div className="notice">Набор ещё не обработан. Запустите обработку в разделе <Link to={`/admin/corpus?domain=${d}&split=${s}`}>Корпус и задачи</Link>.</div>}
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
