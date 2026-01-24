"""
CSV Import Service for Broker Portfolio Uploads

Supports importing portfolio data from:
- Trading 212
- Degiro
- XTB

Clean Code Principles Applied:
- Single Responsibility: Each parser handles one broker format
- Explicit logging instead of print statements
- Type hints throughout
- Constants extracted to module level
"""

from __future__ import annotations

import logging
import re
from io import StringIO
from typing import Final

import pandas as pd

from ..models.portfolio import BrokerType
from .market_data import MarketDataService


logger = logging.getLogger(__name__)


# ==============================================================================
# ISIN to Ticker Mapping
# ==============================================================================

# Common ISIN to ticker mappings for popular stocks
ISIN_TO_TICKER: Final[dict[str, str]] = {
    # US Large Cap
    "US0378331005": "AAPL",     # Apple
    "US5949181045": "MSFT",     # Microsoft
    "US30303M1027": "META",     # Meta
    "US02079K3059": "GOOGL",    # Alphabet Class A
    "US02079K1079": "GOOG",     # Alphabet Class C
    "US0231351067": "AMZN",     # Amazon
    "US88160R1014": "TSLA",     # Tesla
    "US67066G1040": "NVDA",     # NVIDIA
    "US4592001014": "IBM",      # IBM
    "US4781601046": "JNJ",      # Johnson & Johnson
    "US46625H1005": "JPM",      # JPMorgan
    "US9311421039": "WMT",      # Walmart
    "US1912161007": "KO",       # Coca-Cola
    "US58933Y1055": "MCD",      # McDonald's
    "US2546871060": "DIS",      # Disney
    "US0846707026": "BRKB",     # Berkshire Hathaway
    "US6516391066": "NEE",      # NextEra Energy
    "US4370761029": "HD",       # Home Depot
    "US9497461015": "WFC",      # Wells Fargo
    "US0605051046": "BAC",      # Bank of America
    "US7427181091": "PG",       # Procter & Gamble
    "US7170811035": "PFE",      # Pfizer
    "US1667641005": "CVX",      # Chevron
    "US92826C8394": "VZ",       # Verizon
    "US1491231015": "CAT",      # Caterpillar
    "US0258161092": "ABBV",     # AbbVie
    "US9128291084": "V",        # Visa
    "US57636Q1040": "MA",       # Mastercard
    "US8552441094": "SBUX",     # Starbucks
    "US7181721090": "PEP",      # PepsiCo
    # European stocks
    "NL0000235190": "ASML",     # ASML
    "DE0007164600": "SAP",      # SAP
    "FR0000120321": "SANO",     # Sanofi
    "GB00B10RZP78": "ULVR",     # Unilever
    "CH0012005267": "NESN",     # Nestlé
    "DE0005140008": "DBK",      # Deutsche Bank
    "FR0000131104": "BNP",      # BNP Paribas
    "NL0011794037": "ADYEN",    # Adyen
    # Czech stocks
    "CZ0009093209": "ELECC.PR", # Elektrárny Opatovice
    "CZ0005112300": "CEZ.PR",   # ČEZ
    "CZ0008019106": "KOMEBB.PR",# Komerční banka
    # Canadian stocks
    "CA4589774021": "I9TT",     # Intermap Technologies
    "CA74880P1045": "QIPT",     # Quipt Home Medical
    # Hong Kong stocks
    "KYG6427W1042": "777",      # NetDragon Websoft
    # German stocks
    "DE000A40ZVU2": "UMD",      # UMT United Mobility
    # User portfolio specifics
    "US28531P2020": "ECOR",     # electroCore
    "US45817G2012": "IDN",      # Intellicheck
    "US4626841013": "IRIX",     # IRIDEX
    "US8321544053": "SMSI",     # Smith Micro Software
    "US8787392005": "TPCS",     # TechPrecision
    "US92827K3014": "VTSI",     # VirTra
}


def resolve_ticker_from_isin(isin: str) -> str:
    """
    Resolve ticker symbol from ISIN code.
    
    Uses local mapping only (no external API calls).
    
    Args:
        isin: ISIN code (e.g., US0378331005)
        
    Returns:
        Ticker symbol if found, otherwise returns ISIN
    """
    # Check local mapping first
    if isin in ISIN_TO_TICKER:
        return ISIN_TO_TICKER[isin]
    
    # Return ISIN as-is if we can't resolve it
    logger.debug(f"No local mapping for ISIN {isin}")
    return isin


