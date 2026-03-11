import logging
from typing import Dict, Any, Optional

try:
    import yfinance as yf
except ImportError:
    import os
    os.system("pip install yfinance")
    import yfinance as yf

logger = logging.getLogger(__name__)

class MarketDataService:
    @staticmethod
    def _format_ticker(symbol: str, asset_type: str = "crypto") -> str:
        """
        Convert to yfinance ticker format.
        Binance crypto: BTCUSDT -> BTC-USD
        Stocks: AAPL -> AAPL
        """
        symbol = symbol.upper()
        if asset_type.lower() == "crypto":
            if symbol.endswith("USDT"):
                return symbol[:-4] + "-USD"
            if symbol.endswith("USD"):
                return symbol[:-3] + "-USD"
            return symbol + "-USD"
        return symbol

    async def get_market_context(self, symbol: str, asset_type: str = "crypto") -> Dict[str, Any]:
        """
        Fetch recent price context, info, and basic tech stats via yfinance.
        """
        yf_ticker = self._format_ticker(symbol, asset_type)
        logger.info(f"Fetching market context for {yf_ticker} (original: {symbol})")
        
        try:
            ticker = yf.Ticker(yf_ticker)
            # Fetch last 5 days of data
            hist = ticker.history(period="5d")
            
            if hist.empty:
                logger.warning(f"No history found for {yf_ticker}")
                return {"error": f"No data found for symbol {yf_ticker}"}
            
            latest_row = hist.iloc[-1]
            close_price = latest_row["Close"]
            
            # Simple momentum calculation over 5 days
            first_row = hist.iloc[0]
            momentum_5d_pct = ((close_price - first_row["Close"]) / first_row["Close"]) * 100
            
            # Additional basic info (often empty for smaller cryptos, but good for stocks/majors)
            info = ticker.info
            
            return {
                "symbol": yf_ticker,
                "current_price": float(close_price),
                "high_5d": float(hist["High"].max()),
                "low_5d": float(hist["Low"].min()),
                "momentum_5d_pct": round(float(momentum_5d_pct), 2),
                "volume_latest": int(latest_row["Volume"]),
                "market_state": "Open" if not hist.empty else "Unknown",
                "sector": info.get("sector", "N/A"),
                "short_name": info.get("shortName", yf_ticker),
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch market data for {yf_ticker}: {e}")
            return {"error": str(e)}
