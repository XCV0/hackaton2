# TEST_RAG_ERRORS_01 / TEST_RAG_CLEAN_01: было (экспорт сервера) → стало (тот же ответ LLM, новый алгоритм)


## TEST_RAG_ERRORS_01

**configurations**: было 10 (C1, C10, C2, C3, C4, C5, C6, C7, C8, C9) → стало 5 (C10, C3, C4, C5, C6)  
  - C3: merged mentions C1, C7; also referred to as: BM25 configuration; LexRetrieve-BM25  
  - C4: merged mentions C2, C8; also referred to as: dense configuration; LexRetrieve-Dense  
  - C5: merged mentions C9; also referred to as: Dense w/o reranker  
**datasets**: было 3 (DS1, DS2, DS3) → стало 1 (DS1)  
  - DS1: merged mentions DS2  
**tasks**: было 3 (T1, T2, T3) → стало 1 (T2)  
  - T2: merged mentions T1; also referred to as: question answering  
**experiments**: было 5 (E1, E2, E3, E4, E5) → стало 2 (E2, E5)  
  - E2: merged mentions E1, E3, E4; also referred to as: Evaluation on 250 English questions sampled from the 1000-question test split; token-level F1; Exact Match  

**results** (только изменившиеся поля):

| id | поле | было | стало | статус было → стало |
|---|---|---|---|---|
| R001 | experiment_id | E1 | E2 | verified → verified |
| R001 | config_id | C1 | C3 | verified → verified |
| R001 | task_id | T1 | T2 | verified → verified |
| R001 | metric_unit |  | fraction | verified → verified |
| R001 | normalized_unit |  | fraction | verified → verified |
| R001 | metric_direction |  | higher_is_better | verified → verified |
| R001 | duplicate_of |  | R005 | verified → verified |
| R002 | experiment_id | E1 | E2 | verified → verified |
| R002 | config_id | C2 | C4 | verified → verified |
| R002 | task_id | T1 | T2 | verified → verified |
| R002 | metric_unit |  | fraction | verified → verified |
| R002 | normalized_unit |  | fraction | verified → verified |
| R002 | metric_direction |  | higher_is_better | verified → verified |
| R002 | duplicate_of |  | R009 | verified → verified |
| R003 | dataset_id | DS2 | DS1 | verified → verified |
| R003 | metric_direction |  | lower_is_better | verified → verified |
| R004 | dataset_id | DS2 | DS1 | verified → verified |
| R004 | metric_direction |  | lower_is_better | verified → verified |
| R005 | experiment_id | E3 | E2 | needs_review → needs_review |
| R005 | config_id | C7 | C3 | needs_review → needs_review |
| R005 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R005 | task_id | T3 | T2 | needs_review → needs_review |
| R005 | metric_name | EM | Exact Match | needs_review → needs_review |
| R005 | metric_unit |  | fraction | needs_review → needs_review |
| R005 | normalized_unit |  | fraction | needs_review → needs_review |
| R005 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R006 | experiment_id | E3 | E2 | needs_review → needs_review |
| R006 | config_id | C7 | C3 | needs_review → needs_review |
| R006 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R006 | task_id | T3 | T2 | needs_review → needs_review |
| R006 | metric_name | FA | F1 | needs_review → needs_review |
| R006 | metric_unit |  | fraction | needs_review → needs_review |
| R006 | normalized_unit |  | fraction | needs_review → needs_review |
| R006 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R007 | experiment_id | E3 | E2 | needs_review → needs_review |
| R007 | config_id | C7 | C3 | needs_review → needs_review |
| R007 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R007 | task_id | T3 | T2 | needs_review → needs_review |
| R007 | metric_unit |  | fraction | needs_review → needs_review |
| R007 | normalized_unit |  | fraction | needs_review → needs_review |
| R007 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R008 | experiment_id | E3 | E2 | needs_review → needs_review |
| R008 | config_id | C7 | C3 | needs_review → needs_review |
| R008 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R008 | task_id | T3 | T2 | needs_review → needs_review |
| R008 | metric_unit |  | fraction | needs_review → needs_review |
| R008 | normalized_unit |  | fraction | needs_review → needs_review |
| R008 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R009 | experiment_id | E3 | E2 | needs_review → needs_review |
| R009 | config_id | C8 | C4 | needs_review → needs_review |
| R009 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R009 | task_id | T3 | T2 | needs_review → needs_review |
| R009 | metric_name | EM | Exact Match | needs_review → needs_review |
| R009 | metric_unit |  | fraction | needs_review → needs_review |
| R009 | normalized_unit |  | fraction | needs_review → needs_review |
| R009 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R010 | experiment_id | E3 | E2 | needs_review → needs_review |
| R010 | config_id | C8 | C4 | needs_review → needs_review |
| R010 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R010 | task_id | T3 | T2 | needs_review → needs_review |
| R010 | metric_name | FA | F1 | needs_review → needs_review |
| R010 | metric_unit |  | fraction | needs_review → needs_review |
| R010 | normalized_unit |  | fraction | needs_review → needs_review |
| R010 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R011 | experiment_id | E3 | E2 | needs_review → needs_review |
| R011 | config_id | C8 | C4 | needs_review → needs_review |
| R011 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R011 | task_id | T3 | T2 | needs_review → needs_review |
| R011 | metric_unit |  | fraction | needs_review → needs_review |
| R011 | normalized_unit |  | fraction | needs_review → needs_review |
| R011 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R012 | experiment_id | E3 | E2 | needs_review → needs_review |
| R012 | config_id | C8 | C4 | needs_review → needs_review |
| R012 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R012 | task_id | T3 | T2 | needs_review → needs_review |
| R012 | metric_unit |  | fraction | needs_review → needs_review |
| R012 | normalized_unit |  | fraction | needs_review → needs_review |
| R012 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R013 | experiment_id | E3 | E2 | needs_review → needs_review |
| R013 | config_id | C9 | C5 | needs_review → needs_review |
| R013 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R013 | task_id | T3 | T2 | needs_review → needs_review |
| R013 | metric_name | EM | Exact Match | needs_review → needs_review |
| R013 | metric_unit |  | fraction | needs_review → needs_review |
| R013 | normalized_unit |  | fraction | needs_review → needs_review |
| R013 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R014 | experiment_id | E3 | E2 | needs_review → needs_review |
| R014 | config_id | C9 | C5 | needs_review → needs_review |
| R014 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R014 | task_id | T3 | T2 | needs_review → needs_review |
| R014 | metric_name | FA | F1 | needs_review → needs_review |
| R014 | metric_unit |  | fraction | needs_review → needs_review |
| R014 | normalized_unit |  | fraction | needs_review → needs_review |
| R014 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R015 | experiment_id | E3 | E2 | needs_review → needs_review |
| R015 | config_id | C9 | C5 | needs_review → needs_review |
| R015 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R015 | task_id | T3 | T2 | needs_review → needs_review |
| R015 | metric_unit |  | fraction | needs_review → needs_review |
| R015 | normalized_unit |  | fraction | needs_review → needs_review |
| R015 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R016 | experiment_id | E3 | E2 | needs_review → needs_review |
| R016 | config_id | C9 | C5 | needs_review → needs_review |
| R016 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R016 | task_id | T3 | T2 | needs_review → needs_review |
| R016 | metric_unit |  | fraction | needs_review → needs_review |
| R016 | normalized_unit |  | fraction | needs_review → needs_review |
| R016 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R017 | experiment_id | E3 | E2 | needs_review → needs_review |
| R017 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R017 | task_id | T3 | T2 | needs_review → needs_review |
| R017 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R018 | experiment_id | E4 | E2 | verified → verified |
| R018 | config_id | C8 | C4 | verified → verified |
| R018 | dataset_id | DS3 | DS1 | verified → verified |
| R018 | task_id | T1 | T2 | verified → verified |
| R018 | metric_unit |  | fraction | verified → verified |
| R018 | normalized_unit |  | fraction | verified → verified |
| R018 | metric_direction |  | higher_is_better | verified → verified |
| R019 | task_id | T1 | T2 | verified → verified |
| R019 | metric_unit |  | fraction | verified → verified |
| R019 | normalized_unit |  | fraction | verified → verified |
| R019 | metric_direction |  | higher_is_better | verified → verified |
| R020 | experiment_id | E4 | E2 | verified → verified |
| R020 | config_id | C8 | C4 | verified → verified |
| R020 | dataset_id | DS3 | DS1 | verified → verified |
| R020 | task_id | T1 | T2 | verified → verified |
| R020 | metric_name | F1 | F1 delta | verified → verified |
| R020 | metric_variant | difference relative to BM25 | difference vs BM25 | verified → verified |
| R021 | experiment_id | E4 | E2 | needs_review → needs_review |
| R021 | config_id | C7 | C3 | needs_review → needs_review |
| R021 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R021 | task_id | T1 | T2 | needs_review → needs_review |
| R021 | metric_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R021 | normalized_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R021 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R021 | sample_size |  | 250 | needs_review → needs_review |
| R021 | duplicate_of |  | R005 | needs_review → needs_review |
| R021 | source_fragment | Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. | Figure 1: Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. 0.584 BM25 0.612 Dense | needs_review → needs_review |
| R022 | experiment_id | E4 | E2 | needs_review → needs_review |
| R022 | config_id | C8 | C4 | needs_review → needs_review |
| R022 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R022 | task_id | T1 | T2 | needs_review → needs_review |
| R022 | metric_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R022 | normalized_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R022 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R022 | sample_size |  | 250 | needs_review → needs_review |
| R022 | duplicate_of |  | R009 | needs_review → needs_review |
| R022 | source_fragment | Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. | Figure 1: Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. 0.584 BM25 0.612 Dense | needs_review → needs_review |
| R023 | experiment_id | E4 | E2 | needs_review → needs_review |
| R023 | config_id | C9 | C5 | needs_review → needs_review |
| R023 | dataset_id | DS3 | DS1 | needs_review → needs_review |
| R023 | task_id | T1 | T2 | needs_review → needs_review |
| R023 | metric_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R023 | normalized_unit | fraction (0-1 scale) | fraction | needs_review → needs_review |
| R023 | metric_direction |  | higher_is_better | needs_review → needs_review |
| R023 | sample_size |  | 250 | needs_review → needs_review |
| R023 | duplicate_of |  | R013 | needs_review → needs_review |
| R023 | source_fragment | Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. | Figure 1: Exact Match by configuration. Values printed above bars are fractions on the 0-1 scale. 0.584 BM25 0.612 Dense | needs_review → needs_review |

