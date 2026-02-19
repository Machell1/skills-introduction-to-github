//+------------------------------------------------------------------+
//|                                                   ClawUtils.mqh  |
//|                            CLAWBOT - Utility Functions            |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#ifndef CLAWUTILS_MQH
#define CLAWUTILS_MQH

#property copyright "CLAWBOT"
#property version   "1.00"

//+------------------------------------------------------------------+
//| Enumerations                                                      |
//+------------------------------------------------------------------+
enum ENUM_SIGNAL_TYPE
{
   SIGNAL_NONE  = 0,    // No signal
   SIGNAL_BUY   = 1,    // Buy signal
   SIGNAL_SELL  = -1    // Sell signal
};

enum ENUM_SIGNAL_STRENGTH
{
   STRENGTH_NONE   = 0,   // No signal
   STRENGTH_WEAK   = 10,  // Weak signal
   STRENGTH_MEDIUM = 25,  // Medium signal
   STRENGTH_STRONG = 40   // Strong signal
};

enum ENUM_BOT_MODE
{
   MODE_BACKTEST = 0,   // Backtesting / Audit mode
   MODE_LIVE     = 1    // Live trading mode
};

enum ENUM_SESSION
{
   SESSION_ASIAN   = 0,   // Asian session
   SESSION_LONDON  = 1,   // London session
   SESSION_NEWYORK = 2,   // New York session
   SESSION_OVERLAP = 3,   // London/NY overlap
   SESSION_OFF     = 4    // Off-hours
};

//--- Smart Money Concepts enumerations
enum ENUM_MARKET_TREND
{
   TREND_BULLISH   = 1,    // HH + HL pattern
   TREND_BEARISH   = -1,   // LH + LL pattern
   TREND_UNDEFINED = 0     // No clear structure
};

enum ENUM_MARKET_REGIME
{
   REGIME_TRENDING_STRONG    = 0,   // Strong directional move
   REGIME_TRENDING_WEAK      = 1,   // Gradual trend with pullbacks
   REGIME_RANGING            = 2,   // Consolidation / sideways
   REGIME_VOLATILE_EXPANSION = 3,   // High volatility breakout
   REGIME_TRANSITIONING      = 4    // Regime change in progress
};

enum ENUM_PRICE_ZONE
{
   ZONE_EXTREME_PREMIUM  = 0,   // > 75% of swing range (strongest sells)
   ZONE_PREMIUM          = 1,   // 62-75% (sells)
   ZONE_EQUILIBRIUM      = 2,   // 38-62% (no trade / scalp)
   ZONE_DISCOUNT         = 3,   // 25-38% (buys)
   ZONE_EXTREME_DISCOUNT = 4    // < 25% (strongest buys)
};

enum ENUM_STRUCTURE_EVENT
{
   STRUCT_NONE          = 0,
   STRUCT_BOS_BULLISH   = 1,   // Break of structure bullish (continuation)
   STRUCT_BOS_BEARISH   = 2,   // Break of structure bearish (continuation)
   STRUCT_CHOCH_BULLISH = 3,   // Change of character to bullish (reversal)
   STRUCT_CHOCH_BEARISH = 4    // Change of character to bearish (reversal)
};

//+------------------------------------------------------------------+
//| Signal result structure                                           |
//+------------------------------------------------------------------+
struct SignalResult
{
   ENUM_SIGNAL_TYPE     direction;
   ENUM_SIGNAL_STRENGTH strength;
   int                  score;
   string               reason;
   double               entryPrice;    // Suggested entry for pending order (0 = use default)
   double               suggestedTP;   // Suggested TP price (0 = use default ATR)
   double               suggestedSL;   // SMC-based SL (e.g., below OB zone) (0 = use default)
   int                  smcConfluence; // Number of SMC confluences supporting this signal

   void Reset()
   {
      direction     = SIGNAL_NONE;
      strength      = STRENGTH_NONE;
      score         = 0;
      reason        = "";
      entryPrice    = 0;
      suggestedTP   = 0;
      suggestedSL   = 0;
      smcConfluence = 0;
   }
};

//+------------------------------------------------------------------+
//| Trade statistics structure                                        |
//+------------------------------------------------------------------+
struct TradeStats
{
   int    totalTrades;
   int    winTrades;
   int    lossTrades;
   double totalProfit;
   double totalLoss;
   double grossProfit;
   double grossLoss;
   double maxDrawdown;
   double maxDrawdownPercent;
   double profitFactor;
   double winRate;
   double avgWin;
   double avgLoss;
   double expectancy;
   double sharpeRatio;
   double maxConsecWins;
   double maxConsecLosses;
   double peakBalance;

