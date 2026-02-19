//+------------------------------------------------------------------+
//|                                                     CLAWBOT.mq5  |
//|                  CLAWBOT - Multi-Strategy Confluence Trading Bot  |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
//|                                                                    |
//|  CLAWBOT Confluence System:                                        |
//|    C - Confluence (multi-indicator agreement)                      |
//|    L - Levels (key support/resistance via session ranges)          |
//|    A - Action (momentum confirmation)                              |
//|    W - Window (optimal session timing)                             |
//|                                                                    |
//|  Strategies (Hybrid System):                                       |
//|    1. Trend Follow  - Multi-EMA alignment with ADX confirmation   |
//|    2. Momentum      - RSI divergence + MACD + Stochastic          |
//|    3. Session       - Asian range breakout during London/NY       |
//|    4. Mean Revert   - Bollinger Band fade at extremes (NEW)       |
//|                                                                    |
//|  Entry Rule:                                                       |
//|    H4 multi-timeframe filter determines allowed direction         |
//|    Minimum 2 of 4 strategies must agree on direction              |
//|    Pending limit orders for better entry prices                   |
//|    Partial close at TP1 + breakeven + trail remainder             |
//|                                                                    |
//|  Risk Management:                                                  |
//|    ATR-based dynamic SL/TP, position sizing, drawdown limits      |
//|    Trailing stops, daily loss caps, max concurrent positions       |
//|                                                                    |
//|  Audit System:                                                     |
//|    Full trade logging, performance metrics, weakness detection     |
//|    80% win rate threshold for live deployment authorization        |
//|                                                                    |
//+------------------------------------------------------------------+
#property copyright   "CLAWBOT"
#property version     "1.00"
#property description "CLAWBOT - Multi-Strategy Confluence EA for XAUUSD"
#property description "Designed for Deriv MT5 - H1 Timeframe"

//--- Include modules
#include "ClawUtils.mqh"
#include "ClawMTF.mqh"
#include "ClawStrategy_Trend.mqh"
#include "ClawStrategy_Momentum.mqh"
#include "ClawStrategy_Session.mqh"
#include "ClawStrategy_MeanRevert.mqh"
#include "ClawRisk.mqh"
#include "ClawAudit.mqh"

//+------------------------------------------------------------------+
//| Input Parameters                                                   |
//+------------------------------------------------------------------+
//--- General Settings
input string   Inp_Separator1       = "=== GENERAL SETTINGS ===";      // ----
input ulong    Inp_MagicNumber      = 20240101;                        // Magic Number
input string   Inp_Symbol           = "XAUUSD";                        // Trading Symbol
input ENUM_TIMEFRAMES Inp_Timeframe = PERIOD_H1;                       // Trading Timeframe
input ENUM_BOT_MODE   Inp_BotMode   = MODE_BACKTEST;                   // Bot Mode (Backtest/Live)

//--- Risk Management
input string   Inp_Separator2       = "=== RISK MANAGEMENT ===";       // ----
input double   Inp_RiskPerTrade     = 0.8;     // Risk per trade (%)
input double   Inp_MaxDailyLoss     = 5.0;     // Max daily loss (%)
input double   Inp_MaxDrawdown      = 15.0;    // Max total drawdown (%)
input int      Inp_MaxConcurrent    = 3;       // Max concurrent trades
input int      Inp_MaxDailyTrades   = 10;      // Max trades per day
input double   Inp_MinRiskReward    = 0.2;     // Minimum Risk:Reward ratio

//--- Stop Loss / Take Profit
input string   Inp_Separator3       = "=== SL/TP SETTINGS ===";        // ----
input double   Inp_SL_ATR           = 3.0;     // SL ATR multiplier
input double   Inp_TP_ATR           = 0.8;     // TP ATR multiplier
input double   Inp_MinSL            = 200.0;   // Minimum SL (points)
input double   Inp_MaxSL            = 800.0;   // Maximum SL (points)
input double   Inp_TrailActivation  = 0.3;     // Trailing activation (ATR mult)
input double   Inp_TrailDistance    = 0.5;     // Trailing distance (ATR mult)
input double   Inp_MaxSpread        = 40.0;    // Max allowed spread (points)

//--- Trend Strategy (Strategy 1)
input string   Inp_Separator4       = "=== TREND STRATEGY ===";        // ----
input bool     Inp_EnableTrend      = true;    // Enable Trend Strategy
input int      Inp_EMA_Fast         = 8;       // Fast EMA period
input int      Inp_EMA_Signal       = 21;      // Signal EMA period
input int      Inp_EMA_Trend        = 50;      // Trend EMA period
input int      Inp_EMA_Major        = 200;     // Major trend EMA period
input int      Inp_ADX_Period       = 14;      // ADX period
input double   Inp_ADX_Threshold    = 25.0;    // ADX threshold
input int      Inp_CrossoverLookback = 5;      // Crossover lookback bars

