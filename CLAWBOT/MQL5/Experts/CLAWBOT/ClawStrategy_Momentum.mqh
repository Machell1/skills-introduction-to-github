//+------------------------------------------------------------------+
//|                                       ClawStrategy_Momentum.mqh  |
//|                CLAWBOT - Strategy 2: RSI Divergence + Momentum   |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Strategy 2: RSI + MACD + Stochastic Momentum                     |
//|                                                                    |
//| Logic:                                                             |
//|   - RSI(14) identifies oversold/overbought zones                  |
//|   - RSI divergence detection (price vs RSI direction)             |
//|   - MACD histogram confirms momentum shift                        |
//|   - Stochastic crossover provides entry timing                    |
//|   - Combined score determines signal strength                     |
//+------------------------------------------------------------------+
class CClawMomentumStrategy
{
private:
   // Indicator handles
   int m_rsiHandle;
   int m_macdHandle;
   int m_stochHandle;

   // Buffers
   double m_rsi[];
   double m_macdMain[];
   double m_macdSignal[];
   double m_macdHist[];
   double m_stochK[];
   double m_stochD[];

   // Settings
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   int m_rsiPeriod;
   double m_rsiOversold;
   double m_rsiOverbought;
   int m_macdFast;
   int m_macdSlow;
   int m_macdSignalPeriod;
   int m_stochK_Period;
   int m_stochD_Period;
   int m_stochSlowing;
   int m_divergenceLookback;

   bool m_initialized;

   bool DetectBullishDivergence(int lookback);
   bool DetectBearishDivergence(int lookback);
   int  FindSwingLow(const double &arr[], int start, int end);
   int  FindSwingHigh(const double &arr[], int start, int end);

public:
   CClawMomentumStrategy();
   ~CClawMomentumStrategy();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             int rsiPeriod = 14, double rsiOversold = 35.0, double rsiOverbought = 65.0,
             int macdFast = 12, int macdSlow = 26, int macdSignal = 9,
             int stochK = 14, int stochD = 3, int stochSlowing = 3,
             int divergenceLookback = 20);

   void Deinit();
   SignalResult Evaluate();
   string GetName() { return "Momentum"; }
};

//+------------------------------------------------------------------+
CClawMomentumStrategy::CClawMomentumStrategy()
{
   m_initialized = false;
   m_rsiHandle   = INVALID_HANDLE;
   m_macdHandle  = INVALID_HANDLE;
   m_stochHandle = INVALID_HANDLE;
}

