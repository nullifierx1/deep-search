# Deep Search

Deep Search - локальный Python-инструмент для поиска по набору сайтов. Есть GUI на Tkinter/ttk и CLI. Программа открывает поисковые страницы сайтов, извлекает исходные ссылки из выдачи, при необходимости переходит по ним, собирает совпадения по query/regex и сохраняет результат в JSON.

## Возможности

- Поиск сразу по нескольким сайтам из JSON-конфига.
- GUI-приложение с параметрами поиска, таблицей сайтов, деталями результата и логами.
- CLI для скриптового запуска.
- Поддержка обычного query и простого расширения вариантов через `|` и `[...]`.
- Regex-извлечение совпадений из страниц.
- Двухуровневый вывод:
  - `search-level links` - ссылки, найденные прямо на странице поиска сайта;
  - `followed pages` - что найдено после перехода по этим ссылкам.
- Строгая фильтрация search-level ссылок: на первом уровне остаются только ссылки, связанные с запросом.
- Фильтрация навигационного шума через редактируемый `navigation_noise.json`.
- Кеш результатов на 30 дней, кеш логов на 1 день, сохранение последнего выбранного sites JSON.
- Playwright fallback для JS-страниц, если установлен Playwright.
- Экспорт результатов в JSON.

## Быстрый Старт

В этом окружении короткие команды `python` и `python3` могут указывать не на рабочий Python. Проверенный интерпретатор:

```powershell
& "C:\Users\1\AppData\Local\Programs\Python\Python312\python.exe" -m python_deep_search.main --mode gui
```

Если PATH настроен нормально:

```bash
python -m python_deep_search.main --mode gui
```

CLI:

```powershell
& "C:\Users\1\AppData\Local\Programs\Python\Python312\python.exe" -m python_deep_search.main --mode cli "python asyncio"
```

Через Makefile:

```bash
make gui
make cli QUERY="python asyncio"
```

## Установка Зависимостей

Минимально:

```bash
pip install requests pytest
```

Для JS-страниц:

```bash
pip install playwright
playwright install chromium
```

Опционально для более приятной темы GUI:

```bash
pip install ttkbootstrap
```

Если `ttkbootstrap` установлен, GUI попробует использовать тему `flatly`. Если нет - приложение работает на стандартном `ttk`.

## GUI

Запуск:

```bash
python -m python_deep_search.main --mode gui
```

Основные элементы:

- `Query` - поисковый запрос.
- `Regex` - необязательный regex для извлечения точных совпадений.
- `Sites JSON` - файл со списком сайтов.
- `Browser` - необязательное имя браузера для открытия ссылок. Пусто = системный браузер; можно указывать `chrome`, `edge`, `firefox`, `windows-default` или полный путь вида `"C:\Program Files\Google\Chrome\Application\chrome.exe" %s`.
- `Results` - максимум совпадений на сайт.
- `Links` - максимум search-level ссылок на сайт.
- `Timeout` - timeout HTTP-запроса в секундах.
- `Workers` - число параллельных сайтов.
- `Follow limit` - сколько search-level ссылок обходить внутри одного сайта.
- `Follow links` - включить переходы по найденным search-level ссылкам.
- `Use Playwright` - использовать Playwright fallback для JS-страниц.
- `Use cache` - брать и сохранять результаты в кеш.
- `Verbose logs` - более подробные логи.

Правая часть GUI:

- Таблица показывает только сайты, у которых есть search-level ссылки.
- `Search URL` - URL поисковой страницы.
- `Search links` - сколько исходных ссылок найдено на странице поиска.
- `Followed` - сколько ссылок было обойдено.
- В деталях выбранного сайта сначала идут `Search results`, затем `Followed pages`.

## CLI

Базовый запуск:

```bash
python -m python_deep_search.main --mode cli "postgres"
```

С regex:

```bash
python -m python_deep_search.main --mode cli "python asyncio" --regex "\basync\w*\b"
```

С выбором sites JSON:

```bash
python -m python_deep_search.main --mode cli "needle" --sites python_deep_search/json-sites-examples/bunkr.json
```

