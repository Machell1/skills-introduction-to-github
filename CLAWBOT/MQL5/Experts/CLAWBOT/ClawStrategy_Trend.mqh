//+------------------------------------------------------------------+
//|                                          ClawStrategy_Trend.mqh  |
//|                   CLAWBOT - Strategy 1: Multi-EMA Trend Follow   |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Strategy 1: Multi-EMA Trend Following with ADX Confirmation      |
//|                                                                    |
//| Logic:                                                             |
//|   - Uses 8 EMA (fast), 21 EMA (signal), 50 EMA (trend),          |
//|     200 EMA (major trend)                                          |
//|   - ADX(14) confirms trending conditions                          |
//|   - BUY: Fast EMAs aligned bullish + price above 200 EMA + ADX>20|
//|   - SELL: Fast EMAs aligned bearish + price below 200 EMA + ADX>20|
//|   - Crossover of 8/21 EMA within last 3 bars triggers entry      |
//+------------------------------------------------------------------+
class CClawTrendStrategy
{
private:
   // Indicator handles
   int m_emaFastHandle;      // EMA 8
   int m_emaSignalHandle;    // EMA 21
   int m_emaTrendHandle;     // EMA 50
   int m_emaMajorHandle;     // EMA 200
   int m_adxHandle;          // ADX 14

   // Buffers
   double m_emaFast[];
   double m_emaSignal[];
   double m_emaTrend[];
   double m_emaMajor[];
   double m_adxMain[];
   double m_adxPlus[];
   double m_adxMinus[];

   // Settings
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   int m_emaFastPeriod;
   int m_emaSignalPeriod;
   int m_emaTrendPeriod;
   int m_emaMajorPeriod;
   int m_adxPeriod;
   double m_adxThreshold;
   int m_crossoverLookback;

   bool m_initialized;

   bool CheckCrossover(bool bullish, int lookback);

public:
   CClawTrendStrategy();
   ~CClawTrendStrategy();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             int emaFast = 8, int emaSignal = 21,
             int emaTrend = 50, int emaMajor = 200,
             int adxPeriod = 14, double adxThreshold = 20.0,
             int crossoverLookback = 3);

   void Deinit();
   SignalResult Evaluate();
   string GetName() { return "TrendFollow"; }
};

//+------------------------------------------------------------------+
//| Constructor                                                        |
//+------------------------------------------------------------------+
CClawTrendStrategy::CClawTrendStrategy()
{
   m_initialized = false;
   m_emaFastHandle   = INVALID_HANDLE;
   m_emaSignalHandle = INVALID_HANDLE;
   m_emaTrendHandle  = INVALID_HANDLE;
   m_emaMajorHandle  = INVALID_HANDLE;
   m_adxHandle       = INVALID_HANDLE;
}

//+------------------------------------------------------------------+
//| Destructor                                                         |
//+------------------------------------------------------------------+
CClawTrendStrategy::~CClawTrendStrategy()
{
   Deinit();
}

