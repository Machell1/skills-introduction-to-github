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

   // Partial close tracking (POSITION_COMMENT doesn't update after partial close in MT5)
   ulong  m_partialClosedTickets[];
   int    m_partialClosedCount;

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
   bool   ClosePosition(ulong ticket);

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

   // Profit locking: partial close + breakeven
   void   ManagePartialClose(double tp1ATRMult, double partialPct);
   void   ManageBreakeven();

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

   // SL/TP from a specific entry price (for pending orders)
   double CalculateSLPriceFromEntry(ENUM_SIGNAL_TYPE direction, double entryPrice);
   double CalculateTPPriceFromEntry(ENUM_SIGNAL_TYPE direction, double entryPrice, double slPrice);

   // Dynamic position closure - reduces average loss
   void   ManageDynamicClosure(double maxLossATR, double staleBarsThreshold,
                               double staleRangeATR, double adverseMomATR);

   // Dynamic TP using SMC targets
   double CalculateDynamicTP(ENUM_SIGNAL_TYPE direction, double entryPrice,
                             double slPrice, double smcTarget, double regimeMult);
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
   m_partialClosedCount = 0;
   ArrayResize(m_partialClosedTickets, 0);
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

   // Ensure minimum risk:reward ratio (at least 1.5:1 for positive expectancy)
   double minTPDistance = slDistance * 1.5;
   if(m_minRiskReward > 1.5)
      minTPDistance = slDistance * m_minRiskReward;
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

