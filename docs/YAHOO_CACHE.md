> ⚠️ **Stav: historické, částečně neaktuální.** Mechanismus keše existuje, ale
> sémantika „čerstvosti" byla přepsána poté, co audit našel neúspěšné načtení
> zalogované jako čerstvé. Aktuální: [`OPERATIONS.md`](OPERATIONS.md) sekce Market data.

# Yahoo Finance Smart Cache - Dokumentace

## 🎯 Účel

Inteligentní wrapper pro Yahoo Finance API s minimalizací API calls podle Gomes pravidel.

## 🧠 GOMES PRAVIDLA

1. **Market zavřený** (víkend/po zavíračce) → Vrací cache, NEvolá API
2. **Market otevřený** → Aktualizuje každých **15 minut**
3. **Fundamentální data** → Max **1x týdně**
4. **Financial data** → Max **1x čtvrtletí**
5. **Manual refresh** → Vždy refresh (ignoruje cache)

## 📊 Databázová struktura

### Tabulka: `yahoo_finance_cache`

Ukládá cached data z Yahoo Finance:

- **Market Data**: `current_price`, `volume`, `day_low`, `day_high`
- **Fundamental Data**: `market_cap`, `pe_ratio`, `dividend_yield`, `beta`
- **Financial Data**: `revenue_ttm`, `net_income_ttm`, `total_cash`, `total_debt`
- **Timestamps**: `market_data_updated`, `fundamental_data_updated`, `financial_data_updated`

### Tabulka: `yahoo_refresh_log`

Audit log všech API calls pro monitoring rate limits.

## 🚀 API Endpointy

### 1. GET Stock Data (Smart Cache)

```http
POST /api/yahoo/stock
Content-Type: application/json

{
  "ticker": "AAPL",
  "data_types": ["market"],
  "force_refresh": false
}
```

**Response:**
```json
{
  "ticker": "AAPL",
  "current_price": 150.25,
  "market_cap": 2450000000000,
  "pe_ratio": 28.5,
  "company_name": "Apple Inc.",
  "last_updated": "2026-01-27T10:30:00Z",
  "from_cache": true,
  "market_status": {
    "is_open": true,
    "current_time_est": "2026-01-27 10:30:00 EST"
  }
}
```

### 2. Manual Refresh Button

```http
POST /api/yahoo/manual-refresh/AAPL?data_types=all
```

Force refresh pro Manual Refresh tlačítko v UI.

**⚠️ RATE LIMITING**: Frontend musí mít cooldown (1x za minutu)!

### 3. Bulk Refresh (Cron Job)

```http
POST /api/yahoo/bulk-refresh
Content-Type: application/json

{
  "tickers": ["AAPL", "GOOGL", "MSFT", "KUYAF"],
  "data_types": ["all"],
  "force": false
}
```

Pro noční update celého watchlistu.

### 4. Cache Status (Debug)

```http
GET /api/yahoo/cache-status/AAPL
```

**Response:**
```json
{
  "ticker": "AAPL",
  "exists": true,
  "market_data_age_minutes": 8.5,
  "fundamental_data_age_days": 2,
  "financial_data_age_days": 15,
  "error_count": 0
}
```

### 5. Market Status

```http
GET /api/yahoo/market-status
```

Zkontroluje jestli je NYSE otevřená.

## 🔧 Použití v kódu

### Python Service

```python
from app.services.yahoo_cache import YahooFinanceCache
from app.database.connection import get_db

db = next(get_db())
cache = YahooFinanceCache(db)

# Get data with smart caching
data = cache.get_stock_data("AAPL", force_refresh=False)
print(f"Price: ${data['current_price']}")

# Bulk refresh for watchlist
results = cache.bulk_refresh(
    tickers=["AAPL", "GOOGL", "MSFT"],
    data_types=["market"],
    force=False
)
print(f"Success: {sum(results.values())}/{len(results)}")
```

### Market Hours Check

