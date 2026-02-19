//+------------------------------------------------------------------+
//|                                     ClawStrategy_MeanRevert.mqh  |
//|           CLAWBOT - Strategy 4: Bollinger Band Mean Reversion    |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
//|                                                                    |
//| Gold (XAUUSD) on H1 frequently reverts to its mean after          |
//| touching Bollinger Band extremes. This strategy:                   |
//|   - Detects when price touches/pierces outer Bollinger Band       |
//|   - Confirms with RSI oversold/overbought conditions              |
//|   - Provides entry at the band level for limit orders             |
//|   - Takes profit at the middle band (20-period SMA = the mean)   |
//|   - Achieves high win rate due to small, high-probability TP     |
//|                                                                    |
//| BUY:  Price touches lower BB + RSI < 35 -> Buy Limit at lower BB |
//| SELL: Price touches upper BB + RSI > 65 -> Sell Limit at upper BB |
//| TP:   Middle BB (mean reversion target)                           |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

class CClawMeanRevertStrategy
{
private:
   int m_bbHandle;
   int m_rsiHandle;

   double m_bbUpper[];
   double m_bbMiddle[];
   double m_bbLower[];
   double m_rsi[];

   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   int m_bbPeriod;
   double m_bbDeviation;
   int m_rsiPeriod;
   double m_rsiOversold;
   double m_rsiOverbought;
   double m_bandTouchBuffer; // % of BB width for touch detection

   bool m_initialized;

public:
   CClawMeanRevertStrategy();
   ~CClawMeanRevertStrategy();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             int bbPeriod = 20, double bbDev = 2.0,
             int rsiPeriod = 14, double rsiOS = 35.0, double rsiOB = 65.0,
             double bandTouchBuffer = 0.2);
   void Deinit();
   SignalResult Evaluate();
   string GetName() { return "MeanRevert"; }
};

//+------------------------------------------------------------------+
CClawMeanRevertStrategy::CClawMeanRevertStrategy()
{
   m_initialized = false;
   m_bbHandle = INVALID_HANDLE;
   m_rsiHandle = INVALID_HANDLE;
}

