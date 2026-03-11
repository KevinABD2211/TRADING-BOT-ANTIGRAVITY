import logging
import json
from typing import Optional, Dict, Any
from app.models import ParsedSignal, DirectionEnum
from app.config import get_settings
from app.services.market_data import MarketDataService

try:
    import openai
except ImportError:
    import os
    os.system("pip install openai")
    import openai

logger = logging.getLogger(__name__)

class AnalyzerService:
    def __init__(self):
        self.settings = get_settings()
        self.market_data_service = MarketDataService()
        self.client = None
        
        # Initialize OpenAI client if token exists
        if self.settings.llm.provider == "openai" and self.settings.llm.openai_api_key:
            self.client = openai.AsyncOpenAI(api_key=self.settings.llm.openai_api_key)

    async def analyze_signal(self, signal: ParsedSignal) -> Dict[str, Any]:
        """
        Takes a signal, fetches live market context, and uses an LLM to generate
        a confidence score, reasoning, timeline, and dynamic take-profit (if short).
        """
        # Default fallback response if no AI configured or fail
        fallback_response = {
            "confidence_score": 50,
            "reasoning": "AI Analysis skipped (API key missing or failed).",
            "trade_timeline": "Short-Term (1-3 Days)",
            "take_profit": float(signal.take_profit_1) if signal.take_profit_1 else None
        }

        # 1. Fetch Market Context via yfinance
        ctx = await self.market_data_service.get_market_context(
            signal.symbol, 
            asset_type=signal.asset_type.value
        )
        
        # If no client, return early with pure market data appended to reasoning
        if not self.client:
            logger.warning("No OpenAI key configured. Returning fallback analysis.")
            if "error" not in ctx:
                fallback_response["reasoning"] = f"AI Skipped. Live Market Data: 5-Day Momentum is {ctx.get('momentum_5d_pct', 0)}%. Current Price: {ctx.get('current_price', 0)}. Signal relies purely on Rule-Based logic."
            return fallback_response

        # 2. Build the LLM Prompt
        market_str = json.dumps(ctx, indent=2)
        signal_dict = {
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "entry_price": float(signal.entry_price) if signal.entry_price else None,
            "take_profit": float(signal.take_profit_1) if signal.take_profit_1 else None,
            "stop_loss": float(signal.stop_loss) if signal.stop_loss else None,
            "raw_text_source": signal.raw_text
        }

        system_msg = """
        You are an expert quantitative trading analyst for an institutional hedge fund.
        You are given a raw trading signal and the latest 5-day market context sourced from Yahoo Finance.
        Your job is to objectively evaluate the signal and return a JSON structured analysis.
        
        # INSTRUCTIONS:
        1. Evaluate the risk/reward, timeline, and current momentum of the asset.
        2. Calculate a `confidence_score` out of 100 based on the fundamental setup.
        3. Write a concise `reasoning` paragraph (2-3 sentences max) explaining *why* it's good or bad to take this trade now.
        4. Estimate a `trade_timeline` (e.g., "Intraday (1-12h)", "Swing (1-3 Days)", "Position (1+ Weeks)").
        5. CRITICAL: If the signal is a SHORT ('sell') and does NOT have a valid Take Profit, you MUST calculate and return a realistic `take_profit` price target based on recent volatility and current price. For longs with missing TP, you should also calculate it. Return null if a solid TP already exists.
        
        # REQUIRED JSON OUTPUT FORMAT:
        {
            "confidence_score": 85,
            "reasoning": "The recent 5-day momentum shows strong selling pressure...",
            "trade_timeline": "Intraday (1-12h)",
            "take_profit": 42000.50 
        }
        Return ONLY valid JSON.
        """

        user_msg = f"""
        MARKET CONTEXT (YFINANCE):
        {market_str}
        
        TRADE SIGNAL:
        {json.dumps(signal_dict, indent=2)}
        """

        # 3. Call OpenAI
        try:
            logger.info(f"Requesting AI Analysis for {signal.symbol}...")
            completion = await self.client.chat.completions.create(
                model=self.settings.llm.model_name,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=300
            )

            response_content = completion.choices[0].message.content
            ai_data = json.loads(response_content)
            
            logger.info(f"AI Analysis Complete: Score={ai_data.get('confidence_score')}")
            
            # Map standard response structure
            return {
                "confidence_score": ai_data.get("confidence_score", 50),
                "reasoning": ai_data.get("reasoning", "Analysis failed formatting."),
                "trade_timeline": ai_data.get("trade_timeline", "Unknown Timeline"),
                "take_profit": ai_data.get("take_profit", None)
            }

        except Exception as e:
            logger.error(f"OpenAI Analyzer Failed: {e}")
            return fallback_response

    async def generate_autonomous_advice(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """
        No external signal provided. Purely analyze market data and generate a 
        strong LONG or SHORT advice with strict execution parameters.
        """
        # 1. Fetch Market Context via yfinance
        ctx = await self.market_data_service.get_market_context(
            symbol, 
            asset_type=asset_type
        )
        
        if not self.client or "error" in ctx:
            logger.warning(f"Cannot generate advice for {symbol}. Missing API key or Market Data.")
            return None

        # 2. Build the LLM Prompt
        market_str = json.dumps(ctx, indent=2)

        system_msg = """
        You are an expert quantitative trading analyst for an institutional hedge fund.
        You are scanning the market autonomously based purely on live Yahoo Finance data points.
        Your job is to generate exactly ONE definitive advice (LONG or SHORT) for the asset. Do NOT stay neutral.
        
        # INSTRUCTIONS:
        1. Review the momentum and current price.
        2. Pick a "direction" (must be "long" or "short").
        3. Provide realistic targets for `entry_price` (usually near current price), `take_profit`, and `stop_loss`.
        4. Calculate a `confidence_score` (0-100) on your strict call.
        5. Write a concise `reasoning` paragraph (2-3 sentences max) explaining the trigger.
        6. Provide a `trade_timeline`.
        
        # REQUIRED JSON OUTPUT FORMAT:
        {
            "direction": "long",
            "entry_price": 2045.50,
            "take_profit": 2100.00,
            "stop_loss": 2000.00,
            "confidence_score": 88,
            "reasoning": "Strong gold momentum over the last 5 days...",
            "trade_timeline": "Swing (1-3 Days)"
        }
        Return ONLY valid JSON.
        """

        user_msg = f"""
        MARKET CONTEXT (YFINANCE):
        {market_str}
        
        ASSET:
        {symbol} ({asset_type})
        """

        # 3. Call OpenAI
        try:
            logger.info(f"Generating Autonomous Advice for {symbol}...")
            completion = await self.client.chat.completions.create(
                model=self.settings.llm.model_name,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=300
            )

            response_content = completion.choices[0].message.content
            ai_data = json.loads(response_content)
            
            logger.info(f"Autonomous Advice Generated for {symbol}: {ai_data.get('direction').upper()} (Conf={ai_data.get('confidence_score')})")
            
            return {
                "direction": ai_data.get("direction", "long").lower(),
                "entry_price": float(ai_data.get("entry_price", ctx.get("current_price"))),
                "take_profit": float(ai_data.get("take_profit", None)),
                "stop_loss": float(ai_data.get("stop_loss", None)),
                "confidence_score": ai_data.get("confidence_score", 50),
                "reasoning": ai_data.get("reasoning", "Autonomous scan completed."),
                "trade_timeline": ai_data.get("trade_timeline", "Unknown Timeline")
            }

        except Exception as e:
            logger.error(f"OpenAI Autonomous Generation Failed: {e}")
            return None
