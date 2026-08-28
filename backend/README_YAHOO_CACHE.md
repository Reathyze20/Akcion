> ⚠️ **Stav: historické, částečně neaktuální.** Viz `../docs/YAHOO_CACHE.md` pro
> stejnou poznámku a `../docs/OPERATIONS.md` pro aktuální chování.

# 🚀 Yahoo Finance Smart Cache - Quick Start

## ✅ Co bylo implementováno

1. **Database migrace** - `yahoo_finance_cache` a `yahoo_refresh_log` tabulky
2. **Market Hours Helper** - NYSE obchodní hodiny s detekcí svátků
3. **Smart Cache Service** - Inteligentní cachování podle Gomes pravidel
4. **API Endpoints** - REST API pro přístup k datům
5. **Documentation** - Kompletní dokumentace v `docs/YAHOO_CACHE.md`
6. **Tests** - Test suite v `tests/test_yahoo_cache.py`

## 🎯 Jak to použít

### 1. V Pythonu (Backend Services)

```python
from app.services.yahoo_cache import YahooFinanceCache
from app.database.connection import get_db

# Get database session
db = next(get_db())

# Create cache instance
cache = YahooFinanceCache(db)

# Get stock data with smart caching
data = cache.get_stock_data("AAPL", force_refresh=False)

print(f"Price: ${data['current_price']}")
print(f"Market Cap: ${data['market_cap']:,}")
print(f"P/E Ratio: {data['pe_ratio']}")
```

### 2. V Frontendu (React/TypeScript)

```typescript
// Get stock data with smart caching
const response = await fetch('http://localhost:8002/api/yahoo/stock', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    ticker: 'AAPL',
    force_refresh: false
  })
});

const data = await response.json();
console.log(`Price: $${data.current_price}`);
console.log(`From cache: ${data.from_cache}`);
```

### 3. Manual Refresh Button

```typescript
// User clicks "Hard Refresh" button
async function handleManualRefresh(ticker: string) {
  const response = await fetch(
    `http://localhost:8002/api/yahoo/manual-refresh/${ticker}?data_types=all`,
    { method: 'POST' }
  );
  
  const data = await response.json();
  console.log('Refreshed data:', data);
}
```

### 4. Bulk Refresh (Cron Job)

```python
# Run nightly at 2 AM EST
from app.services.yahoo_cache import YahooFinanceCache

cache = YahooFinanceCache(db)

# Get all watchlist tickers
tickers = ["AAPL", "GOOGL", "MSFT", "KUYAF", "BCHT", ...]

# Bulk refresh fundamental + financial data
results = cache.bulk_refresh(
    tickers=tickers,
    data_types=["fundamental", "financial"],
    force=False
)

print(f"Success: {sum(results.values())}/{len(results)}")
```

## 🧪 Testování

### Spustit testy

```bash
# Všechny testy
pytest tests/test_yahoo_cache.py -v

# Pouze unit testy (bez DB)
pytest tests/test_yahoo_cache.py -v -m "not integration and not api"

# Integration testy (s DB)
pytest tests/test_yahoo_cache.py -v -m integration

# API testy
pytest tests/test_yahoo_cache.py -v -m api
```

### Manuální test endpointů

```powershell
# Market status
curl http://localhost:8002/api/yahoo/market-status

# Get stock data
curl -X POST http://localhost:8002/api/yahoo/stock `
  -H "Content-Type: application/json" `
  -d '{"ticker":"AAPL","force_refresh":false}'

# Manual refresh
curl -X POST "http://localhost:8002/api/yahoo/manual-refresh/AAPL?data_types=all"

# Cache status
curl http://localhost:8002/api/yahoo/cache-status/AAPL

# Bulk refresh
curl -X POST http://localhost:8002/api/yahoo/bulk-refresh `
  -H "Content-Type: application/json" `
  -d '{"tickers":["AAPL","GOOGL","MSFT"],"force":false}'
```

## 📊 Monitoring

