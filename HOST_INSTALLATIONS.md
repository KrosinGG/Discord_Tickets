# 🖥️ Реестр установленного ПО на хост-машине (Host Installations Registry)

В соответствии с правилом изоляции проекта, все сторонние библиотеки и зависимости бота устанавливаются **исключительно внутри виртуального окружения `.venv`**.

В этом документе зафиксированы системные утилиты, которые были установлены непосредственно на хост-машину (ОС Windows), их точное расположение и пошаговые инструкции по их полному удалению с компьютера.

---

## 1. Python 3.11.9 (64-bit)
- **Назначение:** Интерпретатор языка Python для создания изолированного виртуального окружения `.venv` и запуска проекта.
- **Путь установки:** `C:\Users\Vladimir Work\AppData\Local\Programs\Python\Python311\`
- **Область установки (Scope):** Текущий пользователь (`User Scope`), системные файлы Windows не затрагивались.
- **Способ установки:** Официальный инсталлятор Python 3.11.9 (`python-3.11.9-amd64.exe`).

### Как удалить Python 3.11 с компьютера:
**Вариант 1 (Через командную строку / PowerShell):**
```powershell
winget uninstall Python.Python.3.11
```
Либо через инсталлятор удаления:
```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python311\uninstall.exe" /passive
```

**Вариант 2 (Через графический интерфейс Windows):**
1. Откройте **Параметры Windows** (`Win + I`) $\to$ **Приложения** $\to$ **Установленные приложения**.
2. В поиске введите `Python 3.11`.
3. Нажмите на три точки $\to$ **Удалить**.

---

## 2. Git for Windows (v2.55.0+)
- **Назначение:** Система контроля версий для работы с репозиторием GitHub `git@github.com:KrosinGG/Discord_Tickets.git`.
- **Путь установки:** `C:\Program Files\Git\`
- **Способ установки:** Windows Package Manager (`winget install --id Git.Git`).

### Как удалить Git с компьютера:
**Вариант 1 (Через PowerShell):**
```powershell
winget uninstall Git.Git
```

**Вариант 2 (Через графический интерфейс Windows):**
1. Откройте **Параметры Windows** (`Win + I`) $\to$ **Приложения** $\to$ **Установленные приложения**.
2. Найдите **Git** в списке.
3. Нажмите **Удалить**.

---

## 3. Кэш браузеров Playwright (Chromium)
- **Назначение:** Headless-браузер Chromium, используемый библиотекой `playwright` для Pixel-Perfect рендеринга PDF-билетов.
- **Путь к кэшу бинарных файлов:** `C:\Users\Vladimir Work\AppData\Local\ms-playwright\`
- **Способ установки:** `python -m playwright install chromium`.

### Как удалить Chromium Playwright с компьютера:
**Вариант 1 (Через команду Playwright в активированном .venv):**
```powershell
.\.venv\Scripts\python.exe -m playwright uninstall --all
```

**Вариант 2 (Удаление папки кэша вручную):**
```powershell
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\ms-playwright"
```

---

## 4. Виртуальное окружение проекта (`.venv`)
- **Путь:** `C:\Discord_Tickets\.venv\`
- **Как удалить:** Просто удалите папку `.venv` внутри репозитория:
```powershell
Remove-Item -Recurse -Force "C:\Discord_Tickets\.venv"
```
После этого на ПК не останется никаких установленных python-пакетов (discord.py, jinja2, segno, playwright и др.).
