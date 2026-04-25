# RFID Race Timing # 
Локальное приложение для хронометража гонки с RFID-ридером Impinj Speedway R420 (встроен эмулятор для отладки)
# Что умеет приложение #
Основные пользовательские сценарии:
1. Ведение стартового листа:
   категории, участники, импорт/экспорт CSV, привязка EPC-меток.
2. Хронометраж гонки:
   массовый старт, индивидуальный старт, круги, warmup, timed mode.
3. Работа судьи:
   DNF, DSQ, штрафы, предупреждения, редактирование результата, сброс категории, новая сессия.
4. Автоматический стартовый протокол:
   очередь участников, пауза/продолжение, мультикатегорийный запуск.
5. Просмотр текущего состояния гонки:
   лента проездов, таблица результатов, таймеры категорий.
6. Генерация протоколов:
   preview, PDF, JSON sync export для одной, выбранных или всех категорий.
7. Работа с реальным RFID-ридером и режимом эмулятора.
# Быстрый старт #
Библиотеки:
  - Flask
  - sllurp
  - python-dotenv
  - WeasyPrint

Основной запуск:
```
python main.py
```
Отладка сырого потока меток:
```
python live_monitor.py
```
Минимальная ручная проверка:
1. Открываются `Судья`, `Стартовый лист`, `Настройки`, `Протокол`.
2. Ридер или эмулятор отдают метки в окно привязки EPC.
3. Масстарт и индивидуальный старт работают.
4. Start protocol создаётся, стартует, ставится на паузу и завершается.
5. Preview/PDF/JSON sync работают для одной, выбранных и всех категорий. 
# Архитектура #
- `main.py` поднимает `app_runtime`, ридер и Flask.
- `rfid_timing/app` собирает runtime и Flask endpoints.
- `rfid_timing/infra` работает с реальным ридером и эмулятором.
- `rfid_timing/domain` содержит правила обработки проездов, протоколов и race state.
- `rfid_timing/repositories` прямой доступ к данным.
- `rfid_timing/services` прикладные сценарии: старт, круги, штрафы, финиш, стартовый протокол.
- `rfid_timing/routes` Flask API для judge/settings/start list.
- `rfid_timing/static` и `rfid_timing/templates` интерфейс.
## Ключевые директории `rfid_timing`: 
### `rfid_timing/app`
| Файл | Назначение |
| --- | --- |
[rfid_timing/app/app_runtime.py] | Сборка runtime: БД, конфиг, event store, reader manager, engine, raw logger, shutdown hooks.
[rfid_timing/app/web.py] | Flask app factory, базовые публичные маршруты, регистрация judge/settings/start_list/protocol.
[rfid_timing/app/race_engine.py] | Высокоуровневый движок гонки, связывающий start/lap/finish/services.
[rfid_timing/app/judge.py] | Регистрация judge-блюпринта/маршрутов страницы судьи.
[rfid_timing/app/settings.py] | Регистрация settings-маршрутов.
[rfid_timing/app/start_list.py] | Регистрация start list-маршрутов.
### `rfid_timing/config`
| Файл | Назначение |
| --- | --- |
[rfid_timing/config/config.py] | Константы приложения: host/port, пути и значения по умолчанию. 
[rfid_timing/config/config_state.py] | Runtime-конфиг с чтением/записью настроек в рабочее хранилище. 
### `rfid_timing/database`
| Файл | Назначение |
| --- | --- |
[rfid_timing/database/database.py] | Инфраструктурный контейнер БД: соединение, транзакции, wiring repositories/services.
[rfid_timing/database/bootstrap.py] | Инициализация схемы, bootstrap БД, миграции и repair-процедуры.
[rfid_timing/database/sync_state.py] | Память runtime для sync import/export без скрытых `_last_sync_*` полей на `Database`.
### `rfid_timing/domain`
| Файл | Назначение |
| --- | --- |
[rfid_timing/domain/models.py] | Базовые модели/структуры домена.
[rfid_timing/domain/timing.py] | Утилиты расчёта времени, лимитов и форматирования времени гонки.
[rfid_timing/domain/processor.py] | Обработка сырого RFID-потока в “проезды” с окном RSSI и антидребезгом.
[rfid_timing/domain/race_service.py]| Сбор текущего состояния гонки для UI и API `/api/state`. 
[rfid_timing/domain/protocol.py] | Тонкий compatibility facade для протоколов.
[rfid_timing/domain/protocol_build.py] | Построение строк протокола, ranking/gap logic, merged/combined sections.
[rfid_timing/domain/protocol_render.py] | Подготовка HTML/PDF context и имён файлов протокола.
[rfid_timing/domain/protocol_routes.py] | Flask endpoints, request parsing, preview/PDF/JSON sync export.
### `rfid_timing/repositories` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/repositories/race.py] | Работа с гонкой/сессией: создание, закрытие, текущая активная гонка. 
[rfid_timing/repositories/category_state.py] | Состояние категорий: started/closed/started_at и связанные выборки.
[rfid_timing/repositories/categories.py] | CRUD категорий и выборки по ним.
[rfid_timing/repositories/riders.py] | CRUD участников и поиск по ним.
[rfid_timing/repositories/results.py] | Результаты гонки: старт, финиш, статус, выборки по категории/участнику.
[rfid_timing/repositories/laps.py] | Круги: запись, редактирование, удаление, пересчёт и нумерация. 
[rfid_timing/repositories/penalties.py] | Штрафы и их хранение.
[rfid_timing/repositories/notes.py] | Судейские заметки по категории/гонке.
[rfid_timing/repositories/feed.py] | Лента проездов для scoreboard/judge UI.
[rfid_timing/repositories/start_protocol.py] | Хранилище очереди стартового протокола.
[rfid_timing/repositories/sync_read.py] | Чтение sync payload/runtime traces.
[rfid_timing/repositories/sync_write.py] | Запись sync import/export runtime state.
### `rfid_timing/services/results` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/services/results/finish_service.py] | Логика финиша участника и расстановки мест.
[rfid_timing/services/results/penalty_service.py] | Применение/снятие штрафов, DNF, DSQ и восстановление состояния результата.
[rfid_timing/services/results/result_state_service.py] | Восстановление и пересчёт состояния результата из кругов и текущих данных.
### `rfid_timing/services/runtime` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/services/runtime/start_service.py] | Масстарт и индивидуальный старт, проверка лимитов времени и запретов старта.
[rfid_timing/services/runtime/lap_service.py] | Обработка проезда в круг, warmup, finish, time-limit и логирование антенны/RSSI.
[rfid_timing/services/runtime/category_reset_service.py] | Сброс одной категории без полного сброса всей гонки.
### `rfid_timing/services/start_protocol` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/services/start_protocol/start_protocol_service.py] | Правила start protocol: очередь, claim/start, завершение, reconciliation.
### `rfid_timing/infra` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/infra/reader.py] | Работа с реальным Impinj/LLRP reader, raw + processed callback chain.
[rfid_timing/infra/emulator.py] | Эмулятор RFID-потока для локальной разработки и тестов.
[rfid_timing/infra/reader_manager.py]| Переключение между железом и эмулятором, restart reader по настройкам.
[rfid_timing/infra/logger.py] | CSV-логирование сырых/обработанных RFID-событий.
[rfid_timing/infra/runtime_secrets.py]| Runtime secrets/случайные ключи, если нужны приложению.
### `rfid_timing/integrations` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/integrations/event_store.py] | In-memory store последних сырых событий для `/api/events` и окна привязки EPC.
[rfid_timing/integrations/csv_import.py] | Импорт/экспорт стартового листа и участников через CSV.
[rfid_timing/integrations/sync_payload.py] | Сборка и приём JSON sync payload.
[rfid_timing/integrations/start_protocol_worker.py] | Фоновый worker автозапуска очереди стартового протокола.
### `rfid_timing/routes/judge` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/routes/judge/judge_actions.py] | Сборка judge API endpoints. 
[rfid_timing/routes/judge/judge_action_decisions.py] | Решения/валидации для judge actions.
[rfid_timing/routes/judge/judge_action_helpers.py] | Общие judge helper-функции для action endpoints. 
[rfid_timing/routes/judge/judge_action_runtime.py] | Runtime judge mutations: finish, DNF, reset, new race и другие действия судьи.
[rfid_timing/routes/judge/judge_protocol.py] | Регистрация маршрутов стартового протокола. 
[rfid_timing/routes/judge/judge_protocol_read.py] | Чтение состояния/списка start protocol для UI. 
[rfid_timing/routes/judge/judge_protocol_mutations.py] | Создание, запуск, пауза, очистка и автосбор start protocol. 
[rfid_timing/routes/judge/judge_protocol_shared.py] | Shared helpers и общие контракты для start protocol routes.
### `rfid_timing/routes/settings` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/routes/settings/settings_routes.py] | Общие endpoints страницы настроек. 
[rfid_timing/routes/settings/settings_reader_routes.py] | Настройки ридера, проверка подключения, режим reader/emulator. 
[rfid_timing/routes/settings/settings_system_routes.py] | Системные действия: бэкап, reset race, служебная информация.
### `rfid_timing/routes/start_list` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/routes/start_list/start_list_categories.py] | API категорий стартового листа.
[rfid_timing/routes/start_list/start_list_riders.py] | API участников стартового листа.
[rfid_timing/routes/start_list/start_list_validators.py] | Валидация входных данных start list API.
### `rfid_timing/http`, `security`, `utils` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/http/actions.py] | Общие HTTP action helpers.
[rfid_timing/http/request_helpers.py] | Унифицированная обработка request/response payload. 
[rfid_timing/security/auth.py] | Судейская авторизация, CSRF и auth helpers. 
[rfid_timing/security/network.py] | Сетевые проверки и ограничения безопасности.
[rfid_timing/utils/formatters.py] | Общие форматтеры строк/времени/представления данных.
## Frontend: шаблоны, CSS и JS:
### `rfid_timing/templates` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/templates/web.html] | Главный экран хронометража/scoreboard.
[rfid_timing/templates/start_list.html] | Стартовый лист, категории, участники, привязка EPC. 
[rfid_timing/templates/judge.html] | Окно судьи: действия, start protocol, таймеры категорий, лента.
[rfid_timing/templates/settings.html] | Настройки ридера, системы и обслуживания.
[rfid_timing/templates/protocol.html] | UI генератора протоколов.
[rfid_timing/templates/protocol_content.html] | Частичный шаблон содержимого протокола.
[rfid_timing/templates/protocol_pdf.html] | HTML-шаблон для PDF-рендера протокола.
### `rfid_timing/static/css` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/css/web.css] | Общая тема, переменные, базовые шрифты и глобальный layout.
[rfid_timing/static/css/home.css] | Стили стартовой/главной панели.
[rfid_timing/static/css/judge.css] | Стили judge UI.
[rfid_timing/static/css/start_list.css] | Стили start list UI.
[rfid_timing/static/css/settings.css] | Стили settings UI.
[rfid_timing/static/css/protocol.css] | Стили preview/PDF протокола.
[rfid_timing/static/css/auth.css] | Стили форм авторизации.
[rfid_timing/static/css/page-hydration.css] | Skeleton/loading-слой до гидратации страниц.
### `rfid_timing/static/js` 
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/web.js] | Главный экран, таблица результатов, лента проездов.
[rfid_timing/static/js/auth.js] | Клиентская авторизация и CSRF/auth helpers. 
[rfid_timing/static/js/theme.js] | Переключение темы.
[rfid_timing/static/js/categoryLabel.js] | Единый формат подписи категории.
### Вспомогательные подпапки
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/files/download.js] | Общий helper для скачивания файлов из браузера: PDF, JSON и других blob/download сценариев.
[rfid_timing/static/js/ui/http.js] | Базовый HTTP client фронта, унифицированные fetch/json helper-функции.
[rfid_timing/static/js/ui/auth-http.js] | HTTP helper поверх базового клиента для judge/auth-aware запросов с CSRF и auth-check логикой.
[rfid_timing/static/js/ui/toast.js] | Унифицированный показ уведомлений и ошибок во фронтенде.
[rfid_timing/static/js/ui/page-hydration.js] | Снятие skeleton/hydration-слоя после инициализации страницы.
### Start list
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/start_list.js] | Тонкий bootstrap страницы стартового листа.
[rfid_timing/static/js/startList.categories.js] | UI категорий стартового листа.
[rfid_timing/static/js/startList.riders.js] | UI участников стартового листа.
[rfid_timing/static/js/startList.importExport.js] | Импорт и экспорт CSV.
[rfid_timing/static/js/startList.tagScanner.js] | Окно привязки EPC и polling `/api/events`.
### Settings
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/settings.init.js] | Bootstrap страницы настроек.
[rfid_timing/static/js/settings.form.js] | Чтение и сохранение формы настроек.
[rfid_timing/static/js/settings.actions.js] | Действия на странице настроек. 
[rfid_timing/static/js/settings.status.js] | Статусы ридера и системы. 
[rfid_timing/static/js/settings.maintenance.js] | Backup/reset и служебные операции.
### Protocol
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/protocol.js] | Тонкий bootstrap генератора протоколов.
[rfid_timing/static/js/protocol.state.js] | Сохранение состояния страницы протокола. 
[rfid_timing/static/js/protocol.scope.js] | Scope и выбор категорий.
[rfid_timing/static/js/protocol.ui.js] | DOM-render preview.
[rfid_timing/static/js/protocol.actions.js] | Preview/PDF/JSON sync requests.
### Judge: core
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/judge.js] | Entrypoint judge-страницы. 
[rfid_timing/static/js/judge.bootstrap.js] | Инициализация judge UI и сборка модулей.
[rfid_timing/static/js/judge.api.js] | HTTP API client judge-страницы.
[rfid_timing/static/js/judge.state.js] | Judge page state. 
[rfid_timing/static/js/judge.dom.js] | DOM-рендер judge-панелей. 
[rfid_timing/static/js/judge.sync.js] Post-action sync judge UI.
[rfid_timing/static/js/judge.racePolling.js] | Polling `/api/state` и связанных judge endpoint-ов.
[rfid_timing/static/js/judge.massStart.js] | Логика масстарта в judge UI.
[rfid_timing/static/js/judge.riderPanel.js] | Панель выбранного участника. 
[rfid_timing/static/js/judge.riderSearch.js] | Поиск и выбор участника.
[rfid_timing/static/js/judge.logNotes.js] | Judge log и заметки.
### Judge actions
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/judge.actions.js] | Тонкий composition layer judge actions. 
[rfid_timing/static/js/judge.actions.helpers.js] | Общие helper-шаблоны judge actions.
[rfid_timing/static/js/judge.actions.rider.js] | Действия по участнику: DNF, DSQ, penalties, edit, warning.
[rfid_timing/static/js/judge.actions.race.js] | Race/category lifecycle actions.
[rfid_timing/static/js/judge.actions.bind.js] | Привязка кнопок и shortcut handlers.
### Judge start protocol
| Файл | Назначение |
| --- | --- |
[rfid_timing/static/js/judge.startProtocol.js] | Тонкий composition layer start protocol UI. |
[rfid_timing/static/js/judge.startProtocol.state.js] | `spStates` и их восстановление. |
[rfid_timing/static/js/judge.startProtocol.scope.js] | Scope и target resolution start protocol. |
[rfid_timing/static/js/judge.startProtocol.queue.js] | Очередь, planned entries и pending detection.
[rfid_timing/static/js/judge.startProtocol.ui.js] | Рендер очереди и countdown.
[rfid_timing/static/js/judge.startProtocol.actions.js] | Generate/run/pause/resume/remove/manual actions.
[rfid_timing/static/js/judge.startProtocol.runtime.js] | Runtime helpers автозапуска и countdown tick.