//+------------------------------------------------------------------+
CClawMeanRevertStrategy::~CClawMeanRevertStrategy()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawMeanRevertStrategy::Init(string symbol, ENUM_TIMEFRAMES tf,
                                    int bbPeriod, double bbDev,
                                    int rsiPeriod, double rsiOS, double rsiOB,
                                    double bandTouchBuffer)
{
   m_symbol = symbol;
   m_timeframe = tf;
   m_bbPeriod = bbPeriod;
   m_bbDeviation = bbDev;
   m_rsiPeriod = rsiPeriod;
   m_rsiOversold = rsiOS;
   m_rsiOverbought = rsiOB;
   m_bandTouchBuffer = bandTouchBuffer;

   m_bbHandle = iBands(m_symbol, m_timeframe, m_bbPeriod, 0, m_bbDeviation, PRICE_CLOSE);
   m_rsiHandle = iRSI(m_symbol, m_timeframe, m_rsiPeriod, PRICE_CLOSE);

   if(m_bbHandle == INVALID_HANDLE || m_rsiHandle == INVALID_HANDLE)
   {
      LogMessage("MEANREV", "Failed to create indicator handles. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_bbUpper, true);
   ArraySetAsSeries(m_bbMiddle, true);
   ArraySetAsSeries(m_bbLower, true);
   ArraySetAsSeries(m_rsi, true);

   m_initialized = true;
   LogMessage("MEANREV", "Mean Reversion strategy initialized (BB " +
              IntegerToString(bbPeriod) + "," + DoubleToString(bbDev, 1) + ")");
   return true;
}

//+------------------------------------------------------------------+
void CClawMeanRevertStrategy::Deinit()
{
   if(m_bbHandle != INVALID_HANDLE)  { IndicatorRelease(m_bbHandle);  m_bbHandle = INVALID_HANDLE; }
   if(m_rsiHandle != INVALID_HANDLE) { IndicatorRelease(m_rsiHandle); m_rsiHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Evaluate mean reversion signal                                    |
//| Returns entry price at Bollinger Band, TP at middle band          |
//+------------------------------------------------------------------+
SignalResult CClawMeanRevertStrategy::Evaluate()
{
   SignalResult result;
   result.Reset();

   if(!m_initialized) return result;

   int barsNeeded = 5;

   if(CopyBuffer(m_bbHandle, 0, 0, barsNeeded, m_bbMiddle) < barsNeeded) return result;
   if(CopyBuffer(m_bbHandle, 1, 0, barsNeeded, m_bbUpper) < barsNeeded) return result;
   if(CopyBuffer(m_bbHandle, 2, 0, barsNeeded, m_bbLower) < barsNeeded) return result;
   if(CopyBuffer(m_rsiHandle, 0, 0, barsNeeded, m_rsi) < barsNeeded) return result;

   // Use bar[1] (completed bar) to avoid repainting
   double close  = iClose(m_symbol, m_timeframe, 1);
   double low    = iLow(m_symbol, m_timeframe, 1);
   double high   = iHigh(m_symbol, m_timeframe, 1);
   double open   = iOpen(m_symbol, m_timeframe, 1);

   double upperBB  = m_bbUpper[1];
   double middleBB = m_bbMiddle[1];
   double lowerBB  = m_bbLower[1];
   double rsiVal   = m_rsi[1];

   double bbWidth = upperBB - lowerBB;
   if(bbWidth <= 0) return result;

   // Touch detection: price within buffer zone of the band
   double touchBuffer = bbWidth * m_bandTouchBuffer;

   bool touchedLowerBand = (low <= lowerBB + touchBuffer);
   bool touchedUpperBand = (high >= upperBB - touchBuffer);
   bool piercedLower = (low <= lowerBB);
   bool piercedUpper = (high >= upperBB);

   // Rejection candle: touched band but closed back inside (bullish/bearish hammer)
   bool bullRejection = touchedLowerBand && (close > lowerBB) && (close > open);
   bool bearRejection = touchedUpperBand && (close < upperBB) && (close < open);

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   // --- BULLISH MEAN REVERSION (buy at lower band, TP at middle) ---
   if(touchedLowerBand && rsiVal < m_rsiOversold)
   {
      result.direction = SIGNAL_BUY;
      result.entryPrice = NormalizeDouble(lowerBB, digits);
      result.suggestedTP = NormalizeDouble(middleBB, digits);

      if(piercedLower && bullRejection && rsiVal < 25)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong mean revert BUY: pierced lower BB + rejection + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
      else if(bullRejection)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 30;
         result.reason = "Mean revert BUY: lower BB rejection + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
      else
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 20;
         result.reason = "Mean revert BUY: touching lower BB + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
   }
   // --- BEARISH MEAN REVERSION (sell at upper band, TP at middle) ---
   else if(touchedUpperBand && rsiVal > m_rsiOverbought)
   {
      result.direction = SIGNAL_SELL;
      result.entryPrice = NormalizeDouble(upperBB, digits);
      result.suggestedTP = NormalizeDouble(middleBB, digits);

      if(piercedUpper && bearRejection && rsiVal > 75)
      {
         result.strength = STRENGTH_STRONG;
         result.score = 40;
         result.reason = "Strong mean revert SELL: pierced upper BB + rejection + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
      else if(bearRejection)
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 30;
         result.reason = "Mean revert SELL: upper BB rejection + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
      else
      {
         result.strength = STRENGTH_MEDIUM;
         result.score = 20;
         result.reason = "Mean revert SELL: touching upper BB + RSI=" +
                         DoubleToString(rsiVal, 1);
      }
   }

   return result;
}
