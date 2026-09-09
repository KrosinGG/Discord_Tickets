# Официальный базовый образ Playwright с предустановленным Chromium и системными библиотеками
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Установка рабочей директории
WORKDIR /app

# Отключение буферизации Python логов
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Копирование списка зависимостей
COPY requirements.txt .

# Установка Python-библиотек
RUN pip install --no-cache-dir -r requirements.txt

# Установка браузера Chromium для Playwright (если не входит в базовый слой)
RUN playwright install chromium

# Копирование исходного кода приложения
COPY . .

# Команда запуска бота
CMD ["python", "bot.py"]