//--- Momentum Strategy (Strategy 2)
input string   Inp_Separator5       = "=== MOMENTUM STRATEGY ===";     // ----
input bool     Inp_EnableMomentum   = true;    // Enable Momentum Strategy
input int      Inp_RSI_Period       = 14;      // RSI period
input double   Inp_RSI_Oversold     = 30.0;    // RSI oversold level
input double   Inp_RSI_Overbought   = 70.0;    // RSI overbought level
input int      Inp_MACD_Fast        = 12;      // MACD fast period
input int      Inp_MACD_Slow        = 26;      // MACD slow period
input int      Inp_MACD_Signal      = 9;       // MACD signal period
input int      Inp_Stoch_K          = 14;      // Stochastic K period
input int      Inp_Stoch_D          = 3;       // Stochastic D period
input int      Inp_Stoch_Slowing    = 3;       // Stochastic slowing

//--- Session Strategy (Strategy 3)
input string   Inp_Separator6       = "=== SESSION STRATEGY ===";      // ----
input bool     Inp_EnableSession    = true;    // Enable Session Strategy
input int      Inp_AsianStart       = 0;       // Asian session start (UTC hour)
input int      Inp_AsianEnd         = 7;       // Asian session end (UTC hour)
input int      Inp_LondonStart      = 7;       // London entry window start
input int      Inp_LondonEnd        = 16;      // London entry window end
input int      Inp_ExitHour         = 20;      // Session exit hour (UTC)

//--- Mean Reversion Strategy (Strategy 4) - NEW
input string   Inp_Separator6b      = "=== MEAN REVERSION STRATEGY ==="; // ----
input bool     Inp_EnableMeanRevert = true;    // Enable Mean Reversion Strategy
input int      Inp_BB_Period        = 20;      // Bollinger Band period
input double   Inp_BB_Deviation     = 2.0;     // Bollinger Band deviation
input double   Inp_BB_TouchBuffer   = 0.2;     // Band touch buffer (% of width)

//--- Multi-Timeframe Filter - NEW
input string   Inp_Separator6c      = "=== MTF FILTER ===";             // ----
input bool     Inp_EnableMTF        = true;    // Enable H4 trend filter
input ENUM_TIMEFRAMES Inp_MTF_TF    = PERIOD_H4; // Higher timeframe for filter

//--- Pending Orders - NEW
input string   Inp_Separator6d      = "=== PENDING ORDERS ===";         // ----
input bool     Inp_UsePendingOrders = true;    // Use limit orders instead of market
input int      Inp_PendingExpBars   = 4;       // Pending order expiry (bars)
input double   Inp_PullbackATR      = 0.3;     // Pullback distance for limit entry (ATR)

//--- Partial Close / Profit Locking - NEW
input string   Inp_Separator6e      = "=== PROFIT LOCKING ===";         // ----
input bool     Inp_EnablePartialClose = true;  // Enable partial close at TP1
input double   Inp_TP1_ATR          = 0.5;     // TP1 distance (ATR mult) for partial close
input double   Inp_PartialClosePct  = 0.5;     // Fraction to close at TP1 (0.5 = 50%)

//--- Confluence Settings
input string   Inp_Separator7       = "=== CONFLUENCE SETTINGS ===";   // ----
input int      Inp_MinScore         = 45;      // Minimum total score for entry
input int      Inp_MinStrategies    = 2;       // Min strategies agreeing
input int      Inp_MinStrategyScore = 15;      // Min individual strategy score to count
input int      Inp_CooldownAfterLosses = 3;    // Consecutive losses before cooldown
input int      Inp_CooldownBars     = 2;       // Bars to skip during cooldown

//--- Backtest / Audit Settings
input string   Inp_Separator8       = "=== AUDIT SETTINGS ===";        // ----
input double   Inp_WinRateThreshold = 80.0;    // Win rate threshold (%)
input string   Inp_ReportPath       = "CLAWBOT_Reports"; // Report folder

//+------------------------------------------------------------------+
//| Global Objects                                                      |
//+------------------------------------------------------------------+
CClawTrendStrategy       g_trendStrategy;
CClawMomentumStrategy    g_momentumStrategy;
CClawSessionStrategy     g_sessionStrategy;
CClawMeanRevertStrategy  g_meanRevertStrategy;
CClawMTF                 g_mtfFilter;
CClawRiskManager         g_riskManager;
CClawAudit               g_audit;

//--- State variables
bool   g_initialized = false;
string g_activeSymbol;
int    g_serverUTCOffset = 0;
int    g_consecutiveLosses = 0;
int    g_cooldownRemaining = 0;

