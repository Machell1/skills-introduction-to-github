//+------------------------------------------------------------------+
//|                                        ClawStrategy_Session.mqh  |
//|              CLAWBOT - Strategy 3: Session Breakout + Timing     |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Strategy 3: Asian Session Range Breakout with Session Timing     |
//|                                                                    |
//| Logic:                                                             |
//|   - Calculate Asian session (00:00-07:00 UTC) High and Low       |
//|   - Wait for London open (07:00-09:00 UTC)                       |
//|   - Trade breakouts above Asian High or below Asian Low          |
//|   - ATR-based buffer to filter false breakouts                   |
//|   - Volume/volatility confirmation                                |
//|   - Exit before NY session close or use trailing stop            |
//|                                                                    |
//| Gold-specific optimizations:                                       |
//|   - Gold tends to consolidate in Asian, break out in London      |
//|   - London/NY overlap (12:00-16:00) is highest volatility        |
//|   - Session timing is crucial for gold trading                    |
//+------------------------------------------------------------------+
class CClawSessionStrategy
{
private:
   // Indicator handles
   int m_atrHandle;

   // Buffers
   double m_atr[];

   // Session range data
   double m_asianHigh;
   double m_asianLow;
   double m_asianMid;
   bool   m_asianRangeValid;
   datetime m_asianRangeDate;

   // Settings
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   int    m_atrPeriod;
   double m_breakoutBufferATR;  // ATR multiplier for breakout buffer
   int    m_asianStartHour;     // UTC
   int    m_asianEndHour;       // UTC
   int    m_londonStartHour;    // UTC
   int    m_londonEndHour;      // UTC for entry window
   int    m_exitHour;           // UTC hour to close session trades
   double m_minRangeATR;        // Minimum Asian range as ATR multiple
   double m_maxRangeATR;        // Maximum Asian range (too wide = don't trade)

   // Breakout-once-per-day tracking
   datetime m_lastBreakoutDate;
   int      m_breakoutDirection;  // 0=none, 1=buy, -1=sell

   bool m_initialized;

   void   CalculateAsianRange();
   bool   IsWithinEntryWindow();
   bool   IsWithinExitWindow();

public:
   CClawSessionStrategy();
   ~CClawSessionStrategy();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             int atrPeriod = 14, double breakoutBuffer = 0.5,
             int asianStart = 0, int asianEnd = 7,
             int londonStart = 7, int londonEnd = 10,
             int exitHour = 20,
             double minRange = 0.3, double maxRange = 2.5);

   void Deinit();
   SignalResult Evaluate();
   string GetName() { return "Session"; }

   double GetAsianHigh()   { return m_asianHigh; }
   double GetAsianLow()    { return m_asianLow; }
   bool   IsRangeValid()   { return m_asianRangeValid; }
};

//+------------------------------------------------------------------+
CClawSessionStrategy::CClawSessionStrategy()
{
   m_initialized = false;
   m_atrHandle = INVALID_HANDLE;
   m_asianHigh = 0;
   m_asianLow = 0;
   m_asianMid = 0;
   m_asianRangeValid = false;
   m_asianRangeDate = 0;
   m_lastBreakoutDate = 0;
   m_breakoutDirection = 0;
}

