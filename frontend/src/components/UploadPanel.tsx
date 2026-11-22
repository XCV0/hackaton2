import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Badge } from "./ui";

/** Upload a user PDF into the separate «demo» set and follow its processing job. */
export default function UploadPanel({ domain, onDone }: { domain: string; onDone?: () => void }) {
  const [dom, setDom] = useState(domain);
  const [mode, setMode] = useState("default");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState<any>(null);
  const [job, setJob] = useState<any>(null);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => setDom(domain), [domain]);
  useEffect(() => {
    if (!res?.job_id || (job && !["queued", "running"].includes(job.status))) return;
    const t = setInterval(async () => {
      try {
        const j = await api(`/api/jobs/${res.job_id}`);
        setJob(j);
        if (!["queued", "running"].includes(j.status)) onDone?.();
      } catch { /* keep polling */ }
    }, 3000);
    return () => clearInterval(t);
  }, [res, job]);
  const pick = (f?: File | null) => {
    setErr(""); setRes(null); setJob(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) { setErr("Нужен файл .pdf"); return; }
    if (f.size > 60 * 1024 * 1024) { setErr("Файл больше 60 МБ"); return; }
    setFile(f);
  };
  const send = async () => {
    if (!file) return;
    setBusy(true); setErr("");
    const fd = new FormData();
    fd.append("file", file); fd.append("domain", dom); fd.append("mode", mode); fd.append("process", "true");
    fd.append("actor", (() => { try { return localStorage.getItem("actor") || "user"; } catch { return "user"; } })());
    try {
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Сервер ответил ${r.status}`);
      setRes(d);
      setJob({ status: "queued" });
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const running = job && ["queued", "running"].includes(job.status);
  return (
    <div className="card card-b stack">
      <div className="row between"><h3 style={{ margin: 0 }}>Загрузить свой PDF</h3><span className="small muted">попадёт в набор <b>demo</b>, корпус кейса не меняется</span></div>
      <div className={`dropzone ${drag ? "on" : ""}`} role="button" tabIndex={0} aria-label="Выбрать PDF"
        onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]); }}>
        <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => pick(e.target.files?.[0])} />
        {file ? <span><b>{file.name}</b> · {(file.size / 1024 / 1024).toFixed(2)} МБ</span> : <span>Перетащите PDF сюда или нажмите, чтобы выбрать</span>}
      </div>
      <div className="row">
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Предметная область
          <select className="input" value={dom} onChange={(e) => setDom(e.target.value)}><option value="rag">RAG-системы</option><option value="solar">Солнечные элементы</option></select></label>
        <label className="small muted" style={{ display: "grid", gap: 3 }}>Режим
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="default">Обычный: нода A + проверки</option><option value="extended">Расширенный: A + B + C</option></select></label>
        <button className="btn primary" style={{ alignSelf: "end" }} disabled={!file || busy || running} onClick={send}>{busy ? "Загрузка…" : "Загрузить и обработать"}</button>
      </div>
      {err && <div className="notice err" role="alert">{err}</div>}
      {res && (
        <div className={`notice ${job?.status === "done" ? "ok" : job?.status?.includes("error") ? "err" : "info"}`} role="status">
          <div className="row between">
            <span>Файл сохранён как <b className="mono">{res.pub_id}</b> ({res.pages} стр.).</span>
            {running ? <Badge cls="b-warn">обработка… {job?.done ?? 0}/{job?.total || 1}</Badge> : job?.status === "done" ? <Badge cls="b-ok">готово</Badge> : <Badge cls="b-err">{job?.status}</Badge>}
          </div>
          {running && <div className="small">Сканы проходят OCR, затем LLM-ноды читают страницы — обычно 1–5 минут. Страницу можно не закрывать.</div>}
          {!running && job?.status && <div className="row" style={{ marginTop: 6 }}>
            <Link className="btn sm primary" to={`/pub/${res.domain}/demo/${res.pub_id}`}>Открыть результаты</Link>
            <Link className="btn sm" to={`/admin/issues?domain=${res.domain}&split=demo&pub=${res.pub_id}`}>Замечания</Link></div>}
          {job?.log && !running && <details className="more"><summary className="small">журнал обработки</summary><pre className="code">{job.log}</pre></details>}
        </div>
      )}
    </div>
  );
}