Открыть найденные search-level ссылки в браузере:

```bash
python -m python_deep_search.main --mode cli "needle" --open
```

Открыть ссылки в конкретном браузере:

```bash
python -m python_deep_search.main --mode cli "needle" --open --browser firefox
```

Для Google Chrome на Windows обычно достаточно:

```bash
python -m python_deep_search.main --mode cli "needle" --open --browser chrome
```

Отключить follow:

```bash
python -m python_deep_search.main --mode cli "needle" --no-follow
```

Отключить Playwright:

```bash
python -m python_deep_search.main --mode cli "needle" --no-playwright
```

Игнорировать кеш:

```bash
python -m python_deep_search.main --mode cli "needle" --no-cache
```

Все основные параметры:

```bash
python -m python_deep_search.main --mode cli "needle" \
  --regex "\bneedle\b" \
  --sites python_deep_search/json-sites-examples/sites.json \
  --max-results 10 \
  --max-links 100 \
  --workers 6 \
  --timeout 15 \
  --follow-limit 5 \
  --browser firefox \
  --out python_deep_search/results.json \
  --verbose
```

## Формат Sites JSON

Минимальный формат:

```json
{
  "github": "https://github.com",
  "stackoverflow": "https://stackoverflow.com"
}
```

Расширенный формат:

```json
{
  "custom": {
    "base_url": "https://example.com",
    "search_template": "{base}/search?q={query}",
    "use_full_path": false,
    "params": {
      "sort": "latest"
    },
    "link_rules": {
      "search_strict_query": true,
      "include_url_patterns": [],
      "exclude_url_patterns": []
    },
    "dedupe": {
      "strip_fragment": true,
      "strip_www": false,
      "strip_trailing_slash": false,
      "strip_suffixes": [],
      "path_rewrites": [],
      "ignore_query": false,
      "lowercase_host": true,
      "lowercase_path": false
    },
    "follow": {
      "enabled": true,
      "collect_child_links": true
    }
  }
}
```

Поля:

- `base_url` - базовый URL сайта.
- `search_template` - шаблон search URL.
- `use_full_path`:
  - `false` - в шаблон можно подставлять `{base}` и `{query}`;
  - `true` - `search_template` используется как полный URL, подставляется только `{query}`.
- `params` - дополнительные query-параметры. Можно объектом или строкой.
- `path_builder` - генератор страниц без search endpoint.
- `link_rules` - правила отбора ссылок.
- `dedupe` - правила построения ключа дедупликации URL.
- `follow` - настройки второго уровня обхода.

### link_rules

```json
{
  "search_strict_query": true,
  "include_url_patterns": ["^https://example\\.com/articles/.+"],
  "exclude_url_patterns": ["/login", "/edit"]
}
```

- `search_strict_query`: если `true`, search-level берёт только ссылки, связанные с query. Для сайтов, где результаты можно надёжно определить через URL-паттерны, можно поставить `false` и использовать `include_url_patterns`.
- `include_url_patterns`: regex-список URL, которые разрешено брать.
- `exclude_url_patterns`: regex-список URL, которые нужно отбросить.

### dedupe

```json
{
  "strip_fragment": true,
  "strip_www": true,
  "strip_trailing_slash": true,
  "strip_suffixes": [".html"],
  "path_rewrites": [
    {
      "from": "^/w/(.*)$",
      "to": "/$1"
    }
  ],
  "ignore_query": true,
  "lowercase_host": true,
  "lowercase_path": false
}
```

Эти настройки не меняют выводимый URL, а только canonical key для дедупликации.

- `strip_fragment`: считать `/page#section` и `/page` одним URL.
- `strip_www`: считать `www.example.com` и `example.com` одним хостом.
- `strip_trailing_slash`: считать `/page/` и `/page` одним путём.
- `strip_suffixes`: убрать suffix из canonical key, например `.html`.
- `path_rewrites`: regex-переписывание пути перед дедупликацией.
- `ignore_query`: не учитывать query-параметры в canonical key.
- `lowercase_host`: привести host к lower-case.
- `lowercase_path`: привести path к lower-case.