```sql
-- Zkontrolovat cached data
SELECT ticker, current_price, market_cap, last_updated, error_count
FROM yahoo_finance_cache
ORDER BY last_updated DESC;

-- Audit log API calls
SELECT ticker, refresh_type, success, duration_ms, created_at
FROM yahoo_refresh_log
ORDER BY created_at DESC
LIMIT 20;

-- Statistiky úspěšnosti
SELECT 
    ticker,
    COUNT(*) as total_calls,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
    AVG(duration_ms) as avg_duration_ms
FROM yahoo_refresh_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY ticker
ORDER BY total_calls DESC;
```

## ⚠️ Důležité poznámky

### Yahoo Finance Rate Limiting

Yahoo blokuje IP při příliš častých requestech:
- **Limit**: ~2000 requests/hour/IP (neoficiální)
- **Blok**: 1-24 hodin

**Naše ochrana:**
- ✅ Cache 15 minut během market hours
- ✅ O víkendech ZERO API calls
- ✅ Fundamentals 1x týdně
- ✅ Frontend cooldown na manual refresh

### O víkendech

```typescript
// Sunday 10:00 EST
const data = await getStockData('AAPL', false);

// from_cache: true
// API calls: 0 ✅
// Latence: <10ms ⚡
```

### Během obchodování

```typescript
// Tuesday 10:00 EST - první call
const data1 = await getStockData('AAPL', false);
// API call: YES (cache empty)

// Tuesday 10:10 EST - druhý call (10 min later)
const data2 = await getStockData('AAPL', false);
// API call: NO (cache fresh <15 min) ✅

// Tuesday 10:20 EST - třetí call (20 min later)
const data3 = await getStockData('AAPL', false);
// API call: YES (cache stale >15 min)
```

## 🎨 Frontend Integration

### Market Status Indicator

```typescript
interface MarketStatus {
  is_open: boolean;
  current_time_est: string;
  is_weekend: boolean;
  is_holiday: boolean;
  weekday: string;
}

function MarketStatusBadge() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  
  useEffect(() => {
    fetch('http://localhost:8002/api/yahoo/market-status')
      .then(r => r.json())
      .then(setStatus);
  }, []);
  
  if (!status) return null;
  
  return (
    <div className={status.is_open ? 'bg-green-500' : 'bg-red-500'}>
      {status.is_open ? '🟢 Market OPEN' : '🔴 Market CLOSED'}
      <div className="text-xs">{status.current_time_est}</div>
    </div>
  );
}
```

### Manual Refresh Button

```typescript
function StockCard({ ticker }: { ticker: string }) {
  const [loading, setLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  
  const handleRefresh = async () => {
    // Cooldown protection (1 minute)
    if (lastRefresh && Date.now() - lastRefresh.getTime() < 60000) {
      alert('Please wait 1 minute between refreshes');
      return;
    }
    
    setLoading(true);
    try {
      const res = await fetch(
        `http://localhost:8002/api/yahoo/manual-refresh/${ticker}?data_types=all`,
        { method: 'POST' }
      );
      const data = await res.json();
      // Update UI...
      setLastRefresh(new Date());
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <button onClick={handleRefresh} disabled={loading}>
      {loading ? '⏳ Refreshing...' : '🔄 Refresh'}
    </button>
  );
}
```

## 📚 Další dokumentace

- **Kompletní spec**: `docs/YAHOO_CACHE.md`
- **API dokumentace**: `http://localhost:8002/api/docs`
- **Tests**: `tests/test_yahoo_cache.py`
- **Migration**: `migrations/add_yahoo_cache.sql`

## 🔮 Budoucí rozšíření

- [ ] WebSocket pro real-time updates
- [ ] Pre-market a After-hours support
- [ ] Fallback na Alpha Vantage při Yahoo rate limit
- [ ] Automatic cleanup job (30+ dní old data)
- [ ] Rate limit warning system
- [ ] Redis cache layer pro ultra-fast reads

---

**Status**: ✅ Production Ready  
**RS Safe**: ✅ Minimální manuální práce  
**Type Safe**: ✅ Full type hints  
**Tested**: ✅ Test suite připravena
