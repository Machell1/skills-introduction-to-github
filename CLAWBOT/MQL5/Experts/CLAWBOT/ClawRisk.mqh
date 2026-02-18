//+------------------------------------------------------------------+
//|                                                    ClawRisk.mqh  |
//|                      CLAWBOT - Risk Management Engine            |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Risk Management Engine                                             |
//|                                                                    |
//| Features:                                                          |
//|   - ATR-based dynamic Stop Loss and Take Profit                   |
//|   - Percentage-based position sizing                               |
//|   - Maximum daily loss protection                                  |
//|   - Maximum total drawdown protection                              |
//|   - Maximum concurrent positions limit                             |
//|   - Trailing stop management                                       |
//|   - Risk:Reward ratio enforcement                                  |
//|   - Daily/weekly trade limits                                      |
//|   - Equity curve protection                                        |
//+------------------------------------------------------------------+
class CClawRiskManager
{
private:
   // Indicator handles
   int m_atrHandle;
   double m_atr[];

   // Settings
   string m_symbol;
   ENUM_TIMEFRAMES m_timeframe;
   ulong  m_magicNumber;

   // Risk parameters
   double m_riskPerTrade;          // % of balance per trade (e.g., 1.5)
   double m_maxDailyLoss;          // % max daily loss (e.g., 3.0)
   double m_maxTotalDrawdown;      // % max total drawdown (e.g., 8.0)
   int    m_maxConcurrentTrades;   // Max open positions (e.g., 2)
   int    m_maxDailyTrades;        // Max trades per day
   double m_minRiskReward;         // Minimum R:R ratio (e.g., 1.5)

   // SL/TP settings
   double m_slATRMultiplier;       // ATR multiplier for SL (e.g., 2.0)
   double m_tpATRMultiplier;       // ATR multiplier for TP (e.g., 3.0)
   double m_minSLPoints;           // Minimum SL in points
   double m_maxSLPoints;           // Maximum SL in points
   double m_trailingActivation;    // ATR multiplier to activate trailing
   double m_trailingDistance;       // ATR multiplier for trail distance

   // Daily tracking
   double   m_dailyStartBalance;
   datetime m_dailyResetDate;
   int      m_dailyTradeCount;
   double   m_peakBalance;

   bool m_initialized;

   void   UpdateDailyTracking();
   double GetDailyPL();

public:
   CClawRiskManager();
   ~CClawRiskManager();

   bool Init(string symbol, ENUM_TIMEFRAMES tf, ulong magic,
             double riskPerTrade = 1.5, double maxDailyLoss = 3.0,
             double maxTotalDrawdown = 8.0, int maxConcurrent = 2,
             int maxDailyTrades = 5, double minRR = 1.5,
             double slATR = 2.0, double tpATR = 3.0,
             double minSL = 150.0, double maxSL = 500.0,
             double trailActivation = 1.0, double trailDistance = 1.5);

   void Deinit();

   // Pre-trade validation
   bool   CanOpenTrade();
   bool   CanOpenBuy();
   bool   CanOpenSell();
   bool   IsDrawdownExceeded();
   bool   IsDailyLossExceeded();

   // Position sizing
   double CalculateLotSize(double slPoints);
   double CalculateSLPrice(ENUM_SIGNAL_TYPE direction);
   double CalculateTPPrice(ENUM_SIGNAL_TYPE direction, double entryPrice, double slPrice);
   double GetCurrentATR();

   // Trailing stop
   void   ManageTrailingStops();

   // Daily management
   void   OnNewDay();
   int    GetDailyTradeCount() { return m_dailyTradeCount; }
   void   IncrementDailyTrades() { m_dailyTradeCount++; }

   // Getters
   double GetRiskPerTrade()     { return m_riskPerTrade; }
   double GetMaxDailyLoss()     { return m_maxDailyLoss; }
   double GetMaxDrawdown()      { return m_maxTotalDrawdown; }
   int    GetMaxConcurrent()    { return m_maxConcurrentTrades; }
   double GetSLMultiplier()     { return m_slATRMultiplier; }
   double GetTPMultiplier()     { return m_tpATRMultiplier; }
};

//+------------------------------------------------------------------+
CClawRiskManager::CClawRiskManager()
{
   m_initialized = false;
   m_atrHandle = INVALID_HANDLE;
   m_dailyStartBalance = 0;
   m_dailyResetDate = 0;
   m_dailyTradeCount = 0;
   m_peakBalance = 0;
}