### follow

```json
{
  "enabled": true,
  "collect_child_links": false
}
```

- `enabled`: если `false`, сайт не будет открывать search-level ссылки вторым уровнем даже при включённом глобальном `Follow links` / без `--no-follow`. Полезно для сайтов, которые часто редиректят на шумные или нежелательные домены.
- `collect_child_links`: если `false`, followed page всё ещё проверяется на matches, но внутренние ссылки этой страницы не попадают в вывод. Это полезно для справочников и wiki-like сайтов, где на странице много боковой навигации.

Пример Bunkr-like конфига:

```json
{
  "bunkr": {
    "base_url": "https://balbums.st",
    "search_template": "{base}/?search={query}",
    "use_full_path": false,
    "params": {
      "mode": "broad",
      "per": "100",
      "sort": "latest"
    },
    "follow": {
      "enabled": false,
      "collect_child_links": false
    }
  }
}
```

Пример cppreference-like конфига с дедупликацией:

```json
{
  "cppreference": {
    "base_url": "https://en.cppreference.com",
    "search_template": "{base}/mwiki/index.php?search={query}",
    "link_rules": {
      "search_strict_query": false,
      "include_url_patterns": [
        "^https://en\\.cppreference\\.com/w/(c|cpp)/.+",
        "^https://en\\.cppreference\\.com/(c|cpp)/.+"
      ],
      "exclude_url_patterns": [
        "/mwiki/",
        "[?&]action=",
        "/Talk:",
        "/Special:"
      ]
    },
    "dedupe": {
      "strip_fragment": true,
      "strip_www": true,
      "strip_trailing_slash": true,
      "strip_suffixes": [".html"],
      "path_rewrites": [
        {
          "from": "^/w/(.*)$",
          "to": "/$1"
        }
      ],
      "ignore_query": true
    },
    "follow": {
      "enabled": true,
      "collect_child_links": false
    }
  }
}
```

## Path Builder

Если у сайта нет поиска, но есть страницы вида `/page/1`, `/page/2`, можно использовать `path_builder`:

```json
{
  "example_path_builder": {
    "base_url": "https://example.com",
    "path_builder": {
      "pattern": "/page/{n}",
      "start": 1,
      "end": 5,
      "step": 1
    }
  }
}
```

`pattern` может содержать `{n}` и `{query}`.

## Query Синтаксис

Обычный текст:

```text
python asyncio
```

Альтернативы через `|`:

```text
python | asyncio
```

Варианты символов через `[...]`:

```text
[Pp]ython
gr[ae]y
```

Для поисковых движков такие запросы раскрываются в несколько буквальных запросов:

- `[Pp]ython` -> `Python`, `python`
- `gr[ae]y` -> `gray`, `grey`
- `[Pp]ython | ghostepython` -> `Python`, `python`, `ghostepython`

Для локального извлечения сниппетов `[...]` используется как простой regex-паттерн.

## Regex

`--regex` или поле `Regex` в GUI применяются к очищенному тексту страницы.

Пример:

```bash
python -m python_deep_search.main --mode cli "asyncio" --regex "\basync\s+def\b"
```

Пустой regex допустим и не создаёт ложных совпадений.

## Как Устроен Результат

Модель результата:

```text
SiteResult
  site_name
  base_url
  search_url
  found
  matches
  urls
  followed
  status_code
  elapsed_sec
  error
```

Главное:

- `urls` - только search-level ссылки, найденные на странице поиска.
- `followed` - результаты переходов по `urls`.
- `matches` - агрегированные совпадения по сайту.

`FollowResult`:

```text
FollowResult
  source_url
  matches
  urls
  error
```

В GUI это отображается так:

```text
Search results
  1. https://site/result-1
  2. https://site/result-2

Followed pages
  1. https://site/result-1
     match [60] ...
     link: https://site/child
```

## Фильтрация Ссылок

На search-level включается строгая фильтрация:

- ссылка должна быть связана с query;
- query ищется в URL, тексте ссылки, `title`, `aria-label`, `img alt`;
- если на search-странице есть только навигация, сайт пропускается на первом уровне.