//+------------------------------------------------------------------+
CClawSessionStrategy::~CClawSessionStrategy()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawSessionStrategy::Init(string symbol, ENUM_TIMEFRAMES tf,
                                 int atrPeriod, double breakoutBuffer,
                                 int asianStart, int asianEnd,
                                 int londonStart, int londonEnd,
                                 int exitHour,
                                 double minRange, double maxRange)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_atrPeriod          = atrPeriod;
   m_breakoutBufferATR  = breakoutBuffer;
   m_asianStartHour     = asianStart;
   m_asianEndHour       = asianEnd;
   m_londonStartHour    = londonStart;
   m_londonEndHour      = londonEnd;
   m_exitHour           = exitHour;
   m_minRangeATR        = minRange;
   m_maxRangeATR        = maxRange;

   m_atrHandle = iATR(m_symbol, m_timeframe, m_atrPeriod);
   if(m_atrHandle == INVALID_HANDLE)
   {
      LogMessage("SESSION", "Failed to create ATR handle. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_atr, true);

   m_initialized = true;
   LogMessage("SESSION", "Strategy initialized successfully");
   return true;
}

//+------------------------------------------------------------------+
void CClawSessionStrategy::Deinit()
{
   if(m_atrHandle != INVALID_HANDLE) { IndicatorRelease(m_atrHandle); m_atrHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Calculate the Asian session range for the current day              |
//+------------------------------------------------------------------+
void CClawSessionStrategy::CalculateAsianRange()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   // Create today's date at midnight
   datetime today = StringToTime(IntegerToString(dt.year) + "." +
                                  IntegerToString(dt.mon) + "." +
                                  IntegerToString(dt.day));

   // Don't recalculate if already done for today
   if(m_asianRangeDate == today && m_asianRangeValid)
      return;

   m_asianRangeDate = today;
   m_asianRangeValid = false;

   // Find bars within Asian session range
   datetime asianStart = today + m_asianStartHour * 3600;
   datetime asianEnd   = today + m_asianEndHour * 3600;

   double high = -DBL_MAX;
   double low  = DBL_MAX;
   int barCount = 0;

   // Scan H1 bars in Asian range
   for(int i = 0; i < 100; i++)
   {
      datetime barTime = iTime(m_symbol, m_timeframe, i);
      if(barTime == 0) continue;

      if(barTime >= asianStart && barTime < asianEnd)
      {
         double barHigh = iHigh(m_symbol, m_timeframe, i);
         double barLow  = iLow(m_symbol, m_timeframe, i);

         if(barHigh > high) high = barHigh;
         if(barLow < low)   low  = barLow;
         barCount++;
      }
      else if(barTime < asianStart)
         break; // Past the session, no need to continue
   }

   if(barCount >= 3) // Need at least 3 bars of data
   {
      m_asianHigh = high;
      m_asianLow  = low;
      m_asianMid  = (high + low) / 2.0;
      m_asianRangeValid = true;
   }
}

//+------------------------------------------------------------------+
//| Check if current time is within the London entry window           |
//+------------------------------------------------------------------+
bool CClawSessionStrategy::IsWithinEntryWindow()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return (dt.hour >= m_londonStartHour && dt.hour < m_londonEndHour);
}

//+------------------------------------------------------------------+
//| Check if current time is past exit window                         |
//+------------------------------------------------------------------+
bool CClawSessionStrategy::IsWithinExitWindow()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return (dt.hour >= m_exitHour);
}

