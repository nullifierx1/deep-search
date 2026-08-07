# Deep Search — контекст диалога и список изменений

## Последние изменения (v3)

### `search_engine.py` — path builder + логирование

**Path builder (`path_builder`):**
- Новый режим обхода сайтов: вместо поискового шаблона движок генерирует URL по паттерну и проходит их подряд
- Конфигурация: `pattern` (шаблон пути с `{n}`), `start`, `end`, `step`
- Подстановка `{n}` (номер страницы) и `{query}` (поисковый запрос)
- Проверка существования каждой страницы (HTTP 200)
- Пауза 0.5с между запросами

Пример JSON:
```json
"path_builder": {
  "pattern": "/catalog?page={n}&q={query}",
  "start": 1,
  "end": 10,
  "step": 1
}
```

**Логирование:**
- `setup_logging(verbose=False, gui_queue=None)` — единая точка настройки
- По умолчанию INFO-уровень в stderr: загрузка URL, HTTP-статусы, ошибки
- `--verbose` / `VERBOSE=1` → DEBUG-уровень с деталями ретраев, Playwright и т.д.
- В GUI: логи дублируются в `QueueHandler` и отображаются в панели «Логи»

### `gui.py` — панель логов

- Чекбокс «Показать логи» — открывает/скрывает текстовую панель внизу окна
- Кнопка «Очистить» — сбрасывает накопленные логи
- Логи обновляются каждые 250мс через `_poll_log_queue()`

### `cli.py` — флаг `--verbose` / `-v`

### `config.py` — парсинг `path_builder`

### `sites.json` — пример `example_path_builder`

---

## Последние изменения (v2)

### `config.py` — двухуровневый JSON с параметрами

**`use_full_path` (bool):**
- Флаг, отключающий сборку search-URL через шаблон `{base}/...?q={query}`
- Если `true`, `search_template` используется как готовый URL — подставляется только `{query}`
- Если `false` (по умолчанию) — прежнее поведение с `{base}` и `{query}`

Пример:
```json
"some_site": {
  "base_url": "https://example.com",
  "search_template": "https://example.com/results?q={query}",
  "use_full_path": true
}
```

**`params` (dict | str) — доп. query-параметры:**
- Поддерживается dict: `{"sort": "latest", "mode": "broad"}` → URL-энкодится
- Поддерживается строка: `"sort=latest&mode=broad"` или `"sort=latest, mode=broad"`
- Параметры добавляются к search_url через `&` (или `?`, если параметров ещё нет)

Пример:
```json
"github": {
  "params": { "type": "repositories", "s": "stars" }
}
// → .../search?q=query&type=repositories&s=stars
```

### `search_engine.py` — `_append_params()`

- Новая хелпер-функция `_append_params(url, params)` — добавляет параметры к URL
- Вызывается в `search_site()` после построения search_url

### `Makefile` — удобный запуск

- `make gui` — графический интерфейс
- `make cli QUERY="..."` — консольный поиск (все опции: REGEX, SITES, FOLLOW_LIMIT, ...)
- `make cli-open`, `make cli-no-follow`, `make cli-no-playwright` — варианты CLI
- `make help` — справка по всем командам

### `sites.json` — переход на двухуровневый формат

Каждый сайт теперь объект с полями `base_url`, `search_template`, `use_full_path`, `params`.

---

## Проблема (v1)

Приложение для глубокого поиска (Python) работало плохо:
1. **Regex искался в сыром HTML** (теги, скрипты, JSON), а не в читаемом тексте
2. **JS-сайты не работали** (GitHub, Reddit, Wikipedia) — requests возвращал пустой скелет
3. **Ссылки с поисковой выдачи были мусором** (CDN, навигация, футер) вместо реальных результатов
4. **Не было перехода по ссылкам** — поиск только по странице выдачи, не по целевым страницам
5. **Не было ретраев** при ошибках сети
6. **GUI не открывал ссылки в браузере**
7. **Сессия requests не переиспользовалась** между потоками
8. **URL с query-параметрами** (как `91prna` с `?keyword=asmr`) ломали шаблоны поиска

---

## Что исправлено (6 файлов)

### 1. `extractors.py` — ядро проблемы поиска

**До:** regex применялся напрямую к сырому HTML
```python
found = compiled.findall(page_html)  # HTML-теги, JS, CSS — всё попадало
```

**После:** сначала очистка текста, потом regex
```python
clean = clean_text(page_html)   # убираем script/style/теги
found = compiled.findall(clean)  # regex по чистому тексту
```

