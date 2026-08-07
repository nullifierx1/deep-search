# Deep Search (Python)

Полная версия скрипта поиска по сайтам с:
- параллельным поиском,
- regex-парсингом,
- фильтрацией сайтов без результатов (исключение из кандидатов),
- GUI (Tkinter),
- CLI,
- загрузкой сайтов из JSON (`ключ -> URL`),
- экспортом результатов в JSON.

## Структура

- `sites.json` — список сайтов
- `config.py` — загрузка и нормализация JSON-конфига
- `extractors.py` — извлечение ссылок, regex и сниппетов
- `search_engine.py` — параллельный движок поиска
- `output.py` — сохранение результатов
- `cli.py` — командный интерфейс
- `gui.py` — графический интерфейс
- `main.py` — запуск GUI/CLI

## Формат `sites.json`

Минимальный формат (как вы просили):

```json
{
  "github": "https://github.com",
  "stackoverflow": "https://stackoverflow.com"
}
```

Дополнительно поддерживается расширенный объект:

```json
{
  "custom": {
    "base_url": "https://example.com",
    "search_template": "{base}/search?q={query}"
  }
}
```

> Если `search_template` не задан, подбирается автоматически по домену или используется fallback `{base}/search?q={query}`.

## Запуск GUI

```bash
python -m python_deep_search.main --mode gui
```

## Запуск CLI

```bash
python -m python_deep_search.main --mode cli "python asyncio" --regex "\\basync\\w*\\b" --max-results 12
```

Дополнительно:

```bash
python -m python_deep_search.main --mode cli "postgres" --open --out ./results.json
```

## Что улучшено по сравнению с исходником

1. **Сайты вынесены в JSON**
2. **Нормальная модульная архитектура**
3. **Фильтрация кандидатов**: сайты без результатов отмечаются и исключаются
4. **GUI + CLI**
5. **Экспорт результатов в JSON**
6. **Прогресс обработки**
7. **Валидация regex и обработка ошибок сети**
