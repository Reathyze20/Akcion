> ⚠️ **Stav: historické, neaktuální.** Dokumentuje neexistující proměnné
> `SMTP_FROM_EMAIL`/`SMTP_TO_EMAIL` (zjištěno, že appce trvale rozbíjejí
> `NotificationService.from_env()`), port 8000 a systemd jednotku, která se nikdy
> nepoužívala. Aktuální: [`OPERATIONS.md`](OPERATIONS.md) sekce Notifications.

# Notification System - Documentation

# =====================================

## Přehled

**Notification Service** posílá real-time alerty přes **Telegram** a **Email** když Master Signal překročí nastavený threshold (default 80%).

---

## Supported Channels

### 1. Telegram Bot

**Výhody:**

- ✅ Okamžité push notifikace
- ✅ Funguje na mobilu i desktopu
- ✅ Jednoduché nastavení
- ✅ Zdarma

### 2. Email (SMTP)

**Výhody:**

- ✅ HTML formátování
- ✅ Univerzální (každý má email)
- ✅ Historie v inboxu
- ✅ Podpora attachmentů (budoucí feature)

---

## Setup

### Telegram Bot Setup

1. **Vytvořte bota**:

   - Otevřete Telegram
   - Najděte `@BotFather`
   - Pošlete `/newbot`
   - Následujte instrukce
   - Zkopírujte **bot token**

2. **Získejte Chat ID**:

   - Začněte konverzaci s vaším botem
   - Pošlete mu jakoukoliv zprávu
   - Otevřete: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Najděte `"chat":{"id": 123456789}` v JSONu
   - Zkopírujte **chat ID**

3. **Nastavte environment variables**:

```bash
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### Email (Gmail) Setup

1. **Zapněte 2FA** v Google účtu

2. **Vytvořte App Password**:

   - Jděte na [Google Account Security](https://myaccount.google.com/security)
   - "2-Step Verification" → "App passwords"
   - Vygenerujte nový password pro "Mail"
   - Zkopírujte 16-znakový kód

3. **Nastavte environment variables**:

```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password-16-chars
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_TO_EMAIL=alerts@yourdomain.com
```

### Alert Settings

```bash
# Check interval v minutách (default: 30)
ALERT_CHECK_INTERVAL=30

# Minimum buy confidence pro alert (default: 80%)
ALERT_MIN_CONFIDENCE=80
```

---

## Usage

### Manuální Test Alert

```python
from app.services.notifications import NotificationService, Alert

service = NotificationService.from_env()

alert = Alert(
    ticker="AAPL",
    buy_confidence=85.5,
    signal_strength="STRONG",
    entry_price=175.50,
    target_price=192.00,
    stop_loss=168.00,
    kelly_size=0.15,
    message="Master Signal detected strong opportunity"
)

await service.send_alert(alert)
```

### Automatický Background Scheduler

Spusťte scheduler, který pravidelně kontroluje opportunities:

```bash
# Spustit jako proces
python -m app.services.alert_scheduler

# Nebo na pozadí (Windows PowerShell)
Start-Process python -ArgumentList "-m","app.services.alert_scheduler" -WindowStyle Hidden

# Linux/Mac (systemd nebo nohup)
nohup python -m app.services.alert_scheduler &
```

Scheduler:

- ✅ Kontroluje každých 30 minut (konfigurovatelné)
- ✅ Jen během market hours (9 AM - 4 PM)
- ✅ Posílá alerts pro všechny tickery s confidence > 80%
- ✅ Auto-retry při chybě

---

## API Endpoints

### 1. Test Alert

```http
POST /api/notifications/test-alert
```

**Request:**

```json
{
  "ticker": "AAPL",
  "buy_confidence": 85.0,
  "entry_price": 175.5,
  "target_price": 192.0,
  "stop_loss": 168.0
}
```

**Response:**

```json
{
  "ticker": "AAPL",
  "buy_confidence": 85.0,
  "signal_strength": "STRONG",
  "message": "This is a test alert...",
  "channels_notified": {
    "TelegramChannel": true,
    "EmailChannel": true
  }
}
```

### 2. Check Opportunities

Manuálně trigger alert check:

```http
POST /api/notifications/check-opportunities?min_confidence=80
```

**Response:**

```json
{
  "alerts_sent": 3,
  "min_confidence": 80.0,
  "tickers": ["AAPL", "MSFT", "GOOGL"]
}
```

### 3. Status

Zkontrolujte, které channels jsou configured:

```http
GET /api/notifications/status
```

**Response:**

```json
{
  "telegram": {
    "configured": true,
    "enabled": true
  },
  "email": {
    "configured": true,
    "enabled": true
  },
  "total_channels": 2
}
```

---

## Message Formats

### Telegram Message

```
🚀 AAPL - STRONG

