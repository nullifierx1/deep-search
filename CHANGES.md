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

---

## 12. «На сайте десятки результатов, а программа показывает 5–7; поиск и открытие ссылок работают нестабильно»

**Выявленные причины:**
- `extract_links()` отбрасывал ссылки с одним сегментом пути (`/album-123`) и query-only URL (`/?id=123`), хотя на ряде сайтов это именно карточки результатов.
- Слишком широкий URL-фильтр исключал допустимые страницы по словам вроде `blog`, `news`, `users` и ограничивал внешние ссылки тремя.
- Ссылки резались несколькими независимыми лимитами: 10 в `path_builder`, 30 в движке, 5 при выводе CLI и 3 при открытии из CLI.
- Кэш результатов не учитывал regex, лимиты, обход ссылок и Playwright: устаревшая урезанная выдача могла повторяться 30 дней.
- GUI получал параметры Tkinter из фонового потока, клик по отдельной ссылке считывал всю строку с номером и не открывал URL, а массовое открытие блокировало UI.
- Текст запроса на самой поисковой странице (например, в заголовке «Search results for …») ошибочно засчитывался как найденное совпадение.

**Исправлено:**
- HTML-ссылки извлекаются стандартным `HTMLParser`, а не регулярным выражением; сохраняются односегментные, query-only и относительные URL. Относительные ссылки резолвятся от текущей поисковой страницы.
- Оставлена только фильтрация очевидных технических ресурсов (скрипты, стили, изображения и служебные wiki-URL); лимит ссылок стал явным параметром `max_links` (100 по умолчанию, до 500 в GUI).
- Убраны скрытые срезы 10/30/5/3: GUI и CLI показывают и открывают весь сохранённый список ссылок в рамках `max_links`.
- Каждый поток поиска использует собственный `requests.Session`, без небезопасного общего состояния.
- Ключ кэша версии 2 учитывает все параметры, влияющие на результат; в CLI есть `--no-cache`, в GUI — переключатель «Использовать кэш».
- Пустой regex теперь допустим и не создаёт бессмысленных совпадений каждого слова страницы.
- GUI считывает настройки до запуска рабочего потока; отдельные URL имеют собственные кликабельные теги. Массовое открытие дедуплицирует URL, спрашивает подтверждение при более чем 10 вкладках и выполняется в фоне через `open_new_tab`.
- Эхо запроса на поисковой странице больше не считается совпадением: сниппеты запроса извлекаются только с обходимых целевых страниц. Явный regex по поисковой странице по-прежнему поддерживается.

**Проверка:** добавлены автоматические тесты извлечения ссылок, кэша, движка поиска и пакетного открытия ссылок в GUI.

**Коммиты:**
```
7e37fd3 Fix search result link extraction
247f811 Improve search limits and cache correctness
3082b42 Fix GUI search and link opening
a15e287 Avoid false matches on search pages
```

---

## 13. «Сделай GUI пригодным как приложение и убери шум Bunkr/homepage из результатов»

**Проблемы:**
- GUI выглядел как один текстовый дамп, плохо масштабировался на ноутбуке и смешивал разные уровни результата.
- Первый уровень выдачи смешивал search-level ссылки и то, что получилось после переходов.
- Search-страницы с навигацией домашней страницы могли отдавать шум вроде `/topimages`, `/topfiles`, `/topalbums`.
- Внутри followed pages снова появлялись навигационные ссылки сайта.
- Дефолтный `sites.json` указывал на несуществующий путь.
- Клик по отдельной ссылке в GUI использовал неверный Text tag range.

**Исправлено:**
- `gui.py`: GUI переработан в двухпанельное приложение: слева параметры, справа таблица сайтов/search URL, ниже детали выбранного сайта.
- `models.py`: добавлен `FollowResult`; `SiteResult.urls` теперь хранит search-level ссылки, а `SiteResult.followed` хранит результаты переходов по ним.
- `search_engine.py`: followed pages сохраняются отдельно; `filter_candidates()` считает кандидатом только сайт с исходными search-level ссылками.
- `extractors.py`: search-level фильтрация стала строгой: если включён `prefer_query_matches`, возвращаются только ссылки, где query найден в URL, тексте ссылки, `title`, `aria-label` или `img alt`.
- `extractors.py`: навигационный шум фильтруется и на followed pages.
- `navigation_noise.json`: список навигационных путей вынесен в отдельный JSON, его можно пополнять без правки кода.
- `cache.py`: схема кеша поднята до `5`, чтобы старые зашумлённые результаты не возвращались.
- `config.py`, `cli.py`, `gui.py`, `Makefile`: дефолтный путь к sites config переведён на существующий `python_deep_search/json-sites-examples/sites.json`.
- `search_engine.py`: `setup_logging()` стал идемпотентным и корректно добавляет GUI queue handler при повторном вызове.

**Проверка:** добавлены тесты для Bunkr-like навигационного шума, query-релевантных ссылок, двухуровневого follow-вывода, дефолтного sites path и кликабельных GUI-ссылок.

**Файлы:** `gui.py`, `models.py`, `search_engine.py`, `extractors.py`, `navigation_noise.json`, `cache.py`, `config.py`, `cli.py`, `Makefile`, `tests/*`, `CHANGES.md`

---

## 14. «Проверить кейс cppreference и сделать расширяемые правила вместо hardcode»

**Проблема:** у сайтов вроде cppreference много повторяющихся ссылок на одну страницу: anchors, `.html`, `/w/...` и альтернативные формы URL. Частные правила в коде под один домен плохо масштабируются.

**Исправлено:**
- `sites.json`-формат расширен блоком `link_rules`:
  - `search_strict_query` управляет строгой привязкой search-level ссылок к query.
  - `include_url_patterns` разрешает брать только URL, подходящие под regex.
  - `exclude_url_patterns` отбрасывает служебные URL.