//+------------------------------------------------------------------+
//| Evaluate strategy and return signal                                |
//+------------------------------------------------------------------+
SignalResult CClawSessionStrategy::Evaluate()
{
   SignalResult result;
   result.Reset();

   if(!m_initialized) return result;

   // Calculate today's Asian range
   CalculateAsianRange();
   if(!m_asianRangeValid)
   {
      return result;
   }

   // Get ATR data
   if(CopyBuffer(m_atrHandle, 0, 0, 5, m_atr) < 5) return result;

   double currentATR = m_atr[1]; // Use completed bar
   if(currentATR <= 0) return result;

   double asianRange = m_asianHigh - m_asianLow;

   // Validate range size (not too small, not too large)
   if(asianRange < m_minRangeATR * currentATR)
   {
      return result; // Range too small, likely no consolidation
   }
   if(asianRange > m_maxRangeATR * currentATR)
   {
      return result; // Range too large, breakout less reliable
   }

   // Calculate breakout levels
   double breakoutBuffer = m_breakoutBufferATR * currentATR;
   double buyLevel  = m_asianHigh + breakoutBuffer;
   double sellLevel = m_asianLow - breakoutBuffer;

   // Get current price data (use bar[1] for completed bar)
   double close = iClose(m_symbol, m_timeframe, 1);
   double open  = iOpen(m_symbol, m_timeframe, 1);
   double high  = iHigh(m_symbol, m_timeframe, 1);
   double low   = iLow(m_symbol, m_timeframe, 1);

   // Get current session
   ENUM_SESSION currentSession = GetCurrentSession();

   // Strong breakout: price closed beyond level
   // Medium: price touched but hasn't closed beyond
   // We prefer London and Overlap sessions for entries

   // Use configurable entry window (default: London 7-10 UTC)
   bool inEntryWindow = IsWithinEntryWindow();
   bool inExitWindow  = IsWithinExitWindow();

   if(inExitWindow)
   {
      return result; // No new entries near session close
   }

   // Only allow one breakout signal per day per direction
   MqlDateTime todayDt;
   TimeToStruct(TimeCurrent(), todayDt);
   datetime todayDate = StringToTime(IntegerToString(todayDt.year) + "." +
                                      IntegerToString(todayDt.mon) + "." +
                                      IntegerToString(todayDt.day));
   if(todayDate != m_lastBreakoutDate)
   {
      m_breakoutDirection = 0; // Reset for new day
   }

   // --- BULLISH BREAKOUT ---
   if(close > buyLevel && inEntryWindow)
   {
      result.direction = SIGNAL_BUY;

      // Strong: closed above level with momentum (close near high of bar)
      bool strongClose = (close - open) > 0 && (high - close) < (close - open) * 0.3;
      // Check if breakout bar has strong body
      bool strongBody = MathAbs(close - open) > currentATR * 0.3;

      if(strongClose && strongBody)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong bullish breakout above Asian range (" +
                         DoubleToString(m_asianHigh, 2) + ") with momentum";
      }
      else if(close > buyLevel)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Bullish breakout above Asian range (" +
                         DoubleToString(m_asianHigh, 2) + ")";
      }
   }
   // --- Weak bullish: high pierced but close not above ---
   else if(high > buyLevel && close > m_asianMid && inEntryWindow)
   {
      result.direction = SIGNAL_BUY;
      result.strength = STRENGTH_WEAK;
      result.score = 10;
      result.reason = "Weak bullish: testing Asian high resistance at " +
                      DoubleToString(m_asianHigh, 2);
   }
   // --- BEARISH BREAKOUT ---
   else if(close < sellLevel && inEntryWindow)
   {
      result.direction = SIGNAL_SELL;

      bool strongClose = (open - close) > 0 && (close - low) < (open - close) * 0.3;
      bool strongBody = MathAbs(close - open) > currentATR * 0.3;

      if(strongClose && strongBody)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong bearish breakout below Asian range (" +
                         DoubleToString(m_asianLow, 2) + ") with momentum";
      }
      else if(close < sellLevel)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Bearish breakout below Asian range (" +
                         DoubleToString(m_asianLow, 2) + ")";
      }
   }
   // --- Weak bearish: low pierced but close not below ---
   else if(low < sellLevel && close < m_asianMid && inEntryWindow)
   {
      result.direction = SIGNAL_SELL;
      result.strength = STRENGTH_WEAK;
      result.score = 10;
      result.reason = "Weak bearish: testing Asian low support at " +
                      DoubleToString(m_asianLow, 2);
   }

   // Suppress if we already signaled this direction today
   if(result.direction != SIGNAL_NONE)
   {
      int dirInt = (result.direction == SIGNAL_BUY) ? 1 : -1;
      if(m_breakoutDirection == dirInt)
      {
         result.Reset(); // Already signaled this breakout today
         return result;
      }

      // Session timing bonus
      if(currentSession == SESSION_OVERLAP)
      {
         result.score = MathMin(result.score + 5, 40);
         result.reason += " [London/NY overlap bonus]";
      }

      // Mark breakout as signaled for today
      m_lastBreakoutDate = todayDate;
      m_breakoutDirection = dirInt;
   }

   return result;
}