//+------------------------------------------------------------------+
//| Validate input parameters                                          |
//+------------------------------------------------------------------+
bool ValidateInputs()
{
   bool valid = true;

   if(Inp_RiskPerTrade <= 0 || Inp_RiskPerTrade > 10.0)
   {
      LogMessage("INIT", "ERROR: RiskPerTrade must be 0.1-10.0%. Got: " + DoubleToString(Inp_RiskPerTrade, 1));
      valid = false;
   }
   if(Inp_MaxDailyLoss <= 0 || Inp_MaxDailyLoss > 20.0)
   {
      LogMessage("INIT", "ERROR: MaxDailyLoss must be 0.1-20.0%. Got: " + DoubleToString(Inp_MaxDailyLoss, 1));
      valid = false;
   }
   if(Inp_MaxDrawdown <= 0 || Inp_MaxDrawdown > 50.0)
   {
      LogMessage("INIT", "ERROR: MaxDrawdown must be 0.1-50.0%. Got: " + DoubleToString(Inp_MaxDrawdown, 1));
      valid = false;
   }
   if(Inp_MaxConcurrent < 1 || Inp_MaxConcurrent > 10)
   {
      LogMessage("INIT", "ERROR: MaxConcurrent must be 1-10. Got: " + IntegerToString(Inp_MaxConcurrent));
      valid = false;
   }
   if(Inp_MinScore < 0 || Inp_MinScore > 120)
   {
      LogMessage("INIT", "ERROR: MinScore must be 0-120. Got: " + IntegerToString(Inp_MinScore));
      valid = false;
   }
   if(Inp_MinStrategies < 1 || Inp_MinStrategies > 3)
   {
      LogMessage("INIT", "ERROR: MinStrategies must be 1-3. Got: " + IntegerToString(Inp_MinStrategies));
      valid = false;
   }
   if(Inp_SL_ATR <= 0 || Inp_TP_ATR <= 0)
   {
      LogMessage("INIT", "ERROR: SL/TP ATR multipliers must be positive.");
      valid = false;
   }
   if(Inp_MinSL > Inp_MaxSL)
   {
      LogMessage("INIT", "ERROR: MinSL > MaxSL. Check SL settings.");
      valid = false;
   }
   if(Inp_EMA_Fast <= 0 || Inp_EMA_Signal <= 0 || Inp_EMA_Trend <= 0 || Inp_EMA_Major <= 0)
   {
      LogMessage("INIT", "ERROR: EMA periods must be positive.");
      valid = false;
   }
   if(Inp_AsianStart < 0 || Inp_AsianStart > 23 || Inp_AsianEnd < 0 || Inp_AsianEnd > 23)
   {
      LogMessage("INIT", "ERROR: Session hours must be 0-23.");
      valid = false;
   }

   return valid;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   LogMessage("INIT", "==================================");
   LogMessage("INIT", "  CLAWBOT v1.00 Starting...");
   LogMessage("INIT", "  Symbol: " + Inp_Symbol);
   LogMessage("INIT", "  Timeframe: " + EnumToString(Inp_Timeframe));
   LogMessage("INIT", "  Mode: " + (Inp_BotMode == MODE_BACKTEST ? "BACKTEST" : "LIVE"));
   LogMessage("INIT", "==================================");

   // Validate inputs
   if(!ValidateInputs())
   {
      LogMessage("INIT", "FATAL: Input validation failed. Check parameters.");
      return INIT_FAILED;
   }

   // Detect server UTC offset
   g_serverUTCOffset = GetServerUTCOffset();
   LogMessage("INIT", "Server UTC offset: " + IntegerToString(g_serverUTCOffset) + " hours");

   // Validate symbol
   g_activeSymbol = Inp_Symbol;
   if(!ValidateSymbol(g_activeSymbol))
   {
      // Try common Deriv alternatives
      bool found = false;
      string alt1 = "XAUUSD";
      string alt2 = "XAUUSDm";
      string alt3 = "#XAUUSD";
      string alt4 = "Gold";

      if(ValidateSymbol(alt1))      { g_activeSymbol = alt1; found = true; }
      else if(ValidateSymbol(alt2)) { g_activeSymbol = alt2; found = true; }
      else if(ValidateSymbol(alt3)) { g_activeSymbol = alt3; found = true; }
      else if(ValidateSymbol(alt4)) { g_activeSymbol = alt4; found = true; }

      if(found)
         LogMessage("INIT", "Using alternative symbol: " + g_activeSymbol);
      else
      {
         LogMessage("INIT", "FATAL: Cannot find tradeable XAUUSD symbol");
         return INIT_FAILED;
      }
   }

   if(Period() != Inp_Timeframe)
      LogMessage("INIT", "WARNING: Chart timeframe does not match settings.");

   // Initialize strategies
   bool initOk = true;

   if(Inp_EnableTrend)
   {
      if(!g_trendStrategy.Init(g_activeSymbol, Inp_Timeframe,
                                Inp_EMA_Fast, Inp_EMA_Signal, Inp_EMA_Trend, Inp_EMA_Major,
                                Inp_ADX_Period, Inp_ADX_Threshold, Inp_CrossoverLookback))
      {
         LogMessage("INIT", "ERROR: Trend strategy initialization failed");
         initOk = false;
      }
   }

   if(Inp_EnableMomentum)
   {
      if(!g_momentumStrategy.Init(g_activeSymbol, Inp_Timeframe,
                                   Inp_RSI_Period, Inp_RSI_Oversold, Inp_RSI_Overbought,
                                   Inp_MACD_Fast, Inp_MACD_Slow, Inp_MACD_Signal,
                                   Inp_Stoch_K, Inp_Stoch_D, Inp_Stoch_Slowing))
      {
         LogMessage("INIT", "ERROR: Momentum strategy initialization failed");
         initOk = false;
      }
   }

   if(Inp_EnableSession)
   {
      if(!g_sessionStrategy.Init(g_activeSymbol, Inp_Timeframe,
                                  14, 0.5,
                                  Inp_AsianStart, Inp_AsianEnd,
                                  Inp_LondonStart, Inp_LondonEnd,
                                  Inp_ExitHour))
      {
         LogMessage("INIT", "ERROR: Session strategy initialization failed");
         initOk = false;
      }
   }

   if(Inp_EnableMeanRevert)
   {
      if(!g_meanRevertStrategy.Init(g_activeSymbol, Inp_Timeframe,
                                     Inp_BB_Period, Inp_BB_Deviation,
                                     Inp_RSI_Period, Inp_RSI_Oversold, Inp_RSI_Overbought,
                                     Inp_BB_TouchBuffer))
      {
         LogMessage("INIT", "ERROR: Mean Reversion strategy initialization failed");
         initOk = false;
      }
   }

   if(Inp_EnableMTF)
   {
      if(!g_mtfFilter.Init(g_activeSymbol, Inp_MTF_TF))
      {
         LogMessage("INIT", "WARNING: MTF filter initialization failed, continuing without it");
         // Don't fail init, just disable the filter
      }
   }

   if(!g_riskManager.Init(g_activeSymbol, Inp_Timeframe, Inp_MagicNumber,
                           Inp_RiskPerTrade, Inp_MaxDailyLoss, Inp_MaxDrawdown,
                           Inp_MaxConcurrent, Inp_MaxDailyTrades, Inp_MinRiskReward,
                           Inp_SL_ATR, Inp_TP_ATR, Inp_MinSL, Inp_MaxSL,
                           Inp_TrailActivation, Inp_TrailDistance))
   {
      LogMessage("INIT", "ERROR: Risk manager initialization failed");
      initOk = false;
   }

   if(!g_audit.Init(AccountInfoDouble(ACCOUNT_BALANCE), Inp_ReportPath))
   {
      LogMessage("INIT", "ERROR: Audit module initialization failed");
      initOk = false;
   }

   if(!initOk)
   {
      LogMessage("INIT", "FATAL: One or more modules failed to initialize");
      return INIT_FAILED;
   }

   EventSetTimer(60);

   g_initialized = true;
   LogMessage("INIT", "CLAWBOT initialized successfully. Waiting for trading signals...");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();

   if(Inp_BotMode == MODE_BACKTEST && g_initialized)
   {
      LogMessage("DEINIT", "Generating final backtest report...");
      g_audit.GenerateFullReport();

      if(g_audit.MeetsThreshold(Inp_WinRateThreshold))
      {
         g_audit.GeneratePassReport();
         LogMessage("DEINIT", "*** BACKTEST PASSED! Win rate >= " +
                    DoubleToString(Inp_WinRateThreshold, 0) + "% ***");
         LogMessage("DEINIT", "Pass report generated. Ready for live deployment.");
         LogMessage("DEINIT", "Run credential_manager.py to set up live trading.");

         Alert("CLAWBOT BACKTEST PASSED! Win rate: " +
               DoubleToString(g_audit.GetWinRate(), 1) + "% | " +
               "Run credential_manager.py to enter your Deriv login credentials.");
      }
      else
      {
         g_audit.GenerateWeaknessReport();
         LogMessage("DEINIT", "*** BACKTEST DID NOT MEET THRESHOLD ***");
         LogMessage("DEINIT", "Win rate: " + DoubleToString(g_audit.GetWinRate(), 1) + "%");
         LogMessage("DEINIT", "Weakness report generated. Upload to Claude for analysis.");

         Alert("CLAWBOT BACKTEST: Win rate " + DoubleToString(g_audit.GetWinRate(), 1) +
               "% (target: " + DoubleToString(Inp_WinRateThreshold, 0) + "%). " +
               "Weakness report in CLAWBOT_Reports. Upload to Claude for fixes.");
      }

      Print(g_audit.GetReportSummary());
   }

   // Clean up pending orders before shutdown
   DeleteAllPendingOrders(g_activeSymbol, Inp_MagicNumber);

   g_trendStrategy.Deinit();
   g_momentumStrategy.Deinit();
   g_sessionStrategy.Deinit();
   g_meanRevertStrategy.Deinit();
   g_mtfFilter.Deinit();
   g_riskManager.Deinit();
   g_audit.Deinit();

   LogMessage("DEINIT", "CLAWBOT shutdown. Reason: " + IntegerToString(reason));
}

