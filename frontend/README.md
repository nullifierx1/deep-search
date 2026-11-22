# Веб-клиент Deep Search

Веб-клиент на React и Vite. Каталог сайтов, поиск и история доступны через [HTTP API `/api/v1`](../python_deep_search/README.md#локальный-api).

В первом терминале из корня репозитория запустите бэкенд:

```powershell
python -m python_deep_search.api --port 8765 --frontend-origin http://127.0.0.1:5173
```

Во втором терминале из корня запустите клиент:

```powershell
npm --prefix frontend ci
npm --prefix frontend run dev
```

Откройте [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite перенаправляет запросы `/api` на порт 8765. Для сборки используйте `npm --prefix frontend run build`.

Для браузерной проверки установите Python-пакет `playwright` и Chromium через `python -m playwright install chromium`. При работающем Vite запустите из корня `python -m frontend.tests.browser_smoke`. Тест поднимает отдельный API и локальный источник.

Оставшиеся задачи собраны в [TODO.md](../TODO.md).
