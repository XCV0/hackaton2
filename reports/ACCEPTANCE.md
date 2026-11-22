# Приёмка (раздел 15 ТЗ) — фактические данные

Сгенерировано `backend/scripts_acceptance.py` из БД `runs/viniti.db` и `reports/`.

## 1. Ручной сценарий RAG: D001 (обычный PDF) и D002 (скан)

**D001** — страниц 16, с текстовым слоем 16, OCR-страниц 0, ср. уверенность OCR None; основная нода A; значений 369; цитаты: {'matched': 368, 'not_found': 1}; статусы: {'verified': 346, 'needs_review': 23}; время 27.6 с.

- Пример: `/record/68659` — EM = 14.4 (с. 1, текст); цитата «it achieves a 14.4% EM
improvement over text-centric methods on Hot-
potQA» найдена движками ['pymupdf', 'pypdf']; итог verified

**D002** — страниц 17, с текстовым слоем 0, OCR-страниц 17, ср. уверенность OCR 91.6; основная нода A; значений 311; цитаты: {'matched_ocr_only': 311}; статусы: {'needs_review': 298, 'not_applicable': 13}; время 157.8 с.

- Пример: `/record/69230` — relevance and correctness of the answer = more than 10 (с. 1, текст); цитата «correctness of the answer is more than 10% compared to known» найдена движками ['ocr']; итог needs_review

Экспорт: `GET /api/export/rag/dev.zip?pub=D001` (проверено: отклонённая R301 отсутствует, исправленная R276 присутствует).

## 2. Полный dev и официальная проверка

- `official_check_rag_dev.json`: код выхода **2**, ошибок 0, на проверку 1977, цитаты {"requested": 5392, "matched": 4818, "unresolved": 574}; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain2_rag/tools/check_submission.py /Users/artemshelkunov/hackaton2/`
- `official_check_rag_dev_ocr.json`: код выхода **2**, ошибок 0, на проверку 1493, цитаты {"requested": 5392, "matched": 5302, "unresolved": 90}; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain2_rag/tools/check_submission.py /Users/artemshelkunov/hackaton2/`
- `official_check_rag_test.json`: код выхода **2**, ошибок 0, на проверку 661, цитаты {"requested": 6242, "matched": 5834, "unresolved": 408}; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain2_rag/tools/check_submission.py /Users/artemshelkunov/hackaton2/`
- `official_check_rag_test_ocr.json`: код выхода **2**, ошибок 0, на проверку 253, цитаты {"requested": 6242, "matched": 6242, "unresolved": 0}; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain2_rag/tools/check_submission.py /Users/artemshelkunov/hackaton2/`
- `official_check_solar_dev.json`: код выхода **0**, ошибок —, на проверку —, цитаты null; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain1_solar/tools/check_submission.py /Users/artemshelkunov/hackaton`
- `official_check_solar_test.json`: код выхода **0**, ошибок —, на проверку —, цитаты null; команда `/Users/artemshelkunov/hackaton2/.venv/bin/python3.14 /Users/artemshelkunov/hackaton2/data/domain1_solar/tools/check_submission.py /Users/artemshelkunov/hackaton`

## 3. Негативные тесты (копии экспорта)

```
PASSED backend/tests/test_pipeline.py::test_quote_matched
PASSED backend/tests/test_pipeline.py::test_quote_wrong_page
PASSED backend/tests/test_pipeline.py::test_paraphrase_is_not_a_quote
PASSED backend/tests/test_pipeline.py::test_negative_wrong_page
PASSED backend/tests/test_pipeline.py::test_negative_paraphrase
PASSED backend/tests/test_pipeline.py::test_negative_unknown_publication
PASSED backend/tests/test_pipeline.py::test_negative_broken_link
PASSED backend/tests/test_pipeline.py::test_negative_duplicate_cycle
8 passed, 16 deselected in 1.51s
```

## 4. Vision

- **printed values on a figure** — D002 с. 10 (Fig. 6: Impact of Retrievers (scan)), модель gpt-6.1-sol, 59 с: значений 21; схемы без метрик []; кривые не оцифрованы []; примеры: [('General Questions: Malware', '6.1'), ('General Questions: Metasploit', '8.6'), ('General Questions: ExploitDB', '7'), ('General Questions: CWE', '7')]
- **architecture diagram without metrics** — D001 с. 3 (Figure 2: Overview of ThreadRAG), модель gpt-6.1-sol, 21 с: значений 0; схемы без метрик ['Figure 2']; кривые не оцифрованы []; примеры: []
- **curve: digitisation forbidden** — D001 с. 8 (Figure 3: Hyperparameter sensitivity (line plots)), модель gpt-6.1-sol, 83 с: значений 22; схемы без метрик []; кривые не оцифрованы []; примеры: [('(a) Top-k Anchors', '0.574'), ('(b) Top-k Retrieved Docs', '0.574'), ('(c) Number of Iterations', '0.574'), ('(d) Energy Threshold (ε)', '0.574')]

## 5. Кворум

- **совпадение нод** (всего 1119): `/record/68659` rag/D001/R001 EM=14.4 — ноды ['A', 'B'], другая нода: 14.4, C: null
- **расхождение нод** (всего 42): `/record/68968` rag/D001/R310 Exact Match=7.8 to 12.6 — ноды ['A', 'B'], другая нода: 0.414, C: {"value": "0.414", "unit": "", "source_fragment": "from 0.288 to 0.414", "confident": true, "reason": "Page 8 prints 0.414 as an absolute HotpotQA EM value (Thr
- **кворум подтвердил опубликованное число, но правило нашло противоречие** (всего 5): `/record/82772` solar/D004/R063 Voc=0.943 — ноды ['A', 'B'], другая нода: 0.943, C: null; правило: jv_consistency PCE = Voc·Jsc·FF / Pin расчёт 10.397 vs опубл. {'Voc_V': 0.943, 'Jsc_mA_cm2': 19.664, 'FF_pct': 56.07, 'Pin_mW_cm2': 100, 'PCE_published': 9.9}

## 6. Солнечная область

- Ручной пересчёт PCE (D001/R071, `/record/82363`): 1.322 В × 15.75 мА/см² × 77.0 % / 100 мВт/см² = **16.033 %**; опубликовано 16.07 %; отклонение 0.23 % (порог 3 %) → pass
- Всего проверок PCE↔ВАХ: 135, нарушений: 11
- Разделение развёртки: публикаций с раздельными измерениями forward и reverse: 5 [('dev', 'D001'), ('dev', 'D005'), ('dev', 'D009'), ('test', 'P037'), ('test', 'P061')]
- primary/cited: {'primary': 2725, 'cited': 116}; пример cited: `/record/82296` D001 PCE=19 ссылка Bai et al., 2018; Wang et al., 2019a; Wang et al., 2019b; Straus et al., 2019; Tan et al., 2019, device_id пуст: True
- Сопоставимость: страница «Сравнение» группирует по ключу (класс материала, тип прибора, AM1.5G 100 мВт/см², площадь, агрегация, развёртка) и выводит причины исключения.

## 8. 10 случайных записей

См. `reports/sample_records.md` (есть).