**issues**: было 17 → стало 18  
  - добавлено: `contradiction` R010;R018 — F1: в тексте 0.668 (с. 4), в Table 2 0.684 (с. 3) для одной конфигурации/набора  
  - уточнено: `ocr_uncertainty` R006 — Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы; название метрики OCR прочитал как «FA», принято F1 по тексту статьи (с. 2, 4)  
  - уточнено: `ocr_uncertainty` R010 — Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы; название метрики OCR прочитал как «FA», принято F1 по тексту статьи (с. 2, 4)  
  - уточнено: `ocr_uncertainty` R014 — Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы; название метрики OCR прочитал как «FA», принято F1 по тексту статьи (с. 2, 4)  

Статусы значений: было {'verified': 7, 'needs_review': 16, 'flagged': 0} → стало {'verified': 7, 'needs_review': 16, 'flagged': 0}

## TEST_RAG_CLEAN_01

**configurations**: было 9 (C1, C2, C3, C4, C5, C6, C7, C8, C9) → стало 4 (C3, C4, C5, C9)  
  - C3: merged mentions C1, C6; also referred to as: BM25 configuration  
  - C4: merged mentions C2, C7; also referred to as: dense configuration  
  - C5: merged mentions C8  
**datasets**: было 2 (DS1, DS2) → стало 1 (DS1)  
**tasks**: было 2 (T1, T2) → стало 1 (T2)  
  - T2: merged mentions T1; also referred to as: question answering  
