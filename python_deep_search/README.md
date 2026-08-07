# Deep Search

Deep Search - локальный инструмент для поиска по списку сайтов. Он открывает поисковые страницы, вытаскивает ссылки первого уровня, при необходимости переходит по ним, ищет совпадения по query/regex и сохраняет результат в JSON.

Главная идея: сначала видеть исходные ссылки из поисковой выдачи сайта, а уже отдельно - то, что найдено после перехода по этим ссылкам.

## Быстрый Старт

GUI:

```bash
python -m python_deep_search.main --mode gui
```

CLI:

```bash
python -m python_deep_search.main --mode cli "search query"
```

Запуск с конкретным списком сайтов:

```bash
python -m python_deep_search.main --mode cli "search query" --sites python_deep_search/json-sites-examples/sites.json
```

Если в окружении несколько Python, используйте тот интерпретатор, в котором установлены зависимости проекта.

## Установка

Минимально:

```bash
pip install requests pytest
```

Для сайтов, где HTML собирается JavaScript:

```bash
pip install playwright
playwright install chromium
```

Опционально для более приятной темы GUI:

```bash
pip install ttkbootstrap
```

## GUI

В левой панели задаются параметры поиска:

- `Query` - поисковый запрос.
- `Regex` - необязательный regex для точного извлечения совпадений со страниц.
- `Sites JSON` - файл со списком сайтов.
- `Browser` - браузер для открытия ссылок: `chrome`, `edge`, `firefox`, `windows-default` или пусто для системного браузера.
- `Results` - максимум текстовых совпадений на сайт.
- `Links` - максимум ссылок первого уровня на сайт.
- `Timeout` - timeout HTTP-запроса.
- `Workers` - сколько сайтов обрабатывать параллельно.
- `Follow limit` - сколько search-level ссылок обходить вторым уровнем.
- `Follow links` - включить переходы по найденным ссылкам.
- `Use Playwright` - пробовать JS-rendering для сайтов со слабым HTML.
- `Use cache` - использовать кеш результатов.
- `Verbose logs` - подробные логи.

GUI запоминает последние значения полей, лимитов, чекбоксов, выбранного view, sites JSON и browser. Настройки сохраняются при запуске поиска, открытии ссылок, выборе файла и закрытии окна.

Правая часть:

- таблица показывает сайты, у которых есть search-level ссылки;
- `Search results` в деталях - исходные ссылки, найденные на странице поиска;
- `Followed pages` - результаты переходов по search-level ссылкам;
- `Open links` открывает видимые ссылки;
- `Open selected` открывает ссылки выбранного сайта;
- `Save JSON` сохраняет результаты.

Для Chrome в поле `Browser` обычно достаточно:

```text
chrome
```

Если короткое имя не найдено, можно указать полный путь:

```text
"C:\Program Files\Google\Chrome\Application\chrome.exe" %s
```

## CLI

Обычный поиск:

```bash
python -m python_deep_search.main --mode cli "postgres"
```

С regex:

```bash
python -m python_deep_search.main --mode cli "python asyncio" --regex "\basync\w*\b"
```

Открыть найденные search-level ссылки:

```bash
python -m python_deep_search.main --mode cli "needle" --open
```

Открыть ссылки в Chrome:

```bash
python -m python_deep_search.main --mode cli "needle" --open --browser chrome
```

Отключить переходы по найденным ссылкам:

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

Основные параметры:

```bash
python -m python_deep_search.main --mode cli "needle" \
  --regex "\bneedle\b" \
  --sites python_deep_search/json-sites-examples/sites.json \
  --max-results 10 \
  --max-links 100 \
  --workers 6 \
  --timeout 15 \
  --follow-limit 5 \
  --browser chrome \
  --out python_deep_search/results.json \
  --verbose
```

## Sites JSON

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
- `search_template` - шаблон поисковой страницы.
- `use_full_path` - если `true`, `search_template` считается полным URL и использует только `{query}`.
- `params` - дополнительные query-параметры.
- `path_builder` - перебор страниц без search endpoint.
- `link_rules` - правила отбора ссылок.
- `dedupe` - правила дедупликации URL.
- `follow` - настройки второго уровня обхода.

## link_rules

`link_rules` управляет тем, какие URL попадут в search-level результат.

```json
{
  "search_strict_query": true,
  "include_url_patterns": ["^https://example\\.com/articles/.+"],
  "exclude_url_patterns": ["/login", "/edit"]
}
```

- `search_strict_query`: если `true`, ссылка должна быть связана с query через URL, текст ссылки, `title`, `aria-label` или `img alt`.
- `include_url_patterns`: если список не пустой, берутся только URL, которые совпали хотя бы с одним regex.
- `exclude_url_patterns`: URL отбрасывается, если совпал хотя бы с одним regex.

### Кейс: всплывают поиски других языков

Иногда сайт отдаёт ссылки вида:

```text
https://example.com/de/search/query
https://example.com/ja/search/query
```

Не добавляйте это в `navigation_noise.json`: он работает по точному path и лучше подходит для стабильной навигации вроде `/topfiles`.

Для языковых search-страниц используйте `exclude_url_patterns` в конкретном сайте:

```json
{
  "example": {
    "base_url": "https://example.com",
    "search_template": "{base}/search/{query}",
    "link_rules": {
      "search_strict_query": true,
      "exclude_url_patterns": [
        "^https://example\\.com/(de|ja|fr|es|it|pt|zh|ru|tr)/search/"
      ]
    }
  }
}
```