**Другие изменения в extractors.py:**
- `clean_text()` теперь вырезает `<script>`, `<style>`, `<noscript>`, `<iframe>`, `<svg>` целиком
- `extract_links()` полностью переписан:
  - Только ссылки на том же домене (отсекает CDN, Google Fonts, и т.д.)
  - Требуется минимум 2 сегмента пути (отсекает `/mcp`, `/team`, `/why-github`)
  - Блокировка 45+ не-контентных сегментов: `search`, `login`, `features`, `solutions`, `feedback`, `help`, `beta`, `resources`, `open-source`, `sponsors`, ...
  - Фильтр файловых расширений: `.css`, `.js`, `.png`, `.webmanifest`, ...
  - Фильтр Wikipedia-служебных страниц: `/w/load.php`, `/w/index.php`, `/w/api.php`
- Другие домены (до 3 штук) только если не CDN/static/assets/fonts/avatars

### 2. `search_engine.py` — движок поиска

**Playwright-фоллбек для JS-сайтов:**
- Если `requests` вернул мало текста (<1500 символов) ИЛИ мало глубоких ссылок (<5) → запускается headless Chromium через Playwright
- Параметр `use_playwright` в `SearchRequest` (CLI: `--no-playwright`)

**Переход по ссылкам (follow_links):**
- После получения поисковой выдачи, движок идёт по найденным контентным ссылкам (до `follow_limit`)
- На каждой целевой странице тоже ищет regex-совпадения и сниппеты
- Пауза 0.5с между запросами к одному сайту
- Параметры `follow_links` и `follow_limit` в `SearchRequest` (CLI: `--no-follow`, `--follow-limit`)

**Ретраи:**
- 3 попытки с задержками 1с / 3с / 5с для `ConnectionError` и `Timeout`
- 4xx ошибки (кроме 429) не ретраятся

**Общая сессия:**
- `deep_search()` создаёт один `requests.Session()` и передаёт его всем `search_site()` вызовам
- Раньше каждый вызов создавал свою сессию — не было connection pooling

### 3. `gui.py` — интерфейс (Tkinter)

- **Кликабельные ссылки** в текстовом поле: синие, подчёркнутые, при клике открываются в браузере
- Кнопки **«Открыть все ссылки»** и **«Открыть ссылки кандидатов»**
- Чекбоксы и спинбоксы для новых опций: «Переходить по ссылкам», лимит, «Playwright»

### 4. `cli.py` — консольный интерфейс

- Новые флаги: `--no-follow`, `--follow-limit N`, `--no-playwright`
- `_safe_print()` с fallback на ASCII при ошибках кодировки cp1251 (Windows)

### 5. `config.py` — конфигурация сайтов

- `normalize_base_url()` теперь обрезает query-параметры из URL (исправляет `91prna`)

### 6. `models.py` — модели данных

- `SearchRequest` получил поля: `follow_links: bool`, `follow_limit: int`, `use_playwright: bool`

---

## Результаты тестирования

### Запрос «javascript», regex `\bfunction\b`

| Сайт | Было (ссылки) | Стало (ссылки) |
|---|---|---|
| **GitHub** | `mcp`, `why-github`, `team`, `solutions/...` | `airbnb/javascript`, `TheAlgorithms/JavaScript`, `trekhleb/javascript-algorithms`, `wesbos/JavaScript30`, `GitbookIO/javascript` |
| **Reddit** | Пустой скелет (0 ссылок) | `r/PythonLearning/comments/...`, `r/programmingmemes/comments/...` (через Playwright) |
| **Wikipedia** | `load.php`, `api.php`, edit-ссылки | `wiki/Python` (через Playwright) |
| **StackOverflow** | favicon, opensearch, CDN | `beta/challenges`, `help/licensing` (требует Playwright) |

---

## Как пользоваться

```bash
# CLI с Playwright (для JS-сайтов: GitHub, Reddit, Wikipedia)
python -m python_deep_search.cli "запрос" --regex "шаблон" --follow-limit 5

# Без Playwright (быстрее, но JS-сайты не заработают)
python -m python_deep_search.cli "запрос" --no-playwright

# Без перехода по ссылкам
python -m python_deep_search.cli "запрос" --no-follow

# Свой JSON сайтов
python -m python_deep_search.cli "запрос" --sites my_sites.json

# GUI
python -m python_deep_search.main --mode gui
```

## Требования

```bash
pip install requests playwright
playwright install chromium
```
