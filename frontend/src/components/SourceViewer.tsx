import { useEffect, useRef, useState } from "react";
import { api, qs } from "../api";
import { Badge, ErrorState, Loading } from "./ui";
import VisionPanel from "./VisionPanel";

type Props = { domain: string; split: string; pid: string; page: number; fragment?: string; value?: string; cell?: number[] | null; pageCount?: number; figure?: string };

function highlight(text: string, frag?: string) {
  if (!frag) return text;
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const f = norm(frag);
  const flat = text.replace(/-\n(?=\w)/g, "").replace(/\s+/g, " ");
  const i = flat.indexOf(f);
  if (i < 0) return flat;
  return <>{flat.slice(0, i)}<mark>{flat.slice(i, i + f.length)}</mark>{flat.slice(i + f.length)}</>;
}

export default function SourceViewer({ domain, split, pid, page, fragment, value, cell, pageCount, figure }: Props) {
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
  const scale = info && imgW ? imgW / info.width : 0;
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
        {tab === "image" && <><button className="btn sm" onClick={() => setZoom(Math.max(1, zoom - 0.5))} aria-label="Уменьшить">−</button><button className="btn sm" onClick={() => setZoom(Math.min(3, zoom + 0.5))} aria-label="Увеличить">+</button></>}
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
      {err && <ErrorState error={err} />}
      {!info && !err && <Loading rows={6} />}
      {info && tab === "image" && (
        <div className="page-wrap">
          <div style={{ position: "relative", width: `${zoom * 100}%` }}>
            <img ref={imgRef} src={`/api/page/${domain}/${split}/${pid}/${pg}.png?dpi=${zoom > 1.5 ? 200 : 130}`} alt={`Страница ${pg} публикации ${pid}`}
              onLoad={(e) => setImgW((e.target as HTMLImageElement).clientWidth)} />
            {onSource && scale > 0 && (info.boxes || []).map((b: number[], i: number) => (
              <div key={i} className={`hl ${cell && i === info.boxes.length - 1 ? "cell" : ""}`}
                style={{ left: b[0] * scale - 2, top: b[1] * scale - 2, width: (b[2] - b[0]) * scale + 4, height: (b[3] - b[1]) * scale + 4 }} />
            ))}
          </div>
        </div>
      )}
      <VisionPanel domain={domain} split={split} pid={pid} page={pg} />
      {info && tab !== "image" && (
        <div className="text-pane" tabIndex={0} aria-label={`Текст страницы, движок ${tab}`}>
          {info.variants[tab] ? highlight(info.variants[tab], onSource ? fragment : undefined) : <span className="faint">Этот движок не дал текста для страницы.</span>}
        </div>
      )}
    </div>
  );
}