//+------------------------------------------------------------------+
//| Expert tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!g_initialized) return;

   // === PHASE 1: MANAGE EXISTING POSITIONS (every tick) ===
   // Partial close at TP1: close 50%, move SL to breakeven
   if(Inp_EnablePartialClose)
      g_riskManager.ManagePartialClose(Inp_TP1_ATR, Inp_PartialClosePct);

   // Breakeven safety net
   g_riskManager.ManageBreakeven();

   // Trailing stops on existing positions
   g_riskManager.ManageTrailingStops();

   // === PHASE 2: NEW BAR LOGIC (signal evaluation + order placement) ===
   if(!IsNewBar(g_activeSymbol, Inp_Timeframe)) return;

   // Pre-check: can we open any trade at all?
   if(!g_riskManager.CanOpenTrade()) return;

   // Cooldown check
   if(g_cooldownRemaining > 0)
   {
      g_cooldownRemaining--;
      return;
   }

   // Spread filter
   double currentSpread = GetCurrentSpread(g_activeSymbol);
   if(currentSpread > Inp_MaxSpread) return;

   // === H4 MULTI-TIMEFRAME FILTER ===
   ENUM_SIGNAL_TYPE mtfDirection = SIGNAL_NONE;
   if(Inp_EnableMTF)
      mtfDirection = g_mtfFilter.GetTrendDirection();

   // Delete stale pending orders before placing new ones
   DeleteAllPendingOrders(g_activeSymbol, Inp_MagicNumber);

   // === EVALUATE ALL STRATEGIES ===
   SignalResult trendSignal, momentumSignal, sessionSignal, meanRevertSignal;
   trendSignal.Reset();
   momentumSignal.Reset();
   sessionSignal.Reset();
   meanRevertSignal.Reset();

   if(Inp_EnableTrend)      trendSignal      = g_trendStrategy.Evaluate();
   if(Inp_EnableMomentum)   momentumSignal   = g_momentumStrategy.Evaluate();
   if(Inp_EnableSession)    sessionSignal    = g_sessionStrategy.Evaluate();
   if(Inp_EnableMeanRevert) meanRevertSignal = g_meanRevertStrategy.Evaluate();

   // === CONFLUENCE ENGINE WITH MTF FILTER ===
   int buyVotes  = 0, sellVotes = 0;
   int buyScore  = 0, sellScore = 0;
   string buyReasons = "", sellReasons = "";
   double bestBuyEntry = 0, bestSellEntry = 0;
   double bestBuyTP = 0, bestSellTP = 0;

   // Helper macro: count a strategy vote if it meets threshold and MTF allows
   // Trend vote
   if(trendSignal.direction == SIGNAL_BUY && trendSignal.score >= Inp_MinStrategyScore)
   {  buyVotes++; buyScore += trendSignal.score;
      buyReasons += "[TREND:" + IntegerToString(trendSignal.score) + "] " + trendSignal.reason + " | ";
      if(trendSignal.entryPrice > 0) bestBuyEntry = trendSignal.entryPrice; }
   else if(trendSignal.direction == SIGNAL_SELL && trendSignal.score >= Inp_MinStrategyScore)
   {  sellVotes++; sellScore += trendSignal.score;
      sellReasons += "[TREND:" + IntegerToString(trendSignal.score) + "] " + trendSignal.reason + " | ";
      if(trendSignal.entryPrice > 0) bestSellEntry = trendSignal.entryPrice; }

   // Momentum vote
   if(momentumSignal.direction == SIGNAL_BUY && momentumSignal.score >= Inp_MinStrategyScore)
   {  buyVotes++; buyScore += momentumSignal.score;
      buyReasons += "[MOM:" + IntegerToString(momentumSignal.score) + "] " + momentumSignal.reason + " | ";
      if(momentumSignal.entryPrice > 0) bestBuyEntry = momentumSignal.entryPrice; }
   else if(momentumSignal.direction == SIGNAL_SELL && momentumSignal.score >= Inp_MinStrategyScore)
   {  sellVotes++; sellScore += momentumSignal.score;
      sellReasons += "[MOM:" + IntegerToString(momentumSignal.score) + "] " + momentumSignal.reason + " | ";
      if(momentumSignal.entryPrice > 0) bestSellEntry = momentumSignal.entryPrice; }

   // Session vote
   if(sessionSignal.direction == SIGNAL_BUY && sessionSignal.score >= Inp_MinStrategyScore)
   {  buyVotes++; buyScore += sessionSignal.score;
      buyReasons += "[SESS:" + IntegerToString(sessionSignal.score) + "] " + sessionSignal.reason + " | ";
      if(sessionSignal.entryPrice > 0) bestBuyEntry = sessionSignal.entryPrice; }
   else if(sessionSignal.direction == SIGNAL_SELL && sessionSignal.score >= Inp_MinStrategyScore)
   {  sellVotes++; sellScore += sessionSignal.score;
      sellReasons += "[SESS:" + IntegerToString(sessionSignal.score) + "] " + sessionSignal.reason + " | ";
      if(sessionSignal.entryPrice > 0) bestSellEntry = sessionSignal.entryPrice; }

   // Mean Reversion vote
   if(meanRevertSignal.direction == SIGNAL_BUY && meanRevertSignal.score >= Inp_MinStrategyScore)
   {  buyVotes++; buyScore += meanRevertSignal.score;
      buyReasons += "[MREV:" + IntegerToString(meanRevertSignal.score) + "] " + meanRevertSignal.reason + " | ";
      if(meanRevertSignal.entryPrice > 0) bestBuyEntry = meanRevertSignal.entryPrice;
      if(meanRevertSignal.suggestedTP > 0) bestBuyTP = meanRevertSignal.suggestedTP; }
   else if(meanRevertSignal.direction == SIGNAL_SELL && meanRevertSignal.score >= Inp_MinStrategyScore)
   {  sellVotes++; sellScore += meanRevertSignal.score;
      sellReasons += "[MREV:" + IntegerToString(meanRevertSignal.score) + "] " + meanRevertSignal.reason + " | ";
      if(meanRevertSignal.entryPrice > 0) bestSellEntry = meanRevertSignal.entryPrice;
      if(meanRevertSignal.suggestedTP > 0) bestSellTP = meanRevertSignal.suggestedTP; }

   // Determine final direction
   ENUM_SIGNAL_TYPE finalDirection = SIGNAL_NONE;
   int finalScore = 0;
   string finalReason = "";
   double suggestedEntry = 0;
   double suggestedTP = 0;

   if(buyVotes >= Inp_MinStrategies && buyScore >= Inp_MinScore && buyScore > sellScore)
   {  finalDirection = SIGNAL_BUY; finalScore = buyScore; finalReason = buyReasons;
      suggestedEntry = bestBuyEntry; suggestedTP = bestBuyTP; }
   else if(sellVotes >= Inp_MinStrategies && sellScore >= Inp_MinScore && sellScore > buyScore)
   {  finalDirection = SIGNAL_SELL; finalScore = sellScore; finalReason = sellReasons;
      suggestedEntry = bestSellEntry; suggestedTP = bestSellTP; }

   if(finalDirection == SIGNAL_NONE) return;

   // Apply MTF filter: only trade in the H4 trend direction
   if(Inp_EnableMTF && mtfDirection != SIGNAL_NONE)
   {
      if(finalDirection != mtfDirection)
      {
         // Signal opposes H4 trend - skip
         return;
      }
      // Signal aligns with H4 trend - bonus confidence
      finalScore += 10;
      finalReason += "[MTF:H4 aligned] ";
   }

   // Place trade (pending order or market order)
   PlaceOrder(finalDirection, finalScore, finalReason, suggestedEntry, suggestedTP);
}

