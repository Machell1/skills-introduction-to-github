//+------------------------------------------------------------------+
//|                                                      ClawSMC.mqh |
//|           CLAWBOT - Smart Money Concepts Analysis Module          |
//|                    For XAUUSD H1 on Deriv MT5                    |
//+------------------------------------------------------------------+
//|                                                                    |
//| Implements institutional trading concepts:                         |
//|   - Market Structure (swing highs/lows, HH/HL/LH/LL tracking)   |
//|   - Break of Structure (BOS) and Change of Character (CHoCH)     |
//|   - Order Blocks (OB) - institutional supply/demand zones        |
//|   - Fair Value Gaps (FVG) - inefficient price delivery zones     |
//|   - Liquidity Sweeps - stop hunts above/below key levels         |
//|   - Premium/Discount Zones - optimal directional bias            |
//|   - Optimal Trade Entry (OTE) - Fibonacci 0.618-0.786 zone      |
//|                                                                    |
//| XAUUSD-specific tuning:                                           |
//|   - Round number liquidity at $50 intervals                      |
//|   - Wider sweep tolerance ($3-5 on gold)                         |
//|   - H1 OBs valid for 72 bars                                    |
//|   - FVG minimum $2.00, maximum $15.00                            |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//--- SMC Constants for XAUUSD
#define SMC_MAX_SWING_POINTS   30
#define SMC_MAX_ORDER_BLOCKS   10
#define SMC_MAX_FVGS           10
#define SMC_MAX_LIQ_LEVELS     20
#define SMC_LOOKBACK           120

//+------------------------------------------------------------------+
//| SMC Data Structures                                               |
//+------------------------------------------------------------------+
struct SMCSwingPoint
{
   double   price;
   datetime time;
   int      barIndex;
   bool     isHigh;        // true = swing high, false = swing low
   bool     broken;        // true once price closes beyond this level
};

struct SMCOrderBlock
{
   double   zoneHigh;       // Top of OB zone
   double   zoneLow;        // Bottom of OB zone
   double   bodyHigh;       // Refined zone: max(open, close)
   double   bodyLow;        // Refined zone: min(open, close)
   datetime timeCreated;
   int      barIndex;
   int      direction;      // +1 = bullish OB (demand), -1 = bearish OB (supply)
   bool     mitigated;      // Price closed through the zone
   bool     tested;         // First touch (entry signal)
   int      touchCount;
};

struct SMCFairValueGap
{
   double   gapHigh;
   double   gapLow;
   double   midpoint;       // Consequent encroachment level
   datetime timeCreated;
   int      barIndex;
   int      direction;      // +1 = bullish FVG, -1 = bearish FVG
   bool     mitigated;
};

struct SMCLiquidityLevel
{
   double   price;
   datetime time;
   int      levelType;      // 0=swing, 1=equal H/L, 2=session H/L, 3=round number
   int      touchCount;
   bool     swept;
};

//+------------------------------------------------------------------+
//| Smart Money Concepts Analysis Engine                              |
//+------------------------------------------------------------------+
class CClawSMC
{
private:
   // Indicator handles
   int m_atrHandle;
   double m_atr[];

   // Symbol and timeframe
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   int m_digits;

   // Configuration
   int    m_swingStrength;       // Bars each side for swing detection
   double m_impulseATRMult;      // Minimum impulse = ATR * this
   int    m_obMaxAge;            // Max bars an OB stays valid
   double m_fvgMinSize;          // Minimum FVG size in price
   double m_fvgMaxSize;          // Maximum FVG size in price
   int    m_fvgMaxAge;           // Max bars an FVG stays valid
   double m_sweepToleranceATR;   // Max sweep depth as ATR multiple
   double m_roundNumberInterval; // $50 for gold

   // Swing points (rolling buffer)
   SMCSwingPoint m_swingPoints[];
   int m_swingCount;

   // Order Blocks
   SMCOrderBlock m_orderBlocks[];
   int m_obCount;

   // Fair Value Gaps
   SMCFairValueGap m_fvgs[];
   int m_fvgCount;

   // Liquidity Levels
   SMCLiquidityLevel m_liqLevels[];
   int m_liqCount;

   // Market structure state
   ENUM_MARKET_TREND    m_marketTrend;
   ENUM_STRUCTURE_EVENT m_lastStructEvent;
   ENUM_PRICE_ZONE      m_priceZone;
   double m_swingRangeHigh;   // Current swing range top
   double m_swingRangeLow;    // Current swing range bottom

   // OTE state
   bool   m_oteActive;
   double m_oteHigh;           // Top of OTE zone (0.618 level)
   double m_oteLow;            // Bottom of OTE zone (0.786 level)
   int    m_oteDirection;      // +1 = bullish OTE, -1 = bearish OTE

   // Liquidity sweep state
   bool   m_sweepDetected;
   int    m_sweepDirection;    // +1 = bullish sweep (buy signal), -1 = bearish

   bool m_initialized;

   // Internal methods
   void DetectSwingPoints(const double &high[], const double &low[],
                          const datetime &time[], int bars);
   void UpdateMarketStructure(const double &close[], int bars);
   void DetectOrderBlocks(const double &open[], const double &high[],
                          const double &low[], const double &close[],
                          const datetime &time[], int bars);
   void DetectFairValueGaps(const double &high[], const double &low[],
                            const datetime &time[], int bars);
   void UpdateLiquidityLevels(const double &high[], const double &low[],
                              const double &close[]);
   void UpdatePriceZone(double currentPrice);
   void DetectLiquiditySweeps(const double &high[], const double &low[],
                              const double &close[], const double &open[]);
   void CalculateOTE(const double &close[]);
   void MitigateOBs(const double &high[], const double &low[],
                     const double &close[]);
   void MitigateFVGs(const double &high[], const double &low[]);
   void AddSwingPoint(double price, datetime time, int barIdx, bool isHigh);
   void AddOrderBlock(double zHigh, double zLow, double bHigh, double bLow,
                      datetime time, int barIdx, int dir);
   void AddFVG(double gHigh, double gLow, datetime time, int barIdx, int dir);
   void AddLiquidityLevel(double price, datetime time, int type);