Для всех уровней дополнительно отбрасываются:

- технические ресурсы (`.css`, `.js`, `.png`, `.svg`, `.json`, шрифты и т.п.);
- служебные wiki URL (`/w/load.php`, `/w/api.php`, `/w/index.php`);
- навигационные пути из `navigation_noise.json`.

## navigation_noise.json

Файл:

```text
python_deep_search/navigation_noise.json
```

Формат:

```json
[
  "/",
  "/live",
  "/topalbums",
  "/topfiles",
  "/topimages",
  "/topvideos"
]
```

Если в GUI или CLI появился повторяющийся навигационный шум, добавьте путь в этот список. Можно писать с `/` или без него, код нормализует путь.

Пример:

```json
[
  "/",
  "/live",
  "/topalbums",
  "/topfiles",
  "/topimages",
  "/topvideos",
  "/popular"
]
```

После изменения списка лучше запустить поиск с отключённым кешем или изменить query, потому что старые результаты могли быть сохранены.

## Кеш

Кеш хранится в:

```text
python_deep_search/.cache/
```

Файлы:

- `results_cache.json` - результаты поиска, TTL 30 дней.
- `settings.json` - настройки, включая последний выбранный sites JSON.
- `log_cache.json` - GUI/CLI логи, TTL 1 день.

Кеш-ключ учитывает:

- query;
- regex;
- лимиты;
- follow настройки;
- Playwright;
- sites config;
- schema version.

CLI: отключить кеш:

```bash
python -m python_deep_search.main --mode cli "needle" --no-cache
```

GUI: выключить `Use cache`.

## Makefile

Команды:

```bash
make gui
make cli QUERY="needle"
make cli-open QUERY="needle"
make cli-no-follow QUERY="needle"
make cli-no-playwright QUERY="needle"
make test
make help
```

Переменные:

```bash
QUERY="needle"
REGEX="\bneedle\b"
SITES="python_deep_search/json-sites-examples/sites.json"
FOLLOW_LIMIT=5
MAX_RESULTS=10
TIMEOUT=15
WORKERS=6
OUT="python_deep_search/results.json"
VERBOSE=1
```

## Структура Проекта

```text
python_deep_search/
  __init__.py
  main.py
  cli.py
  gui.py
  models.py
  search_engine.py
  extractors.py
  config.py
  cache.py
  output.py
  navigation_noise.json
  json-sites-examples/
    sites.json
    bunkr.json
    lk-sites.json
tests/
  test_cache.py
  test_cli.py
  test_extractors.py
  test_gui_links.py
  test_search_engine.py
```

## Проверка

В этом окружении:

```powershell
& "C:\Users\1\AppData\Local\Programs\Python\Python312\python.exe" -m pytest
& "C:\Users\1\AppData\Local\Programs\Python\Python312\python.exe" -m compileall -q python_deep_search tests
```

Если Python настроен в PATH:

```bash
python -m pytest
python -m compileall -q python_deep_search tests
```

## Troubleshooting

### `python` запускает MySQL Workbench Python

Используйте полный путь:

```powershell
& "C:\Users\1\AppData\Local\Programs\Python\Python312\python.exe" -m python_deep_search.main --mode gui
```

Или поправьте PATH так, чтобы `C:\Users\1\AppData\Local\Programs\Python\Python312\` был раньше MySQL/WindowsApps.

### `python3` ведёт в Windows Store

Это Windows App Execution Alias. Отключите alias для `python.exe` / `python3.exe` в настройках Windows или используйте полный путь к Python.

### В GUI виден старый шум

Проверьте:

- выключен ли `Use cache`;
- добавлен ли путь в `navigation_noise.json`;
- относится ли шум к search-level или к followed pages.

После изменения фильтров лучше выполнить поиск с `--no-cache` или выключенным `Use cache`.

### JS-сайт отдаёт пустую страницу

Установите Playwright:

```bash
pip install playwright
playwright install chromium
```

И не выключайте `Use Playwright`.
