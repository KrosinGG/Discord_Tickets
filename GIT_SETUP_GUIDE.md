# 🚀 Инструкция по настройке Git и подключению к GitHub на новом ПК

Эта инструкция описывает шаги для настройки Git, привязки SSH-ключа к GitHub и первой выгрузки проекта `Discord_Tickets`.

---

## Вариант 1: Подключение через SSH (Рекомендуемый)

### Шаг 1. Настройка имени и email в Git
Откройте PowerShell и выполните команды (замените данные на ваши):
```powershell
git config --global user.name "KrosinGG"
git config --global user.email "ваш_email_от_github@example.com"
```

### Шаг 2. Генерация нового SSH-ключа
Выполните команду для создания современного ed25519 ключа:
```powershell
ssh-keygen -t ed25519 -C "ваш_email_от_github@example.com"
```
- На запрос `Enter file in which to save the key...` нажмите **Enter** (сохранить по умолчанию в `~/.ssh/id_ed25519`).
- На запрос `Enter passphrase...` можно нажать **Enter** дважды (без пароля) или задать кодовую фразу для дополнительной защиты.

### Шаг 3. Копирование открытого (публичного) ключа
Выведите содержимое открытого ключа в терминал:
```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```
Выделите и скопируйте всю выведенную строку (начинается с `ssh-ed25519 AAAA...`).

### Шаг 4. Добавление ключа в GitHub
1. Перейдите в браузере в настройки GitHub: [github.com/settings/keys](https://github.com/settings/keys)
2. Нажмите зеленую кнопку **New SSH key**.
3. В поле **Title** введите название ПК (например: `Work PC Windows`).
4. В поле **Key type** оставьте `Authentication Key`.
5. В поле **Key** вставьте скопированную строку.
6. Нажмите **Add SSH key** и подтвердите паролем GitHub при необходимости.

### Шаг 5. Проверка соединения
В PowerShell выполните:
```powershell
ssh -T git@github.com
```
- При первом подключении появится вопрос: `Are you sure you want to continue connecting (yes/no/[fingerprint])?` — введите **yes** и нажмите **Enter**.
- Ответ должен содержать: `Hi KrosinGG! You've successfully authenticated...`.

---

## Вариант 2: Подключение через HTTPS (Personal Access Token)

Если вы предпочитаете HTTPS вместо SSH:
1. Создайте токен доступа: [github.com/settings/tokens](https://github.com/settings/tokens) (Generate new token classic $\to$ выберите область `repo`).
2. Скопируйте сгенерированный токен (`ghp_...`).
3. При первом `git push` Git for Windows откроет окно авторизации (GitHub Login), где можно войти через браузер либо указать токен.

---

## Шаг 6. Инициализация и отправка проекта на GitHub

После того как проект собран и протестирован:
```powershell
cd C:\Discord_Tickets

# Инициализация репозитория (если еще не инициализирован)
git init

# Привязка удаленного репозитория (SSH)
git remote add origin git@github.com:KrosinGG/Discord_Tickets.git

# (Или для HTTPS: git remote add origin https://github.com/KrosinGG/Discord_Tickets.git)

# Переключение на основную ветку
git branch -M main

# Индексация файлов (с учетом .gitignore)
git add .

# Первый коммит
git commit -m "feat: initial commit - Apple Wallet pkpass to Pixel-Perfect PDF Discord bot"

# Пуш в удаленный репозиторий
git push -u origin main
```
