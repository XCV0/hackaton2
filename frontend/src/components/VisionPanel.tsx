import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, post } from "../api";
import { Badge } from "./ui";

/** Reviewer-driven Vision reading of printed numbers on figures. Results never become verified automatically. */
export default function VisionPanel({ domain, split, pid, page }: { domain: string; split: string; pid: string; page: number }) {
  const [st, setSt] = useState<any>(null);
  const [waiting, setWaiting] = useState(false);
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const load = () => api(`/api/vision/${domain}/${split}/${pid}/${page}`).then(setSt).catch((e) => setErr(e.message));
  useEffect(() => { setSt(null); setWaiting(false); load(); }, [domain, split, pid, page]);
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(async () => {
      const r = await api(`/api/vision/${domain}/${split}/${pid}/${page}`);
      if (r.status !== "none" && (!st || r.id !== st.id)) { setSt(r); setWaiting(false); }
    }, 8000);
    return () => clearInterval(t);
  }, [waiting, st]);
  const start = async () => { setErr(""); try { await post(`/api/vision/${domain}/${split}/${pid}/${page}`, {}); setWaiting(true); } catch (e: any) { setErr(e.message); } };
  const add = async (v: any) => {
    const r = await post("/api/records/add_figure_value", { domain, split, pub_id: pid, page, figure: v.figure, metric_name: v.metric_name || v.label, raw_value: v.raw_value,
      raw_unit: v.raw_unit, label: v.label, read_by: `Vision ${st.model}`, vision_run: st.id, actor: localStorage.getItem("actor") || "reviewer" });
    nav(`/record/${r.id}`);
  };
  const a = st?.answer || {};
  return (
    <details className="more" style={{ borderTop: "1px solid var(--line)", paddingTop: 6 }}>
      <summary>Vision: прочитать напечатанные числа на рисунках этой страницы</summary>
      <div className="stack small">
        <div className="muted">Модель читает только явно напечатанные числа и подписи. Кривые не оцифровываются, у схем без чисел значения не создаются. Добавленное значение уходит в очередь визуальной проверки.</div>
        <div className="row"><button className="btn sm" onClick={start} disabled={waiting}>{waiting ? "Модель читает страницу… (несколько минут)" : st?.status === "done" ? "Прочитать заново" : "Запустить Vision"}</button>
          {st?.status === "done" && <span className="faint">запуск #{st.id} · {st.model} · {st.seconds} с</span>}</div>
        {err && <div className="notice err">{err}</div>}
        {st?.status === "error" && <div className="notice err">Vision не ответил: {st.error}</div>}
        {st?.status === "done" && (
          <div className="stack">
            {(a.values || []).length === 0 ? <div className="faint">Напечатанных значений на рисунках не найдено.</div> :
              <table className="tbl"><thead><tr><th>Рисунок</th><th>Что</th><th>Значение</th><th /></tr></thead><tbody>
                {(a.values || []).map((v: any, i: number) => <tr key={i}><td>{v.figure}</td><td className="wrap-any">{v.label}{v.metric_name ? ` · ${v.metric_name}` : ""}</td>
                  <td className="num">{v.raw_value} {v.raw_unit}</td><td><button className="btn sm" onClick={() => add(v)}>Добавить на проверку</button></td></tr>)}</tbody></table>}
            {(a.diagrams_without_metrics || []).length > 0 && <div><Badge cls="b-info">Схемы без метрик</Badge> {a.diagrams_without_metrics.join(", ")} — значения не создаются</div>}
            {(a.curves_not_digitised || []).length > 0 && <div><Badge cls="b-warn">Кривые не оцифрованы</Badge> {a.curves_not_digitised.join(", ")} — запрет оцифровки</div>}
          </div>)}
      </div>
    </details>
  );
}
