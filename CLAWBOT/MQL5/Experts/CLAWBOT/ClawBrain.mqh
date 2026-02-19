//+------------------------------------------------------------------+
//|                                                    ClawBrain.mqh |
//|        CLAWBOT - Adaptive Strategy Brain / Market Regime Engine  |
//|                    For XAUUSD H1 on Deriv MT5                    |
//+------------------------------------------------------------------+
//|                                                                    |
//| The Brain decides WHEN and HOW to trade by analyzing:             |
//|   1. Market Regime (trending/ranging/volatile/transitioning)      |
//|   2. Current Session (Asian/London/NY/Overlap)                   |
//|   3. SMC Market Structure (trend, price zone, structure events)  |
//|                                                                    |
//| It outputs:                                                        |
//|   - Strategy weight multipliers (boost/suppress each strategy)   |
//|   - Lot size multiplier (regime-based position sizing)           |
//|   - Trading permission (should we trade at all right now?)       |
//|   - Minimum score adjustments                                    |
//|                                                                    |
//| Regime Detection uses:                                             |
//|   - ADX for trend strength                                       |
//|   - ATR ratio (current vs average) for volatility                |
//|   - Bollinger Band width for squeeze/expansion                   |
//|   - Market structure consistency from SMC module                  |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Strategy weight output structure                                  |
//+------------------------------------------------------------------+
struct StrategyWeights
{
   double trend;           // Weight for trend strategy (0.0 - 2.0)
   double momentum;        // Weight for momentum strategy
   double session;         // Weight for session strategy
   double meanRevert;      // Weight for mean reversion strategy
   double smc;             // Weight for SMC strategy
   double lotMultiplier;   // Position size multiplier (0.25 - 1.0)
   bool   allowTrading;    // Whether to trade in current conditions
   int    minScoreAdj;     // Adjustment to minimum confluence score

   void Reset()
   {
      trend         = 1.0;
      momentum      = 1.0;
      session       = 1.0;
      meanRevert    = 1.0;
      smc           = 1.0;
      lotMultiplier = 1.0;
      allowTrading  = true;
      minScoreAdj   = 0;
   }
};

//+------------------------------------------------------------------+
//| Adaptive Strategy Brain                                           |
//+------------------------------------------------------------------+
class CClawBrain
{
private:
   // Indicator handles for regime detection
   int m_adxHandle;
   int m_atrHandle;
   int m_atrSlowHandle;   // Longer ATR for ratio calculation
   int m_bbHandle;

   // Buffers
   double m_adxMain[];
   double m_adxPlus[];
   double m_adxMinus[];
   double m_atrFast[];
   double m_atrSlow[];
   double m_bbUpper[];
   double m_bbLower[];
   double m_bbMiddle[];

   // Symbol/timeframe
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;

   // Current state
   ENUM_MARKET_REGIME m_currentRegime;
   ENUM_MARKET_REGIME m_prevRegime;
   int m_regimeBarCount;         // How many bars in current regime
   ENUM_SESSION m_currentSession;

   // Regime detection thresholds
   double m_adxTrendThreshold;   // ADX above this = trending
   double m_adxStrongThreshold;  // ADX above this = strong trend
   double m_atrHighRatio;        // ATR ratio above this = volatile
   double m_atrLowRatio;         // ATR ratio below this = compressed

   bool m_initialized;

   // Internal
   void DetectRegime();
   void ApplyRegimeWeights(StrategyWeights &weights);
   void ApplySessionWeights(StrategyWeights &weights);
   void ApplySMCContext(StrategyWeights &weights,
                        ENUM_MARKET_TREND smcTrend,
                        ENUM_PRICE_ZONE priceZone,
                        ENUM_STRUCTURE_EVENT structEvent);

public:
   CClawBrain();
   ~CClawBrain();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             double adxTrend = 20.0, double adxStrong = 30.0,
             double atrHighRatio = 1.5, double atrLowRatio = 0.8);
   void Deinit();

   // Call on each new bar AFTER SMC.Update()
   void Update(ENUM_MARKET_TREND smcTrend,
               ENUM_PRICE_ZONE priceZone,
               ENUM_STRUCTURE_EVENT structEvent);

   // Get the current strategy weights
   StrategyWeights GetWeights(ENUM_MARKET_TREND smcTrend,
                              ENUM_PRICE_ZONE priceZone,
                              ENUM_STRUCTURE_EVENT structEvent);

   // Getters
   ENUM_MARKET_REGIME GetCurrentRegime() { return m_currentRegime; }
   ENUM_SESSION GetCurrentSession()      { return m_currentSession; }
   string GetRegimeName();
};