class BrokerCSVParser:
    """
    Parser for CSV files from different brokers.
    
    Supports:
    - Trading 212: Ticker, No. of shares, Average price
    - Degiro: Symbol/ISIN, Množství, Hodnota v EUR (CZ/EN formats)
    - XTB: Symbol, Volume, Open Price
    """

    @staticmethod
    def parse_broker_csv(file_content: str, broker_type: BrokerType) -> list[dict]:
        """
        Parse CSV file based on broker type and return standardized position data.
        
        Args:
            file_content: Raw CSV file content as string
            broker_type: Type of broker (T212, DEGIRO, XTB)
            
        Returns:
            List of dicts with keys: ticker, shares_count, avg_cost, currency
            
        Raises:
            ValueError: If broker type is unsupported
        """
        logger.info(f"Parsing {broker_type} CSV, content length: {len(file_content)}")
        
        parsers = {
            BrokerType.T212: BrokerCSVParser._parse_t212,
            BrokerType.DEGIRO: BrokerCSVParser._parse_degiro,
            BrokerType.XTB: BrokerCSVParser._parse_xtb,
        }
        
        parser = parsers.get(broker_type)
        if parser is None:
            raise ValueError(f"Unsupported broker type: {broker_type}")
        
        return parser(file_content)

    # ==========================================================================
    # Trading 212 Parser
    # ==========================================================================

    @staticmethod
    def _parse_t212(content: str) -> list[dict]:
        """
        Parse Trading 212 CSV export.
        
        Expected columns: Ticker, No. of shares, Average price
        
        Args:
            content: Raw CSV content
            
        Returns:
            List of position dicts
            
        Raises:
            ValueError: If required columns are missing or parsing fails
        """
        try:
            df = pd.read_csv(StringIO(content))
            df.columns = df.columns.str.strip().str.lower()
            
            # Column mapping
            column_mapping = {
                "ticker": "ticker",
                "no. of shares": "shares_count",
                "average price": "avg_cost",
            }
            
            required_cols = ["ticker", "no. of shares", "average price"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            df = df.rename(columns=column_mapping)
            
            positions = []
            for _, row in df.iterrows():
                currency = BrokerCSVParser._extract_currency(row, df.columns, default="USD")
                
                positions.append({
                    "ticker": str(row["ticker"]).strip().upper(),
                    "shares_count": float(row["shares_count"]),
                    "avg_cost": float(row["avg_cost"]),
                    "currency": currency,
                })
            
            logger.info(f"Parsed {len(positions)} positions from Trading 212 CSV")
            return positions
            
        except Exception as e:
            raise ValueError(f"Error parsing Trading 212 CSV: {e}") from e

    # ==========================================================================
    # Degiro Parser
    # ==========================================================================

    @staticmethod
    def _parse_degiro(content: str) -> list[dict]:
        """
        Parse Degiro CSV export (supports CZ/EN formats).
        
        Handles various Degiro CSV structures:
        - Product, Symbol/ISIN, Množství, Uzavírací, Hodnota, Hodnota v EUR
        
        Args:
            content: Raw CSV content
            
        Returns:
            List of position dicts
            
        Raises:
            ValueError: If required columns are missing or parsing fails
        """
        try:
            # Try UTF-8 first (most common), fallback to latin-1
            try:
                df = pd.read_csv(StringIO(content), encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(StringIO(content), encoding="latin-1")
            logger.debug(f"Loaded Degiro CSV with {len(df)} rows")
            
            # Normalize column names
            df.columns = df.columns.str.strip().str.lower()
            logger.debug(f"Columns: {list(df.columns)}")
            
            # Skip metadata row if present
            df = BrokerCSVParser._skip_metadata_row(df)
            
            # Find required columns
            ticker_col = BrokerCSVParser._find_column(
                df.columns, ["symbol/isin", "symbol", "ticker", "isin"]
            )
            product_col = BrokerCSVParser._find_column(
                df.columns, ["product", "produkt", "name", "naam"]
            )
            quantity_col = BrokerCSVParser._find_column(
                df.columns, ["množství", "mno", "qty", "quantity", "aantal", "amount", "shares"],
                partial_match=True,
            )
            # DEGIRO: "Uzavírací" = closing price per share, "Hodnota v EUR" = total value
            # We need price per share, not total value
            price_per_share_col = BrokerCSVParser._find_column(
                df.columns, ["uzavírací", "uzav", "closing", "close price", "koers"],
                partial_match=True,
            )
            total_value_col = BrokerCSVParser._find_column(
                df.columns, ["hodnota v eur", "value in eur", "waarde in eur", "hodnota v"],
                partial_match=True,
            )
            currency_col = BrokerCSVParser._find_column(
                df.columns, ["hodnota"],
                exact_match=True,
            )
            
            # Validate required columns
            if not ticker_col:
                raise ValueError(f"Could not find ticker/symbol column. Available: {list(df.columns)}")
            if not quantity_col:
                raise ValueError(f"Could not find quantity column. Available: {list(df.columns)}")
            
            # Prefer price per share, fallback to calculating from total value
            price_col = price_per_share_col
            use_total_value = False
            if not price_col and total_value_col:
                price_col = total_value_col
                use_total_value = True
                logger.info("Using total value column - will divide by shares")
            
            if not price_col:
                raise ValueError(f"Could not find price column. Available: {list(df.columns)}")
            
            logger.debug(f"Detected columns: ticker={ticker_col}, qty={quantity_col}, price={price_col}, use_total_value={use_total_value}")
            
            # Extract currencies before renaming
            extracted_currencies = BrokerCSVParser._extract_currencies_from_column(df, currency_col)
            
            # Rename columns
            rename_map = {
                ticker_col: "ticker",
                quantity_col: "shares_count",
                price_col: "price_value",  # Could be per-share or total
            }
            if product_col:
                rename_map[product_col] = "company_name"
            df = df.rename(columns=rename_map)
            
            # Parse rows
            positions = []
            for idx, row in df.iterrows():
                position = BrokerCSVParser._parse_degiro_row(row, idx, extracted_currencies, use_total_value)
                if position:
                    positions.append(position)
            
            logger.info(f"Parsed {len(positions)} positions from Degiro CSV")
            return positions
            
        except Exception as e:
            raise ValueError(f"Error parsing Degiro CSV: {e}") from e

    @staticmethod
    def _parse_degiro_row(
        row: pd.Series,
        idx: int,
        extracted_currencies: dict[int, str],
        use_total_value: bool = False,
    ) -> dict | None:
        """Parse a single Degiro CSV row."""
        try:
            ticker_raw = str(row["ticker"]).strip().upper()
            
            # Skip empty/invalid tickers or cash positions
            if not ticker_raw or ticker_raw == "NAN" or pd.isna(ticker_raw):
                return None
            
            # Get company name from Produkt column
            company_name = str(row.get("company_name", "")).strip()
            if company_name.lower() == "nan" or not company_name:
                company_name = None
            
            # Skip cash positions
            if company_name and "CASH" in company_name.upper():
                return None
            
            # DEGIRO format: Could be "AEHR | US00760J1088" or just "US00760J1088"
            if "|" in ticker_raw:
                parts = ticker_raw.split("|")
                symbol_part = parts[0].strip()
                isin_part = parts[1].strip() if len(parts) > 1 else ""
                ticker_raw = symbol_part if symbol_part else isin_part
            
            # Try to resolve ISIN to ticker using company name
            ticker = ticker_raw
            if MarketDataService._is_isin(ticker_raw) and company_name:
                # Try to get ticker from company name
                resolved = MarketDataService.resolve_ticker_by_name(company_name)
                if resolved:
                    ticker = resolved
                    logger.debug(f"Resolved {ticker_raw} -> {ticker} via company name '{company_name}'")
            
            # Handle Czech number format (comma as decimal separator)
            shares_str = str(row["shares_count"]).replace(",", ".").strip()
            price_str = str(row["price_value"]).replace(",", ".").strip()
            
            # Remove currency prefix/suffix (e.g., "$ 28.04" or "28.76 EUR")
            price_str = price_str.replace("$", "").replace("€", "").replace("£", "").strip()
            price_parts = price_str.split()
            if len(price_parts) > 1:
                # Could be "28.76 EUR" or "EUR 28.76"
                for part in price_parts:
                    try:
                        price_str = part.replace(",", ".")
                        float(price_str)
                        break
                    except ValueError:
                        continue
            
            shares = float(shares_str)
            price_value = float(price_str)
            
            # If using total value column, calculate per-share price
            if use_total_value and shares > 0:
                avg_cost = price_value / shares
                logger.debug(f"Row {idx}: total_value={price_value}, shares={shares}, avg_cost={avg_cost:.4f}")
            else:
                avg_cost = price_value
            
            # Determine currency (prefer extracted, fallback to column, then USD)
            currency = extracted_currencies.get(idx, "USD")
            if "currency" in row and not currency:
                currency_val = str(row["currency"]).strip().upper()
                if currency_val and currency_val != "NAN" and not pd.isna(currency_val):
                    currency = currency_val
            
            logger.info(f"Parsed: {ticker} ({company_name}), {shares} shares @ {avg_cost:.2f} {currency}")
            
            return {
                "ticker": ticker,
                "shares_count": shares,
                "avg_cost": avg_cost,
                "currency": currency,
                "company_name": company_name,
            }
        except (ValueError, KeyError) as e:
            logger.warning(f"Degiro row {idx} parse error: {e}")
            return None

    # ==========================================================================
    # XTB Parser
    # ==========================================================================

    @staticmethod
    def _parse_xtb(content: str) -> list[dict]:
        """
        Parse XTB CSV export.
        
        Expected columns: Symbol, Volume, Open Price
        
        Args:
            content: Raw CSV content
            
        Returns:
            List of position dicts
            
        Raises:
            ValueError: If required columns are missing or parsing fails
        """
        try:
            df = pd.read_csv(StringIO(content))
            df.columns = df.columns.str.strip().str.lower()
            
            column_mapping = {
                "symbol": "ticker",
                "volume": "shares_count",
                "open price": "avg_cost",
            }
            
            required_cols = ["symbol", "volume", "open price"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            df = df.rename(columns=column_mapping)
            
            positions = []
            for _, row in df.iterrows():
                currency = BrokerCSVParser._extract_currency(row, df.columns, default="USD")
                
                positions.append({
                    "ticker": str(row["ticker"]).strip().upper(),
                    "shares_count": float(row["shares_count"]),
                    "avg_cost": float(row["avg_cost"]),
                    "currency": currency,
                })
            
            logger.info(f"Parsed {len(positions)} positions from XTB CSV")
            return positions
            
        except Exception as e:
            raise ValueError(f"Error parsing XTB CSV: {e}") from e

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    @staticmethod
    def _find_column(
        columns: pd.Index,
        candidates: list[str],
        partial_match: bool = False,
        exact_match: bool = False,
    ) -> str | None:
        """
        Find a column by name from a list of candidates.
        
        Args:
            columns: DataFrame columns to search
            candidates: List of possible column names
            partial_match: If True, match substring
            exact_match: If True, require exact match only
            
        Returns:
            Found column name or None
        """
        for candidate in candidates:
            if exact_match:
                if candidate in columns:
                    return candidate
            elif partial_match:
                for col in columns:
                    if candidate in col.lower():
                        return col
            else:
                if candidate in columns:
                    return candidate
        return None

    @staticmethod
    def _skip_metadata_row(df: pd.DataFrame) -> pd.DataFrame:
        """Skip first row if it looks like metadata (not data)."""
        if len(df) == 0:
            return df
        
        first_row_is_data = False
        for val in df.iloc[0]:
            val_str = str(val).strip().upper()
            if val_str.startswith("ISIN") or val_str == "SYMBOL/ISIN":
                first_row_is_data = True
                break
        
        if not first_row_is_data:
            logger.debug("Skipping first row (appears to be metadata)")
            return df.iloc[1:].reset_index(drop=True)
        
        return df

    @staticmethod
    def _extract_currency(
        row: pd.Series, 
        columns: pd.Index, 
        default: str = "USD"
    ) -> str:
        """Extract currency from row, with fallback to default."""
        if "currency" in columns:
            currency_val = str(row.get("currency", default)).strip().upper()
            if currency_val and currency_val != "NAN":
                return currency_val
        return default

    @staticmethod
    def _extract_currencies_from_column(
        df: pd.DataFrame,
        currency_col: str | None,
    ) -> dict[int, str]:
        """
        Extract currency codes from a column.
        
        Args:
            df: DataFrame
            currency_col: Column name containing currency codes
            
        Returns:
            Dict mapping row index to currency code
        """
        extracted = {}
        if not currency_col or currency_col not in df.columns:
            return extracted
        
        for idx, val in df[currency_col].items():
            val_str = str(val).strip().upper()
            # Valid currency codes are 3 alphabetic characters
            if len(val_str) == 3 and val_str.isalpha():
                extracted[idx] = val_str
        
        logger.debug(f"Extracted {len(extracted)} currencies from {len(df)} rows")
        return extracted


# ==============================================================================
# Validation
# ==============================================================================

def validate_position_data(positions: list[dict]) -> list[dict]:
    """
    Validate and clean parsed position data.
    
    Filters out:
    - Empty tickers
    - Non-positive share counts
    - Non-positive costs
    
    Args:
        positions: List of position dicts
        
    Returns:
        Validated and cleaned positions
    """
    validated = []
    
    for pos in positions:
        # Skip empty tickers
        if not pos.get("ticker"):
            continue
        
        try:
            shares = float(pos["shares_count"])
            cost = float(pos["avg_cost"])
            
            if shares <= 0 or cost <= 0:
                continue
            
            currency = pos.get("currency", "USD")
            if not currency or currency == "NAN":
                currency = "USD"
            
            validated.append({
                "ticker": pos["ticker"],
                "shares_count": shares,
                "avg_cost": cost,
                "currency": currency,
                "company_name": pos.get("company_name"),  # Preserve company name
            })
        except (ValueError, TypeError):
            continue
    
    logger.info(f"Validated {len(validated)} of {len(positions)} positions")
    return validated
