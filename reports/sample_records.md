# 10 случайных записей с полной цепочкой обработки

Сгенерировано `backend/scripts_sample.py` (seed=2026). Ссылки ведут в UI (http://127.0.0.1:8077/record/<id>).

## 1. [скан] rag/dev/D002 R122 — Elo = 921 
- UI: /record/69351
- PDF: `D002.pdf`, страница **11**, раздел «b) Performances on Multi-Hop Cybersecurity Questions», таблица «Table V», рисунок «» — **скан, текст из OCR**
- Цитата: «MIXTRAL, despite its lower performance
on general questions, performs better on Multi-Hop questions
with a better Elo of 921»
- Нода: A (text); строка/столбец:  / 
- Нормализация: raw `921 ` → `921 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched_ocr_only**, движки ['ocr'], число в цитате: True, ts 2026-11-21T17:04:42+00:00
- Кворум: {"mode": "extended", "nodes": ["A", "B"], "outcome": "agree", "other_value": "921", "other_fragment": "MIXTRAL, despite its lower performance\non general questions, performs better on Multi-Hop questions\nwith a better Elo of 921", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**needs_review**, review=pending, причины: ['ocr_uncertainty', 'ocr_page']
- Замечания: ocr_uncertainty: Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы

## 2. [скан] rag/dev/D013 R017 — Pearson correlation = 0.594 
- UI: /record/74399
- PDF: `D013.pdf`, страница **4**, раздел «3», таблица «Table 1», рисунок «» — **скан, текст из OCR**
- Цитата: «OAGC 0.594 0.472 10.450 / 0.344»
- Нода: A (table); строка/столбец:  / 
- Нормализация: raw `0.594 ` → `0.594 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched_ocr_only**, движки ['ocr'], число в цитате: True, ts 2026-11-21T17:07:28+00:00
- Кворум: {"mode": "default", "nodes": ["A", "R"], "outcome": "single", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**needs_review**, review=pending, причины: ['ocr_uncertainty', 'ocr_page']
- Замечания: ocr_uncertainty: Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы

## 3. [таблица] rag/test/P032 R071 — Accuracy = 85.9 
- UI: /record/87556
- PDF: `P032.pdf`, страница **6**, раздел «Experimental Setup», таблица «Table 1», рисунок «»
- Цитата: «Table 1: Evaluation on LLM-AggreFact. Models are ordered by average balanced accuracy (BAc»
- Нода: R (table); строка/столбец: Mistral-Large 123B / RAG Truth
- Нормализация: raw `85.9 ` → `85.9 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:20:16+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: metric_scale=unknown_scale
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 4. [таблица] rag/test/P032 R223 — Accuracy = 62.3 
- UI: /record/87708
- PDF: `P032.pdf`, страница **6**, раздел «Experimental Setup», таблица «Table 1», рисунок «»
- Цитата: «Table 1: Evaluation on LLM-AggreFact. Models are ordered by average balanced accuracy (BAc»
- Нода: R (table); строка/столбец: Llama-3.2-3B-Instruct 3B / Claim Verify
- Нормализация: raw `62.3 ` → `62.3 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:20:16+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: metric_scale=unknown_scale
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 5. [рисунок] solar/dev/D003 R020 — lattice_spacing = 0.344 nm
- UI: /record/82527
- PDF: `D003.pdf`, страница **3**, раздел «», таблица «», рисунок «Figure 1C»
- Цитата: «0.313
and
0.344 nm»
- Нода: A (text); строка/столбец:  / 
- Нормализация: raw `0.344 nm` → `0.344 nm` (metric outside official list: kept as is)
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: True, ts 2026-11-21T17:19:39+00:00
- Кворум: {"mode": "default", "nodes": ["A", "R"], "outcome": "single", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 6. [cited] solar/test/P046 R009 — Voc = 854 mV
- UI: /record/80770
- PDF: `P046.pdf`, страница **5**, раздел «ABSTRACT», таблица «Table 3», рисунок «»
- Цитата: «TABLE 3 | Absorber properties and JV parameters of the best Cu-free AIGS cells with Mo bac»
- Нода: R (table); строка/столбец: Best cell from [49], / VOC (mV)
- Нормализация: raw `854 mV` → `0.854 V` (mV x 0.001 -> V)
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:19:10+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 7. [flagged] solar/test/P073 R007 — FF = 75.48 %
- UI: /record/81711
- PDF: `P073.pdf`, страница **11**, раздел «3. Results and Discussion», таблица «Table 2», рисунок «»
- Цитата: «Table 2. Photovoltaic characteristics of the CIGS devices fabricated under different Na do»
- Нода: R (table); строка/столбец: 3.5% / FF (%)
- Нормализация: raw `75.48 %` → `75.48 %` (% x 1 -> %)
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:19:28+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: jv_consistency=fail (PCE = Voc·Jsc·FF / Pin, расчёт 14432.513)
- Итог: verification=**flagged**, review=pending, причины: ['rule_violation:jv_consistency']
- Замечания: jv_consistency: PCE по ВАХ: 568.4 В × 33.64 мА/см² × 75.48 % / 100 мВт/см² = 14432.51 %; опубликовано 14.43 % (расхождение 99917.4 % > 3 %); агрегация: не указана (Pin не указа

## 8. [после кворума] solar/dev/D004 R078 — PCE = 4.3 %
- UI: /record/82787
- PDF: `D004.pdf`, страница **11**, раздел «», таблица «Table 2», рисунок «»
- Цитата: «TiO2/MoS2-based Nanocomposite (NC) as ETL.
ITO/NC(TiO2/MoS2)/MAPbI3/spiro-
OMeTAD/Au
4.3
[36]»
- Нода: A (table); строка/столбец:  / 
- Нормализация: raw `4.3 %` → `4.3 %` (% x 1 -> %)
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: True, ts 2026-11-21T17:19:40+00:00
- Кворум: {"mode": "extended", "nodes": ["A", "B"], "outcome": "agree", "other_value": "4.3", "other_fragment": "4.3\n[36]", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 9. [случайная] rag/test/P019 R048 — Exact Match = 0.475 
- UI: /record/86655
- PDF: `P019.pdf`, страница **7**, раздел «Method», таблица «Table 1», рисунок «»
- Цитата: «Table 1: Evaluation results on multi-hop QA benchmarks. EM, F1, P, and R denote Exact Matc»
- Нода: R (table); строка/столбец: GenGround / MuSiQue GPT-4o-mini R
- Нормализация: raw `0.475 ` → `0.475 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:20:10+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: не применимы
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет

## 10. [случайная] rag/test/P012 R190 — nDCG = 48.50 
- UI: /record/85461
- PDF: `P012.pdf`, страница **8**, раздел «Related Work», таблица «Table 4», рисунок «»
- Цитата: «Table 4: Ranking performance (NDCG@5, %) of various LLM-specific utility-based ranking met»
- Нода: R (table); строка/столбец: Initial Retrieval / over the likelihood method within the same block using the paired t-test (𝑝< 0.05), respectively. Llama3.1-8B-Instruct and HotpotQA
- Нормализация: raw `48.50 ` → `48.5 ` (kept on the published scale (no rescaling by metric name))
- Проверка цитаты: **matched**, движки ['pymupdf', 'pypdf'], число в цитате: False, ts 2026-11-21T17:20:05+00:00
- Кворум: {"mode": "default", "nodes": ["R"], "outcome": "single_node", "limitation": "only one extraction node ran", "same_model_limitation": false}
- Правила: metric_scale=unknown_scale
- Итог: verification=**verified**, review=none, причины: []
- Замечания: нет