   void Reset()
   {
      totalTrades      = 0;
      winTrades        = 0;
      lossTrades       = 0;
      totalProfit      = 0;
      totalLoss        = 0;
      grossProfit      = 0;
      grossLoss        = 0;
      maxDrawdown      = 0;
      maxDrawdownPercent = 0;
      profitFactor     = 0;
      winRate          = 0;
      avgWin           = 0;
      avgLoss          = 0;
      expectancy       = 0;
      sharpeRatio      = 0;
      maxConsecWins    = 0;
      maxConsecLosses  = 0;
      peakBalance      = 0;
   }
};

//+------------------------------------------------------------------+
//| Normalize lot size to broker specifications                       |
//+------------------------------------------------------------------+
double NormalizeLot(string symbol, double lot)
{
   double minLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(lot < minLot) lot = minLot;
   if(lot > maxLot) lot = maxLot;

   lot = MathFloor(lot / lotStep) * lotStep;
   lot = NormalizeDouble(lot, 2);

   return lot;
}

//+------------------------------------------------------------------+
//| Get current trading session based on UTC time                     |
//+------------------------------------------------------------------+
ENUM_SESSION GetCurrentSession()
{
   MqlDateTime dt;
   datetime serverTime = TimeCurrent();
   TimeToStruct(serverTime, dt);

   // Convert to approximate UTC (Deriv servers are typically UTC+0 or UTC+2)
   int hour = dt.hour;

   // Asian session: 00:00 - 07:00 UTC
   if(hour >= 0 && hour < 7)
      return SESSION_ASIAN;

   // London/NY overlap: 12:00 - 16:00 UTC
   if(hour >= 12 && hour < 16)
      return SESSION_OVERLAP;

   // London session: 07:00 - 16:00 UTC
   if(hour >= 7 && hour < 16)
      return SESSION_LONDON;

   // New York session: 16:00 - 21:00 UTC
   if(hour >= 16 && hour < 21)
      return SESSION_NEWYORK;

   return SESSION_OFF;
}

//+------------------------------------------------------------------+
//| Check if current time is within trading hours                     |
//+------------------------------------------------------------------+
bool IsWithinTradingHours(int startHour, int endHour)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   if(startHour < endHour)
      return (dt.hour >= startHour && dt.hour < endHour);
   else // Wraps around midnight
      return (dt.hour >= startHour || dt.hour < endHour);
}

//+------------------------------------------------------------------+
//| Get the point value for XAUUSD                                   |
//+------------------------------------------------------------------+
double GetPointValue(string symbol)
{
   double tickSize  = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double point     = SymbolInfoDouble(symbol, SYMBOL_POINT);

   if(tickSize == 0) return 0;

   return (point / tickSize) * tickValue;
}

//+------------------------------------------------------------------+
//| Calculate distance in points between two prices                   |
//+------------------------------------------------------------------+
int PriceToPoints(string symbol, double priceDistance)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point == 0) return 0;
   return (int)MathRound(MathAbs(priceDistance) / point);
}

//+------------------------------------------------------------------+
//| Calculate price distance from points                              |
//+------------------------------------------------------------------+
double PointsToPrice(string symbol, int points)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   return points * point;
}

//+------------------------------------------------------------------+
//| Count open positions for this EA                                  |
//+------------------------------------------------------------------+
int CountOpenPositions(string symbol, ulong magicNumber)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)magicNumber)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Count open buy positions                                          |
//+------------------------------------------------------------------+
int CountBuyPositions(string symbol, ulong magicNumber)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)magicNumber &&
            PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Count open sell positions                                         |
//+------------------------------------------------------------------+
int CountSellPositions(string symbol, ulong magicNumber)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)magicNumber &&
            PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Get total floating P/L for this EA                                |
//+------------------------------------------------------------------+
double GetFloatingPL(string symbol, ulong magicNumber)
{
   double pl = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol &&
            PositionGetInteger(POSITION_MAGIC) == (long)magicNumber)
         {
            pl += PositionGetDouble(POSITION_PROFIT) +
                  PositionGetDouble(POSITION_SWAP);
         }
      }
   }
   return pl;
}

//+------------------------------------------------------------------+
//| Log message with timestamp                                        |
//+------------------------------------------------------------------+
void LogMessage(string prefix, string message)
{
   Print("[CLAWBOT][" + prefix + "] " + TimeToString(TimeCurrent()) + " | " + message);
}