- Добавлен блок `dedupe`:
  - `strip_fragment`
  - `strip_www`
  - `strip_trailing_slash`
  - `strip_suffixes`
  - `path_rewrites`
  - `ignore_query`
  - `lowercase_host`
  - `lowercase_path`
- Добавлен блок `follow.collect_child_links`: можно обходить найденную страницу ради совпадений, но не выводить её внутренние ссылки.
- `extractors.py`: дедупликация теперь строится через настраиваемый canonical key без доменных hardcode-правил.
- `search_engine.py`: site-level правила передаются в извлечение search-level и followed links.
- `json-sites-examples/cppreference.json`: добавлен пример конфига для cppreference-like сайтов.
- `cache.py`: схема кеша поднята до `6`.
- `README.md`: добавлено полное руководство по новым флагам.

**Проверка:** добавлены тесты на загрузку `cppreference.json`, regex include/exclude, canonical dedupe для cppreference-like URL и `follow.collect_child_links=false`.

**Файлы:** `config.py`, `extractors.py`, `search_engine.py`, `cache.py`, `json-sites-examples/cppreference.json`, `README.md`, `tests/*`, `CHANGES.md`

---

## 15. «Проверить hardcode, добавить site-level no-follow и выбор браузера»

**Найдено при ревизии:**
- Открытие ссылок было жёстко привязано к `webbrowser.open_new_tab()` без выбора браузера.
- `follow_links` был только глобальным параметром запроса; в JSON можно было отключить вывод child links, но нельзя было запретить сам переход по search-level ссылкам для конкретного сайта.
- Search templates для популярных сайтов остаются fallback-эвристикой в `config.py`, но их можно переопределять через `search_template` в JSON.
- Навигационный шум уже вынесен в `navigation_noise.json`; site-specific дедупликация и include/exclude правила уже задаются через JSON.
- Кандидаты на будущую конфигурацию: User-Agent/headers, retry delays, пороги meaningful content, список технических/static host фильтров в `extractors.py`.

**Изменено:**
- Добавлен JSON-флаг `follow.enabled`. Если `false`, сайт не открывает найденные search-level ссылки вторым уровнем, даже когда глобальный follow включён.
- `bunkr.json` теперь показывает пример сайта с `"follow": {"enabled": false, "collect_child_links": false}` для шумных/редиректящих сайтов.
- Добавлен `browser.py` с общим helper открытия вкладок.
- CLI получил `--browser`, который работает вместе с `--open`.
- GUI получил поле `Browser`; выбранное значение сохраняется в settings cache и используется для кликов по ссылкам и массового открытия.
- Cache schema поднята до `7`, чтобы старые результаты с другим follow-поведением не всплывали из кеша.
- README обновлён под `follow.enabled`, `--browser` и GUI Browser field.

**Проверка:** добавлены тесты на `follow.enabled=false`, аргумент `--browser`, named/default browser helper и GUI bulk open с выбранным браузером.

**Файлы:** `browser.py`, `config.py`, `search_engine.py`, `cli.py`, `gui.py`, `cache.py`, `json-sites-examples/*.json`, `README.md`, `tests/*`, `CHANGES.md`

---

## 16. «Сделать короткое имя chrome рабочим для выбора браузера»

**Проблема:** на Windows `webbrowser.get("chrome")` может не находить Google Chrome, даже когда `chrome.exe` установлен в стандартном каталоге.

**Изменено:**
- `browser.py` автоматически регистрирует известные Windows-пути для `chrome` и `edge` перед открытием ссылки.
- В CLI и GUI теперь можно указывать просто `chrome`, если Chrome установлен в стандартный путь.
- README обновлён: описаны `chrome`, `edge`, `firefox`, `windows-default` и fallback через полный путь к `.exe`.

**Проверка:** добавлен тест автосрегистрации Chrome; полный набор тестов проходит.

**Файлы:** `browser.py`, `tests/test_browser.py`, `README.md`, `CHANGES.md`

---

## 17. «Исправить Open links для Chrome с путём, содержащим пробелы»

**Проблема:** `webbrowser.BackgroundBrowser("C:\\Program Files\\...\\chrome.exe %s")` воспринимал всю строку как имя executable. Из-за пробела в `Program Files` запуск Chrome падал, а GUI показывал только счётчик failed.

**Исправлено:**
- Chrome/Edge регистрируются как `BackgroundBrowser([path, "%s"])`, то есть путь к `.exe` и URL идут отдельными аргументами.
- Полный путь с placeholder тоже поддерживается: `"C:\Program Files\Google\Chrome\Application\chrome.exe" %s`.
- GUI теперь показывает `Browser error`, если массовое открытие не смогло открыть ни одной ссылки.

**Проверка:** добавлены тесты на корректную регистрацию пути с пробелами и command placeholder; реальная проверка `open_browser_tab("https://www.google.com", "chrome")` вернула `(True, None)`.

**Файлы:** `browser.py`, `gui.py`, `tests/test_browser.py`, `CHANGES.md`

---

## 18. «Немного увеличить GUI и добавить очистку result cache»

**Изменено:**
- GUI стал чуть крупнее: базовые шрифты, стартовое окно, минимальный размер, левая панель, кнопки и строки таблицы увеличены без изменения общей структуры.
- В Makefile добавлена команда `make clean-cache-results`.
- Команда удаляет только `python_deep_search/.cache/results_cache.json`, не трогая `settings.json` и `log_cache.json`.
- README обновлён списком Makefile-команд.

**Файлы:** `gui.py`, `Makefile`, `README.md`, `CHANGES.md`
