import logging
from typing import Optional
from app.config import get_settings

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    import os
    os.system("pip install alpaca-trade-api")
    import alpaca_trade_api as tradeapi

logger = logging.getLogger(__name__)

class AlpacaService:
    def __init__(self):
        settings = get_settings().alpaca
        self.api = tradeapi.REST(
            key_id=settings.api_key if settings.api_key != "your_key_here" else "dummy",
            secret_key=settings.api_secret if settings.api_secret != "your_secret_here" else "dummy",
            base_url=settings.base_url,
            api_version='v2'
        )
        self.enabled = settings.api_key and settings.api_key != "your_key_here"
        
    def is_configured(self) -> bool:
        return self.enabled

    def get_account(self):
        if not self.enabled:
            return None
        try:
            return self.api.get_account()
        except Exception as e:
            logger.error(f"Alpaca get_account error: {e}")
            return None

    def place_order(self, symbol: str, qty: float, side: str, order_type: str = 'market',
                    time_in_force: str = 'gtc', take_profit: Optional[float] = None, 
                    stop_loss: Optional[float] = None) -> Optional[dict]:
        """
        Place an order using Alpaca API. Returns the raw order dictionary or None on failure.
        """
        if not self.enabled:
            logger.warning("Alpaca is not configured. Mocking the order placement.")
            # Return a mock order response
            return {
                "id": "mock_alpaca_id_" + symbol,
                "client_order_id": "mock_client_id",
                "status": "accepted",
                "symbol": symbol,
                "qty": str(qty),
                "side": side,
                "type": order_type
            }

        try:
            # Prepare advanced order if TP/SL provided
            order_params = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "type": order_type,
                "time_in_force": time_in_force,
            }

            if take_profit or stop_loss:
                # Need to use bracket orders or OCO if supported, but for simplicity we can use order_class='bracket'
                order_params['order_class'] = 'bracket'
                if take_profit:
                    order_params['take_profit'] = {'limit_price': take_profit}
                if stop_loss:
                    order_params['stop_loss'] = {'stop_price': stop_loss, 'limit_price': stop_loss}
            
            # Place order
            order = self.api.submit_order(**order_params)
            logger.info(f"Placed Alpaca Order: {order}")
            return order._raw

        except Exception as e:
            logger.error(f"Failed to place Alpaca order: {e}")
            return None

    def get_positions(self):
        if not self.enabled:
            return []
        try:
            positions = self.api.list_positions()
            return [p._raw for p in positions]
        except Exception as e:
            logger.error(f"Failed to get Alpaca positions: {e}")
            return []
