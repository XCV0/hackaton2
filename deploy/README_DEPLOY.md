# Деплой Evidence Extractor на сервер (Ubuntu 24.04)

Адрес: https://viniti.cdnvidikturbik.online — открыт для всех (без пароля, по решению владельца). HTTPS — Let's Encrypt, автопродление (certbot.timer), HTTP перенаправляется на HTTPS.

| Что | Где на сервере |
|---|---|
| Код, собранный сайт, отчёты | /opt/viniti |
| Корпус кейса | /opt/viniti/data/domain1_solar, /opt/viniti/data/domain2_rag |
| База (результаты + ключи LLM) | /opt/viniti/runs/viniti.db (права 600) |
| Python-окружение | /opt/viniti-venv |
| Сервис | systemd `viniti` (пользователь viniti, 127.0.0.1:8077) |
| nginx | /etc/nginx/sites-available/viniti |
| Claude Code CLI | /home/viniti/.local/bin/claude |

## Команды
```bash
systemctl status viniti            # состояние
journalctl -u viniti -f            # логи
systemctl restart viniti           # перезапуск
htpasswd /etc/nginx/viniti.htpasswd <имя>   # добавить/сменить пользователя сайта
sudo -u viniti -H claude           # вход в Claude Code (внутри: /login) для провайдера claude-cli
```

## Обновить код с Mac
```bash
rsync -az --exclude .git --exclude .venv --exclude frontend/node_modules --exclude data/ --exclude 'runs/viniti.db*' \
  ./ root@87.58.204.87:/opt/viniti/ && ssh root@87.58.204.87 'chown -R viniti:viniti /opt/viniti && systemctl restart viniti'
```

## Вход через релей 188.225.46.168 (HAProxy, СПб)
Чтобы сайт был доступен из любой сети, трафик идёт через релей `188.225.46.168`, где уже работает HAProxy:

```
клиент ─► 188.225.46.168:443 HAProxy (mode tcp, SNI viniti.cdnvidikturbik.online) ─► 87.58.204.87:443 nginx (TLS, свой LE-сертификат) ─► uvicorn :8077
клиент ─► 188.225.46.168:80  nginx (conf.d/viniti-acme.conf): /.well-known/acme-challenge ─► 87.58.204.87:80, остальное ─► 301 https
```
- TLS не расшифровывается на релее: браузер видит сертификат `viniti.cdnvidikturbik.online` с основного сервера.
- На релее добавлены только: маршрут `use_backend be_viniti …` + `backend be_viniti` (timeout tunnel 1h) в `/etc/haproxy/haproxy.cfg`
  (бэкап `haproxy.cfg.bak.20261122110921`) и файл `/etc/nginx/conf.d/viniti-acme.conf`. Остальные маршруты не тронуты (проверено до/после).
- DNS: A-запись `viniti` → `188.225.46.168`, в Cloudflare **DNS only** (серое облако), как у avi1–avi4.
- Продление сертификата проверено `certbot renew --dry-run` на основном сервере.

Откат на релее: `cp /etc/haproxy/haproxy.cfg.bak.20261122110921 /etc/haproxy/haproxy.cfg && rm /etc/nginx/conf.d/viniti-acme.conf && systemctl reload haproxy nginx`.