Если домен может меняться:

```json
"exclude_url_patterns": [
  "^https://[^/]+/(de|ja|fr|es|it|pt|zh|ru|tr)/search/"
]
```

Если нужен только английский раздел, лучше явно разрешить нужный path:

```json
"link_rules": {
  "search_strict_query": false,
  "include_url_patterns": [
    "^https://example\\.com/en/articles/.+"
  ],
  "exclude_url_patterns": [
    "^https://example\\.com/(de|ja|fr|es|it|pt|zh|ru|tr)/"
  ]
}
```

## dedupe

`dedupe` не меняет выводимый URL. Он строит canonical key, чтобы не показывать одну и ту же страницу несколько раз.

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

Полезные случаи:

- `strip_fragment`: `/page#section` и `/page` считаются одним URL.
- `strip_www`: `www.example.com` и `example.com` считаются одним host.
- `strip_suffixes`: удобно для `.html`.
- `path_rewrites`: удобно, когда сайт отдаёт одну страницу в двух видах, например `/w/cpp/vector` и `/cpp/vector`.
- `ignore_query`: удобно, когда tracking/query параметры создают дубли.

## follow

`follow` управляет переходами по search-level ссылкам.

```json
{
  "enabled": true,
  "collect_child_links": false
}
```

- `enabled: false` - сайт не будет открывать найденные ссылки вторым уровнем, даже если глобальный `Follow links` включён.
- `collect_child_links: false` - страница будет проверяться на matches, но её внутренние ссылки не попадут в вывод.

### Кейс: сайт редиректит на шумные домены

Для таких сайтов отключайте follow на уровне сайта:

```json
{
  "noisy": {
    "base_url": "https://example.com",
    "search_template": "{base}/?search={query}",
    "follow": {
      "enabled": false,
      "collect_child_links": false
    }
  }
}
```

Так вы увидите только исходные search-level ссылки, но программа не будет переходить дальше.

## navigation_noise.json

`navigation_noise.json` - глобальный список точных path, которые считаются навигационным шумом:

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

Подходит для:

- `/login`
- `/register`
- `/topfiles`
- `/topimages`
- `/privacy`

Не подходит для:

- `/de/search/query`
- `/ja/search/query`
- сложных regex-условий;
- правил только для одного сайта.

Для таких случаев используйте `link_rules.exclude_url_patterns` внутри конкретного сайта.

После изменения фильтров запускайте поиск без кеша или выключайте `Use cache`, иначе можно увидеть старые результаты.

## Типовые Конфиги

### Bunkr-like сайт

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
    "link_rules": {
      "search_strict_query": true,
      "exclude_url_patterns": [
        "^https://[^/]+/(de|ja|fr|es|it|pt|zh|ru|tr)/search/"
      ]
    },
    "follow": {
      "enabled": false,
      "collect_child_links": false
    }
  }
}
```

### Cправочник / wiki-like сайт

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

## Query Синтаксис

Обычный запрос:

```text
python asyncio
```

Альтернативы:

```text
python | asyncio
```

Варианты символов:

```text
[Pp]ython
gr[ae]y
```

Это раскрывается в несколько буквальных запросов:

- `[Pp]ython` -> `Python`, `python`
- `gr[ae]y` -> `gray`, `grey`
- `[Pp]ython | ghostepython` -> `Python`, `python`, `ghostepython`

## Кеш

Кеш хранится в `python_deep_search/.cache/`.

- `results_cache.json` - результаты поиска.
- `settings.json` - настройки GUI, последний sites JSON, выбранный браузер.
- GUI-настройки хранятся в `settings.json` с префиксом `gui_`.
- `log_cache.json` - логи.

Отключить кеш в CLI:

```bash
python -m python_deep_search.main --mode cli "needle" --no-cache
```

В GUI выключите `Use cache`.

Очистить только результаты поиска, не трогая settings:

```bash
make clean-cache-results
```

## Makefile

Основные команды:

```bash
make gui
make cli QUERY="needle"
make cli-open QUERY="needle"
make cli-no-follow QUERY="needle"
make cli-no-playwright QUERY="needle"
make clean-cache-results
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

## Troubleshooting

### В GUI виден старый шум

Чаще всего это кеш. Выключите `Use cache` или выполните:

```bash
make clean-cache-results
```

### `navigation_noise.json` не фильтрует `/de/search/query`

Это ожидаемо: `navigation_noise.json` проверяет точные path. Для `/de/search/query` используйте `link_rules.exclude_url_patterns`.

### Слишком много дублей

Настройте `dedupe`: обычно помогают `strip_fragment`, `strip_www`, `strip_trailing_slash`, `strip_suffixes` и `path_rewrites`.

### Search-level пустой, хотя сайт что-то нашёл

Проверьте:

- не слишком ли строгий `search_strict_query`;
- нужен ли `include_url_patterns`;
- не отбрасывает ли URL `exclude_url_patterns`;
- не лежит ли старый результат в кеше.

### Сайт отдаёт пустой HTML

Установите Playwright и включите `Use Playwright`:

```bash
pip install playwright
playwright install chromium
```

### Open links не открывает Chrome

В GUI поле `Browser`:

```text
chrome
```

Если не сработало:

```text
"C:\Program Files\Google\Chrome\Application\chrome.exe" %s
```
