import { ReactNode, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ISSUE_LABEL, QUOTE, REVIEW, VERIFICATION } from "../api";

export function useAsync<T>(fn: () => Promise<T>, deps: any[]) {
  const [state, set] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    set((s) => ({ data: s.data, loading: true }));
    fn().then((data) => alive && set({ data, loading: false })).catch((e) => alive && set({ error: String(e.message || e), loading: false }));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload: () => setTick((t) => t + 1) };
}

/** URL-backed filter state (filters survive reload and are shareable). */
export function useUrlState(defaults: Record<string, string>) {
  const [sp, setSp] = useSearchParams();
  const get = (k: string) => sp.get(k) ?? defaults[k] ?? "";
  const vals: Record<string, string> = {};
  Object.keys(defaults).forEach((k) => (vals[k] = get(k)));
  sp.forEach((v, k) => (vals[k] = v));
  const set = (patch: Record<string, string | number | undefined>) => {
    const n = new URLSearchParams(sp);
    Object.entries(patch).forEach(([k, v]) => {
      if (v === undefined || v === "" || v === defaults[k]) n.delete(k); else n.set(k, String(v));
    });
    setSp(n, { replace: true });
  };
  return [vals, set] as const;
}

export function Badge({ cls, children, title }: { cls: string; children: ReactNode; title?: string }) {
  return <span className={`badge ${cls}`} title={title}>{children}</span>;
}

export function VerBadge({ v }: { v?: string }) {
  const m = VERIFICATION[v || ""] || { label: v || "—", cls: "b-plain", hint: "" };
  return <Badge cls={m.cls} title={m.hint}>{m.label}</Badge>;
}
export function ReviewBadge({ v }: { v?: string }) {
  const m = REVIEW[v || ""] || { label: v || "—", cls: "b-plain" };
  return <Badge cls={m.cls}>{m.label}</Badge>;
}
export function QuoteBadge({ v }: { v?: string | null }) {
  const m = QUOTE[v || ""] || { label: v || "нет проверки", cls: "b-plain" };
  return <Badge cls={m.cls}>{m.label}</Badge>;
}
export function IssueTag({ t }: { t: string }) {
  const err = ["jv_consistency", "voc_limit", "contradiction", "metric_scale", "range", "champion_vs_mean", "eqe_consistency"].includes(t);
  return <Badge cls={err ? "b-err" : "b-warn"} title={t}>{ISSUE_LABEL[t] || t}</Badge>;
}
export function OriginBadge({ o }: { o?: string }) {
  if (o === "cited") return <Badge cls="b-violet" title="Значение перенесено из другой работы">cited</Badge>;
  if (o === "primary") return <Badge cls="b-info" title="Собственный результат авторов">primary</Badge>;
  return null;
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return <div className="stack" style={{ padding: 16 }} aria-busy="true" aria-label="Загрузка">{Array.from({ length: rows }).map((_, i) => <div key={i} className="skel" style={{ width: `${90 - i * 12}%` }} />)}</div>;
}
export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return <div className="state err" role="alert"><b>Не удалось загрузить данные</b>{error}{retry && <div style={{ marginTop: 10 }}><button className="btn sm" onClick={retry}>Повторить</button></div>}</div>;
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="state"><b>{title}</b>{children}</div>;
}

export function Kpi({ v, l, s, tone }: { v: ReactNode; l: string; s?: ReactNode; tone?: "ok" | "warn" | "err" }) {
  const color = tone === "ok" ? "var(--teal)" : tone === "warn" ? "var(--amber)" : tone === "err" ? "var(--red)" : undefined;
  return <div className="card kpi"><div className="l">{l}</div><div className="v" style={{ color }}>{v}</div>{s && <div className="s">{s}</div>}</div>;
}

export function SortTh({ k, label, sort, onSort, title }: { k: string; label: string; sort: string; onSort: (s: string) => void; title?: string }) {
  const active = sort.replace("-", "") === k;
  const desc = sort.startsWith("-");
  return (
    <th className="sortable" title={title} aria-sort={active ? (desc ? "descending" : "ascending") : "none"} tabIndex={0}
      onClick={() => onSort(active && !desc ? `-${k}` : k)} onKeyDown={(e) => e.key === "Enter" && onSort(active && !desc ? `-${k}` : k)}>
      {label} {active ? (desc ? "↓" : "↑") : <span className="faint">↕</span>}
    </th>
  );
}