//+------------------------------------------------------------------+
CClawRiskManager::~CClawRiskManager()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawRiskManager::Init(string symbol, ENUM_TIMEFRAMES tf, ulong magic,
                             double riskPerTrade, double maxDailyLoss,
                             double maxTotalDrawdown, int maxConcurrent,
                             int maxDailyTrades, double minRR,
                             double slATR, double tpATR,
                             double minSL, double maxSL,
                             double trailActivation, double trailDistance)
{
   m_symbol    = symbol;
   m_timeframe = tf;
   m_magicNumber = magic;

   m_riskPerTrade        = riskPerTrade;
   m_maxDailyLoss        = maxDailyLoss;
   m_maxTotalDrawdown    = maxTotalDrawdown;
   m_maxConcurrentTrades = maxConcurrent;
   m_maxDailyTrades      = maxDailyTrades;
   m_minRiskReward       = minRR;

   m_slATRMultiplier     = slATR;
   m_tpATRMultiplier     = tpATR;
   m_minSLPoints         = minSL;
   m_maxSLPoints         = maxSL;
   m_trailingActivation  = trailActivation;
   m_trailingDistance     = trailDistance;

   m_atrHandle = iATR(m_symbol, m_timeframe, 14);
   if(m_atrHandle == INVALID_HANDLE)
   {
      LogMessage("RISK", "Failed to create ATR handle. Error: " + IntegerToString(GetLastError()));
      return false;
   }

   ArraySetAsSeries(m_atr, true);

   m_dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   m_peakBalance = m_dailyStartBalance;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   m_dailyResetDate = StringToTime(IntegerToString(dt.year) + "." +
                                    IntegerToString(dt.mon) + "." +
                                    IntegerToString(dt.day));

   m_initialized = true;
   LogMessage("RISK", "Risk Manager initialized. Risk/trade=" + DoubleToString(m_riskPerTrade, 1) +
              "%, MaxDD=" + DoubleToString(m_maxTotalDrawdown, 1) + "%");
   return true;
}