//+------------------------------------------------------------------+
CClawMomentumStrategy::~CClawMomentumStrategy()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawMomentumStrategy::Init(string symbol, ENUM_TIMEFRAMES tf,
                                  int rsiPeriod, double rsiOversold, double rsiOverbought,
                                  int macdFast, int macdSlow, int macdSignal,
                                  int stochK, int stochD, int stochSlowing,
                                  int divergenceLookback)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_rsiPeriod          = rsiPeriod;
   m_rsiOversold        = rsiOversold;
   m_rsiOverbought      = rsiOverbought;
   m_macdFast           = macdFast;
   m_macdSlow           = macdSlow;
   m_macdSignalPeriod   = macdSignal;
   m_stochK_Period      = stochK;
   m_stochD_Period      = stochD;
   m_stochSlowing       = stochSlowing;
   m_divergenceLookback = divergenceLookback;

   // Create indicator handles
   m_rsiHandle   = iRSI(m_symbol, m_timeframe, m_rsiPeriod, PRICE_CLOSE);
   m_macdHandle  = iMACD(m_symbol, m_timeframe, m_macdFast, m_macdSlow, m_macdSignalPeriod, PRICE_CLOSE);
   m_stochHandle = iStochastic(m_symbol, m_timeframe, m_stochK_Period, m_stochD_Period, m_stochSlowing, MODE_SMA, STO_LOWHIGH);

   if(m_rsiHandle == INVALID_HANDLE || m_macdHandle == INVALID_HANDLE || m_stochHandle == INVALID_HANDLE)
   {
      LogMessage("MOMENTUM", "Failed to create indicator handles. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_rsi, true);
   ArraySetAsSeries(m_macdMain, true);
   ArraySetAsSeries(m_macdSignal, true);
   ArraySetAsSeries(m_macdHist, true);
   ArraySetAsSeries(m_stochK, true);
   ArraySetAsSeries(m_stochD, true);

   m_initialized = true;
   LogMessage("MOMENTUM", "Strategy initialized successfully");
   return true;
}

//+------------------------------------------------------------------+
void CClawMomentumStrategy::Deinit()
{
   if(m_rsiHandle != INVALID_HANDLE)   { IndicatorRelease(m_rsiHandle);   m_rsiHandle = INVALID_HANDLE; }
   if(m_macdHandle != INVALID_HANDLE)  { IndicatorRelease(m_macdHandle);  m_macdHandle = INVALID_HANDLE; }
   if(m_stochHandle != INVALID_HANDLE) { IndicatorRelease(m_stochHandle); m_stochHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Find swing low index in an array                                  |
//+------------------------------------------------------------------+
int CClawMomentumStrategy::FindSwingLow(const double &arr[], int start, int end)
{
   int lowestIdx = start;
   for(int i = start + 1; i <= end; i++)
   {
      if(arr[i] < arr[lowestIdx])
         lowestIdx = i;
   }
   return lowestIdx;
}

//+------------------------------------------------------------------+
//| Find swing high index in an array                                 |
//+------------------------------------------------------------------+
int CClawMomentumStrategy::FindSwingHigh(const double &arr[], int start, int end)
{
   int highestIdx = start;
   for(int i = start + 1; i <= end; i++)
   {
      if(arr[i] > arr[highestIdx])
         highestIdx = i;
   }
   return highestIdx;
}

//+------------------------------------------------------------------+
//| Detect bullish divergence: price lower low, RSI higher low        |
//+------------------------------------------------------------------+
bool CClawMomentumStrategy::DetectBullishDivergence(int lookback)
{
   // Get price lows
   double priceLows[];
   ArrayResize(priceLows, lookback + 1);
   for(int i = 0; i <= lookback; i++)
      priceLows[i] = iLow(m_symbol, m_timeframe, i + 1);

   // Find two recent swing lows in price
   int recentLow = FindSwingLow(priceLows, 0, lookback / 2);
   int olderLow  = FindSwingLow(priceLows, lookback / 2, lookback);

   // Bullish divergence: price makes lower low, RSI makes higher low
   if(priceLows[recentLow] < priceLows[olderLow] &&
      m_rsi[recentLow + 1] > m_rsi[olderLow + 1])
   {
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Detect bearish divergence: price higher high, RSI lower high      |
//+------------------------------------------------------------------+
bool CClawMomentumStrategy::DetectBearishDivergence(int lookback)
{
   double priceHighs[];
   ArrayResize(priceHighs, lookback + 1);
   for(int i = 0; i <= lookback; i++)
      priceHighs[i] = iHigh(m_symbol, m_timeframe, i + 1);

   int recentHigh = FindSwingHigh(priceHighs, 0, lookback / 2);
   int olderHigh  = FindSwingHigh(priceHighs, lookback / 2, lookback);

   // Bearish divergence: price makes higher high, RSI makes lower high
   if(priceHighs[recentHigh] > priceHighs[olderHigh] &&
      m_rsi[recentHigh + 1] < m_rsi[olderHigh + 1])
   {
      return true;
   }

   return false;
}

//+------------------------------------------------------------------+
//| Evaluate strategy and return signal                                |
//+------------------------------------------------------------------+
SignalResult CClawMomentumStrategy::Evaluate()
{
   SignalResult result;
   result.Reset();

   if(!m_initialized) return result;

   int barsNeeded = m_divergenceLookback + 5;

   if(CopyBuffer(m_rsiHandle, 0, 0, barsNeeded, m_rsi) < barsNeeded) return result;
   if(CopyBuffer(m_macdHandle, 0, 0, barsNeeded, m_macdMain) < barsNeeded) return result;
   if(CopyBuffer(m_macdHandle, 1, 0, barsNeeded, m_macdSignal) < barsNeeded) return result;
   if(CopyBuffer(m_stochHandle, 0, 0, barsNeeded, m_stochK) < barsNeeded) return result;
   if(CopyBuffer(m_stochHandle, 1, 0, barsNeeded, m_stochD) < barsNeeded) return result;

   // Calculate MACD histogram manually
   ArrayResize(m_macdHist, barsNeeded);
   for(int i = 0; i < barsNeeded; i++)
      m_macdHist[i] = m_macdMain[i] - m_macdSignal[i];

   // Use bar[1] to avoid repainting
   double rsiVal     = m_rsi[1];
   double macdHist   = m_macdHist[1];
   double macdHistPrev = m_macdHist[2];
   double stochK     = m_stochK[1];
   double stochD     = m_stochD[1];
   double stochKPrev = m_stochK[2];
   double stochDPrev = m_stochD[2];

   // Component scoring
   int rsiScore   = 0;
   int macdScore  = 0;
   int stochScore = 0;
   int divScore   = 0;

   ENUM_SIGNAL_TYPE direction = SIGNAL_NONE;
   string reasons = "";

   // --- BULLISH EVALUATION ---
   bool rsiOversold     = (rsiVal < m_rsiOversold);
   bool rsiRecovering   = (rsiVal < 45 && m_rsi[2] < m_rsi[1]); // RSI turning up
   bool macdBullish     = (macdHist > macdHistPrev); // Histogram increasing
   bool macdCrossUp     = (macdHist > 0 && macdHistPrev <= 0);
   bool stochBullCross  = (stochK > stochD && stochKPrev <= stochDPrev && stochK < 30);
   bool stochOversold   = (stochK < 20 && stochD < 20);
   bool bullDivergence  = DetectBullishDivergence(m_divergenceLookback);

   // --- BEARISH EVALUATION ---
   bool rsiOverbought   = (rsiVal > m_rsiOverbought);
   bool rsiDeclining    = (rsiVal > 55 && m_rsi[2] > m_rsi[1]);
   bool macdBearish     = (macdHist < macdHistPrev);
   bool macdCrossDown   = (macdHist < 0 && macdHistPrev >= 0);
   bool stochBearCross  = (stochK < stochD && stochKPrev >= stochDPrev && stochK > 70);
   bool stochOverbought = (stochK > 80 && stochD > 80);
   bool bearDivergence  = DetectBearishDivergence(m_divergenceLookback);

   // Score bullish signals
   int bullScore = 0;
   string bullReasons = "";

   if(rsiOversold || rsiRecovering)
   {
      bullScore += (rsiOversold) ? 12 : 6;
      bullReasons += "RSI=" + DoubleToString(rsiVal, 1) + " ";
   }
   if(macdBullish || macdCrossUp)
   {
      bullScore += (macdCrossUp) ? 12 : 6;
      bullReasons += "MACD_bull ";
   }
   if(stochBullCross || stochOversold)
   {
      bullScore += (stochBullCross) ? 10 : 5;
      bullReasons += "Stoch_bull ";
   }
   if(bullDivergence)
   {
      bullScore += 15;
      bullReasons += "Bull_divergence ";
   }

   // Score bearish signals
   int bearScore = 0;
   string bearReasons = "";

   if(rsiOverbought || rsiDeclining)
   {
      bearScore += (rsiOverbought) ? 12 : 6;
      bearReasons += "RSI=" + DoubleToString(rsiVal, 1) + " ";
   }
   if(macdBearish || macdCrossDown)
   {
      bearScore += (macdCrossDown) ? 12 : 6;
      bearReasons += "MACD_bear ";
   }
   if(stochBearCross || stochOverbought)
   {
      bearScore += (stochBearCross) ? 10 : 5;
      bearReasons += "Stoch_bear ";
   }
   if(bearDivergence)
   {
      bearScore += 15;
      bearReasons += "Bear_divergence ";
   }

   // Determine dominant direction
   if(bullScore > bearScore && bullScore >= 10)
   {
      result.direction = SIGNAL_BUY;
      result.score = MathMin(bullScore, 40);
      reasons = bullReasons;
   }
   else if(bearScore > bullScore && bearScore >= 10)
   {
      result.direction = SIGNAL_SELL;
      result.score = MathMin(bearScore, 40);
      reasons = bearReasons;
   }
   else
   {
      return result;
   }

   // Classify strength
   if(result.score >= 30)
      result.strength = STRENGTH_STRONG;
   else if(result.score >= 18)
      result.strength = STRENGTH_MEDIUM;
   else
      result.strength = STRENGTH_WEAK;

   string dirStr = (result.direction == SIGNAL_BUY) ? "Bullish" : "Bearish";
   result.reason = dirStr + " momentum: " + reasons + "| Score=" + IntegerToString(result.score);

   return result;
}