//+------------------------------------------------------------------+
//| Place a pending limit order or market order                        |
//+------------------------------------------------------------------+
void PlaceOrder(ENUM_SIGNAL_TYPE direction, int score, string reason,
                double suggestedEntry, double suggestedTP)
{
   // Direction-specific duplicate check
   if(direction == SIGNAL_BUY && CountBuyPositions(g_activeSymbol, Inp_MagicNumber) > 0) return;
   if(direction == SIGNAL_SELL && CountSellPositions(g_activeSymbol, Inp_MagicNumber) > 0) return;

   // Don't place if we already have a pending order
   if(CountPendingOrders(g_activeSymbol, Inp_MagicNumber) > 0) return;

   double point = SymbolInfoDouble(g_activeSymbol, SYMBOL_POINT);
   if(point <= 0) return;
   int digits = (int)SymbolInfoInteger(g_activeSymbol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(g_activeSymbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(g_activeSymbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) return;

   // Determine entry price
   double entryPrice = 0;
   bool usePending = Inp_UsePendingOrders;

   if(suggestedEntry > 0)
   {
      // Use strategy-suggested entry (e.g., Bollinger band level)
      entryPrice = NormalizeDouble(suggestedEntry, digits);
   }
   else if(usePending)
   {
      // Calculate pullback entry: place limit order at a better price
      double atr = g_riskManager.GetCurrentATR();
      double pullback = atr * Inp_PullbackATR;

      if(direction == SIGNAL_BUY)
         entryPrice = NormalizeDouble(ask - pullback, digits);
      else
         entryPrice = NormalizeDouble(bid + pullback, digits);
   }

   // Validate pending order placement
   double minStopPts = GetMinStopLevel(g_activeSymbol);
   double minStopDist = minStopPts * point;

   if(usePending && entryPrice > 0)
   {
      // Check if entry is on the correct side for a limit order
      if(direction == SIGNAL_BUY && entryPrice >= ask - minStopDist)
         usePending = false; // Too close to market, use market order
      else if(direction == SIGNAL_SELL && entryPrice <= bid + minStopDist)
         usePending = false;
   }

   // Fallback to market order
   if(!usePending || entryPrice <= 0)
   {
      entryPrice = (direction == SIGNAL_BUY) ? ask : bid;
   }

   // Calculate SL from the entry price
   double slPrice = g_riskManager.CalculateSLPriceFromEntry(direction, entryPrice);
   if(slPrice <= 0) return;

   // Enforce minimum stop level on SL
   double slDist = MathAbs(entryPrice - slPrice) / point;
   if(slDist < minStopPts)
   {
      if(direction == SIGNAL_BUY)
         slPrice = NormalizeDouble(entryPrice - minStopPts * point, digits);
      else
         slPrice = NormalizeDouble(entryPrice + minStopPts * point, digits);
   }

   // Calculate TP: use suggested TP from mean reversion, or default ATR-based
   double tpPrice = 0;
   if(suggestedTP > 0)
      tpPrice = NormalizeDouble(suggestedTP, digits);
   else
      tpPrice = g_riskManager.CalculateTPPriceFromEntry(direction, entryPrice, slPrice);

   if(tpPrice <= 0) return;

   // Enforce minimum stop level on TP
   double tpDist = MathAbs(entryPrice - tpPrice) / point;
   if(tpDist < minStopPts)
   {
      if(direction == SIGNAL_BUY)
         tpPrice = NormalizeDouble(entryPrice + minStopPts * point, digits);
      else
         tpPrice = NormalizeDouble(entryPrice - minStopPts * point, digits);
   }

   // Calculate lot size
   double slPoints = MathAbs(entryPrice - slPrice) / point;
   double lotSize = g_riskManager.CalculateLotSize(slPoints);
   if(lotSize <= 0) return;

   // Scale by confluence strength
   if(score < 60)
      lotSize = NormalizeLot(g_activeSymbol, lotSize * 0.50);
   else if(score < 80)
      lotSize = NormalizeLot(g_activeSymbol, lotSize * 0.75);
   if(lotSize <= 0) return;

   // Build order request
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   request.symbol   = g_activeSymbol;
   request.volume   = lotSize;
   request.sl       = slPrice;
   request.tp       = tpPrice;
   request.magic    = Inp_MagicNumber;
   request.comment  = "CLAWBOT|S=" + IntegerToString(score) + "|" +
                       TimeToString(TimeCurrent(), TIME_DATE);

   if(usePending && MathAbs(entryPrice - ((direction == SIGNAL_BUY) ? ask : bid)) > minStopDist)
   {
      // === PENDING LIMIT ORDER ===
      request.action = TRADE_ACTION_PENDING;
      request.price  = entryPrice;

      if(direction == SIGNAL_BUY)
         request.type = (entryPrice < ask) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_BUY_STOP;
      else
         request.type = (entryPrice > bid) ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_SELL_STOP;

      // Set expiration
      request.type_time  = ORDER_TIME_SPECIFIED;
      request.expiration = TimeCurrent() + Inp_PendingExpBars * PeriodSeconds(Inp_Timeframe);

      request.type_filling = ORDER_FILLING_RETURN;
   }
   else
   {
      // === MARKET ORDER (fallback) ===
      request.action    = TRADE_ACTION_DEAL;
      request.deviation = 30;

      if(direction == SIGNAL_BUY)
      {  request.type = ORDER_TYPE_BUY; request.price = ask; }
      else
      {  request.type = ORDER_TYPE_SELL; request.price = bid; }

      long fillPolicy = SymbolInfoInteger(g_activeSymbol, SYMBOL_FILLING_MODE);
      if((fillPolicy & SYMBOL_FILLING_FOK) != 0)
         request.type_filling = ORDER_FILLING_FOK;
      else if((fillPolicy & SYMBOL_FILLING_IOC) != 0)
         request.type_filling = ORDER_FILLING_IOC;
      else
         request.type_filling = ORDER_FILLING_RETURN;
   }

   OrderSend(request, result);

   if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
   {
      string dirStr = (direction == SIGNAL_BUY) ? "BUY" : "SELL";
      string typeStr = (request.action == TRADE_ACTION_PENDING) ? "PENDING " : "";
      LogMessage("ORDER", "*** " + typeStr + dirStr + " ORDER PLACED ***");
      LogMessage("ORDER", "Entry: " + DoubleToString(entryPrice, digits) +
                 " | Lot: " + DoubleToString(lotSize, 2) +
                 " | SL: " + DoubleToString(slPrice, digits) +
                 " | TP: " + DoubleToString(tpPrice, digits));
      LogMessage("ORDER", "Score: " + IntegerToString(score) + " | " + reason);

      if(request.action == TRADE_ACTION_DEAL)
         g_riskManager.IncrementDailyTrades();
   }
   else
   {
      LogMessage("ORDER", "Order failed. Code: " + IntegerToString(result.retcode) + " | " + result.comment);
   }
}

//+------------------------------------------------------------------+
//| Trade event handler - record closed trades for audit               |
//+------------------------------------------------------------------+
void OnTrade()
{
   if(!g_initialized) return;

   static int lastDealsTotal = 0;

   // Select all history first, then count
   if(!HistorySelect(0, TimeCurrent())) return;
   int newDealsTotal = HistoryDealsTotal();

   if(newDealsTotal > lastDealsTotal)
   {
      for(int i = lastDealsTotal; i < newDealsTotal; i++)
      {
         ulong dealTicket = HistoryDealGetTicket(i);
         if(dealTicket <= 0) continue;

         if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != (long)Inp_MagicNumber) continue;
         if(HistoryDealGetInteger(dealTicket, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;

         double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT) +
                         HistoryDealGetDouble(dealTicket, DEAL_SWAP) +
                         HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);

         // Closing deal type is opposite of position direction:
         // DEAL_TYPE_SELL closes a BUY (record as type 0=buy)
         // DEAL_TYPE_BUY closes a SELL (record as type 1=sell)
         int dealType = (HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_SELL) ? 0 : 1;

         int strategy = 0; // Combined confluence (all strategies vote together)

         MqlDateTime dt;
         TimeToStruct((datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME), dt);

         double rr = 0; // R:R requires matching entry deal (future enhancement)

         g_audit.RecordTrade(profit, rr, dealType, strategy, dt.hour, dt.day_of_week);
         g_audit.UpdateBalance(AccountInfoDouble(ACCOUNT_BALANCE));

         // Track consecutive losses for cooldown
         if(profit >= 0)
            g_consecutiveLosses = 0;
         else
         {
            g_consecutiveLosses++;
            if(g_consecutiveLosses >= Inp_CooldownAfterLosses)
            {
               g_cooldownRemaining = Inp_CooldownBars;
               LogMessage("CLOSED", "Cooldown activated after " + IntegerToString(g_consecutiveLosses) + " consecutive losses");
               g_consecutiveLosses = 0;
            }
         }

         string profitStr = (profit >= 0) ? "+" : "";
         LogMessage("CLOSED", "Deal #" + IntegerToString((int)dealTicket) +
                    " | P/L: " + profitStr + DoubleToString(profit, 2) +
                    " | Balance: " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2));
      }
   }

   lastDealsTotal = newDealsTotal;
}