//+------------------------------------------------------------------+
CClawBrain::CClawBrain()
{
   m_initialized    = false;
   m_adxHandle      = INVALID_HANDLE;
   m_atrHandle      = INVALID_HANDLE;
   m_atrSlowHandle  = INVALID_HANDLE;
   m_bbHandle       = INVALID_HANDLE;
   m_currentRegime  = REGIME_RANGING;
   m_prevRegime     = REGIME_RANGING;
   m_regimeBarCount = 0;
}

//+------------------------------------------------------------------+
CClawBrain::~CClawBrain()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawBrain::Init(string symbol, ENUM_TIMEFRAMES tf,
                       double adxTrend, double adxStrong,
                       double atrHighRatio, double atrLowRatio)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_adxTrendThreshold  = adxTrend;
   m_adxStrongThreshold = adxStrong;
   m_atrHighRatio       = atrHighRatio;
   m_atrLowRatio        = atrLowRatio;

   m_adxHandle     = iADX(m_symbol, m_timeframe, 14);
   m_atrHandle     = iATR(m_symbol, m_timeframe, 14);
   m_atrSlowHandle = iATR(m_symbol, m_timeframe, 50);
   m_bbHandle      = iBands(m_symbol, m_timeframe, 20, 0, 2.0, PRICE_CLOSE);

   if(m_adxHandle == INVALID_HANDLE || m_atrHandle == INVALID_HANDLE ||
      m_atrSlowHandle == INVALID_HANDLE || m_bbHandle == INVALID_HANDLE)
   {
      LogMessage("BRAIN", "Failed to create indicator handles. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_adxMain, true);
   ArraySetAsSeries(m_adxPlus, true);
   ArraySetAsSeries(m_adxMinus, true);
   ArraySetAsSeries(m_atrFast, true);
   ArraySetAsSeries(m_atrSlow, true);
   ArraySetAsSeries(m_bbUpper, true);
   ArraySetAsSeries(m_bbLower, true);
   ArraySetAsSeries(m_bbMiddle, true);

   m_initialized = true;
   LogMessage("BRAIN", "Adaptive Brain initialized (ADX trend=" +
              DoubleToString(adxTrend, 0) + ", strong=" + DoubleToString(adxStrong, 0) + ")");
   return true;
}

//+------------------------------------------------------------------+
void CClawBrain::Deinit()
{
   if(m_adxHandle != INVALID_HANDLE)     { IndicatorRelease(m_adxHandle);     m_adxHandle = INVALID_HANDLE; }
   if(m_atrHandle != INVALID_HANDLE)     { IndicatorRelease(m_atrHandle);     m_atrHandle = INVALID_HANDLE; }
   if(m_atrSlowHandle != INVALID_HANDLE) { IndicatorRelease(m_atrSlowHandle); m_atrSlowHandle = INVALID_HANDLE; }
   if(m_bbHandle != INVALID_HANDLE)      { IndicatorRelease(m_bbHandle);      m_bbHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Detect current market regime                                      |
//+------------------------------------------------------------------+
void CClawBrain::DetectRegime()
{
   if(CopyBuffer(m_adxHandle, 0, 0, 10, m_adxMain) < 10) return;
   if(CopyBuffer(m_adxHandle, 1, 0, 10, m_adxPlus) < 10) return;
   if(CopyBuffer(m_adxHandle, 2, 0, 10, m_adxMinus) < 10) return;
   if(CopyBuffer(m_atrHandle, 0, 0, 10, m_atrFast) < 10) return;
   if(CopyBuffer(m_atrSlowHandle, 0, 0, 10, m_atrSlow) < 10) return;
   if(CopyBuffer(m_bbHandle, 1, 0, 10, m_bbUpper) < 10) return;
   if(CopyBuffer(m_bbHandle, 2, 0, 10, m_bbLower) < 10) return;
   if(CopyBuffer(m_bbHandle, 0, 0, 10, m_bbMiddle) < 10) return;

   double adx = m_adxMain[1];
   double atrRatio = (m_atrSlow[1] > 0) ? m_atrFast[1] / m_atrSlow[1] : 1.0;

   // BB squeeze detection
   double bbWidth = 0;
   if(m_bbMiddle[1] > 0)
      bbWidth = (m_bbUpper[1] - m_bbLower[1]) / m_bbMiddle[1];

   // ADX acceleration (how fast ADX is rising/falling)
   double adxAccel = m_adxMain[1] - m_adxMain[3];

   m_prevRegime = m_currentRegime;

   // --- Regime Classification ---
   // Volatile expansion: high ATR ratio + rapidly rising ADX
   if(atrRatio > m_atrHighRatio && adxAccel > 5.0)
   {
      m_currentRegime = REGIME_VOLATILE_EXPANSION;
   }
   // Strong trend: ADX above strong threshold + consistent direction
   else if(adx > m_adxStrongThreshold && atrRatio >= 1.0)
   {
      m_currentRegime = REGIME_TRENDING_STRONG;
   }
   // Weak trend: ADX above trend threshold
   else if(adx > m_adxTrendThreshold)
   {
      m_currentRegime = REGIME_TRENDING_WEAK;
   }
   // Ranging: low ADX + low/normal volatility
   else if(adx < m_adxTrendThreshold && atrRatio < 1.2)
   {
      m_currentRegime = REGIME_RANGING;
   }
   // Transitioning: ADX was high and is now dropping
   else if(m_prevRegime == REGIME_TRENDING_STRONG && adx < m_adxStrongThreshold)
   {
      m_currentRegime = REGIME_TRANSITIONING;
   }
   else
   {
      // Default: keep current or set to ranging
      if(adx < m_adxTrendThreshold)
         m_currentRegime = REGIME_RANGING;
   }

   // Track how long we've been in this regime
   if(m_currentRegime == m_prevRegime)
      m_regimeBarCount++;
   else
   {
      m_regimeBarCount = 1;
      LogMessage("BRAIN", "Regime change: " + GetRegimeName());
   }
}

//+------------------------------------------------------------------+
//| Update brain state - call each new bar                            |
//+------------------------------------------------------------------+
void CClawBrain::Update(ENUM_MARKET_TREND smcTrend,
                          ENUM_PRICE_ZONE priceZone,
                          ENUM_STRUCTURE_EVENT structEvent)
{
   if(!m_initialized) return;

   m_currentSession = ::GetCurrentSession();
   DetectRegime();
}

//+------------------------------------------------------------------+
//| Get strategy weights for current conditions                       |
//+------------------------------------------------------------------+
StrategyWeights CClawBrain::GetWeights(ENUM_MARKET_TREND smcTrend,
                                        ENUM_PRICE_ZONE priceZone,
                                        ENUM_STRUCTURE_EVENT structEvent)
{
   StrategyWeights w;
   w.Reset();

   if(!m_initialized) return w;

   // Step 1: Apply regime-based weights
   ApplyRegimeWeights(w);

   // Step 2: Apply session-based adjustments
   ApplySessionWeights(w);

   // Step 3: Apply SMC context adjustments
   ApplySMCContext(w, smcTrend, priceZone, structEvent);

   return w;
}

//+------------------------------------------------------------------+
//| Apply strategy weights based on market regime                     |
//+------------------------------------------------------------------+
void CClawBrain::ApplyRegimeWeights(StrategyWeights &w)
{
   switch(m_currentRegime)
   {
      case REGIME_TRENDING_STRONG:
         w.trend         = 1.6;   // Maximize trend-following exposure
         w.momentum      = 1.3;
         w.session       = 1.1;
         w.meanRevert    = 0.2;   // Counter-trend is very dangerous in strong trends
         w.smc           = 1.5;   // SMC shines in trends (BOS + OB entries)
         w.lotMultiplier = 1.2;   // Full confidence in strong trends
         w.minScoreAdj   = -8;    // Easier entry (strong trending is most profitable)
         break;

      case REGIME_TRENDING_WEAK:
         w.trend         = 1.3;
         w.momentum      = 1.1;
         w.session       = 0.9;
         w.meanRevert    = 0.4;
         w.smc           = 1.3;
         w.lotMultiplier = 0.85;  // More aggressive in weak trends
         break;

      case REGIME_RANGING:
         w.trend         = 0.2;   // Trend following fails badly in ranges
         w.momentum      = 0.6;
         w.session       = 0.4;
         w.meanRevert    = 1.6;   // Mean reversion excels - boost further
         w.smc           = 1.0;   // Range extremes = liquidity
         w.lotMultiplier = 0.45;  // Smaller size - ranging has more noise
         w.minScoreAdj   = 8;     // Much stricter in ranging (most false signals)
         break;

      case REGIME_VOLATILE_EXPANSION:
         w.trend         = 0.4;
         w.momentum      = 0.4;
         w.session       = 0.2;
         w.meanRevert    = 0.2;
         w.smc           = 0.7;
         w.lotMultiplier = 0.3;   // Very small size in volatile markets
         w.minScoreAdj   = 15;    // Extremely strict entry - most losses come from volatile entries
         break;

      case REGIME_TRANSITIONING:
         w.trend         = 0.3;   // Old trend is dying - don't follow
         w.momentum      = 1.1;
         w.session       = 0.4;
         w.meanRevert    = 0.9;
         w.smc           = 1.4;   // CHoCH detection is critical here
         w.lotMultiplier = 0.4;   // Very cautious during transitions
         w.minScoreAdj   = 8;     // Strict - transitions produce whipsaws
         break;
   }
}

//+------------------------------------------------------------------+
//| Apply session-based weight adjustments (compound with regime)     |
//+------------------------------------------------------------------+
void CClawBrain::ApplySessionWeights(StrategyWeights &w)
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   int hour = dt.hour;

   // Asian session (00:00-07:00): low volume, range forming
   if(m_currentSession == SESSION_ASIAN)
   {
      w.trend      *= 0.3;    // Almost never trend-follow in Asian
      w.momentum   *= 0.4;
      w.session    *= 0.2;    // No breakout yet
      w.meanRevert *= 1.1;    // Range scalping OK but cautious
      w.smc        *= 0.5;
      w.lotMultiplier *= 0.4; // Very small size in Asian

      // Early Asian (00-04): no trading - too quiet, spreads wide
      if(hour < 4) w.allowTrading = false;
   }
   // London open (07:00-10:00): breakouts, sweeps, highest SMC activity
   else if(m_currentSession == SESSION_LONDON && hour < 10)
   {
      w.trend      *= 1.2;    // Stronger trend follow during London open
      w.session    *= 1.5;    // Asian range breakout prime time
      w.smc        *= 1.4;    // Liquidity sweeps + BOS
      w.meanRevert *= 0.5;    // Definitely don't fade breakouts
      w.lotMultiplier *= 1.1; // Slightly more aggressive at London open
   }
   // London/NY overlap (12:00-16:00): highest volume, all strategies valid
   else if(m_currentSession == SESSION_OVERLAP)
   {
      w.trend      *= 1.2;
      w.momentum   *= 1.2;
      w.session    *= 1.2;
      w.smc        *= 1.3;
      w.lotMultiplier *= 1.1; // Bigger size during best session
   }
   // London close (15:00-17:00): mean reversion
   else if(hour >= 15 && hour < 17)
   {
      w.trend      *= 0.5;
      w.meanRevert *= 1.4;
      w.smc        *= 0.8;
   }
   // NY afternoon (17:00-21:00): declining volatility - reduce exposure
   else if(m_currentSession == SESSION_NEWYORK)
   {
      w.trend      *= 0.6;
      w.meanRevert *= 1.0;
      w.smc        *= 0.7;
      w.lotMultiplier *= 0.5; // Small size in declining NY
   }
   // Off hours (21:00-00:00): no trading
   else if(m_currentSession == SESSION_OFF)
   {
      w.allowTrading = false;
   }

   // Friday afternoon caution (close positions, don't open new ones)
   if(dt.day_of_week == 5 && hour >= 16)
      w.allowTrading = false;

   // Monday early (00-05): skip the gap-risk period
   if(dt.day_of_week == 1 && hour < 5)
      w.allowTrading = false;
}

//+------------------------------------------------------------------+
//| Apply SMC context for directional filtering                       |
//+------------------------------------------------------------------+
void CClawBrain::ApplySMCContext(StrategyWeights &w,
                                  ENUM_MARKET_TREND smcTrend,
                                  ENUM_PRICE_ZONE priceZone,
                                  ENUM_STRUCTURE_EVENT structEvent)
{
   // Premium zone: suppress buys, boost sells
   if(priceZone == ZONE_EXTREME_PREMIUM || priceZone == ZONE_PREMIUM)
   {
      // Strategies that might generate buy signals get suppressed
      // (This is handled at signal level, but we also reduce lot size for buys)
      w.meanRevert *= 1.2;  // Mean reversion sells from premium
   }
   // Discount zone: suppress sells, boost buys
   else if(priceZone == ZONE_EXTREME_DISCOUNT || priceZone == ZONE_DISCOUNT)
   {
      w.meanRevert *= 1.2;
   }

   // CHoCH events: boost SMC and transition weights
   if(structEvent == STRUCT_CHOCH_BULLISH || structEvent == STRUCT_CHOCH_BEARISH)
   {
      w.smc    *= 1.3;
      w.trend  *= 0.5;   // Old trend is invalidated
   }

   // BOS events: boost trend continuation
   if(structEvent == STRUCT_BOS_BULLISH || structEvent == STRUCT_BOS_BEARISH)
   {
      w.trend *= 1.2;
      w.smc   *= 1.2;
   }
}

//+------------------------------------------------------------------+
string CClawBrain::GetRegimeName()
{
   switch(m_currentRegime)
   {
      case REGIME_TRENDING_STRONG:    return "TRENDING_STRONG";
      case REGIME_TRENDING_WEAK:      return "TRENDING_WEAK";
      case REGIME_RANGING:            return "RANGING";
      case REGIME_VOLATILE_EXPANSION: return "VOLATILE_EXPANSION";
      case REGIME_TRANSITIONING:      return "TRANSITIONING";
   }
   return "UNKNOWN";
}
