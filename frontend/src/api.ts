export type Domain = "rag" | "solar";
export type Split = "dev" | "test";

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "content-type": "application/json", ...(init?.headers || {}) } });
  const text = await r.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    const msg = (data && (data.detail || data.error)) || `Сервер ответил ${r.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}

export const post = <T = any>(path: string, body: any) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T = any>(path: string, body: any) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const DOMAIN_TITLE: Record<string, string> = { rag: "RAG", solar: "Солнечные элементы" };
export const DOMAIN_LONG: Record<string, string> = { rag: "Retrieval-Augmented Generation", solar: "Тонкоплёночные солнечные элементы" };

export const VERIFICATION: Record<string, { label: string; cls: string; hint: string }> = {
  verified: { label: "Подтверждено источником", cls: "b-ok", hint: "Цитата найдена буквально на указанной странице и число привязано к ней" },
  flagged: { label: "Противоречие правилу", cls: "b-err", hint: "Источник подтверждён, но нарушено предметное правило — возможна внутренняя несогласованность статьи" },
  needs_review: { label: "Нужна проверка", cls: "b-warn", hint: "Происхождение не доказано машинно (цитата не найдена, скан, рисунок или расхождение нод)" },
  not_applicable: { label: "Без значения", cls: "b-plain", hint: "Значение отсутствует или не извлекаемо" },
};
export const REVIEW: Record<string, { label: string; cls: string }> = {
  none: { label: "Ручная проверка не требуется", cls: "b-plain" },
  pending: { label: "В очереди", cls: "b-warn" },
  confirmed: { label: "Подтверждено человеком", cls: "b-ok" },
  corrected: { label: "Исправлено человеком", cls: "b-violet" },
  rejected: { label: "Отклонено", cls: "b-err" },
};
export const QUOTE: Record<string, { label: string; cls: string }> = {
  matched: { label: "Цитата найдена", cls: "b-ok" },
  matched_ocr_only: { label: "Найдена только в OCR", cls: "b-warn" },
  wrong_page: { label: "На другой странице", cls: "b-err" },
  not_found: { label: "Цитата не найдена", cls: "b-err" },
  no_text_layer: { label: "Нет текста страницы", cls: "b-warn" },
  bad_page: { label: "Страница вне PDF", cls: "b-err" },
  no_fragment: { label: "Без цитаты", cls: "b-warn" },
};
export const ISSUE_LABEL: Record<string, string> = {
  jv_consistency: "PCE ≠ Voc·Jsc·FF/Pin",
  voc_limit: "Voc ≥ Eg/q",
  eqe_consistency: "Jsc(EQE) vs Jsc(ВАХ)",
  champion_vs_mean: "Среднее > лучшего",
  range: "Вне диапазона",
  metric_scale: "Вне шкалы метрики",
  metric_k: "k метрики",
  protocol_mismatch: "Несопоставимый протокол",
  normalization: "Нормализация",
  contradiction: "Противоречие в статье",
  citation_not_found: "Цитата не найдена",
  source_figure_review: "Рисунок: визуальная проверка",
  node_disagreement: "Расхождение нод",
  ocr_uncertainty: "Неуверенность OCR",
  duplicate_of: "Ошибка duplicate_of",
  extraction_linking: "Ошибка связывания (нода)",
};

export function qs(o: Record<string, any>) {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
}