**experiments**: было 5 (E1, E2, E3, E4, E5) → стало 2 (E3, E5)  
  - E3: merged mentions E1, E2, E4; also referred to as: Evaluated test subset of 250 English questions sampled from the 1000-question test split; Exact Match and token-level F1 are fractions on the 0-1 scale; Recall@k and nDCG@  

**results** (только изменившиеся поля):

| id | поле | было | стало | статус было → стало |
|---|---|---|---|---|
| R001 | experiment_id | E1 | E3 | verified → verified |
| R001 | config_id | C1 | C3 | verified → verified |
| R001 | task_id | T1 | T2 | verified → verified |
| R001 | metric_name | Exact Match | EM | verified → verified |
| R001 | metric_unit |  | fraction | verified → verified |
| R001 | normalized_unit |  | fraction | verified → verified |
| R001 | metric_direction |  | higher_is_better | verified → verified |
| R001 | duplicate_of |  | R005 | verified → verified |
| R002 | experiment_id | E1 | E3 | verified → verified |
| R002 | config_id | C2 | C4 | verified → verified |
| R002 | task_id | T1 | T2 | verified → verified |
| R002 | metric_name | Exact Match | EM | verified → verified |
| R002 | metric_unit |  | fraction | verified → verified |
| R002 | normalized_unit |  | fraction | verified → verified |
| R002 | metric_direction |  | higher_is_better | verified → verified |
| R002 | duplicate_of |  | R009 | verified → verified |
| R003 | metric_direction |  | lower_is_better | verified → verified |
| R004 | metric_direction |  | lower_is_better | verified → verified |
| R005 | experiment_id | E4 | E3 | verified → verified |
| R005 | config_id | C6 | C3 | verified → verified |
| R005 | dataset_id | DS2 | DS1 | verified → verified |
| R005 | task_id | T1 | T2 | verified → verified |
| R005 | metric_direction |  | higher_is_better | verified → verified |
| R005 | sample_size |  | 250 | verified → verified |
| R006 | experiment_id | E4 | E3 | verified → verified |
| R006 | config_id | C6 | C3 | verified → verified |
| R006 | dataset_id | DS2 | DS1 | verified → verified |
| R006 | task_id | T1 | T2 | verified → verified |
| R006 | metric_direction |  | higher_is_better | verified → verified |
| R007 | experiment_id | E4 | E3 | verified → verified |
| R007 | config_id | C6 | C3 | verified → verified |
| R007 | dataset_id | DS2 | DS1 | verified → verified |
| R007 | task_id | T1 | T2 | verified → verified |
| R007 | metric_direction |  | higher_is_better | verified → verified |
| R008 | experiment_id | E4 | E3 | verified → verified |
| R008 | config_id | C6 | C3 | verified → verified |
| R008 | dataset_id | DS2 | DS1 | verified → verified |
| R008 | task_id | T1 | T2 | verified → verified |
| R008 | metric_direction |  | higher_is_better | verified → verified |
| R009 | experiment_id | E4 | E3 | verified → verified |
| R009 | config_id | C7 | C4 | verified → verified |
| R009 | dataset_id | DS2 | DS1 | verified → verified |
| R009 | task_id | T1 | T2 | verified → verified |
| R009 | metric_direction |  | higher_is_better | verified → verified |
| R009 | sample_size |  | 250 | verified → verified |
| R010 | experiment_id | E4 | E3 | verified → verified |
| R010 | config_id | C7 | C4 | verified → verified |
| R010 | dataset_id | DS2 | DS1 | verified → verified |
| R010 | task_id | T1 | T2 | verified → verified |
| R010 | metric_direction |  | higher_is_better | verified → verified |
| R011 | experiment_id | E4 | E3 | verified → verified |
| R011 | config_id | C7 | C4 | verified → verified |
| R011 | dataset_id | DS2 | DS1 | verified → verified |
| R011 | task_id | T1 | T2 | verified → verified |
| R011 | metric_direction |  | higher_is_better | verified → verified |
| R012 | experiment_id | E4 | E3 | verified → verified |
| R012 | config_id | C7 | C4 | verified → verified |
| R012 | dataset_id | DS2 | DS1 | verified → verified |
| R012 | task_id | T1 | T2 | verified → verified |
| R012 | metric_direction |  | higher_is_better | verified → verified |
| R013 | experiment_id | E4 | E3 | verified → verified |
| R013 | config_id | C8 | C5 | verified → verified |
| R013 | dataset_id | DS2 | DS1 | verified → verified |
| R013 | task_id | T1 | T2 | verified → verified |
| R013 | metric_direction |  | higher_is_better | verified → verified |
| R014 | experiment_id | E4 | E3 | verified → verified |
| R014 | config_id | C8 | C5 | verified → verified |
| R014 | dataset_id | DS2 | DS1 | verified → verified |
| R014 | task_id | T1 | T2 | verified → verified |
| R014 | metric_direction |  | higher_is_better | verified → verified |
| R015 | experiment_id | E4 | E3 | verified → verified |
| R015 | config_id | C8 | C5 | verified → verified |
| R015 | dataset_id | DS2 | DS1 | verified → verified |
| R015 | task_id | T1 | T2 | verified → verified |
| R015 | metric_direction |  | higher_is_better | verified → verified |
| R016 | experiment_id | E4 | E3 | verified → verified |
| R016 | config_id | C8 | C5 | verified → verified |
| R016 | dataset_id | DS2 | DS1 | verified → verified |
| R016 | task_id | T1 | T2 | verified → verified |
| R016 | metric_direction |  | higher_is_better | verified → verified |
| R017 | experiment_id | E4 | E3 | verified → verified |
| R017 | dataset_id | DS2 | DS1 | verified → verified |
| R017 | task_id | T1 | T2 | verified → verified |
| R017 | metric_direction |  | higher_is_better | verified → verified |
| R018 | experiment_id | E4 | E3 | needs_review → verified |
| R018 | dataset_id | DS2 | DS1 | needs_review → verified |
| R018 | task_id | T1 | T2 | needs_review → verified |
| R018 | metric_direction |  | higher_is_better | needs_review → verified |
| R018 | source_fragment | obtains Recall@10 = | With 3 passages, a sensitivity variant obtains Recall@3 = 0.728; with 10 passages, another variant obtains Recall@10 = 0 | needs_review → verified |
| R019 | task_id | T1 | T2 | verified → verified |
| R019 | metric_direction |  | higher_is_better | verified → verified |

**issues**: было 0 → стало 0  

Статусы значений: было {'verified': 18, 'needs_review': 1, 'flagged': 0} → стало {'verified': 19, 'needs_review': 0, 'flagged': 0}
