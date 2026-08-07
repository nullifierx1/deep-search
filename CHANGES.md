# Deep Search — полная история изменений

> Хронология диалога: запросы пользователя → проблемы → решения.

---

## 1. «Добавь обработку получения полного пути — не добавлять search, а получать готовый путь»

**Проблема:** для некоторых сайтов URL поиска не строится по шаблону `{base}/search?q={query}` — он уже готовый.

**Решение:**
- `config.py`: поле `use_full_path` (bool). Если `true` — `search_template` используется как есть, подставляется только `{query}`. Если `false` — старое поведение с `{base}`.
- `search_engine.py`: ветка в `search_site()` — `search_url = template.format(query=...)` вместо `_build_search_url`.
- `sites.json`: переведён на двухуровневый формат (`base_url`, `search_template`, `use_full_path`).
- Доп. параметры `params` (dict/string) — добавляются к URL через `_append_params()`.

**Файлы:** `config.py`, `search_engine.py`, `sites.json`

---

## 2. «Сделай удобный Makefile — запуск через консоль и GUI»

**Проблема:** нет единого способа запуска.

**Решение:**
- `make gui` — графический интерфейс
- `make cli QUERY="..."` — CLI с настраиваемыми опциями (REGEX, SITES, FOLLOW_LIMIT, VERBOSE, ...)
- `make cli-open`, `make cli-no-follow`, `make cli-no-playwright`
- `make help` — справка

**Файлы:** `Makefile`

---

## 3. «Добавь path builder — строить пути по образцу из JSON и обходить их»

**Проблема:** для сайтов без поиска нужно обходить страницы подряд (пагинация).

**Решение:**
- `config.py`: `_normalize_path_builder()` — парсит `pattern` (с `{n}`), `start`, `end`, `step`.
- `search_engine.py`: `_crawl_path_builder()` — генерирует URL, проверяет HTTP 200, извлекает контент, пауза 0.5с.
- `sites.json`: пример `example_path_builder`.

**Файлы:** `config.py`, `search_engine.py`, `sites.json`

---

## 4. «Подкрути логгер — непонятно что где валится. Логгер нужен в GUI кнопкой»

**Проблема:** логи были только `debug()` без обработчика — в консоли пусто, в GUI не видно ошибок.

**Решение:**
- `setup_logging(verbose, gui_queue)` — единая точка: stderr (INFO) + QueueHandler для GUI.
- `search_engine.py`: все `logger.debug()` → `logger.info()`: загрузка URL, HTTP-статусы, ошибки, ретраи.
- `cli.py`: флаг `--verbose` / `-v`.
- `gui.py`: панель «Логи» — кнопка-переключатель, тёмный фон, подсветка уровней, `_poll_log_queue()` каждые 250мс.

**Файлы:** `search_engine.py`, `cli.py`, `gui.py`, `models.py` (поле `verbose`)

---

## 5. «В поле Запрос можно вводить regex? Мне нужно | и [] — только их»

**Проблема:** поле «Запрос» ищет буквально, хочется `[Pp]ython | ghostepython` для вариантов.

**Решение:**
- `extractors.py`: `_query_word_to_pattern()` — экранирует всё кроме `|` и `[...]`, `-` внутри скобок восстанавливается.
- `extract_query_snippets()`: если слово содержит `[` — компилируется в regex, иначе быстрый `str.find`.

**Файлы:** `extractors.py`

---

## 6. «Поисковой запрос искажается — %5BPp%5Dython+%7C+ghostepython»

**Проблема:** `quote_plus()` URL-энкодит спецсимволы — в логах нечитаемо.

**Решение:** логи показывают читаемый запрос + URL рядом:
```
github: запрос «[Pp]ython | ghostepython» → https://github.com/search?q=...
```

**Файлы:** `search_engine.py`

---

## 7. «Почему [Pp]ython ничего не находит? Я хочу искать по всем раскрытым запросам»