//+------------------------------------------------------------------+
void CClawRiskManager::Deinit()
{
   if(m_atrHandle != INVALID_HANDLE) { IndicatorRelease(m_atrHandle); m_atrHandle = INVALID_HANDLE; }
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Update daily tracking on new day                                   |
//+------------------------------------------------------------------+
void CClawRiskManager::UpdateDailyTracking()
{
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   datetime today = StringToTime(IntegerToString(dt.year) + "." +
                                  IntegerToString(dt.mon) + "." +
                                  IntegerToString(dt.day));

   if(today != m_dailyResetDate)
   {
      OnNewDay();
      m_dailyResetDate = today;
   }
}

//+------------------------------------------------------------------+
void CClawRiskManager::OnNewDay()
{
   m_dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   m_dailyTradeCount = 0;
   LogMessage("RISK", "New trading day. Start balance: " + DoubleToString(m_dailyStartBalance, 2));
}

//+------------------------------------------------------------------+
//| Get today's realized + floating P/L                                |
//+------------------------------------------------------------------+
double CClawRiskManager::GetDailyPL()
{
   double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double floatingPL = GetFloatingPL(m_symbol, m_magicNumber);
   return (currentBalance - m_dailyStartBalance) + floatingPL;
}

//+------------------------------------------------------------------+
//| Check if a new trade can be opened                                 |
//+------------------------------------------------------------------+
bool CClawRiskManager::CanOpenTrade()
{
   if(!m_initialized) return false;

   UpdateDailyTracking();

   // Check max concurrent positions
   int openPos = CountOpenPositions(m_symbol, m_magicNumber);
   if(openPos >= m_maxConcurrentTrades)
   {
      LogMessage("RISK", "Max concurrent trades reached (" + IntegerToString(openPos) + "/" +
                 IntegerToString(m_maxConcurrentTrades) + ")");
      return false;
   }

   // Check daily trade limit
   if(m_dailyTradeCount >= m_maxDailyTrades)
   {
      LogMessage("RISK", "Daily trade limit reached (" + IntegerToString(m_dailyTradeCount) + "/" +
                 IntegerToString(m_maxDailyTrades) + ")");
      return false;
   }

   // Check daily loss limit
   if(IsDailyLossExceeded())
   {
      LogMessage("RISK", "Daily loss limit exceeded");
      return false;
   }

   // Check total drawdown
   if(IsDrawdownExceeded())
   {
      LogMessage("RISK", "Total drawdown limit exceeded");
      return false;
   }

   // Check if it's a trading day (no Sunday)
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(dt.day_of_week == 0 || dt.day_of_week == 6)
   {
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
bool CClawRiskManager::CanOpenBuy()
{
   if(!CanOpenTrade()) return false;
   // Don't open a buy if we already have a buy position
   return CountBuyPositions(m_symbol, m_magicNumber) == 0;
}

//+------------------------------------------------------------------+
bool CClawRiskManager::CanOpenSell()
{
   if(!CanOpenTrade()) return false;
   return CountSellPositions(m_symbol, m_magicNumber) == 0;
}

//+------------------------------------------------------------------+
bool CClawRiskManager::IsDailyLossExceeded()
{
   double dailyPL = GetDailyPL();
   double maxLossAmount = m_dailyStartBalance * (m_maxDailyLoss / 100.0);
   return (dailyPL < -maxLossAmount);
}

//+------------------------------------------------------------------+
bool CClawRiskManager::IsDrawdownExceeded()
{
   double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(currentEquity > m_peakBalance)
      m_peakBalance = currentEquity;

   double drawdown = (m_peakBalance - currentEquity) / m_peakBalance * 100.0;
   return (drawdown > m_maxTotalDrawdown);
}

//+------------------------------------------------------------------+
//| Get current ATR value                                              |
//+------------------------------------------------------------------+
double CClawRiskManager::GetCurrentATR()
{
   if(CopyBuffer(m_atrHandle, 0, 0, 3, m_atr) < 3) return 0;
   return m_atr[1]; // Completed bar ATR
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk percentage and SL distance        |
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateLotSize(double slPoints)
{
   if(slPoints <= 0) return 0;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double riskAmount = balance * (m_riskPerTrade / 100.0);

   double pointValue = GetPointValue(m_symbol);
   if(pointValue <= 0) return 0;

   double lot = riskAmount / (slPoints * pointValue);

   lot = NormalizeLot(m_symbol, lot);

   LogMessage("RISK", "Lot calculation: Balance=" + DoubleToString(balance, 2) +
              " Risk$=" + DoubleToString(riskAmount, 2) +
              " SL_pts=" + DoubleToString(slPoints, 0) +
              " Lot=" + DoubleToString(lot, 2));

   return lot;
}

//+------------------------------------------------------------------+
//| Calculate Stop Loss price based on ATR                             |
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateSLPrice(ENUM_SIGNAL_TYPE direction)
{
   double atr = GetCurrentATR();
   if(atr <= 0) return 0;

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double slDistance = atr * m_slATRMultiplier;

   // Convert to points for min/max check
   double slPoints = slDistance / point;
   if(slPoints < m_minSLPoints) slDistance = m_minSLPoints * point;
   if(slPoints > m_maxSLPoints) slDistance = m_maxSLPoints * point;

   double currentPrice;
   if(direction == SIGNAL_BUY)
   {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      return NormalizeDouble(currentPrice - slDistance, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
   }
   else if(direction == SIGNAL_SELL)
   {
      currentPrice = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      return NormalizeDouble(currentPrice + slDistance, (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS));
   }

   return 0;
}

//+------------------------------------------------------------------+
//| Calculate Take Profit price ensuring minimum R:R ratio             |
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateTPPrice(ENUM_SIGNAL_TYPE direction, double entryPrice, double slPrice)
{
   double atr = GetCurrentATR();
   if(atr <= 0 || slPrice <= 0) return 0;

   double slDistance = MathAbs(entryPrice - slPrice);
   double tpDistance = atr * m_tpATRMultiplier;

   // Ensure minimum risk:reward ratio
   double minTPDistance = slDistance * m_minRiskReward;
   if(tpDistance < minTPDistance)
      tpDistance = minTPDistance;

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   if(direction == SIGNAL_BUY)
      return NormalizeDouble(entryPrice + tpDistance, digits);
   else if(direction == SIGNAL_SELL)
      return NormalizeDouble(entryPrice - tpDistance, digits);

   return 0;
}

//+------------------------------------------------------------------+
//| Manage trailing stops for all open positions                       |
//+------------------------------------------------------------------+
void CClawRiskManager::ManageTrailingStops()
{
   if(!m_initialized) return;

   double atr = GetCurrentATR();
   if(atr <= 0) return;

   double trailActivateDistance = atr * m_trailingActivation;
   double trailStopDistance     = atr * m_trailingDistance;
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;

      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)m_magicNumber) continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      long   posType   = PositionGetInteger(POSITION_TYPE);

      if(posType == POSITION_TYPE_BUY)
      {
         double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         double profit = bid - openPrice;

         // Only trail if profit exceeds activation threshold
         if(profit >= trailActivateDistance)
         {
            double newSL = NormalizeDouble(bid - trailStopDistance, digits);
            if(newSL > currentSL && newSL > openPrice) // Only move SL up
            {
               MqlTradeRequest request = {};
               MqlTradeResult  tradeResult = {};
               request.action   = TRADE_ACTION_SLTP;
               request.position = ticket;
               request.symbol   = m_symbol;
               request.sl       = newSL;
               request.tp       = currentTP;

               if(OrderSend(request, tradeResult))
               {
                  LogMessage("TRAIL", "BUY trail SL moved to " + DoubleToString(newSL, digits) +
                             " (profit: " + DoubleToString(profit, digits) + ")");
               }
            }
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         double profit = openPrice - ask;

         if(profit >= trailActivateDistance)
         {
            double newSL = NormalizeDouble(ask + trailStopDistance, digits);
            if(newSL < currentSL || currentSL == 0)
            {
               if(newSL < openPrice) // Only move SL down
               {
                  MqlTradeRequest request = {};
                  MqlTradeResult  tradeResult = {};
                  request.action   = TRADE_ACTION_SLTP;
                  request.position = ticket;
                  request.symbol   = m_symbol;
                  request.sl       = newSL;
                  request.tp       = currentTP;

                  if(OrderSend(request, tradeResult))
                  {
                     LogMessage("TRAIL", "SELL trail SL moved to " + DoubleToString(newSL, digits) +
                                " (profit: " + DoubleToString(profit, digits) + ")");
                  }
               }
            }
         }
      }
   }
}