   // Helpers
   SMCSwingPoint GetLastSwingHigh(int skip = 0);
   SMCSwingPoint GetLastSwingLow(int skip = 0);

public:
   CClawSMC();
   ~CClawSMC();

   bool Init(string symbol, ENUM_TIMEFRAMES tf,
             int swingStrength = 3,
             double impulseATRMult = 2.5,
             int obMaxAge = 72,
             double fvgMinSize = 2.0,
             double fvgMaxSize = 15.0,
             int fvgMaxAge = 50,
             double sweepTolATR = 1.5,
             double roundNumInterval = 50.0);
   void Deinit();

   // Call on each new bar to update all SMC data
   void Update();

   // Getters for brain/strategy use
   ENUM_MARKET_TREND    GetMarketTrend()       { return m_marketTrend; }
   ENUM_STRUCTURE_EVENT GetLastStructEvent()    { return m_lastStructEvent; }
   ENUM_PRICE_ZONE      GetPriceZone()         { return m_priceZone; }
   double               GetSwingRangeHigh()    { return m_swingRangeHigh; }
   double               GetSwingRangeLow()     { return m_swingRangeLow; }
   bool                 IsOTEActive()          { return m_oteActive; }
   int                  GetOTEDirection()       { return m_oteDirection; }
   double               GetOTEHigh()           { return m_oteHigh; }
   double               GetOTELow()            { return m_oteLow; }
   bool                 WasSweepDetected()     { return m_sweepDetected; }
   int                  GetSweepDirection()    { return m_sweepDirection; }

   // Query methods
   bool HasBullishOB(double currentPrice, double &zoneHigh, double &zoneLow);
   bool HasBearishOB(double currentPrice, double &zoneHigh, double &zoneLow);
   bool HasBullishFVG(double currentPrice, double &gapHigh, double &gapLow);
   bool HasBearishFVG(double currentPrice, double &gapHigh, double &gapLow);
   double GetNearestRoundNumber(double price, int direction);

   // Composite SMC signal
   SignalResult Evaluate();

   // Target finding for dynamic TP
   double GetNearestBuyTarget(double currentPrice);
   double GetNearestSellTarget(double currentPrice);

   string GetName() { return "SMC"; }
};

//+------------------------------------------------------------------+
CClawSMC::CClawSMC()
{
   m_initialized   = false;
   m_atrHandle     = INVALID_HANDLE;
   m_swingCount    = 0;
   m_obCount       = 0;
   m_fvgCount      = 0;
   m_liqCount      = 0;
   m_marketTrend   = TREND_UNDEFINED;
   m_lastStructEvent = STRUCT_NONE;
   m_priceZone     = ZONE_EQUILIBRIUM;
   m_swingRangeHigh = 0;
   m_swingRangeLow  = 0;
   m_oteActive     = false;
   m_sweepDetected = false;
   m_sweepDirection = 0;
}