//+------------------------------------------------------------------+
//| Timer function - periodic health checks                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_initialized) return;

   if(g_riskManager.IsDrawdownExceeded())
   {
      LogMessage("ALERT", "!!! DRAWDOWN LIMIT EXCEEDED - TRADING HALTED !!!");
      if(Inp_BotMode == MODE_LIVE)
         CloseAllPositions();
   }

   if(g_riskManager.IsDailyLossExceeded())
      LogMessage("ALERT", "Daily loss limit reached. No more trades today.");
}

//+------------------------------------------------------------------+
//| Emergency close all positions with retry logic                     |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   int maxRetries = 3;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != g_activeSymbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)Inp_MagicNumber) continue;

      bool closed = false;
      for(int retry = 0; retry < maxRetries && !closed; retry++)
      {
         MqlTradeRequest request = {};
         MqlTradeResult  result  = {};

         request.action   = TRADE_ACTION_DEAL;
         request.position = ticket;
         request.symbol   = g_activeSymbol;
         request.volume   = PositionGetDouble(POSITION_VOLUME);
         request.deviation = 100; // Wide slippage for emergency
         request.magic    = Inp_MagicNumber;

         long posType = PositionGetInteger(POSITION_TYPE);
         if(posType == POSITION_TYPE_BUY)
         {  request.type = ORDER_TYPE_SELL; request.price = SymbolInfoDouble(g_activeSymbol, SYMBOL_BID); }
         else
         {  request.type = ORDER_TYPE_BUY; request.price = SymbolInfoDouble(g_activeSymbol, SYMBOL_ASK); }

         long fillPolicy = SymbolInfoInteger(g_activeSymbol, SYMBOL_FILLING_MODE);
         if((fillPolicy & SYMBOL_FILLING_FOK) != 0)
            request.type_filling = ORDER_FILLING_FOK;
         else if((fillPolicy & SYMBOL_FILLING_IOC) != 0)
            request.type_filling = ORDER_FILLING_IOC;
         else
            request.type_filling = ORDER_FILLING_RETURN;

         OrderSend(request, result);

         if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
         {
            LogMessage("CLOSE", "Emergency closed position #" + IntegerToString((int)ticket));
            closed = true;
         }
         else
         {
            LogMessage("CLOSE", "Retry " + IntegerToString(retry + 1) + "/" + IntegerToString(maxRetries) +
                       " for #" + IntegerToString((int)ticket) + " Error: " + IntegerToString(result.retcode));
            Sleep(500 * (retry + 1));
         }
      }

      if(!closed)
         LogMessage("CLOSE", "CRITICAL: Could not close #" + IntegerToString((int)ticket) + " after retries!");
   }
}

//+------------------------------------------------------------------+
//| Tester event - called at end of backtest                           |
//+------------------------------------------------------------------+
double OnTester()
{
   g_audit.CalculateStatistics();

   double winRate = g_audit.GetWinRate();
   double pf = g_audit.GetProfitFactor();
   double dd = g_audit.GetMaxDrawdown();
   int trades = g_audit.GetTotalTrades();

   double fitness = 0;
   if(trades >= 30 && dd > 0)
      fitness = (winRate * 0.4) + (MathMin(pf, 5.0) * 10 * 0.3) + ((100.0 - MathMin(dd, 100.0)) * 0.3);

   Print("=== CLAWBOT BACKTEST COMPLETE ===");
   Print(g_audit.GetReportSummary());
   Print("Fitness Score: " + DoubleToString(fitness, 2));

   return fitness;
}
