import logging
from typing import Dict, Any, Optional

import httpx

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
        Fetch recent price context, info, and basic tech stats via Yahoo Finance JSON API (Vercel Safe).
        """
        yf_ticker = self._format_ticker(symbol, asset_type)
        logger.info(f"Fetching market context for {yf_ticker} (original: {symbol})")
        
        try:
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{yf_ticker}?interval=1d&range=5d"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers, timeout=10.0)
                res.raise_for_status()
                data = res.json()
            
            result = data.get("chart", {}).get("result", [])
            if not result:
                logger.warning(f"No history found for {yf_ticker}")
                return {"error": f"No data found for symbol {yf_ticker}"}
                
            chart_data = result[0]
            meta = chart_data.get("meta", {})
            indicators = chart_data.get("indicators", {}).get("quote", [{}])[0]
            
            closes = indicators.get("close", [])
            highs = indicators.get("high", [])
            lows = indicators.get("low", [])
            volumes = indicators.get("volume", [])
            
            # Filter out None values which Yahoo sometimes returns for market holidays
            valid_closes = [c for c in closes if c is not None]
            valid_highs = [h for h in highs if h is not None]
            valid_lows = [l for l in lows if l is not None]
            
            if not valid_closes:
                return {"error": f"Empty historical price data for {yf_ticker}"}
                
            close_price = valid_closes[-1]
            first_price = valid_closes[0]
            momentum_5d_pct = ((close_price - first_price) / first_price) * 100 if first_price else 0
            
            volume_latest = volumes[-1] if volumes and volumes[-1] is not None else 0
            
            return {
                "symbol": yf_ticker,
                "current_price": float(close_price),
                "high_5d": float(max(valid_highs)) if valid_highs else 0.0,
                "low_5d": float(min(valid_lows)) if valid_lows else 0.0,
                "momentum_5d_pct": round(float(momentum_5d_pct), 2),
                "volume_latest": int(volume_latest),
                "market_state": "Ready (API V8)",
                "sector": meta.get("instrumentType", "N/A"),
                "short_name": meta.get("symbol", yf_ticker),
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch market data for {yf_ticker} via httpx: {e}")
            return {"error": str(e)}