//+------------------------------------------------------------------+
CClawSMC::~CClawSMC()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawSMC::Init(string symbol, ENUM_TIMEFRAMES tf,
                     int swingStrength, double impulseATRMult,
                     int obMaxAge, double fvgMinSize, double fvgMaxSize,
                     int fvgMaxAge, double sweepTolATR, double roundNumInterval)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_digits    = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   m_swingStrength       = swingStrength;
   m_impulseATRMult      = impulseATRMult;
   m_obMaxAge            = obMaxAge;
   m_fvgMinSize          = fvgMinSize;
   m_fvgMaxSize          = fvgMaxSize;
   m_fvgMaxAge           = fvgMaxAge;
   m_sweepToleranceATR   = sweepTolATR;
   m_roundNumberInterval = roundNumInterval;

   m_atrHandle = iATR(m_symbol, m_timeframe, 14);
   if(m_atrHandle == INVALID_HANDLE)
   {
      LogMessage("SMC", "Failed to create ATR handle. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_atr, true);
   ArrayResize(m_swingPoints, SMC_MAX_SWING_POINTS);
   ArrayResize(m_orderBlocks, SMC_MAX_ORDER_BLOCKS);
   ArrayResize(m_fvgs, SMC_MAX_FVGS);
   ArrayResize(m_liqLevels, SMC_MAX_LIQ_LEVELS);

   m_initialized = true;
   LogMessage("SMC", "Smart Money Concepts module initialized (swing=" +
              IntegerToString(swingStrength) + ", OB_age=" + IntegerToString(obMaxAge) + ")");
   return true;
}

//+------------------------------------------------------------------+
void CClawSMC::Deinit()
{
   if(m_atrHandle != INVALID_HANDLE) { IndicatorRelease(m_atrHandle); m_atrHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Master update - call on each new bar                              |
//+------------------------------------------------------------------+
void CClawSMC::Update()
{
   if(!m_initialized) return;

   int bars = SMC_LOOKBACK;

   // Copy price data
   double open[], high[], low[], close[];
   datetime time[];
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);
   ArraySetAsSeries(time, true);

   if(CopyOpen(m_symbol, m_timeframe, 0, bars, open)   < bars) return;
   if(CopyHigh(m_symbol, m_timeframe, 0, bars, high)   < bars) return;
   if(CopyLow(m_symbol, m_timeframe, 0, bars, low)     < bars) return;
   if(CopyClose(m_symbol, m_timeframe, 0, bars, close) < bars) return;
   if(CopyTime(m_symbol, m_timeframe, 0, bars, time)   < bars) return;
   if(CopyBuffer(m_atrHandle, 0, 0, bars, m_atr)       < bars) return;

   // Reset per-bar events
   m_lastStructEvent = STRUCT_NONE;
   m_sweepDetected   = false;

   // Step 1: Detect swing points
   DetectSwingPoints(high, low, time, bars);

   // Step 2: Update market structure (trend, BOS, CHoCH)
   UpdateMarketStructure(close, bars);

   // Step 3: Detect order blocks (after impulse moves)
   DetectOrderBlocks(open, high, low, close, time, bars);

   // Step 4: Detect fair value gaps
   DetectFairValueGaps(high, low, time, bars);

   // Step 5: Update liquidity levels
   UpdateLiquidityLevels(high, low, close);

   // Step 6: Mitigate old OBs and FVGs
   MitigateOBs(high, low, close);
   MitigateFVGs(high, low);

   // Step 7: Update price zone
   UpdatePriceZone(close[1]);

   // Step 8: Check for liquidity sweeps
   DetectLiquiditySweeps(high, low, close, open);

   // Step 9: Calculate OTE zone after BOS/CHoCH
   CalculateOTE(close);
}

//+------------------------------------------------------------------+
//| Detect swing highs and lows using N-bar window                    |
//+------------------------------------------------------------------+
void CClawSMC::DetectSwingPoints(const double &high[], const double &low[],
                                  const datetime &time[], int bars)
{
   int N = m_swingStrength;

   // Reset swing array for fresh scan
   m_swingCount = 0;

   // Scan from bar N+1 (to avoid bar[0] repainting) to lookback
   for(int i = N + 1; i < bars - N && m_swingCount < SMC_MAX_SWING_POINTS; i++)
   {
      bool isSwingHigh = true;
      bool isSwingLow  = true;

      for(int j = 1; j <= N; j++)
      {
         // More recent neighbors (smaller index)
         if(high[i] <= high[i - j]) isSwingHigh = false;
         if(low[i]  >= low[i - j])  isSwingLow  = false;

         // Older neighbors (larger index)
         if(high[i] <= high[i + j]) isSwingHigh = false;
         if(low[i]  >= low[i + j])  isSwingLow  = false;
      }

      if(isSwingHigh)
         AddSwingPoint(high[i], time[i], i, true);
      if(isSwingLow)
         AddSwingPoint(low[i], time[i], i, false);
   }
}

//+------------------------------------------------------------------+
void CClawSMC::AddSwingPoint(double price, datetime t, int barIdx, bool isHigh)
{
   if(m_swingCount >= SMC_MAX_SWING_POINTS) return;

   m_swingPoints[m_swingCount].price    = price;
   m_swingPoints[m_swingCount].time     = t;
   m_swingPoints[m_swingCount].barIndex = barIdx;
   m_swingPoints[m_swingCount].isHigh   = isHigh;
   m_swingPoints[m_swingCount].broken   = false;
   m_swingCount++;
}

//+------------------------------------------------------------------+
//| Get the Nth most recent swing high (skip=0 for latest)            |
//+------------------------------------------------------------------+
SMCSwingPoint CClawSMC::GetLastSwingHigh(int skip)
{
   SMCSwingPoint empty;
   ZeroMemory(empty);
   int found = 0;
   for(int i = 0; i < m_swingCount; i++)
   {
      if(m_swingPoints[i].isHigh)
      {
         if(found == skip) return m_swingPoints[i];
         found++;
      }
   }
   return empty;
}

//+------------------------------------------------------------------+
SMCSwingPoint CClawSMC::GetLastSwingLow(int skip)
{
   SMCSwingPoint empty;
   ZeroMemory(empty);
   int found = 0;
   for(int i = 0; i < m_swingCount; i++)
   {
      if(!m_swingPoints[i].isHigh)
      {
         if(found == skip) return m_swingPoints[i];
         found++;
      }
   }
   return empty;
}

//+------------------------------------------------------------------+
//| Update market structure: trend direction + BOS/CHoCH events       |
//+------------------------------------------------------------------+
void CClawSMC::UpdateMarketStructure(const double &close[], int bars)
{
   // Need at least 4 swing points for structure analysis
   SMCSwingPoint sh0 = GetLastSwingHigh(0);  // Most recent swing high
   SMCSwingPoint sh1 = GetLastSwingHigh(1);  // Previous swing high
   SMCSwingPoint sl0 = GetLastSwingLow(0);   // Most recent swing low
   SMCSwingPoint sl1 = GetLastSwingLow(1);   // Previous swing low

   if(sh0.price == 0 || sh1.price == 0 || sl0.price == 0 || sl1.price == 0)
   {
      m_marketTrend = TREND_UNDEFINED;
      return;
   }

   // Update swing range
   m_swingRangeHigh = sh0.price;
   m_swingRangeLow  = sl0.price;

   // Determine structure pattern
   bool higherHigh = (sh0.price > sh1.price);
   bool higherLow  = (sl0.price > sl1.price);
   bool lowerHigh  = (sh0.price < sh1.price);
   bool lowerLow   = (sl0.price < sl1.price);

   ENUM_MARKET_TREND prevTrend = m_marketTrend;

   // Classic HH+HL = bullish, LH+LL = bearish
   if(higherHigh && higherLow)
      m_marketTrend = TREND_BULLISH;
   else if(lowerHigh && lowerLow)
      m_marketTrend = TREND_BEARISH;
   else
      m_marketTrend = TREND_UNDEFINED;

   // BOS/CHoCH detection using most recent close
   double currentClose = close[1]; // Completed bar

   // BOS: price breaks a swing point IN the trend direction
   if(m_marketTrend == TREND_BULLISH && currentClose > sh0.price && !sh0.broken)
   {
      m_lastStructEvent = STRUCT_BOS_BULLISH;
      // Mark as broken
      for(int i = 0; i < m_swingCount; i++)
         if(m_swingPoints[i].isHigh && m_swingPoints[i].price == sh0.price)
            m_swingPoints[i].broken = true;
   }
   else if(m_marketTrend == TREND_BEARISH && currentClose < sl0.price && !sl0.broken)
   {
      m_lastStructEvent = STRUCT_BOS_BEARISH;
      for(int i = 0; i < m_swingCount; i++)
         if(!m_swingPoints[i].isHigh && m_swingPoints[i].price == sl0.price)
            m_swingPoints[i].broken = true;
   }

   // CHoCH: price breaks a swing point AGAINST the trend direction
   if(prevTrend == TREND_BEARISH && currentClose > sh0.price)
   {
      m_lastStructEvent = STRUCT_CHOCH_BULLISH;
      m_marketTrend = TREND_BULLISH;
   }
   else if(prevTrend == TREND_BULLISH && currentClose < sl0.price)
   {
      m_lastStructEvent = STRUCT_CHOCH_BEARISH;
      m_marketTrend = TREND_BEARISH;
   }
}

//+------------------------------------------------------------------+
//| Detect Order Blocks after impulsive moves                         |
//+------------------------------------------------------------------+
void CClawSMC::DetectOrderBlocks(const double &open[], const double &high[],
                                  const double &low[], const double &close[],
                                  const datetime &time[], int bars)
{
   if(m_atr[1] <= 0) return;
   double impulseThreshold = m_atr[1] * m_impulseATRMult;

   // Age out old OBs (use timeCreated for real elapsed bars, not static barIndex)
   int periodSec = PeriodSeconds(m_timeframe);
   for(int k = m_obCount - 1; k >= 0; k--)
   {
      int age = (periodSec > 0) ? (int)((TimeCurrent() - m_orderBlocks[k].timeCreated) / periodSec) : m_orderBlocks[k].barIndex;
      if(age > m_obMaxAge || m_orderBlocks[k].mitigated || m_orderBlocks[k].touchCount >= 2)
      {
         // Remove by shifting array
         for(int j = k; j < m_obCount - 1; j++)
            m_orderBlocks[j] = m_orderBlocks[j + 1];
         m_obCount--;
      }
   }

   // Scan for 3-bar impulse moves (bars 2 to lookback-4)
   int scanEnd = (int)MathMin(bars - 4, 60);
   for(int i = 2; i < scanEnd; i++)
   {
      // 3-bar impulse from bar[i+2] (oldest) to bar[i] (newest)
      double displacement = close[i] - open[i + 2];

      // Bullish impulse
      if(displacement > impulseThreshold)
      {
         // Find the last bearish candle before the impulse (at bar i+3 or further)
         for(int j = i + 3; j < i + 7 && j < bars; j++)
         {
            if(close[j] < open[j]) // Bearish candle = bullish OB
            {
               // Check if this OB already exists (avoid duplicates)
               bool exists = false;
               for(int e = 0; e < m_obCount; e++)
                  if(MathAbs(m_orderBlocks[e].zoneHigh - high[j]) < m_atr[1] * 0.1 &&
                     m_orderBlocks[e].direction == 1)
                     exists = true;

               if(!exists)
               {
                  double bHigh = MathMax(open[j], close[j]);
                  double bLow  = MathMin(open[j], close[j]);
                  AddOrderBlock(high[j], low[j], bHigh, bLow, time[j], j, 1);
               }
               break;
            }
         }
      }
      // Bearish impulse
      else if(-displacement > impulseThreshold)
      {
         for(int j = i + 3; j < i + 7 && j < bars; j++)
         {
            if(close[j] > open[j]) // Bullish candle = bearish OB
            {
               bool exists = false;
               for(int e = 0; e < m_obCount; e++)
                  if(MathAbs(m_orderBlocks[e].zoneLow - low[j]) < m_atr[1] * 0.1 &&
                     m_orderBlocks[e].direction == -1)
                     exists = true;

               if(!exists)
               {
                  double bHigh = MathMax(open[j], close[j]);
                  double bLow  = MathMin(open[j], close[j]);
                  AddOrderBlock(high[j], low[j], bHigh, bLow, time[j], j, -1);
               }
               break;
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
void CClawSMC::AddOrderBlock(double zHigh, double zLow, double bHigh, double bLow,
                               datetime t, int barIdx, int dir)
{
   if(m_obCount >= SMC_MAX_ORDER_BLOCKS)
   {
      // Remove oldest
      for(int i = 0; i < m_obCount - 1; i++)
         m_orderBlocks[i] = m_orderBlocks[i + 1];
      m_obCount--;
   }

   m_orderBlocks[m_obCount].zoneHigh    = zHigh;
   m_orderBlocks[m_obCount].zoneLow     = zLow;
   m_orderBlocks[m_obCount].bodyHigh    = bHigh;
   m_orderBlocks[m_obCount].bodyLow     = bLow;
   m_orderBlocks[m_obCount].timeCreated = t;
   m_orderBlocks[m_obCount].barIndex    = barIdx;
   m_orderBlocks[m_obCount].direction   = dir;
   m_orderBlocks[m_obCount].mitigated   = false;
   m_orderBlocks[m_obCount].tested      = false;
   m_orderBlocks[m_obCount].touchCount  = 0;
   m_obCount++;
}

//+------------------------------------------------------------------+
//| Detect Fair Value Gaps (3-candle pattern)                         |
//+------------------------------------------------------------------+
void CClawSMC::DetectFairValueGaps(const double &high[], const double &low[],
                                    const datetime &time[], int bars)
{
   // Age out old FVGs (use timeCreated for real elapsed bars, not static barIndex)
   int fvgPeriodSec = PeriodSeconds(m_timeframe);
   for(int k = m_fvgCount - 1; k >= 0; k--)
   {
      int fvgAge = (fvgPeriodSec > 0) ? (int)((TimeCurrent() - m_fvgs[k].timeCreated) / fvgPeriodSec) : m_fvgs[k].barIndex;
      if(fvgAge > m_fvgMaxAge || m_fvgs[k].mitigated)
      {
         for(int j = k; j < m_fvgCount - 1; j++)
            m_fvgs[j] = m_fvgs[j + 1];
         m_fvgCount--;
      }
   }

   int scanEnd = (int)MathMin(bars - 2, 50);
   for(int i = 1; i < scanEnd; i++)
   {
      // candle1 = bar[i+2] (oldest), candle2 = bar[i+1] (middle), candle3 = bar[i] (newest)

      // Bullish FVG: candle1.high < candle3.low
      if(low[i] > high[i + 2])
      {
         double gapSize = low[i] - high[i + 2];
         if(gapSize >= m_fvgMinSize && gapSize <= m_fvgMaxSize)
         {
            bool exists = false;
            for(int e = 0; e < m_fvgCount; e++)
               if(MathAbs(m_fvgs[e].gapHigh - low[i]) < 0.5 && m_fvgs[e].direction == 1)
                  exists = true;
            if(!exists)
               AddFVG(low[i], high[i + 2], time[i + 1], i + 1, 1);
         }
      }

      // Bearish FVG: candle1.low > candle3.high
      if(high[i] < low[i + 2])
      {
         double gapSize = low[i + 2] - high[i];
         if(gapSize >= m_fvgMinSize && gapSize <= m_fvgMaxSize)
         {
            bool exists = false;
            for(int e = 0; e < m_fvgCount; e++)
               if(MathAbs(m_fvgs[e].gapLow - high[i]) < 0.5 && m_fvgs[e].direction == -1)
                  exists = true;
            if(!exists)
               AddFVG(low[i + 2], high[i], time[i + 1], i + 1, -1);
         }
      }
   }
}

//+------------------------------------------------------------------+
void CClawSMC::AddFVG(double gHigh, double gLow, datetime t, int barIdx, int dir)
{
   if(m_fvgCount >= SMC_MAX_FVGS)
   {
      for(int i = 0; i < m_fvgCount - 1; i++)
         m_fvgs[i] = m_fvgs[i + 1];
      m_fvgCount--;
   }

   m_fvgs[m_fvgCount].gapHigh     = gHigh;
   m_fvgs[m_fvgCount].gapLow      = gLow;
   m_fvgs[m_fvgCount].midpoint    = (gHigh + gLow) / 2.0;
   m_fvgs[m_fvgCount].timeCreated = t;
   m_fvgs[m_fvgCount].barIndex    = barIdx;
   m_fvgs[m_fvgCount].direction   = dir;
   m_fvgs[m_fvgCount].mitigated   = false;
   m_fvgCount++;
}

//+------------------------------------------------------------------+
//| Update liquidity levels: swing H/L, equal H/L, round numbers     |
//+------------------------------------------------------------------+
void CClawSMC::UpdateLiquidityLevels(const double &high[], const double &low[],
                                      const double &close[])
{
   m_liqCount = 0;

   // Add swing highs and lows as liquidity
   for(int i = 0; i < m_swingCount && m_liqCount < SMC_MAX_LIQ_LEVELS; i++)
   {
      AddLiquidityLevel(m_swingPoints[i].price, m_swingPoints[i].time, 0);
   }

   // Detect equal highs/lows (two swing points within ATR*0.1)
   double tolerance = m_atr[1] * 0.1;
   for(int i = 0; i < m_swingCount && m_liqCount < SMC_MAX_LIQ_LEVELS; i++)
   {
      for(int j = i + 1; j < m_swingCount; j++)
      {
         if(m_swingPoints[i].isHigh == m_swingPoints[j].isHigh &&
            MathAbs(m_swingPoints[i].price - m_swingPoints[j].price) < tolerance)
         {
            // Equal highs/lows - strong liquidity pool
            double avgPrice = (m_swingPoints[i].price + m_swingPoints[j].price) / 2.0;
            AddLiquidityLevel(avgPrice, m_swingPoints[i].time, 1);
            break;
         }
      }
   }

   // Add round numbers near current price
   double currentPrice = close[1];
   double baseLevel = MathFloor(currentPrice / m_roundNumberInterval) * m_roundNumberInterval;
   for(int r = -2; r <= 3 && m_liqCount < SMC_MAX_LIQ_LEVELS; r++)
   {
      double roundLevel = baseLevel + r * m_roundNumberInterval;
      if(roundLevel > 0)
         AddLiquidityLevel(roundLevel, TimeCurrent(), 3);
   }
}

//+------------------------------------------------------------------+
void CClawSMC::AddLiquidityLevel(double price, datetime t, int type)
{
   if(m_liqCount >= SMC_MAX_LIQ_LEVELS) return;

   // Avoid duplicates
   for(int i = 0; i < m_liqCount; i++)
      if(MathAbs(m_liqLevels[i].price - price) < 1.0) return;

   m_liqLevels[m_liqCount].price      = price;
   m_liqLevels[m_liqCount].time       = t;
   m_liqLevels[m_liqCount].levelType  = type;
   m_liqLevels[m_liqCount].touchCount = 1;
   m_liqLevels[m_liqCount].swept      = false;
   m_liqCount++;
}

//+------------------------------------------------------------------+
//| Mitigate order blocks: invalidate when price closes through       |
//+------------------------------------------------------------------+
void CClawSMC::MitigateOBs(const double &high[], const double &low[],
                             const double &close[])
{
   for(int i = 0; i < m_obCount; i++)
   {
      if(m_orderBlocks[i].mitigated) continue;

      if(m_orderBlocks[i].direction == 1) // Bullish OB
      {
         // Price enters zone (first touch)
         if(low[1] <= m_orderBlocks[i].zoneHigh && low[1] >= m_orderBlocks[i].zoneLow)
         {
            if(!m_orderBlocks[i].tested)
               m_orderBlocks[i].tested = true;
            m_orderBlocks[i].touchCount++;
         }
         // Mitigated: price closes below zone
         if(close[1] < m_orderBlocks[i].zoneLow)
            m_orderBlocks[i].mitigated = true;
      }
      else // Bearish OB
      {
         if(high[1] >= m_orderBlocks[i].zoneLow && high[1] <= m_orderBlocks[i].zoneHigh)
         {
            if(!m_orderBlocks[i].tested)
               m_orderBlocks[i].tested = true;
            m_orderBlocks[i].touchCount++;
         }
         if(close[1] > m_orderBlocks[i].zoneHigh)
            m_orderBlocks[i].mitigated = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Mitigate FVGs: invalidate when price fills the gap                |
//+------------------------------------------------------------------+
void CClawSMC::MitigateFVGs(const double &high[], const double &low[])
{
   for(int i = 0; i < m_fvgCount; i++)
   {
      if(m_fvgs[i].mitigated) continue;

      if(m_fvgs[i].direction == 1) // Bullish FVG
      {
         // Mitigated when price drops through the gap
         if(low[1] <= m_fvgs[i].gapLow)
            m_fvgs[i].mitigated = true;
      }
      else // Bearish FVG
      {
         if(high[1] >= m_fvgs[i].gapHigh)
            m_fvgs[i].mitigated = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Update premium/discount zone based on current swing range         |
//+------------------------------------------------------------------+
void CClawSMC::UpdatePriceZone(double currentPrice)
{
   if(m_swingRangeHigh <= m_swingRangeLow || m_swingRangeHigh == 0)
   {
      m_priceZone = ZONE_EQUILIBRIUM;
      return;
   }

   double range = m_swingRangeHigh - m_swingRangeLow;
   double position = (currentPrice - m_swingRangeLow) / range;

   if(position >= 0.75)      m_priceZone = ZONE_EXTREME_PREMIUM;
   else if(position >= 0.62) m_priceZone = ZONE_PREMIUM;
   else if(position >= 0.38) m_priceZone = ZONE_EQUILIBRIUM;
   else if(position >= 0.25) m_priceZone = ZONE_DISCOUNT;
   else                      m_priceZone = ZONE_EXTREME_DISCOUNT;
}

//+------------------------------------------------------------------+
//| Detect liquidity sweeps on the most recent bar                    |
//+------------------------------------------------------------------+
void CClawSMC::DetectLiquiditySweeps(const double &high[], const double &low[],
                                      const double &close[], const double &open[])
{
   m_sweepDetected  = false;
   m_sweepDirection = 0;

   if(m_atr[1] <= 0) return;
   double maxSweepDepth = m_atr[1] * m_sweepToleranceATR;
   double minSweepDepth = m_atr[1] * 0.05;

   for(int i = 0; i < m_liqCount; i++)
   {
      if(m_liqLevels[i].swept) continue;
      double level = m_liqLevels[i].price;

      // Bullish sweep: wick below liquidity (sell stops taken), close above
      double sweepBelow = level - low[1];
      if(sweepBelow > minSweepDepth && sweepBelow < maxSweepDepth &&
         close[1] > level && close[1] > open[1])
      {
         m_sweepDetected  = true;
         m_sweepDirection = 1; // Bullish (buy signal)
         m_liqLevels[i].swept = true;
         return;
      }

      // Bearish sweep: wick above liquidity (buy stops taken), close below
      double sweepAbove = high[1] - level;
      if(sweepAbove > minSweepDepth && sweepAbove < maxSweepDepth &&
         close[1] < level && close[1] < open[1])
      {
         m_sweepDetected  = true;
         m_sweepDirection = -1; // Bearish (sell signal)
         m_liqLevels[i].swept = true;
         return;
      }
   }
}

//+------------------------------------------------------------------+
//| Calculate OTE zone after BOS/CHoCH events                        |
//+------------------------------------------------------------------+
void CClawSMC::CalculateOTE(const double &close[])
{
   // OTE is only valid after a structure break
   if(m_lastStructEvent == STRUCT_NONE)
   {
      // Decay OTE if price has moved beyond it
      if(m_oteActive)
      {
         if(m_oteDirection == 1 && close[1] < m_oteLow)
            m_oteActive = false;
         else if(m_oteDirection == -1 && close[1] > m_oteHigh)
            m_oteActive = false;
      }
      return;
   }

   SMCSwingPoint sh = GetLastSwingHigh(0);
   SMCSwingPoint sl = GetLastSwingLow(0);

   if(sh.price == 0 || sl.price == 0) return;

   // Bullish OTE: after bullish BOS/CHoCH, retrace to 0.618-0.786 of the swing
   if(m_lastStructEvent == STRUCT_BOS_BULLISH || m_lastStructEvent == STRUCT_CHOCH_BULLISH)
   {
      double range = sh.price - sl.price;
      if(range > 0)
      {
         m_oteHigh      = sh.price - range * 0.618;   // Upper limit of OTE
         m_oteLow       = sh.price - range * 0.786;   // Lower limit of OTE
         m_oteDirection  = 1;
         m_oteActive    = true;
      }
   }
   // Bearish OTE: after bearish BOS/CHoCH
   else if(m_lastStructEvent == STRUCT_BOS_BEARISH || m_lastStructEvent == STRUCT_CHOCH_BEARISH)
   {
      double range = sh.price - sl.price;
      if(range > 0)
      {
         m_oteLow       = sl.price + range * 0.618;
         m_oteHigh      = sl.price + range * 0.786;
         m_oteDirection  = -1;
         m_oteActive    = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Query: nearest unmitigated bullish OB at or below current price   |
//+------------------------------------------------------------------+
bool CClawSMC::HasBullishOB(double currentPrice, double &zoneHigh, double &zoneLow)
{
   double closest = DBL_MAX;
   int bestIdx = -1;

   for(int i = 0; i < m_obCount; i++)
   {
      if(m_orderBlocks[i].direction != 1) continue;
      if(m_orderBlocks[i].mitigated) continue;

      // OB should be at or below current price (we want to buy into demand)
      double dist = currentPrice - m_orderBlocks[i].bodyHigh;
      if(dist >= 0 && dist < closest)
      {
         closest = dist;
         bestIdx = i;
      }
      // Also check if price is currently inside the OB
      if(currentPrice <= m_orderBlocks[i].zoneHigh &&
         currentPrice >= m_orderBlocks[i].zoneLow)
      {
         zoneHigh = m_orderBlocks[i].bodyHigh;
         zoneLow  = m_orderBlocks[i].bodyLow;
         return true;
      }
   }

   if(bestIdx >= 0 && closest < m_atr[1] * 3.0)
   {
      zoneHigh = m_orderBlocks[bestIdx].bodyHigh;
      zoneLow  = m_orderBlocks[bestIdx].bodyLow;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool CClawSMC::HasBearishOB(double currentPrice, double &zoneHigh, double &zoneLow)
{
   double closest = DBL_MAX;
   int bestIdx = -1;

   for(int i = 0; i < m_obCount; i++)
   {
      if(m_orderBlocks[i].direction != -1) continue;
      if(m_orderBlocks[i].mitigated) continue;

      double dist = m_orderBlocks[i].bodyLow - currentPrice;
      if(dist >= 0 && dist < closest)
      {
         closest = dist;
         bestIdx = i;
      }
      if(currentPrice <= m_orderBlocks[i].zoneHigh &&
         currentPrice >= m_orderBlocks[i].zoneLow)
      {
         zoneHigh = m_orderBlocks[i].bodyHigh;
         zoneLow  = m_orderBlocks[i].bodyLow;
         return true;
      }
   }

   if(bestIdx >= 0 && closest < m_atr[1] * 3.0)
   {
      zoneHigh = m_orderBlocks[bestIdx].bodyHigh;
      zoneLow  = m_orderBlocks[bestIdx].bodyLow;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
bool CClawSMC::HasBullishFVG(double currentPrice, double &gapHigh, double &gapLow)
{
   for(int i = 0; i < m_fvgCount; i++)
   {
      if(m_fvgs[i].direction != 1 || m_fvgs[i].mitigated) continue;

      // Check if price is near/inside the FVG
      if(currentPrice <= m_fvgs[i].gapHigh &&
         currentPrice >= m_fvgs[i].gapLow - m_atr[1] * 0.5)
      {
         gapHigh = m_fvgs[i].gapHigh;
         gapLow  = m_fvgs[i].gapLow;
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
bool CClawSMC::HasBearishFVG(double currentPrice, double &gapHigh, double &gapLow)
{
   for(int i = 0; i < m_fvgCount; i++)
   {
      if(m_fvgs[i].direction != -1 || m_fvgs[i].mitigated) continue;

      if(currentPrice >= m_fvgs[i].gapLow &&
         currentPrice <= m_fvgs[i].gapHigh + m_atr[1] * 0.5)
      {
         gapHigh = m_fvgs[i].gapHigh;
         gapLow  = m_fvgs[i].gapLow;
         return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
double CClawSMC::GetNearestRoundNumber(double price, int direction)
{
   double base = MathFloor(price / m_roundNumberInterval) * m_roundNumberInterval;
   if(direction > 0)
      return base + m_roundNumberInterval;
   else
      return base;
}

//+------------------------------------------------------------------+
//| Composite SMC signal evaluation                                   |
//| Scores each SMC confluence and returns combined signal            |
//+------------------------------------------------------------------+
SignalResult CClawSMC::Evaluate()
{
   SignalResult result;
   result.Reset();

   if(!m_initialized) return result;

   double currentPrice = iClose(m_symbol, m_timeframe, 1);
   if(currentPrice <= 0) return result;

   int buyScore  = 0;
   int sellScore = 0;
   int buyConf   = 0;
   int sellConf  = 0;
   string buyReasons = "";
   string sellReasons = "";
   double buyEntry = 0, sellEntry = 0;
   double buySL = 0, sellSL = 0;
   double buyTP = 0, sellTP = 0;

   // --- 1. Market Structure Direction (+8) ---
   if(m_marketTrend == TREND_BULLISH)
   {
      buyScore += 8;
      buyReasons += "Bullish_struct ";
   }
   else if(m_marketTrend == TREND_BEARISH)
   {
      sellScore += 8;
      sellReasons += "Bearish_struct ";
   }

   // --- 2. BOS/CHoCH events (+8) ---
   if(m_lastStructEvent == STRUCT_BOS_BULLISH)
   {
      buyScore += 8; buyConf++;
      buyReasons += "BOS_bull ";
   }
   else if(m_lastStructEvent == STRUCT_BOS_BEARISH)
   {
      sellScore += 8; sellConf++;
      sellReasons += "BOS_bear ";
   }
   else if(m_lastStructEvent == STRUCT_CHOCH_BULLISH)
   {
      buyScore += 10; buyConf++;
      buyReasons += "CHoCH_bull ";
   }
   else if(m_lastStructEvent == STRUCT_CHOCH_BEARISH)
   {
      sellScore += 10; sellConf++;
      sellReasons += "CHoCH_bear ";
   }

   // --- 3. Order Blocks (+10) ---
   double obHigh = 0, obLow = 0;
   if(HasBullishOB(currentPrice, obHigh, obLow))
   {
      buyScore += 10; buyConf++;
      buyReasons += "Bull_OB ";
      buyEntry = obHigh;  // Entry at top of refined OB
      buySL = obLow - m_atr[1] * 0.3; // SL below OB
   }
   if(HasBearishOB(currentPrice, obHigh, obLow))
   {
      sellScore += 10; sellConf++;
      sellReasons += "Bear_OB ";
      sellEntry = obLow;
      sellSL = obHigh + m_atr[1] * 0.3;
   }

   // --- 4. Fair Value Gaps (+8) ---
   double fvgHigh = 0, fvgLow = 0;
   if(HasBullishFVG(currentPrice, fvgHigh, fvgLow))
   {
      buyScore += 8; buyConf++;
      buyReasons += "Bull_FVG ";
      if(buyEntry == 0) buyEntry = (fvgHigh + fvgLow) / 2.0; // CE entry
   }
   if(HasBearishFVG(currentPrice, fvgHigh, fvgLow))
   {
      sellScore += 8; sellConf++;
      sellReasons += "Bear_FVG ";
      if(sellEntry == 0) sellEntry = (fvgHigh + fvgLow) / 2.0;
   }

   // --- 5. Premium/Discount Zone (+6) ---
   if(m_priceZone == ZONE_DISCOUNT || m_priceZone == ZONE_EXTREME_DISCOUNT)
   {
      buyScore += 6; buyConf++;
      buyReasons += "Discount ";
   }
   else if(m_priceZone == ZONE_PREMIUM || m_priceZone == ZONE_EXTREME_PREMIUM)
   {
      sellScore += 6; sellConf++;
      sellReasons += "Premium ";
   }

   // --- 6. OTE Zone (+4) ---
   if(m_oteActive)
   {
      if(m_oteDirection == 1 && currentPrice >= m_oteLow && currentPrice <= m_oteHigh)
      {
         buyScore += 4; buyConf++;
         buyReasons += "OTE ";
         if(buyEntry == 0) buyEntry = (m_oteHigh + m_oteLow) / 2.0;
      }
      else if(m_oteDirection == -1 && currentPrice >= m_oteLow && currentPrice <= m_oteHigh)
      {
         sellScore += 4; sellConf++;
         sellReasons += "OTE ";
         if(sellEntry == 0) sellEntry = (m_oteHigh + m_oteLow) / 2.0;
      }
   }

   // --- 7. Liquidity Sweep (+8) ---
   if(m_sweepDetected)
   {
      if(m_sweepDirection == 1)
      {
         buyScore += 8; buyConf++;
         buyReasons += "Liq_sweep ";
      }
      else
      {
         sellScore += 8; sellConf++;
         sellReasons += "Liq_sweep ";
      }
   }

   // --- Determine final direction ---
   if(buyScore > sellScore && buyScore >= 14)
   {
      result.direction     = SIGNAL_BUY;
      result.score         = (int)MathMin(buyScore, 40);
      result.reason        = buyReasons;
      result.entryPrice    = NormalizeDouble(buyEntry, m_digits);
      result.suggestedSL   = NormalizeDouble(buySL, m_digits);
      result.smcConfluence = buyConf;

      // TP: swing range high or next round number
      if(m_swingRangeHigh > currentPrice)
         result.suggestedTP = NormalizeDouble(m_swingRangeHigh, m_digits);
   }
   else if(sellScore > buyScore && sellScore >= 14)
   {
      result.direction     = SIGNAL_SELL;
      result.score         = (int)MathMin(sellScore, 40);
      result.reason        = sellReasons;
      result.entryPrice    = NormalizeDouble(sellEntry, m_digits);
      result.suggestedSL   = NormalizeDouble(sellSL, m_digits);
      result.smcConfluence = sellConf;

      if(m_swingRangeLow > 0 && m_swingRangeLow < currentPrice)
         result.suggestedTP = NormalizeDouble(m_swingRangeLow, m_digits);
   }

   // Classify strength
   if(result.score >= 30)
      result.strength = STRENGTH_STRONG;
   else if(result.score >= 20)
      result.strength = STRENGTH_MEDIUM;
   else if(result.score > 0)
      result.strength = STRENGTH_WEAK;

   return result;
}

//+------------------------------------------------------------------+
//| Find nearest resistance target above currentPrice for BUY TP      |
//| Checks: bearish OBs, bearish FVGs, swing highs, round numbers    |
//+------------------------------------------------------------------+
double CClawSMC::GetNearestBuyTarget(double currentPrice)
{
   if(!m_initialized || currentPrice <= 0) return 0;

   double bestTarget = 0;
   double bestDist   = DBL_MAX;

   // Check bearish (supply) order blocks above price
   for(int i = 0; i < m_obCount; i++)
   {
      if(m_orderBlocks[i].direction != -1) continue;  // Only bearish OBs
      if(m_orderBlocks[i].mitigated) continue;
      double obLevel = m_orderBlocks[i].bodyLow;  // Bottom of supply zone
      if(obLevel > currentPrice)
      {
         double dist = obLevel - currentPrice;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = obLevel; }
      }
   }

   // Check bearish FVGs above price
   for(int i = 0; i < m_fvgCount; i++)
   {
      if(m_fvgs[i].direction != -1) continue;  // Only bearish FVGs
      if(m_fvgs[i].mitigated) continue;
      double fvgLevel = m_fvgs[i].gapLow;  // Bottom of bearish FVG
      if(fvgLevel > currentPrice)
      {
         double dist = fvgLevel - currentPrice;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = fvgLevel; }
      }
   }

   // Check swing highs above price
   for(int i = 0; i < m_swingCount; i++)
   {
      if(!m_swingPoints[i].isHigh) continue;
      if(m_swingPoints[i].broken) continue;
      double swLevel = m_swingPoints[i].price;
      if(swLevel > currentPrice)
      {
         double dist = swLevel - currentPrice;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = swLevel; }
      }
   }

   // Check nearest round number above
   double roundAbove = GetNearestRoundNumber(currentPrice, 1);
   if(roundAbove > currentPrice)
   {
      double dist = roundAbove - currentPrice;
      if(dist < bestDist)
      { bestDist = dist; bestTarget = roundAbove; }
   }

   return NormalizeDouble(bestTarget, m_digits);
}

//+------------------------------------------------------------------+
//| Find nearest support target below currentPrice for SELL TP        |
//| Checks: bullish OBs, bullish FVGs, swing lows, round numbers     |
//+------------------------------------------------------------------+
double CClawSMC::GetNearestSellTarget(double currentPrice)
{
   if(!m_initialized || currentPrice <= 0) return 0;

   double bestTarget = 0;
   double bestDist   = DBL_MAX;

   // Check bullish (demand) order blocks below price
   for(int i = 0; i < m_obCount; i++)
   {
      if(m_orderBlocks[i].direction != 1) continue;  // Only bullish OBs
      if(m_orderBlocks[i].mitigated) continue;
      double obLevel = m_orderBlocks[i].bodyHigh;  // Top of demand zone
      if(obLevel < currentPrice)
      {
         double dist = currentPrice - obLevel;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = obLevel; }
      }
   }

   // Check bullish FVGs below price
   for(int i = 0; i < m_fvgCount; i++)
   {
      if(m_fvgs[i].direction != 1) continue;  // Only bullish FVGs
      if(m_fvgs[i].mitigated) continue;
      double fvgLevel = m_fvgs[i].gapHigh;  // Top of bullish FVG
      if(fvgLevel < currentPrice)
      {
         double dist = currentPrice - fvgLevel;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = fvgLevel; }
      }
   }

   // Check swing lows below price
   for(int i = 0; i < m_swingCount; i++)
   {
      if(m_swingPoints[i].isHigh) continue;
      if(m_swingPoints[i].broken) continue;
      double swLevel = m_swingPoints[i].price;
      if(swLevel < currentPrice)
      {
         double dist = currentPrice - swLevel;
         if(dist < bestDist)
         { bestDist = dist; bestTarget = swLevel; }
      }
   }

   // Check nearest round number below
   double roundBelow = GetNearestRoundNumber(currentPrice, -1);
   if(roundBelow > 0 && roundBelow < currentPrice)
   {
      double dist = currentPrice - roundBelow;
      if(dist < bestDist)
      { bestDist = dist; bestTarget = roundBelow; }
   }

   return NormalizeDouble(bestTarget, m_digits);
}