**Проблема 1:** query `[Pp]ython | ghostepython` уходил поисковику как есть — GitHub не понимал скобки.
**Проблема 2:** нужно не один запрос, а по одному на каждый вариант раскрытия.

**Решение (этап 1):** `_to_search_query()` — стрипит `[]` и `|` для поисковика. Но `Ppython` — мусор.
**Решение (этап 2):** `_to_search_query()` — берёт первый символ из `[...]`, lowercase. `[Pp]ython` → `python`.
**Решение (этап 3 — финальное):** `_expand_query()` + `_expand_alternative()`:
- `[Pp]ython | ghostepython` → `['Python', 'python', 'ghostepython']` — три независимых поиска.
- `gr[ae]y` → `['gray', 'grey']` — два поиска.
- Результаты со всех запросов агрегируются, дубликаты убираются.
- `search_site()` переписан: цикл по всем expanded queries, сбор ссылок и совпадений.

**Файлы:** `search_engine.py`, `extractors.py`

---

## 8. «Почисти проект, убери мусор от недопонимания»

**Проблема:** после серии итераций остался мёртвый код.

**Исправлено:**
- `extractors.py`: убран дублирующийся `import urljoin` (был дважды).
- `extractors.py`: `_QUERY_META_RE` упрощён с `[\[\|]` до `\[` (пайп уже обрабатывается уровнем выше).
- `search_engine.py`: удалён мёртвый `_BRACKET_RE` (от выпиленной `_to_search_query`).
- `gui.py`: убран неиспользуемый `from pathlib import Path`.
- `gui.py`: починены цвета в панели логов — теги задаются один раз, а не пересоздаются на каждой строке.

**Файлы:** `extractors.py`, `search_engine.py`, `gui.py`

---

## 9. «Исправь переход по ссылкам в GUI — находит 5, а открывает 1. Сделай GUI красивее»

**Проблема 1:** `visited_urls` использовался и для дедупликации ссылок поиска, и для `follow_links`. Из-за этого follow_links **никогда не срабатывал** — все ссылки уже были в `visited_urls` и пропускались.

**Проблема 2:** `all_urls[:10]` — display-лимит маловат. `extract_links(limit=25)` — extraction-лимит тоже.

**Проблема 3:** `webbrowser.open()` вызывался в цикле без задержки — браузер открывал только первую вкладку.

**Решение:**
- `search_engine.py`: `visited_urls` разделён на `seen_links` (дедупликация) и `visited_follow` (для обхода, инициализируется только search-URL).
- `search_engine.py`: лимиты увеличены — `extract_links(limit=50)`, `all_urls[:30]`.
- `gui.py`: `_open_links()` — убран `[:3]`, открываются **все** ссылки с паузой 0.3с между вкладками.

**Рестайлинг GUI:**
- Тема `clam` через `ttk.Style`, цветовая схема (синий акцент, светлый фон).
- Моноширинный шрифт Consolas в результатах.
- Статус-бар со счётчиком ссылок и всеми кнопками.
- Тёмная панель логов с цветовой подсветкой.
- Кнопка «Логи» в статус-баре (показать/скрыть).
- ✓/✗ иконки для статуса сайтов.

**Файлы:** `search_engine.py`, `gui.py`

---

## 10. «Добавь кэширование: результаты на месяц, сохранение sites.json, логи на день»

**Проблема:** при повторном поиске всё перекачивается заново. Путь к sites.json сбрасывается при перезапуске. Логи теряются.

**Решение — `cache.py` (новый модуль):**
- **Кэш результатов** (`results_cache.json`, TTL 30 дней): хэш(query + sites) → links + matches. При повторе — мгновенная выдача без сети.
- **Сохранение настроек** (`settings.json`): `last_sites` — последний использованный sites.json. GUI и CLI подхватывают при старте.
- **Кэш логов** (`log_cache.json`, TTL 1 день, макс 500 строк): `LogCacheHandler` цепляется к корневому логгеру. GUI подгружает старые логи при запуске.
- `deep_search()`: проверка кэша перед поиском, сохранение после.
- `gui.py`: `_load_cached_logs()` при старте, `_pick_sites_file()` и `_start_search()` сохраняют путь.
- `cli.py`: авто-подхват `last_sites` если `--sites` не указан явно.

