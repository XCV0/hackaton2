# REQUIREMENTS — кейс ВИНИТИ РАН × ЮФУ

Источники требований:
- **[C]** — условия кейса `ВИНИТИ+ЮФУ.pdf` (12 слайдов);
- **[T]** — техническое задание пользователя (разделы 1–16);
- **[S1]** — комплект области 1: `README_участникам.md`, `submission_template/README.md`, `tools/check_submission.py`;
- **[S2]** — комплект RAG: `README_участникам.md`, `CHECKLIST.txt`, `submission_template/README.md`, `schema.json`, `dev_gold/README_STATUS.md`, `tools/check_submission.py`.

## 1. Инвентаризация входных материалов (этап 0, фактический прогон)

`data/domain1_solar → ~/Downloads/Кейс5_область1_участникам`, `data/domain2_rag → ~/Downloads/RAG_ВИНИТИ_участникам_2026-11-20` (символические ссылки; исходники не изменяются).

| Область | Набор | PDF | Страниц | Сканы без текстового слоя | Частично без текста | Эталон |
|---|---|---|---|---|---|---|
| 1 Солнечные | dev | 21 (D001–D022, без D011) | 212 | 0 | 0 | dev_gold: 7 таблиц, 659 результатов |
| 1 Солнечные | test | 90 (P001–P090) | 1000 | 0 | P018 (11/13 стр.) | нет |
| 2 RAG | dev | 21 (D001–D021) | 371 | **D002, D013, D021** | 0 | dev_gold: 7 таблиц, 37 616 результатов + coverage/*.json |
| 2 RAG | test | 90 (P001–P090) | 1442 | 14: P013 P023 P026 P030 P033 P044 P047 P054 P056 P063 P064 P065 P075 P082 | P017 (23/24) | нет |

- Дубликатов по SHA-256 и по DOI нет (`reports/inventory.json`). DOI найден на первых страницах у 114 из 222 PDF.
- `Кейс5…/dev/dev.zip` — архив тех же 21 dev-PDF (хеши совпадают побайтно), отдельного содержимого нет.
- Число сканов и SHA-256 совпадают с `CHECKLIST.txt`.
- Официальные проверщики: `tools/check_submission.py` в обоих комплектах; не изменяются, запускаются как подпроцесс.

## 2. Официальные схемы выходных данных

Колонки читаются в рантайме из `submission_template/*.csv` (и сверяются с `schema.json` для RAG) — `backend/app/core/domain.py`. Экспорт не может разойтись со схемой.

**Область 1** (7 таблиц): publications, materials, devices, layers, measurements, results, issues. Закрытые словари — из `check_submission.py` области 1 (material_class, dimensionality, bandgap_method, device_role, device_type, architecture, substrate_type, area_definition, layer_function, measurement_type, scan_direction, stability_protocol, mask_used, certified, in_scope, aggregation, result_origin, extraction_status).

**Область 2 RAG** (7 таблиц): publications, configurations, datasets, tasks, experiments, results, issues. Закрытые словари: in_scope, result_origin, extraction_status; рекомендуемый — metric_direction.

## 3. Требования → реализация → проверка

| # | Требование | Источник | Где реализовано | Как проверяется |
|---|---|---|---|---|
| R1 | Обе области обязательны, одно ядро, домены — конфигурациями | [T]1,4 | `core/*` (домен-независимо), `domains/rag.yaml`, `domains/solar.yaml`, схемы из шаблонов | `test_domain_schema_from_official_templates`; обработка обеих областей |
| R2 | publication_id = имя PDF; строка publications для каждого PDF, включая исключённые | [S1][S2] | `pipeline.process`, `export.build_tables` (добивает необработанные) | официальный проверщик: «PDF has no publication row» = 0 |
| R3 | in_scope=false → exclusion_reason, нет строк в других таблицах | [S2] | `pipeline.process` (ранний выход), проверщик | официальный проверщик; solar D006/D016 исключены, совпадает с эталоном |
| R4 | Не додумывать; пусто ≠ 0; не NaN/null/unknown | [C][S1][S2] | промпты нод, нормализация не заполняет без явной единицы, `extract_rules` precision-first | `test_solar_normalisation_units` (неизвестная единица → пусто) |
| R5 | Сохранять raw и нормализованное значение | [C][T]5 | `normalize.normalize_result` (+трасса `_norm` в evidence) | карточка результата: «Опубликовано · Нормализовано · Проверено» |
| R6 | Нормализация солнечной области: PCE,FF→%, Voc→V, Jsc→mA/cm², Eg→eV, толщина→nm, площадь→cm², время→h | [C] сл.6 | `domains/solar.yaml: units`, `normalize.py` | `test_solar_normalisation_units` |
| R7 | RAG: доли/проценты/BLEU/время не пересчитывать по имени метрики | [S2] | `normalize.py` (только явная единица; s→ms) | `test_rag_no_rescaling_by_metric_name` |
| R8 | source_page — страница PDF с 1; source_fragment — дословная цитата той же страницы | [S1][S2][T]5 | `quotes.verify_quote` | `test_quote_matched`, `test_quote_wrong_page`, официальный проверщик |
| R9 | Нормализация цитат только Unicode/пробелы/перенос через дефис; без склейки движков и страниц | [S2][T]5 | `pdftext.norm_rag` (копия официальной), проверка по каждому движку отдельно | `test_no_cross_engine_or_cross_page_glue` |
| R10 | Цитата проверяется pypdf и PyMuPDF независимо (+OCR как отдельный вариант) | [S2][T]5 | `quotes.verify_quote` → `engines` | карточка: «Найдена движками» |
| R11 | Пересказ «таблица 3, строка X» — не цитата | [S2][T]5 | `PARAPHRASE_RE`, quote not_found | `test_paraphrase_is_not_a_quote`, `test_negative_paraphrase` |
| R12 | Ненайденная цитата не становится verified | [T]5 | статусы в `pipeline.process` | статус needs_review + issue citation_not_found |
| R13 | Таблица: страница, таблица, строка, столбец, ячейка | [T]5 | `segment.parse_table_grid`, evidence.cell_bbox / row_label / col_label | подсветка ячейки в просмотрщике |
| R14 | Рисунок: текстовый поиск не подтверждает визуальное чтение | [S2][T]5,7 | figure → needs_review + source_figure_review | issue `source_figure_review` |
| R15 | Хранить, какие проверки выполнялись, когда и с каким результатом | [T]5 | `records.checks` (ts, outcome, inputs, formula) | карточка «Проверки» |
| R16 | Каскад нод: A на корпус; A+B на gold/проблемных; C точечно; без бесконечных циклов | [T]6 | `pipeline.process` (mode default/extended, бюджет C = 12 на статью), `extract_llm.reread` | `test_quorum_agree_and_disagree`; журнал node_runs |
| R17 | Сохранять ответ каждой ноды, модель, параметры, промпт, вход, решение | [T]6 | таблица `node_runs`; `records.quorum` | вкладка «Ноды» публикации |
| R18 | Честно указывать ограничение «одна модель» | [T]6 | `quorum.same_model_limitation`; по умолчанию B — другая модель | карточка «Кворум нод» |
| R19 | Различать 5 исходов (расхождение / подтверждено / нарушение правила / нет цитаты / разные условия) | [T]6 | статусы needs_review / verified / flagged; issue types; сравнение по ключу условий | фильтры очереди, страница «Сравнение» |
| R20 | OCR только для страниц без текстового слоя, не меняет PDF, не исправляет цифры | [S2][T]7 | `pdftext.run_ocr` (Tesseract 300 dpi, psm 3 — как в официальном `--ocr`) | статистика OCR, `matched_ocr_only` → needs_review |
| R21 | Vision: только напечатанные числа, без оцифровки кривых, без чисел из схем | [T]7 | `extract_llm.vision_page` (промпт с явными запретами), результат → needs_review | приёмка Vision (раздел 15.4) |
| R22 | Сканы D002, D013, D021 проходят полный путь | [T]7 | OCR → сегментация по OCR-словам → ноды → проверка | корпус: OCR-страницы; отчёт PROGRESS |
| R23 | Солнечные проверки: PCE↔Voc·Jsc·FF/Pin (3 %), Voc<Eg/q, Jsc(EQE) vs Jsc(ВАХ) (5 %), champion≠mean, forward/reverse раздельно, площади раздельно | [C] сл.5–6 | `rules.solar_rules`, comparability key | `test_pce_recalculation_*`, `test_voc_limit_and_champion_vs_mean`, `test_forward_reverse_are_separate_groups` |
| R24 | Нарушение правила не переписывает значение; issue с числами и формулой | [C] сл.6,10 | `rules._iss` (formula, inputs) | `test_pce_recalculation_violation_keeps_published_value` |
| R25 | RAG-правила: шкала, @k и metric_k, top_k ≠ metric_k, дубликаты без циклов, разные значения — не дубли | [S2][C] сл.10 | `rules.rag_rules`, `rules.duplicate_graph_errors` | `test_rag_scale_and_k`, `test_rag_contradiction_not_duplicate`, `test_negative_duplicate_cycle` |
| R26 | Сравнение только сопоставимых записей, объяснять несопоставимость | [C] сл.5,9 [T]10.6 | `/api/compare`, страница «Сравнение» | UI: группы и список «исключено с причинами» |
| R27 | Пользовательский UI: обзор, поиск/каталог (фильтры в URL), карточки, источник, сравнение, экспорт | [T]10 | `frontend/src/pages/*` | браузерная проверка (PROGRESS) |
| R28 | Админка: корпус, задачи/перезапуск, очередь flagged, фильтры, редактор, PDF рядом, решения с комментарием, история, ответы нод, конфигурации, метрики, аудит | [T]11 | `pages/Admin.tsx`, `/api/admin/*`, `/api/records/{id}/review`, `audit` | браузерная проверка |
| R29 | Ручная правка не переписывает raw незаметно | [T]11 | `review: correct` сохраняет `original_extraction`, аудит before/after, предупреждение в UI при смене raw | история изменений в карточке |
| R30 | Экспорт = данные UI; аудит экспорта | [T]10.7, 11 | `export.build_tables` читает те же `records`; `audit(export)` с хешами | аудит «export» |
| R31 | Метрики без подсматривания в эталон | [T]13 | только `evaluate.py` читает dev_gold, вызывается после обработки | `test_pipeline_never_reads_gold` |
| R32 | Метрики: P/R/F1, покрытие, доля цитат, ручная проверка, кворум, issues, время/стоимость; срезы | [T]13 | `evaluate.evaluate`, `technical_report` | `reports/metrics_*.json`, «Метрики качества» |
| R33 | На test — без precision/recall | [T]13 | `evaluate` для test → только technical_report | UI метрик для test |
| R34 | Официальный проверщик не изменять; коды 0/1/2 | [S2][T]9 | `export.run_official_checker` (подпроцесс) | `reports/official_check_*.json` |
| R35 | PDF — данные, не инструкции | [T]3 | системный промпт нод; содержимое PDF только в `<paper_pages>` | — |
| R36 | Ключ LLM вводится на сайте, выбор модели там же | пользователь | `core/llm.py`, Admin → «LLM и ноды» (пресеты провайдеров, AgentRouter через /v1/responses) | проверка соединения в UI |

## 4. Недостающие сведения

1. **Официального шаблона RAG нет** — комплект прямо называет `submission_template` RAG «рекомендуемой адаптацией» (`official_rag_template: false`). Используем его как формат сдачи.
2. Слайд 6 условий ссылается на «точные правила в описании кейса» (ограничения на Jsc, FF, PCE) — полного текста описания в материалах нет. Диапазоны в `solar.yaml: rules.ranges` — наши допущения (PCE 0–35 %, FF 0–92 %, Voc 0–2 В, Jsc 0–50 мА/см²), настраиваются в админке.
3. Эталон test и соответствие test-номеров исходным статьям не выдаются ([S2]).
4. PostgreSQL и Docker недоступны (Docker daemon не запущен, psql отсутствует) → SQLite (WAL); схема — обычный SQL.
5. LLM-доступ: только пользовательский ключ AgentRouter (модели `gpt-6.1-sol`, `gpt-5.6-sol`); сторонних ключей нет.

## 5. Допущения

- Порог «пригодного текстового слоя» — ≥40 печатных символов на странице; иначе OCR.
- OCR: Tesseract 5 (`eng`, 300 dpi, psm 3) — тот же режим, что `--ocr` официального проверщика, поэтому цитаты из OCR-текста воспроизводимы проверщиком.
- Нода R (детерминированная: геометрия таблиц + текстовые шаблоны) работает всегда и служит второй, методически независимой нодой для кворума, если нода B не задана.
- Для солнечной области цитаты дополнительно сверяются с упрощённой нормализацией официального проверщика области 1 (он читает только pypdf); при выборе цитаты из таблицы предпочитаем совместимую с ним.
- `source_section` определяется по жирным/крупным заголовкам; для сканов — по строкам OCR.
- Значения на графиках без напечатанных чисел не извлекаются (запрет оцифровки), хотя ~79 % эталона RAG dev — оцифрованные точки графиков. Поэтому метрики считаются и на полном эталоне, и на подмножестве «напечатанных» значений.
- Идентификаторы записей БД (`/record/<id>`) меняются при повторной обработке публикации; стабильны `publication_id/result_id` в экспорте. Ручные решения переносятся на новую версию записи по сигнатуре (страница, метрика, raw, таблица, связь, начало цитаты).

## 6. Критерии готовности

1. Обе области обработаны на dev и test; каждый PDF имеет строку publications.
2. Официальные проверщики: 0 ошибок (код ≠ 1) на экспортах dev и test; отчёты сохранены (без OCR и с OCR для RAG).
3. Ручной сценарий D001 (обычный) и D002 (скан): PDF → результат → источник → проверка → UI → экспорт.
4. Негативные тесты обнаруживают: неверную страницу, пересказ, несуществующий publication_id, разорванную связь, цикл duplicate_of.
5. Метрики dev посчитаны после полной обработки D001–D021 с зафиксированным правилом сопоставления.
6. UI проверен в браузере на desktop и узком экране.
7. PROGRESS.md честно перечисляет, что не сделано и не проверено.
