import React, { createContext, useContext, useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import "./styles.css";
import { api } from "./api";
import Overview from "./pages/Overview";
import Catalog from "./pages/Catalog";
import Results from "./pages/Results";
import Publication from "./pages/Publication";
import RecordPage from "./pages/Record";
import Compare from "./pages/Compare";
import ExportPage from "./pages/Export";
import SearchPage from "./pages/Search";
import Admin from "./pages/Admin";
import UploadPanel from "./components/UploadPanel";

/** Stable link /v/<domain>/<split>/<pub>/<result_id>: survives re-processing (DB ids change, result ids are stable). */
function Permalink() {
  const p = useParams();
  const nav = useNavigate();
  const [err, setErr] = useState("");
  useEffect(() => {
    api(`/api/resolve/${p.domain}/${p.split}/${p.pid}/${p.rec}`).then((r) => nav(`/record/${r.id}`, { replace: true })).catch((e) => setErr(e.message));
  }, [p.domain, p.split, p.pid, p.rec]);
  return err ? <div className="state err"><b>Запись не найдена</b>{err}<div><a href={`/pub/${p.domain}/${p.split}/${p.pid}`}>Открыть публикацию</a></div></div>
    : <div className="state">Открываю {p.pid}/{p.rec}…</div>;
}

type Scope = { domain: string; split: string; setDomain: (d: string) => void; setSplit: (s: string) => void };
const Ctx = createContext<Scope>({ domain: "rag", split: "dev", setDomain: () => {}, setSplit: () => {} });
export const useScope = () => useContext(Ctx);

function readLS(k: string, d: string) { try { return localStorage.getItem(k) || d; } catch { return d; } }
function writeLS(k: string, v: string) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }

