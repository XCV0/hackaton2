import { Link } from "react-router-dom";
import { api, DOMAIN_LONG } from "../api";
import { Badge, ErrorState, Kpi, Loading, pct, useAsync } from "../components/ui";

function VerBar({ v }: { v: Record<string, number> }) {
  const total = Object.values(v || {}).reduce((a, b) => a + b, 0);
  if (!total) return <div className="bar" />;
  const seg = (k: string, c: string) => <span key={k} style={{ width: `${((v[k] || 0) / total) * 100}%`, background: c }} title={`${k}: ${v[k] || 0}`} />;
  return <div className="bar" aria-label="Распределение статусов проверки">{seg("verified", "var(--teal)")}{seg("flagged", "var(--red)")}{seg("needs_review", "#e0a11b")}{seg("not_applicable", "var(--line-2)")}</div>;
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