//+------------------------------------------------------------------+
//| Manage partial close: close a portion at TP1 profit level        |
//| tp1ATRMult = ATR multiplier for TP1 (e.g., 0.5)                  |
//| partialPct = fraction to close (e.g., 0.5 = 50%)                 |
//+------------------------------------------------------------------+
void CClawRiskManager::ManagePartialClose(double tp1ATRMult, double partialPct)
{
   if(!m_initialized) return;

   double atr = GetCurrentATR();
   if(atr <= 0) return;

   double tp1Distance = atr * tp1ATRMult;
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)m_magicNumber) continue;

      // Check if this position has already been partially closed
      // Note: POSITION_COMMENT is NOT updated by partial close deals in MT5,
      // so we track partial-closed tickets in a separate array
      bool alreadyClosed = false;
      for(int pc = 0; pc < m_partialClosedCount; pc++)
      {
         if(m_partialClosedTickets[pc] == ticket) { alreadyClosed = true; break; }
      }
      if(alreadyClosed) continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double volume    = PositionGetDouble(POSITION_VOLUME);
      long   posType   = PositionGetInteger(POSITION_TYPE);

      double profit = 0;
      if(posType == POSITION_TYPE_BUY)
         profit = SymbolInfoDouble(m_symbol, SYMBOL_BID) - openPrice;
      else if(posType == POSITION_TYPE_SELL)
         profit = openPrice - SymbolInfoDouble(m_symbol, SYMBOL_ASK);

      // Check if profit exceeds TP1 distance
      if(profit >= tp1Distance)
      {
         double closeVolume = NormalizeLot(m_symbol, volume * partialPct);
         if(closeVolume <= 0) continue;

         // Partial close: send a deal to reduce position
         MqlTradeRequest request = {};
         MqlTradeResult  result  = {};

         request.action   = TRADE_ACTION_DEAL;
         request.position = ticket;
         request.symbol   = m_symbol;
         request.volume   = closeVolume;
         request.deviation = 30;
         request.magic    = m_magicNumber;
         request.comment  = "CLAWBOT_TP1";

         if(posType == POSITION_TYPE_BUY)
         {
            request.type  = ORDER_TYPE_SELL;
            request.price = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         }
         else
         {
            request.type  = ORDER_TYPE_BUY;
            request.price = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         }

         long fillPolicy = SymbolInfoInteger(m_symbol, SYMBOL_FILLING_MODE);
         if((fillPolicy & SYMBOL_FILLING_FOK) != 0)
            request.type_filling = ORDER_FILLING_FOK;
         else if((fillPolicy & SYMBOL_FILLING_IOC) != 0)
            request.type_filling = ORDER_FILLING_IOC;
         else
            request.type_filling = ORDER_FILLING_RETURN;

         OrderSend(request, result);

         if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
         {
            // Track this ticket so we don't partial close again
            ArrayResize(m_partialClosedTickets, m_partialClosedCount + 1);
            m_partialClosedTickets[m_partialClosedCount] = ticket;
            m_partialClosedCount++;

            LogMessage("TP1", "Partial close " + DoubleToString(partialPct * 100, 0) + "% of #" +
                       IntegerToString((int)ticket) + " at profit " + DoubleToString(profit, digits));

            // Move SL to breakeven on the remaining portion
            double beSL = openPrice;
            // Add a small buffer (spread) to ensure true breakeven
            double spread = SymbolInfoDouble(m_symbol, SYMBOL_ASK) - SymbolInfoDouble(m_symbol, SYMBOL_BID);
            if(posType == POSITION_TYPE_BUY)
               beSL = NormalizeDouble(openPrice + spread, digits);
            else
               beSL = NormalizeDouble(openPrice - spread, digits);

            MqlTradeRequest beReq = {};
            MqlTradeResult  beRes = {};
            beReq.action   = TRADE_ACTION_SLTP;
            beReq.position = ticket;
            beReq.symbol   = m_symbol;
            beReq.sl       = beSL;
            beReq.tp       = PositionGetDouble(POSITION_TP);

            OrderSend(beReq, beRes);
            if(beRes.retcode == TRADE_RETCODE_DONE)
               LogMessage("TP1", "SL moved to breakeven (" + DoubleToString(beSL, digits) + ") for #" +
                          IntegerToString((int)ticket));
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Manage breakeven: move SL to entry once profit > activation      |
//| This is a safety net in case ManagePartialClose didn't trigger   |
//+------------------------------------------------------------------+
void CClawRiskManager::ManageBreakeven()
{
   if(!m_initialized) return;

   double atr = GetCurrentATR();
   if(atr <= 0) return;

   // Activate breakeven at the same distance as trailing activation
   double beActivation = atr * m_trailingActivation;
   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != m_symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)m_magicNumber) continue;

      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      long   posType   = PositionGetInteger(POSITION_TYPE);

      if(posType == POSITION_TYPE_BUY)
      {
         // Already at or above breakeven?
         if(currentSL >= openPrice) continue;

         double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
         if((bid - openPrice) >= beActivation)
         {
            double spread = SymbolInfoDouble(m_symbol, SYMBOL_ASK) - bid;
            double beSL = NormalizeDouble(openPrice + spread, digits);
            if(beSL > currentSL)
            {
               MqlTradeRequest req = {};
               MqlTradeResult  res = {};
               req.action   = TRADE_ACTION_SLTP;
               req.position = ticket;
               req.symbol   = m_symbol;
               req.sl       = beSL;
               req.tp       = PositionGetDouble(POSITION_TP);
               OrderSend(req, res);
            }
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
         // Already at or below breakeven?
         if(currentSL > 0 && currentSL <= openPrice) continue;

         if((openPrice - ask) >= beActivation)
         {
            double spread = ask - SymbolInfoDouble(m_symbol, SYMBOL_BID);
            double beSL = NormalizeDouble(openPrice - spread, digits);
            if(currentSL == 0 || beSL < currentSL)
            {
               MqlTradeRequest req = {};
               MqlTradeResult  res = {};
               req.action   = TRADE_ACTION_SLTP;
               req.position = ticket;
               req.symbol   = m_symbol;
               req.sl       = beSL;
               req.tp       = PositionGetDouble(POSITION_TP);
               OrderSend(req, res);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Calculate SL price from a specific entry price (for pending orders)|
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateSLPriceFromEntry(ENUM_SIGNAL_TYPE direction, double entryPrice)
{
   double atr = GetCurrentATR();
   if(atr <= 0) return 0;

   double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
   double slDistance = atr * m_slATRMultiplier;

   double slPoints = slDistance / point;
   if(slPoints < m_minSLPoints) slDistance = m_minSLPoints * point;
   if(slPoints > m_maxSLPoints) slDistance = m_maxSLPoints * point;

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   if(direction == SIGNAL_BUY)
      return NormalizeDouble(entryPrice - slDistance, digits);
   else if(direction == SIGNAL_SELL)
      return NormalizeDouble(entryPrice + slDistance, digits);

   return 0;
}

//+------------------------------------------------------------------+
//| Calculate TP price from a specific entry price (for pending orders)|
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateTPPriceFromEntry(ENUM_SIGNAL_TYPE direction, double entryPrice, double slPrice)
{
   double atr = GetCurrentATR();
   if(atr <= 0 || slPrice <= 0) return 0;

   double slDistance = MathAbs(entryPrice - slPrice);
   double tpDistance = atr * m_tpATRMultiplier;

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
//| Close a specific position by ticket                               |
//+------------------------------------------------------------------+
bool CClawRiskManager::ClosePosition(ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return false;

   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   request.action   = TRADE_ACTION_DEAL;
   request.position = ticket;
   request.symbol   = m_symbol;
   request.volume   = PositionGetDouble(POSITION_VOLUME);
   request.deviation = 50;
   request.magic    = m_magicNumber;

   long posType = PositionGetInteger(POSITION_TYPE);
   if(posType == POSITION_TYPE_BUY)
   {  request.type = ORDER_TYPE_SELL; request.price = SymbolInfoDouble(m_symbol, SYMBOL_BID); }
   else
   {  request.type = ORDER_TYPE_BUY; request.price = SymbolInfoDouble(m_symbol, SYMBOL_ASK); }

   long fillPolicy = SymbolInfoInteger(m_symbol, SYMBOL_FILLING_MODE);
   if((fillPolicy & SYMBOL_FILLING_FOK) != 0)
      request.type_filling = ORDER_FILLING_FOK;
   else if((fillPolicy & SYMBOL_FILLING_IOC) != 0)
      request.type_filling = ORDER_FILLING_IOC;
   else
      request.type_filling = ORDER_FILLING_RETURN;

   OrderSend(request, result);
   return (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED);
}

//+------------------------------------------------------------------+
//| Dynamic Position Closure - Reduces average loss significantly     |
//|                                                                    |
//| 1. Max Loss Cap: close if unrealized loss > maxLossATR * ATR      |
//|    (active from bar 0 - immediate protection)                      |
//| 2. Adverse Momentum Exit: close if losing > adverseMomATR*ATR AND |
//|    BOTH of last 2 bars closed strongly against position            |
//|    (requires min 3 bars age to avoid premature exits)              |
//| 3. Stale Trade Exit: close if position age > staleBars AND P/L    |
//|    is within ±staleRangeATR * ATR AND position is in loss          |
//| 4. Progressive SL Tightening: gently move SL after 8+ bars        |
//|    - After 8 bars: tighten SL to 80% of original distance        |
//|    - After 14 bars: tighten to 60%                                 |
//|    - After 20 bars: tighten to 45%                                 |
//+------------------------------------------------------------------+
void CClawRiskManager::ManageDynamicClosure(double maxLossATR, double staleBarsThreshold,
                                             double staleRangeATR, double adverseMomATR)
{
   if(!m_initialized) return;

   double atr = GetCurrentATR();
   if(atr <= 0) return;

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);

   // Get last 2 completed bars for momentum check (require 2 consecutive adverse bars)
   double lastClose1 = iClose(m_symbol, m_timeframe, 1);
   double lastOpen1  = iOpen(m_symbol, m_timeframe, 1);
   double lastHigh1  = iHigh(m_symbol, m_timeframe, 1);
   double lastLow1   = iLow(m_symbol, m_timeframe, 1);
   double lastClose2 = iClose(m_symbol, m_timeframe, 2);
   double lastOpen2  = iOpen(m_symbol, m_timeframe, 2);
   double lastHigh2  = iHigh(m_symbol, m_timeframe, 2);
   double lastLow2   = iLow(m_symbol, m_timeframe, 2);
   double barRange1  = lastHigh1 - lastLow1;
   double barRange2  = lastHigh2 - lastLow2;
   if(lastClose1 <= 0 || lastOpen1 <= 0) return;

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
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);

      // Calculate position age in bars
      int barsSinceOpen = (int)((TimeCurrent() - openTime) / PeriodSeconds(m_timeframe));

      // Calculate unrealized P/L in price terms
      double unrealizedPL = 0;
      if(posType == POSITION_TYPE_BUY)
         unrealizedPL = SymbolInfoDouble(m_symbol, SYMBOL_BID) - openPrice;
      else
         unrealizedPL = openPrice - SymbolInfoDouble(m_symbol, SYMBOL_ASK);

      double originalSLDist = MathAbs(openPrice - currentSL);
      if(originalSLDist <= 0) originalSLDist = atr * m_slATRMultiplier;

      // === CHECK 1: Max Loss Cap (always active) ===
      if(unrealizedPL < -(maxLossATR * atr))
      {
         if(ClosePosition(ticket))
            LogMessage("DYNCLS", "MAX LOSS CAP closed #" + IntegerToString((int)ticket) +
                       " | Loss: " + DoubleToString(unrealizedPL, digits) +
                       " | Cap: " + DoubleToString(-maxLossATR * atr, digits));
         continue;
      }

      // === CHECK 2: Adverse Momentum Exit (min 3 bars old) ===
      // Requires BOTH of the last 2 bars to close strongly against position
      if(barsSinceOpen >= 3 && unrealizedPL < -(adverseMomATR * atr))
      {
         bool adverseBar1 = false;
         bool adverseBar2 = false;

         if(posType == POSITION_TYPE_BUY)
         {
            // Bar 1: strong bearish (closed in bottom 25% of range)
            if(lastClose1 < lastOpen1 && barRange1 > 0 &&
               (lastClose1 - lastLow1) < barRange1 * 0.25)
               adverseBar1 = true;
            // Bar 2: also bearish
            if(lastClose2 < lastOpen2 && barRange2 > 0 &&
               (lastClose2 - lastLow2) < barRange2 * 0.35)
               adverseBar2 = true;
         }
         else
         {
            // Bar 1: strong bullish (closed in top 25% of range)
            if(lastClose1 > lastOpen1 && barRange1 > 0 &&
               (lastHigh1 - lastClose1) < barRange1 * 0.25)
               adverseBar1 = true;
            // Bar 2: also bullish
            if(lastClose2 > lastOpen2 && barRange2 > 0 &&
               (lastHigh2 - lastClose2) < barRange2 * 0.35)
               adverseBar2 = true;
         }

         // Only close if BOTH bars are adverse (confirms momentum, not just noise)
         if(adverseBar1 && adverseBar2)
         {
            if(ClosePosition(ticket))
               LogMessage("DYNCLS", "ADVERSE MOMENTUM closed #" + IntegerToString((int)ticket) +
                          " | Loss: " + DoubleToString(unrealizedPL, digits) +
                          " | Bars: " + IntegerToString(barsSinceOpen));
            continue;
         }
      }

      // === CHECK 3: Stale Trade Exit (only for losing positions) ===
      if(barsSinceOpen >= (int)staleBarsThreshold &&
         unrealizedPL < 0 &&
         MathAbs(unrealizedPL) < staleRangeATR * atr)
      {
         if(ClosePosition(ticket))
            LogMessage("DYNCLS", "STALE TRADE closed #" + IntegerToString((int)ticket) +
                       " | P/L: " + DoubleToString(unrealizedPL, digits) +
                       " | Bars: " + IntegerToString(barsSinceOpen));
         continue;
      }

      // === CHECK 4: Progressive SL Tightening (aggressive schedule) ===
      // Tighten SL faster to reduce average loss on aging positions
      if(unrealizedPL < 0 && currentSL > 0 && barsSinceOpen >= 5)
      {
         double tightenFactor = 1.0;
         if(barsSinceOpen >= 16)
            tightenFactor = 0.30;    // Very tight after 16 bars
         else if(barsSinceOpen >= 10)
            tightenFactor = 0.45;    // Aggressive after 10 bars
         else if(barsSinceOpen >= 5)
            tightenFactor = 0.65;    // Start tightening at 5 bars

         if(tightenFactor < 1.0)
         {
            double newSLDist = originalSLDist * tightenFactor;
            double minDist = SymbolInfoDouble(m_symbol, SYMBOL_POINT) * m_minSLPoints * 0.5;
            if(newSLDist < minDist) newSLDist = minDist;

            double newSL = 0;
            if(posType == POSITION_TYPE_BUY)
            {
               newSL = NormalizeDouble(openPrice - newSLDist, digits);
               if(newSL <= currentSL) continue;
            }
            else
            {
               newSL = NormalizeDouble(openPrice + newSLDist, digits);
               if(currentSL > 0 && newSL >= currentSL) continue;
            }

            MqlTradeRequest req = {};
            MqlTradeResult  res = {};
            req.action   = TRADE_ACTION_SLTP;
            req.position = ticket;
            req.symbol   = m_symbol;
            req.sl       = newSL;
            req.tp       = currentTP;

            if(OrderSend(req, res) && (res.retcode == TRADE_RETCODE_DONE))
            {
               LogMessage("DYNCLS", "SL TIGHTENED #" + IntegerToString((int)ticket) +
                          " to " + DoubleToString(newSL, digits) +
                          " (factor=" + DoubleToString(tightenFactor, 2) +
                          ", bars=" + IntegerToString(barsSinceOpen) + ")");
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Calculate Dynamic Take Profit                                      |
//|                                                                    |
//| Uses SMC structural targets when available, with regime scaling.   |
//| Enforces minimum TP of 1.0 * ATR and minimum R:R of 0.8.         |
//+------------------------------------------------------------------+
double CClawRiskManager::CalculateDynamicTP(ENUM_SIGNAL_TYPE direction, double entryPrice,
                                             double slPrice, double smcTarget, double regimeMult)
{
   double atr = GetCurrentATR();
   if(atr <= 0 || slPrice <= 0) return 0;

   int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
   double slDistance = MathAbs(entryPrice - slPrice);

   // Base TP: ATR multiplier scaled by regime
   double baseTpDist = atr * m_tpATRMultiplier * regimeMult;

   // If SMC target is valid, calculate distance to it
   double smcTpDist = 0;
   if(smcTarget > 0)
   {
      if(direction == SIGNAL_BUY && smcTarget > entryPrice)
         smcTpDist = smcTarget - entryPrice;
      else if(direction == SIGNAL_SELL && smcTarget < entryPrice)
         smcTpDist = entryPrice - smcTarget;
   }

   // Choose the best TP distance
   double tpDistance = baseTpDist;

   if(smcTpDist > 0)
   {
      // Use SMC target if it's within reasonable range (0.8x to 2.5x base)
      if(smcTpDist >= baseTpDist * 0.8 && smcTpDist <= baseTpDist * 2.5)
         tpDistance = smcTpDist;
      else if(smcTpDist > baseTpDist * 2.5)
         tpDistance = baseTpDist;
      else
         tpDistance = MathMax(smcTpDist, baseTpDist);
   }

   // Enforce minimum TP: at least 1.0 * ATR (ensures average win is meaningful)
   double minTP = atr * 1.0;
   if(tpDistance < minTP) tpDistance = minTP;

   // Enforce minimum R:R of 1.5 (critical: TP must be 1.5x SL distance for positive expectancy)
   double minRRDist = slDistance * 1.5;
   if(tpDistance < minRRDist) tpDistance = minRRDist;

   if(direction == SIGNAL_BUY)
      return NormalizeDouble(entryPrice + tpDistance, digits);
   else if(direction == SIGNAL_SELL)
      return NormalizeDouble(entryPrice - tpDistance, digits);

   return 0;
}