```python
from app.core.market_hours import is_market_open, should_refresh_market_data

# Check if market is open
if is_market_open():
    print("NYSE je otevřená")
else:
    print("NYSE je zavřená")

# Decide if refresh needed
should_refresh, reason = should_refresh_market_data(last_updated)
if should_refresh:
    print(f"Refreshing: {reason}")
```

## 📅 NYSE Market Hours

- **Regular Hours**: 9:30 AM - 4:00 PM EST
- **Pre-Market**: 4:00 AM - 9:30 AM EST (připraveno pro budoucí rozšíření)
- **After-Hours**: 4:00 PM - 8:00 PM EST (připraveno pro budoucí rozšíření)
- **Víkendy**: Zavřeno
- **Státní svátky 2026**: Implementováno v `market_hours.py`

## 🎯 Scénáře použití

### Scénář 1: Otevření aplikace v pondělí 10:00 EST

```
1. Frontend načte portfolio
2. Pro každý ticker zavolá /api/yahoo/stock
3. Backend zkontroluje cache:
   - Market otevřený ✓
   - Data stará 2 hodiny → REFRESH
4. Zavolá Yahoo API → Uloží do cache
5. Vrátí fresh data
```

### Scénář 2: Otevření aplikace v sobotu

```
1. Frontend načte portfolio  
2. Pro každý ticker zavolá /api/yahoo/stock
3. Backend zkontroluje cache:
   - Víkend → CACHE ONLY
4. Vrátí data z pátku bez API call
5. Minimální latence, zero API calls 🎉
```

### Scénář 3: Manual Refresh Button

```
1. Uživatel klikne "Hard Refresh" na KUYAF
2. Frontend zavolá /api/yahoo/manual-refresh/KUYAF
3. Backend:
   - Ignoruje cache
   - Ignoruje market hours
   - Vždy volá Yahoo API
4. Vrátí aktuální data
```

### Scénář 4: Noční Cron Job

```
1. Cron job v 2:00 AM EST
2. Zavolá /api/yahoo/bulk-refresh
3. Data types: ["fundamental", "financial"]
4. Refreshne všechny watchlist tickers
5. Připraveno pro ráno bez API calls
```

## 🛡️ Ochrana před Rate Limiting

### Yahoo Finance limity
- **Neoficiální**: ~2000 requests/hour/IP
- **Při překročení**: Temporary IP ban (1-24h)

### Naše ochrana
1. ✅ Cache market data 15 minut během obchodování
2. ✅ O víkendech ZERO API calls
3. ✅ Fundamentální data 1x týdně
4. ✅ Manual refresh s cooldown na frontendu
5. ✅ Bulk operations v noci (mimo trading hours)
6. ✅ Error tracking v `yahoo_refresh_log`

## 📈 Monitoring

```sql
-- Kolik API calls dnes?
SELECT COUNT(*) 
FROM yahoo_refresh_log 
WHERE created_at > CURRENT_DATE;

-- Které tickers mají nejvíc chyb?
SELECT ticker, COUNT(*) as errors
FROM yahoo_refresh_log
WHERE success = false
GROUP BY ticker
ORDER BY errors DESC;

-- Průměrná doba response
SELECT AVG(duration_ms) as avg_ms
FROM yahoo_refresh_log
WHERE success = true;
```

## 🔮 Budoucí rozšíření

- [ ] Pre-market a After-hours support
- [ ] WebSocket pro real-time prices (během market hours)
- [ ] Automatické cleanup starých dat (30+ dní)
- [ ] Rate limit warnings když se blížíme k limitu
- [ ] Multiple providers (fallback na Alpha Vantage)

## 🚨 Důležité poznámky

1. **Production Ready**: Kód je připravený pro produkci
2. **RS Safe**: Minimální manuální práce, vše je automatizované
3. **Family Financial Security**: Zero tolerance pro chyby
4. **Type Safe**: Všechno má type hints a Pydantic validace