**Файлы:** `cache.py` (новый), `search_engine.py`, `gui.py`, `cli.py`

---

## 11. «С GUI вместе работать будет? Всё что в CLI должно быть и в GUI»

**Проблема:** не хватало чекбокса Verbose в GUI.

**Решение:**
- `gui.py`: добавлен `verbose_var` + чекбокс «Verbose».
- `_start_search()`: динамически меняет уровень логгера перед поиском.
- `_search_worker()`: передаёт `verbose` в `SearchRequest`.

**Файлы:** `gui.py`

---

## Итоговая структура проекта

```
python_deep_search/
├── __init__.py          # Пакет
├── models.py            # SearchMatch, SiteResult, SearchRequest
├── extractors.py        # clean_text, extract_links, extract_regex_matches, extract_query_snippets
├── config.py            # load_sites_config, normalize_base_url, _guess_search_template
├── search_engine.py     # search_site, deep_search, setup_logging, _expand_query, _crawl_path_builder
├── cache.py             # Кэш результатов, настроек, логов
├── output.py            # save_results_json, to_serializable
├── cli.py               # CLI (argparse)
├── gui.py               # GUI (Tkinter + ttk)
├── main.py              # entrypoint (--mode gui/cli)
├── sites.json           # Конфигурация сайтов (двухуровневый формат)
└── .cache/              # Кэш (не в git)
    ├── results_cache.json
    ├── settings.json
    └── log_cache.json
```

---

## Все коммиты

```
7f96bc4 Add verbose checkbox to GUI, sync CLI features with GUI
7488687 Add lazy caching: results (30d), log persistence (1d), last sites path
c728d25 Fix follow_links never firing (shared visited set), increase link limits to 30/50
1538549 Redesign GUI: modern styling, fix link opening, add log toggle button
7cdfa50 Cleanup: remove dead code, fix duplicate import, fix GUI log colors
c8e928d Query expansion: expand [...] and | to multiple literal search queries
2c6d43a Fix _to_search_query: take first char from [...], lowercase result
538d0fd Split query parsing: clean query for search engine, raw pattern for local extraction
3271394 Fix log readability: show raw query alongside encoded URL
cbcfa9c Support | and [] regex operators in query field (extract_query_snippets)
c8d330d Add path builder, structured logging (stderr + GUI panel), --verbose flag
73546f0 Update .gitignore: exclude leaked-sites.json, Next.js frontend noise
ddb194a Add package README with usage instructions
d37a774 Add CHANGES.md with full project history: v1 fixes and v2 features
32bb4d7 Add Makefile with cli/gui run targets and dev tools
205ed73 Add main launcher entrypoint with --mode gui/cli dispatch
884f08d Add Tkinter GUI with clickable links, open-in-browser buttons
e504d6d Add CLI interface with argparse, safe_print and webbrowser integration
35a9751 Add JSON results serializer with to_serializable and save_results_json
158ef89 Add site config with known templates, normalize_base_url, two-level JSON
01eaf61 Add search engine with retries, Playwright fallback, link following, session pooling
18cc62f Add HTML extraction: clean_text, link filtering, regex/query snippet matching
f4be53b Initial project structure: package init and data models
```

---

## Как пользоваться

```bash
# CLI
python -m python_deep_search.main --mode cli "запрос" --regex "шаблон" --verbose
make cli QUERY="python django" REGEX="\bclass\b" VERBOSE=1

# GUI
python -m python_deep_search.main --mode gui
make gui
```

## Требования

```bash
pip install requests playwright
playwright install chromium
```