export function PubLink({ d, s, p }: { d: string; s: string; p: string }) {
  return <Link to={`/pub/${d}/${s}/${p}`} className="mono">{p}</Link>;
}

export function Toast({ msg, onDone }: { msg: string; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 3500); return () => clearTimeout(t); }, [msg]);
  return <div className="toast" role="status">{msg}</div>;
}

export function pct(x?: number | null, d = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(x * 100).toFixed(d)} %`;
}

/* ---------- plain-language glossary: a small "?" with a tooltip next to technical terms ---------- */
export const GLOSSARY: Record<string, string> = {
  "нода": "«Читатель» статьи: R — правила без ИИ; A и B — две модели ИИ, читающие независимо; C — модель, которая перечитывает страницу при споре; V — чтение чисел на рисунках.",
  "кворум": "Сверка двух независимых «читателей». Если оба прочли одно и то же число — это сильное подтверждение.",
  "цитата": "Кусок текста статьи, где написано число, слово в слово. Сайт проверяет, что он реально есть на указанной странице.",
  "raw": "Число ровно так, как напечатано в статье. Никогда не меняется.",
  "нормализация": "Перевод в общие единицы: мВ → В, доля → %, секунды → мс. Делается только если единица явно указана.",
  "primary": "primary — результат самих авторов статьи; cited — число, взятое из чужой работы (со ссылкой).",
  "L1": "Совпало: та же страница и то же число.",
  "L2": "Совпало: страница, число, та же метрика и k.",
  "L3": "Строгое совпадение: плюс тот же набор данных и конфигурация (RAG) или агрегация и развёртка (солнечные).",
  "рентген": "Все числа страницы поверх картинки: цветные рамки — извлечённые значения (цвет = статус), пунктир — напечатанные числа, которые никто не извлёк. Клик по пунктиру — добавить значение.",
  "агрегация": "Что это за число: лучший прибор (champion), среднее (mean) или медиана. Пусто — в статье не сказано.",
  "замечание": "Подозрение сайта: числа не сходятся, цитата не найдена, значение со скана или рисунка и т. п.",
};

export function Term({ k, children }: { k: string; children?: ReactNode }) {
  const tip = GLOSSARY[k] || GLOSSARY[k.toLowerCase()] || "";
  return (
    <span className="term">{children ?? k}{tip && <span className="term-q" tabIndex={0} role="note" aria-label={tip} data-tip={tip}>?</span>}</span>
  );
}

/* ---------- one combined status badge (human decision wins over machine status); details in the tooltip ---------- */
export function StatusBadge({ r }: { r: any }) {
  const rv = r.review_status;
  const human: Record<string, [string, string]> = { confirmed: ["Проверено человеком", "b-ok"], corrected: ["Исправлено человеком", "b-violet"],
    rejected: ["Отклонено", "b-err"] };
  const [label, cls] = human[rv] || ((VERIFICATION as any)[r.verification_status] ? [VERIFICATION[r.verification_status].label, VERIFICATION[r.verification_status].cls] : [r.verification_status, "b-plain"]);
  const q = (QUOTE as any)[r.quote_outcome || ""]?.label || "";
  const tip = [human[rv] ? `Машинная проверка: ${(VERIFICATION as any)[r.verification_status]?.label || r.verification_status}` : (VERIFICATION as any)[r.verification_status]?.hint,
    q && `Цитата: ${q}`, rv === "pending" && "Ждёт решения в очереди проверки",
    (r.issue_types || []).length ? `Замечания: ${(r.issue_types || []).map((t: string) => (ISSUE_LABEL as any)[t] || t).join(", ")}` : ""].filter(Boolean).join("\n");
  return <span className={`badge ${cls}`} title={tip}>{label}{(r.issue_types || []).length ? <b className="badge-n">{(r.issue_types || []).length}</b> : null}</span>;
}