//+------------------------------------------------------------------+
//| Initialize indicators                                              |
//+------------------------------------------------------------------+
bool CClawTrendStrategy::Init(string symbol, ENUM_TIMEFRAMES tf,
                               int emaFast, int emaSignal,
                               int emaTrend, int emaMajor,
                               int adxPeriod, double adxThreshold,
                               int crossoverLookback)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_emaFastPeriod    = emaFast;
   m_emaSignalPeriod  = emaSignal;
   m_emaTrendPeriod   = emaTrend;
   m_emaMajorPeriod   = emaMajor;
   m_adxPeriod        = adxPeriod;
   m_adxThreshold     = adxThreshold;
   m_crossoverLookback = crossoverLookback;

   // Create indicator handles
   m_emaFastHandle   = iMA(m_symbol, m_timeframe, m_emaFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
   m_emaSignalHandle = iMA(m_symbol, m_timeframe, m_emaSignalPeriod, 0, MODE_EMA, PRICE_CLOSE);
   m_emaTrendHandle  = iMA(m_symbol, m_timeframe, m_emaTrendPeriod, 0, MODE_EMA, PRICE_CLOSE);
   m_emaMajorHandle  = iMA(m_symbol, m_timeframe, m_emaMajorPeriod, 0, MODE_EMA, PRICE_CLOSE);
   m_adxHandle       = iADX(m_symbol, m_timeframe, m_adxPeriod);

   if(m_emaFastHandle == INVALID_HANDLE || m_emaSignalHandle == INVALID_HANDLE ||
      m_emaTrendHandle == INVALID_HANDLE || m_emaMajorHandle == INVALID_HANDLE ||
      m_adxHandle == INVALID_HANDLE)
   {
      LogMessage("TREND", "Failed to create indicator handles. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   // Set arrays as series
   ArraySetAsSeries(m_emaFast, true);
   ArraySetAsSeries(m_emaSignal, true);
   ArraySetAsSeries(m_emaTrend, true);
   ArraySetAsSeries(m_emaMajor, true);
   ArraySetAsSeries(m_adxMain, true);
   ArraySetAsSeries(m_adxPlus, true);
   ArraySetAsSeries(m_adxMinus, true);

   m_initialized = true;
   LogMessage("TREND", "Strategy initialized successfully");
   return true;
}

//+------------------------------------------------------------------+
//| Release indicator handles                                          |
//+------------------------------------------------------------------+
void CClawTrendStrategy::Deinit()
{
   if(m_emaFastHandle != INVALID_HANDLE)   { IndicatorRelease(m_emaFastHandle);   m_emaFastHandle = INVALID_HANDLE; }
   if(m_emaSignalHandle != INVALID_HANDLE) { IndicatorRelease(m_emaSignalHandle); m_emaSignalHandle = INVALID_HANDLE; }
   if(m_emaTrendHandle != INVALID_HANDLE)  { IndicatorRelease(m_emaTrendHandle);  m_emaTrendHandle = INVALID_HANDLE; }
   if(m_emaMajorHandle != INVALID_HANDLE)  { IndicatorRelease(m_emaMajorHandle);  m_emaMajorHandle = INVALID_HANDLE; }
   if(m_adxHandle != INVALID_HANDLE)       { IndicatorRelease(m_adxHandle);       m_adxHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Check for EMA crossover within lookback period                    |
//+------------------------------------------------------------------+
bool CClawTrendStrategy::CheckCrossover(bool bullish, int lookback)
{
   for(int i = 1; i <= lookback; i++)
   {
      if(bullish)
      {
         // Fast EMA crossed above Signal EMA
         if(m_emaFast[i] > m_emaSignal[i] && m_emaFast[i + 1] <= m_emaSignal[i + 1])
            return true;
      }
      else
      {
         // Fast EMA crossed below Signal EMA
         if(m_emaFast[i] < m_emaSignal[i] && m_emaFast[i + 1] >= m_emaSignal[i + 1])
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Evaluate strategy and return signal                                |
//+------------------------------------------------------------------+
SignalResult CClawTrendStrategy::Evaluate()
{
   SignalResult result;
   result.Reset();

   if(!m_initialized) return result;

   // Copy indicator data (need lookback + 2 bars for crossover detection)
   int barsNeeded = m_crossoverLookback + 3;

   if(CopyBuffer(m_emaFastHandle, 0, 0, barsNeeded, m_emaFast) < barsNeeded) return result;
   if(CopyBuffer(m_emaSignalHandle, 0, 0, barsNeeded, m_emaSignal) < barsNeeded) return result;
   if(CopyBuffer(m_emaTrendHandle, 0, 0, barsNeeded, m_emaTrend) < barsNeeded) return result;
   if(CopyBuffer(m_emaMajorHandle, 0, 0, barsNeeded, m_emaMajor) < barsNeeded) return result;
   if(CopyBuffer(m_adxHandle, 0, 0, barsNeeded, m_adxMain) < barsNeeded) return result;
   if(CopyBuffer(m_adxHandle, 1, 0, barsNeeded, m_adxPlus) < barsNeeded) return result;
   if(CopyBuffer(m_adxHandle, 2, 0, barsNeeded, m_adxMinus) < barsNeeded) return result;

   // Use bar[1] (completed bar) for analysis to avoid repainting
   double close = iClose(m_symbol, m_timeframe, 1);

   // Check trend alignment conditions
   bool bullishAlignment = (m_emaFast[1] > m_emaSignal[1]) &&
                           (m_emaSignal[1] > m_emaTrend[1]) &&
                           (close > m_emaMajor[1]);

   bool bearishAlignment = (m_emaFast[1] < m_emaSignal[1]) &&
                           (m_emaSignal[1] < m_emaTrend[1]) &&
                           (close < m_emaMajor[1]);

   // ADX trending condition
   bool isTrending = m_adxMain[1] > m_adxThreshold;
   bool strongTrend = m_adxMain[1] > 30.0;

   // DI directional confirmation
   bool diPlusDominant  = m_adxPlus[1] > m_adxMinus[1];
   bool diMinusDominant = m_adxMinus[1] > m_adxPlus[1];

   // Check for recent crossover
   bool bullCrossover = CheckCrossover(true, m_crossoverLookback);
   bool bearCrossover = CheckCrossover(false, m_crossoverLookback);

   // --- BUY SIGNAL EVALUATION ---
   if(bullishAlignment && isTrending && diPlusDominant)
   {
      result.direction = SIGNAL_BUY;

      if(bullCrossover && strongTrend)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong bullish: EMA alignment + fresh crossover + strong ADX(" +
                         DoubleToString(m_adxMain[1], 1) + ")";
      }
      else if(bullCrossover)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Medium bullish: EMA alignment + fresh crossover, ADX=" +
                         DoubleToString(m_adxMain[1], 1);
      }
      else if(strongTrend)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Medium bullish: EMA aligned + strong trend continuation";
      }
      else
      {
         result.strength = STRENGTH_WEAK;
         result.score = 10;
         result.reason = "Weak bullish: EMA aligned but no fresh crossover";
      }
   }
   // --- SELL SIGNAL EVALUATION ---
   else if(bearishAlignment && isTrending && diMinusDominant)
   {
      result.direction = SIGNAL_SELL;

      if(bearCrossover && strongTrend)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong bearish: EMA alignment + fresh crossover + strong ADX(" +
                         DoubleToString(m_adxMain[1], 1) + ")";
      }
      else if(bearCrossover)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Medium bearish: EMA alignment + fresh crossover, ADX=" +
                         DoubleToString(m_adxMain[1], 1);
      }
      else if(strongTrend)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 25;
         result.reason = "Medium bearish: EMA aligned + strong trend continuation";
      }
      else
      {
         result.strength = STRENGTH_WEAK;
         result.score = 10;
         result.reason = "Weak bearish: EMA aligned but no fresh crossover";
      }
   }

   return result;
}