Buy Confidence: 85.5%

💰 Entry: $175.50
🎯 Target: $192.00
🛑 Stop Loss: $168.00
📊 Position Size: 15.0%

Master Signal detected strong opportunity in AAPL
```

### Email Message

HTML email s tabulkou:

| Field             | Value           |
| ----------------- | --------------- |
| **Entry Price**   | $175.50         |
| **Target Price**  | $192.00 (green) |
| **Stop Loss**     | $168.00 (red)   |
| **Position Size** | 15.0%           |

---

## systemd Service (Linux)

Pro produkční deployment vytvořte systemd service:

```ini
# /etc/systemd/system/akcion-alerts.service

[Unit]
Description=Akcion Trading Alert Scheduler
After=network.target

[Service]
Type=simple
User=akcion
WorkingDirectory=/opt/akcion/backend
Environment="PATH=/opt/akcion/venv/bin"
ExecStart=/opt/akcion/venv/bin/python -m app.services.alert_scheduler
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Aktivace:

```bash
sudo systemctl daemon-reload
sudo systemctl enable akcion-alerts
sudo systemctl start akcion-alerts
sudo systemctl status akcion-alerts
```

---

## Windows Task Scheduler

1. Otevřete Task Scheduler
2. Create Basic Task:
   - **Name**: Akcion Alert Scheduler
   - **Trigger**: At startup
   - **Action**: Start a program
   - **Program**: `python.exe`
   - **Arguments**: `-m app.services.alert_scheduler`
   - **Start in**: `C:\Users\...\Akcion\backend`
3. Settings:
   - ✅ Run whether user is logged on or not
   - ✅ Run with highest privileges
   - ✅ If task fails, restart every 1 minute

---

## Custom Notification Channels

Přidejte vlastní channel (např. Discord, Slack):

```python
from app.services.notifications import NotificationChannel, Alert

class DiscordChannel(NotificationChannel):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        import httpx

        payload = {
            "content": f"🚀 **{alert.ticker}** - {alert.buy_confidence:.1f}%",
            "embeds": [{
                "title": alert.signal_strength,
                "description": alert.message,
                "color": 5814783  # Green
            }]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.webhook_url, json=payload)
            return response.status_code == 204

# Usage
from app.services.notifications import NotificationService

service = NotificationService()
service.add_channel(DiscordChannel(webhook_url="..."))
```

---

## Troubleshooting

### Telegram: "Unauthorized"

- ❌ Bot token je špatně
- ✅ Zkontrolujte token v `.env`
- ✅ Použijte `@BotFather` pro verify

### Telegram: "Chat not found"

- ❌ Chat ID je špatně nebo bot nemá permission
- ✅ Pošlete zprávu botovi první
- ✅ Zkontrolujte chat ID přes `/getUpdates`

### Email: "Authentication failed"

- ❌ App password je špatně
- ✅ Vygenerujte nový App Password v Google
- ✅ Používejte 16-char kód bez mezer

### Email: "Connection refused"

- ❌ SMTP server/port je špatně
- ✅ Gmail: `smtp.gmail.com:587`
- ✅ Outlook: `smtp.office365.com:587`

### Alerts se neposílají

1. Zkontrolujte, že scheduler běží:

```bash
ps aux | grep alert_scheduler  # Linux
Get-Process | Where-Object {$_.ProcessName -like "*python*"}  # Windows
```

2. Zkontrolujte logy:

```bash
tail -f /var/log/akcion/alerts.log  # Linux
Get-Content alerts.log -Tail 50 -Wait  # Windows
```

3. Zkontrolujte market hours:

```python
from app.services.alert_scheduler import is_market_hours
print(is_market_hours())  # Should be True during 9 AM - 4 PM
```

---

## Best Practices

1. **Testujte před produkčním použitím**:

```bash
curl -X POST http://localhost:8000/api/notifications/test-alert \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","buy_confidence":85}'
```

2. **Nastavte rozumný threshold**:

   - 80%+ pro konzervativní approach
   - 75%+ pro agresivnější
   - **NIKDY < 70%** (příliš mnoho false positives)

3. **Limitujte frekvenci**:

   - Check interval minimálně 15 minut
   - Deduplikujte alerts (stejný ticker do 1 hodiny)

4. **Monitorujte rate limits**:
   - Telegram: 30 zpráv/sekundu
   - Gmail: 500 emailů/den (free tier)

---

## Changelog

### v1.0.0 (2025-01-17)

- ✅ Telegram bot support
- ✅ Email (SMTP) support
- ✅ Background scheduler
- ✅ API endpoints
- ✅ Market hours filtering
