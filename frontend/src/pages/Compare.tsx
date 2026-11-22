import { Link } from "react-router-dom";
import { api, DOMAIN_LONG, qs } from "../api";
import { Badge, Empty, ErrorState, Loading, useAsync, useUrlState, VerBadge } from "../components/ui";
import { useScope } from "../main";

const KEY_TITLE: Record<string, string> = { dataset: "набор", dataset_version: "версия", split: "разбиение", metric: "метрика", variant: "вариант", k: "k", unit: "шкала",
  origin: "происхождение", material_class: "материал", device_type: "тип прибора", spectrum: "спектр", intensity: "мВт/см²", area: "площадь",
  area_definition: "определение площади", aggregation: "агрегация", scan: "развёртка" };

export default function Compare() {
  const { domain, split } = useScope();
  const [f, set] = useUrlState({ metric: domain === "solar" ? "PCE" : "", dataset: "", material_class: "" });
  const metrics = useAsync(() => api<any[]>(`/api/metric_names${qs({ domain, split })}`), [domain, split]);
  const metric = f.metric || (metrics.data?.[0]?.name ?? "");
  const { data, error, loading, reload } = useAsync(() => metric ? api(`/api/compare${qs({ domain, split, metric, dataset: f.dataset, material_class: f.material_class })}`) : Promise.resolve(null),
    [domain, split, metric, f.dataset, f.material_class]);
  return (
    <div className="stack">
      <div className="topbar"><div><div className="crumbs">{DOMAIN_LONG[domain]} · {split}</div><h1>Сравнение результатов</h1>
        <div className="muted">Автоматически сравниваются только записи с совпадающими условиями. Разные протоколы не объединяются в один рейтинг.</div></div></div>
      <div className="card">
        <div className="filters">
          <label>Метрика<select className="input" value={metric} onChange={(e) => set({ metric: e.target.value })}>
            {(metrics.data || []).map((m) => <option key={m.name} value={m.name}>{m.name} ({m.n})</option>)}</select></label>
          {domain === "rag" && <label>Набор данных содержит<input className="input" value={f.dataset} onChange={(e) => set({ dataset: e.target.value })} placeholder="HotpotQA" /></label>}
          {domain === "solar" && <label>Класс материала<select className="input" value={f.material_class} onChange={(e) => set({ material_class: e.target.value })}>
            <option value="">любой</option>{["perovskite", "CIGS", "CdTe", "kesterite", "Sb2Se3", "thin-film Si", "other"].map((m) => <option key={m}>{m}</option>)}</select></label>}
        </div>
        <div className="card-b stack">
          <div className="notice info small">{domain === "solar"
            ? "Ключ сопоставимости: класс материала, тип прибора, AM1.5G 100 мВт/см², диапазон и определение площади, агрегация (champion/mean), направление развёртки. Сертифицированные значения и стабильность — отдельно."
            : "Ключ сопоставимости: набор данных (версия, разбиение), метрика, её вариант, k и шкала, происхождение (primary/cited)."}</div>
          {loading && !data && <Loading rows={6} />}
          {error && <ErrorState error={error} retry={reload} />}
          {!metric && <Empty title="Нет данных для сравнения">Сначала обработайте корпус.</Empty>}
          {data && data.groups.length === 0 && <Empty title="Нет сопоставимых групп">Все записи с этой метрикой исключены из сравнения — причины ниже.</Empty>}
          {data && data.groups.slice(0, 30).map((g: any, i: number) => (
            <div key={i} className="card">
              <div className="card-h"><div className="row" style={{ gap: 4 }}>{Object.entries(g.key).filter(([, v]) => v).map(([k, v]: any) => <span key={k} className="tag">{KEY_TITLE[k] || k}: {v}</span>)}</div>
                <span className="small muted">{g.items.length} знач. · {g.publications} публ.</span></div>
              <div className="tbl-wrap" style={{ maxHeight: 320 }}><table className="tbl"><thead><tr><th>#</th><th>Публ.</th><th>{domain === "rag" ? "Конфигурация" : "Прибор"}</th><th>Опубл.</th><th>Норм.</th><th>Стр.</th><th>Проверка</th></tr></thead>
                <tbody>{g.items.map((it: any, j: number) => <tr key={it.id}><td className="num">{j + 1}</td><td><Link className="mono" to={`/pub/${domain}/${split}/${it.pub_id}`}>{it.pub_id}</Link></td>
                  <td><Link to={`/record/${it.id}`}><div className="clip">{it.label || it.rec_id}</div></Link></td><td className="num">{it.raw_value}</td><td className="num">{it.value} {it.unit}</td><td className="num">{it.page}</td><td><VerBadge v={it.verification} /></td></tr>)}</tbody></table></div>
            </div>))}
          {data && data.excluded_total > 0 && (
            <details className="more"><summary>Исключено из автоматического сравнения: {data.excluded_total}</summary>
              <div className="tbl-wrap" style={{ maxHeight: 360 }}><table className="tbl"><thead><tr><th>Публ.</th><th>Запись</th><th>Значение</th><th>Почему несопоставимо</th></tr></thead>
                <tbody>{data.excluded.map((it: any) => <tr key={it.id}><td className="mono">{it.pub_id}</td><td><Link to={`/record/${it.id}`}>{it.rec_id}</Link> <span className="muted small">{it.label}</span></td>
                  <td className="num">{it.raw_value}</td><td><div className="row" style={{ gap: 4 }}>{it.reasons.map((x: string) => <Badge key={x} cls="b-plain">{x}</Badge>)}</div></td></tr>)}</tbody></table></div></details>)}
        </div>
      </div>
    </div>
  );
}
