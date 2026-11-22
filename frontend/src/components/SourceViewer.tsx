import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, post, qs } from "../api";
import { Badge, ErrorState, Loading, Term } from "./ui";
import VisionPanel from "./VisionPanel";

type Props = { domain: string; split: string; pid: string; page: number; fragment?: string; value?: string; cell?: number[] | null; pageCount?: number; figure?: string;
  xrayDefault?: boolean; currentId?: number };

const XCLS: Record<string, string> = { verified: "x-ok", flagged: "x-err", needs_review: "x-warn", not_applicable: "x-na" };

function highlight(text: string, frag?: string) {
  if (!frag) return text;
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const f = norm(frag);
  const flat = text.replace(/-\n(?=\w)/g, "").replace(/\s+/g, " ");
  const i = flat.indexOf(f);
  if (i < 0) return flat;
  return <>{flat.slice(0, i)}<mark>{flat.slice(i, i + f.length)}</mark>{flat.slice(i + f.length)}</>;
}

export default function SourceViewer({ domain, split, pid, page, fragment, value, cell, pageCount, figure, xrayDefault, currentId }: Props) {
  const nav = useNavigate();
  const [xray, setXray] = useState<boolean>(() => {
    if (xrayDefault || new URLSearchParams(window.location.search).get("xray") === "1") return true;
    try { return localStorage.getItem("xray") === "1"; } catch { return false; }
  });
  const [xd, setXd] = useState<any>(null);
  const [hideInts, setHideInts] = useState(true);
  const [addFor, setAddFor] = useState<any>(null);
  const [pg, setPg] = useState(page || 1);
  const [zoom, setZoom] = useState(1);
  const [tab, setTab] = useState<"image" | "pymupdf" | "pypdf" | "ocr">("image");
  const [info, setInfo] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [imgW, setImgW] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);
  useEffect(() => { setPg(page || 1); }, [page, pid]);
  const onSource = pg === page;
  useEffect(() => {
    setInfo(null); setErr(null);
    api(`/api/page/${domain}/${split}/${pid}/${pg}/text${qs({ fragment: onSource ? fragment : "", value: onSource ? value : "", cell: onSource && cell ? cell.join(",") : "" })}`)
      .then(setInfo).catch((e) => setErr(e.message));
  }, [domain, split, pid, pg, fragment, value]);
  useEffect(() => {
    const el = imgRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setImgW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [info, tab]);
  useEffect(() => {
    setXd(null); setAddFor(null);
    if (!xray) return;
    api(`/api/page/${domain}/${split}/${pid}/${pg}/xray`).then(setXd).catch(() => setXd({ error: true }));
  }, [xray, domain, split, pid, pg]);
  const toggleXray = () => { const v = !xray; setXray(v); try { localStorage.setItem("xray", v ? "1" : "0"); } catch { /* ignore */ } };
  const scale = info && imgW ? imgW / info.width : 0;
  const cands = (xd?.candidates || []).filter((c: any) => {
    if (!hideInts) return true;
    const core = c.text.replace(/^[(\[]+/, "").replace(/[)\],;:*†‡§]+$/, "");
    return /[.,%]/.test(core) && !/^\d+\.$/.test(core);
  });
  const total = pageCount || info?.page_count || 1;
  return (
    <div className="viewer">
      <div className="viewer-bar">
        <button className="btn sm" disabled={pg <= 1} onClick={() => setPg(pg - 1)} aria-label="Предыдущая страница">←</button>
        <span className="small">Стр. <b>{pg}</b> / {total}{pg !== page && <> · <button className="btn sm ghost" onClick={() => setPg(page)}>к источнику (с. {page})</button></>}</span>
        <button className="btn sm" disabled={pg >= total} onClick={() => setPg(pg + 1)} aria-label="Следующая страница">→</button>
        <span style={{ flex: 1 }} />
        <div className="seg" role="tablist" aria-label="Представление страницы">
          <button className={tab === "image" ? "on" : ""} onClick={() => setTab("image")}>Изображение</button>
          <button className={tab === "pymupdf" ? "on" : ""} onClick={() => setTab("pymupdf")}>PyMuPDF</button>
          <button className={tab === "pypdf" ? "on" : ""} onClick={() => setTab("pypdf")}>pypdf</button>
          <button className={tab === "ocr" ? "on" : ""} onClick={() => setTab("ocr")} disabled={!info?.variants?.ocr}>OCR</button>
        </div>
        {tab === "image" && <><button className="btn sm" onClick={() => setZoom(Math.max(1, zoom - 0.5))} aria-label="Уменьшить">−</button><button className="btn sm" onClick={() => setZoom(Math.min(3, zoom + 0.5))} aria-label="Увеличить">+</button>
          <button className={`btn sm ${xray ? "teal" : ""}`} onClick={toggleXray} aria-pressed={xray} title="Показать все числа страницы">Рентген</button></>}
        <a className="btn sm" href={`/api/pdf/${domain}/${split}/${pid}.pdf#page=${pg}`} target="_blank" rel="noreferrer">Открыть PDF ↗</a>
      </div>
      {info && (
        <div className="row small">
          {info.has_text_layer ? <Badge cls="b-info">Текстовый слой</Badge> : <Badge cls="b-warn">Скан: текст только из OCR</Badge>}
          {info.ocr_engine && <span className="faint">{info.ocr_engine}{info.ocr_conf ? ` · ср. уверенность ${info.ocr_conf.toFixed(0)}` : ""}</span>}
          {onSource && fragment && info.fragment_match && Object.entries(info.fragment_match).filter(([, v]) => v !== null).map(([k, v]) =>
            <Badge key={k} cls={v ? "b-ok" : "b-plain"}>{k}: {v ? "цитата есть" : "нет"}</Badge>)}
          {onSource && info.highlight_method && <span className="faint">подсветка: {info.highlight_method}</span>}
          {onSource && (fragment || value) && !info.boxes?.length && <Badge cls="b-warn">Подсветить не удалось — сверяйте визуально</Badge>}
          {figure && onSource && <Badge cls="b-warn">Рисунок {figure}: текстовый поиск не подтверждает визуальное чтение</Badge>}
        </div>
      )}
      {xray && tab === "image" && xd && !xd.error && (
        <div className="xray-bar small">
          <Term k="рентген"><b>Рентген</b></Term>
          <span>чисел на странице: <b>{xd.stats.numbers}</b></span>
          <span className="x-key x-ok">подтверждено</span><span className="x-key x-warn">на проверку</span><span className="x-key x-err">противоречие</span>
          <span className="x-key x-miss">не извлечено: {cands.length}</span>
          <label className="row" style={{ gap: 4 }}><input type="checkbox" checked={hideInts} onChange={(e) => setHideInts(e.target.checked)} />скрыть целые (годы, номера)</label>
          <span className="faint">клик по рамке — значение; по пунктиру — добавить</span>
        </div>)}
      {xray && xd?.error && <div className="notice small">Рентген для этой страницы недоступен.</div>}
      {err && <ErrorState error={err} />}
      {!info && !err && <Loading rows={6} />}
      {info && tab === "image" && (
        <div className="page-wrap">
          <div style={{ position: "relative", width: `${zoom * 100}%` }}>
            <img ref={imgRef} src={`/api/page/${domain}/${split}/${pid}/${pg}.png?dpi=${zoom > 1.5 ? 200 : 130}`} alt={`Страница ${pg} публикации ${pid}`}
              onLoad={(e) => setImgW((e.target as HTMLImageElement).clientWidth)} />
            {onSource && scale > 0 && !xray && (info.boxes || []).map((b: number[], i: number) => (
              <div key={i} className={`hl ${cell && i === info.boxes.length - 1 ? "cell" : ""}`}
                style={{ left: b[0] * scale - 2, top: b[1] * scale - 2, width: (b[2] - b[0]) * scale + 4, height: (b[3] - b[1]) * scale + 4 }} />
            ))}
            {xray && scale > 0 && xd && !xd.error && <>
              {(xd.records || []).filter((r: any) => r.box).map((r: any) => (
                <button key={r.id} type="button" className={`xbox ${XCLS[r.status] || "x-na"} ${r.id === currentId ? "x-cur" : ""}`}
                  title={`${r.rec_id} · ${r.metric} = ${r.raw_value} ${r.unit || ""} · ${r.status}${r.how?.startsWith("value") ? " (положение по совпадению числа)" : ""}`}
                  aria-label={`Значение ${r.metric} ${r.raw_value}`}
                  onClick={() => nav(`/record/${r.id}`)}
                  style={{ left: r.box[0] * scale - 2, top: r.box[1] * scale - 2, width: (r.box[2] - r.box[0]) * scale + 4, height: (r.box[3] - r.box[1]) * scale + 4 }} />))}
              {cands.map((c: any, i: number) => (
                <button key={`c${i}`} type="button" className="xbox x-miss" title={`Не извлечено: ${c.text} — нажмите, чтобы добавить`} aria-label={`Добавить число ${c.text}`}
                  onClick={() => setAddFor(c)}
                  style={{ left: c.box[0] * scale - 2, top: c.box[1] * scale - 2, width: (c.box[2] - c.box[0]) * scale + 4, height: (c.box[3] - c.box[1]) * scale + 4 }} />))}
            </>}
          </div>
        </div>
      )}
      {addFor && <AddFromPage domain={domain} split={split} pid={pid} page={pg} cand={addFor} onClose={() => setAddFor(null)}
        onAdded={(id) => nav(`/record/${id}`)} />}
      <VisionPanel domain={domain} split={split} pid={pid} page={pg} />
      {info && tab !== "image" && (
        <div className="text-pane" tabIndex={0} aria-label={`Текст страницы, движок ${tab}`}>
          {info.variants[tab] ? highlight(info.variants[tab], onSource ? fragment : undefined) : <span className="faint">Этот движок не дал текста для страницы.</span>}
        </div>
      )}
    </div>
  );
}