//+------------------------------------------------------------------+
//| Write line to CSV file                                            |
//+------------------------------------------------------------------+
bool WriteToCSV(string filename, string line, bool append = true)
{
   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(append) flags |= FILE_READ;

   int handle = FileOpen(filename, flags, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("[CLAWBOT] Failed to open file: ", filename, " Error: ", GetLastError());
      return false;
   }

   if(append)
      FileSeek(handle, 0, SEEK_END);

   FileWriteString(handle, line + "\n");
   FileClose(handle);
   return true;
}

//+------------------------------------------------------------------+
//| Get day of week name                                              |
//+------------------------------------------------------------------+
string GetDayName(int dayOfWeek)
{
   switch(dayOfWeek)
   {
      case 0: return "Sunday";
      case 1: return "Monday";
      case 2: return "Tuesday";
      case 3: return "Wednesday";
      case 4: return "Thursday";
      case 5: return "Friday";
      case 6: return "Saturday";
   }
   return "Unknown";
}

//+------------------------------------------------------------------+
//| Check if it's a new bar                                           |
//+------------------------------------------------------------------+
bool IsNewBar(string symbol, ENUM_TIMEFRAMES tf)
{
   static datetime lastBarTime = 0;
   datetime currentBarTime = iTime(symbol, tf, 0);

   if(currentBarTime != lastBarTime)
   {
      lastBarTime = currentBarTime;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Validate symbol is available and tradeable                        |
//+------------------------------------------------------------------+
bool ValidateSymbol(string symbol)
{
   if(!SymbolInfoInteger(symbol, SYMBOL_EXIST))
   {
      // Try alternate naming conventions for Deriv
      string alternates[] = {"XAUUSD", "XAUUSDm", "XAUUSD.s", "Gold", "#XAUUSD"};
      for(int i = 0; i < ArraySize(alternates); i++)
      {
         if(SymbolInfoInteger(alternates[i], SYMBOL_EXIST))
         {
            LogMessage("INIT", "Symbol " + symbol + " not found, but " + alternates[i] + " exists. Please update settings.");
            return false;
         }
      }
      LogMessage("INIT", "Symbol " + symbol + " does not exist on this broker.");
      return false;
   }

   if(!SymbolInfoInteger(symbol, SYMBOL_SELECT))
   {
      SymbolSelect(symbol, true);
   }

   long tradeMode = SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(tradeMode == SYMBOL_TRADE_MODE_DISABLED)
   {
      LogMessage("INIT", "Trading is disabled for " + symbol);
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Get server-to-UTC offset in hours (for Deriv servers)             |
//| Deriv typically runs UTC+0 or UTC+2. This auto-detects.          |
//+------------------------------------------------------------------+
int GetServerUTCOffset()
{
   datetime serverTime = TimeCurrent();
   datetime gmtTime    = TimeGMT();
   int offsetSeconds   = (int)(serverTime - gmtTime);
   int offsetHours     = offsetSeconds / 3600;
   return offsetHours;
}

//+------------------------------------------------------------------+
//| Convert server hour to UTC hour                                    |
//+------------------------------------------------------------------+
int ServerHourToUTC(int serverHour)
{
   int offset = GetServerUTCOffset();
   int utcHour = serverHour - offset;
   if(utcHour < 0) utcHour += 24;
   if(utcHour >= 24) utcHour -= 24;
   return utcHour;
}

//+------------------------------------------------------------------+
//| Get current spread in points                                       |
//+------------------------------------------------------------------+
double GetCurrentSpread(string symbol)
{
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point <= 0) return 0;
   return (ask - bid) / point;
}

//+------------------------------------------------------------------+
//| Get minimum stop level in points                                   |
//+------------------------------------------------------------------+
double GetMinStopLevel(string symbol)
{
   long stopLevel = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stopLevel <= 0) stopLevel = 10; // Safe default
   return (double)stopLevel;
}

//+------------------------------------------------------------------+
//| Count pending orders for this EA                                  |
//+------------------------------------------------------------------+
int CountPendingOrders(string symbol, ulong magicNumber)
{
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0)
      {
         if(OrderGetString(ORDER_SYMBOL) == symbol &&
            OrderGetInteger(ORDER_MAGIC) == (long)magicNumber)
         {
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Delete all pending orders for this EA                             |
//+------------------------------------------------------------------+
void DeleteAllPendingOrders(string symbol, ulong magicNumber)
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0)
      {
         if(OrderGetString(ORDER_SYMBOL) == symbol &&
            OrderGetInteger(ORDER_MAGIC) == (long)magicNumber)
         {
            MqlTradeRequest request = {};
            MqlTradeResult  result  = {};
            request.action = TRADE_ACTION_REMOVE;
            request.order  = ticket;
            OrderSend(request, result);
         }
      }
   }
}

#endif // CLAWUTILS_MQH