function Layout() {
  const [sp, setSp] = useSearchParams();
  const [domain, setD] = useState(sp.get("domain") || readLS("domain", "rag"));
  const [split, setS] = useState(sp.get("split") || readLS("split", "dev"));
  const [open, setOpen] = useState(false);
  const [counts, setCounts] = useState<any>(null);
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => { setOpen(false); }, [loc.pathname]);
  useEffect(() => {
    const d = sp.get("domain"), s = sp.get("split");
    if (d && d !== domain) setD(d);
    if (s && s !== split) setS(s);
  }, [sp]);
  useEffect(() => { api("/api/overview").then(setCounts).catch(() => setCounts(null)); }, [loc.pathname, domain, split]);
  const update = (k: "domain" | "split", v: string) => {
    k === "domain" ? setD(v) : setS(v);
    writeLS(k, v);
    if (sp.has(k)) { const n = new URLSearchParams(sp); n.set(k, v); n.delete("offset"); setSp(n, { replace: true }); }
  };
  const c = counts?.[domain]?.splits?.[split];
  const q = `?domain=${domain}&split=${split}`;
  const [search, setSearch] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(readLS("settingsOpen", "0") === "1" || loc.pathname.match(/\/admin\/(corpus|metrics|llm|config|audit)/) !== null);
  const [uploadOpen, setUploadOpen] = useState(false);
  return (
    <Ctx.Provider value={{ domain, split, setDomain: (d) => update("domain", d), setSplit: (s) => update("split", s) }}>
      <div className="app">
        <aside className={`side ${open ? "open" : ""}`} aria-label="Навигация">
          <div className="brand">
            <div className="brand-mark"><svg width="18" height="18" viewBox="0 0 32 32"><path d="M7 17l6 6 12-14" stroke="#67c2bd" strokeWidth="3.5" fill="none" strokeLinecap="round" /></svg></div>
            <div><b>Evidence Extractor</b><span>ВИНИТИ РАН × ЮФУ</span></div>
          </div>
          <div className="scope">
            <label>Предметная область
              <select value={domain} onChange={(e) => update("domain", e.target.value)} aria-label="Предметная область">
                <option value="rag">RAG-системы</option><option value="solar">Солнечные элементы</option>
              </select></label>
            <label>Набор
              <select value={split} onChange={(e) => update("split", e.target.value)} aria-label="Набор">
                <option value="dev">dev (есть эталон)</option><option value="test">test (без эталона)</option><option value="demo">demo (тестовые PDF)</option>
              </select></label>
          </div>
          <form onSubmit={(e) => { e.preventDefault(); if (search.trim()) nav(`/search?q=${encodeURIComponent(search.trim())}&domain=${domain}&split=${split}`); }}>
            <input className="input" style={{ width: "100%", background: "#102340", color: "#fff", borderColor: "#2c4a72" }} placeholder="Полнотекстовый поиск…"
              value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Полнотекстовый поиск" />
          </form>
          <nav className="nav">
            <div className="grp">Работа</div>
            <NavLink to="/" end>Обзор</NavLink>
            <NavLink to={`/catalog${q}`}>Публикации {c && <span className="count">{c.pdfs}</span>}</NavLink>
            <NavLink to={`/results${q}`}>Результаты {c && <span className="count">{c.results}</span>}</NavLink>
            <NavLink to={`/admin/review${q}`}>Очередь проверки {c && (c.verification?.needs_review || c.verification?.flagged) ? <span className="count warn">{(c.verification?.needs_review || 0) + (c.verification?.flagged || 0)}</span> : null}</NavLink>
            <NavLink to={`/admin/issues${q}`}>Замечания {c && c.open_issues ? <span className="count">{c.open_issues}</span> : null}</NavLink>
            <NavLink to={`/compare${q}`}>Сравнение</NavLink>
            <NavLink to={`/export${q}`}>Экспорт</NavLink>
            <button type="button" className="grp grp-toggle" aria-expanded={settingsOpen} onClick={() => { setSettingsOpen(!settingsOpen); writeLS("settingsOpen", settingsOpen ? "0" : "1"); }}>
              Настройки и контроль <span aria-hidden="true">{settingsOpen ? "▾" : "▸"}</span></button>
            {settingsOpen && <>
              <NavLink to={`/admin/corpus${q}`}>Корпус и задачи</NavLink>
              <NavLink to={`/admin/metrics${q}`}>Метрики качества</NavLink>
              <NavLink to={`/admin/llm${q}`}>LLM и ноды</NavLink>
              <NavLink to={`/admin/config${q}`}>Схемы и правила</NavLink>
              <NavLink to={`/admin/audit${q}`}>Аудит</NavLink>
            </>}
          </nav>
          <div className="side-foot">PDF — данные, а не инструкции. Значения не додумываются.</div>
        </aside>
        <main className="main">
          <div className="topstrip">
            <button className="btn sm menu-btn" onClick={() => setOpen(true)} aria-label="Открыть меню">☰ Меню</button>
            <span style={{ flex: 1 }} />
            <button className="btn primary sm" onClick={() => setUploadOpen(true)}>⇪ Загрузить PDF</button>
          </div>
          {uploadOpen && <div className="modal-bg" role="dialog" aria-modal="true" aria-label="Загрузка PDF" onClick={(e) => { if (e.target === e.currentTarget) setUploadOpen(false); }}>
            <div className="modal"><div className="row between" style={{ marginBottom: 8 }}><b>Загрузить PDF на проверку</b>
              <button className="btn sm ghost" onClick={() => setUploadOpen(false)} aria-label="Закрыть">✕</button></div>
              <UploadPanel domain={domain} autoOpen onOpened={() => setUploadOpen(false)} /></div></div>}
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/results" element={<Results />} />
            <Route path="/pub/:domain/:split/:pid" element={<Publication />} />
            <Route path="/record/:id" element={<RecordPage />} />
            <Route path="/v/:domain/:split/:pid/:rec" element={<Permalink />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/export" element={<ExportPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/admin/:tab" element={<Admin />} />
            <Route path="*" element={<div className="state"><b>Страница не найдена</b><a href="/">На обзор</a></div>} />
          </Routes>
        </main>
      </div>
    </Ctx.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><BrowserRouter><Layout /></BrowserRouter></React.StrictMode>
);