function AddFromPage({ domain, split, pid, page, cand, onClose, onAdded }:
  { domain: string; split: string; pid: string; page: number; cand: any; onClose: () => void; onAdded: (id: number) => void }) {
  const [metric, setMetric] = useState("");
  const [unit, setUnit] = useState(cand.text.endsWith("%") ? "%" : "");
  const [quote, setQuote] = useState(cand.line);
  const [table, setTable] = useState("");
  const [origin, setOrigin] = useState("primary");
  const [cite, setCite] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [metrics, setMetrics] = useState<string[]>([]);
  useEffect(() => { api(`/api/metric_names${qs({ domain, split })}`).then((m: any[]) => setMetrics(m.map((x) => x.name))).catch(() => {}); }, [domain, split]);
  const raw = cand.text.replace(/[,;:]$/, "").replace(/%$/, "");
  const save = async () => {
    setBusy(true); setErr("");
    try {
      const r = await post("/api/records/add_from_page", { domain, split, pub_id: pid, page, raw_value: raw, raw_unit: unit, metric_name: metric, quote,
        source_table: table, result_origin: origin, cited_publication_id: cite, box: cand.box, actor: (() => { try { return localStorage.getItem("actor") || "reviewer"; } catch { return "reviewer"; } })() });
      onAdded(r.id);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="card card-b stack add-panel" role="dialog" aria-label="Добавить значение со страницы">
      <div className="row between"><b>Добавить значение <span className="mono">{raw}</span> со стр. {page}</b><button className="btn sm ghost" onClick={onClose} aria-label="Закрыть">✕</button></div>
      <div className="small muted">Цитата — строка страницы, где стоит число; её можно сократить. После сохранения сайт сам проверит, что цитата есть на странице и число в ней.</div>
      <div className="grid g2">
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Показатель *
          <input className="input" value={metric} onChange={(e) => setMetric(e.target.value)} list="xr-metrics" placeholder="например EM, PCE, Voc" autoFocus /></label>
        <datalist id="xr-metrics">{metrics.map((m) => <option key={m} value={m} />)}</datalist>
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Единица (как в статье)
          <input className="input" value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="%, V, mA/cm2, fraction…" /></label>
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Таблица (если из таблицы)
          <input className="input" value={table} onChange={(e) => setTable(e.target.value)} placeholder="Table 2" /></label>
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Происхождение
          <select className="input" value={origin} onChange={(e) => setOrigin(e.target.value)}><option value="primary">primary — результат авторов</option><option value="cited">cited — из чужой работы</option></select></label>
        {origin === "cited" && <label className="small muted" style={{ display: "grid", gap: 3 }}>Ссылка в статье
          <input className="input" value={cite} onChange={(e) => setCite(e.target.value)} placeholder="[12] или Lewis et al., 2020" /></label>}
      </div>
      <label className="small muted" style={{ display: "grid", gap: 3 }}>Цитата со страницы
        <textarea className="input mono" rows={2} value={quote} onChange={(e) => setQuote(e.target.value)} /></label>
      {err && <div className="notice err">{err}</div>}
      <div className="row"><button className="btn primary" disabled={busy || !metric.trim()} onClick={save}>{busy ? "Сохраняю…" : "Добавить и проверить"}</button>
        <button className="btn ghost" onClick={onClose}>Отмена</button></div>
    </div>
  );
}
