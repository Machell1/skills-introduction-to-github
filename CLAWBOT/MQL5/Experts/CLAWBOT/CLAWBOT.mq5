//+------------------------------------------------------------------+
//|                                                     CLAWBOT.mq5  |
//|         CLAWBOT - SMC-Powered Adaptive Confluence Trading Bot    |
//|                    For XAUUSD H1 on Deriv MT5                    |
//+------------------------------------------------------------------+
//|                                                                    |
//|  CLAWBOT Confluence System v2.0:                                   |
//|    C - Confluence (multi-strategy + SMC agreement)                |
//|    L - Levels (OBs, FVGs, liquidity, session ranges)             |
//|    A - Action (momentum + structure confirmation)                 |
//|    W - Window (adaptive session + regime timing)                  |
//|                                                                    |
//|  Strategies (5-Strategy Hybrid + Adaptive Brain):                  |
//|    1. Trend Follow  - Multi-EMA alignment with ADX               |
//|    2. Momentum      - RSI divergence + MACD + Stochastic         |
//|    3. Session       - Asian range breakout during London/NY      |
//|    4. Mean Revert   - Bollinger Band fade at extremes            |
//|    5. Smart Money   - OBs, FVGs, BOS/CHoCH, liquidity sweeps    |
//|                                                                    |
//|  Adaptive Brain:                                                   |
//|    - Detects market regime (trending/ranging/volatile/transition) |
//|    - Adjusts strategy weights per regime + session               |
//|    - Uses SMC structure for directional filtering                 |
//|    - Scales position size by confidence and regime               |
//|                                                                    |
//|  Entry Flow:                                                       |
//|    Brain.Update() -> SMC.Update() -> All strategies evaluate     |
//|    -> Brain applies weights -> Weighted confluence scoring       |
//|    -> MTF + SMC zone filter -> Pending/market order              |
//|    -> Partial close at TP1 + breakeven + trail remainder         |
//|                                                                    |
//+------------------------------------------------------------------+
#property copyright   "CLAWBOT"
#property version     "2.00"
#property description "CLAWBOT v2 - SMC-Powered Adaptive Confluence EA for XAUUSD"
#property description "Designed for Deriv MT5 - H1 Timeframe"

//--- Include modules
#include "ClawUtils.mqh"
#include "ClawMTF.mqh"
#include "ClawSMC.mqh"
#include "ClawBrain.mqh"
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
input double   Inp_RiskPerTrade     = 2.0;     // Risk % (auto-scaled by equity)
input double   Inp_MaxDailyLoss     = 5.0;     // Max daily loss % (auto-scaled)
input double   Inp_MaxDrawdown      = 20.0;    // Max drawdown % (auto-scaled)
input int      Inp_MaxConcurrent    = 3;       // Max concurrent (auto-scaled)
input int      Inp_MaxDailyTrades   = 5;       // Max daily trades (auto-scaled)
input double   Inp_MinRiskReward    = 0.0;     // 0 = allow TP closer than SL (high-WR mode)

//--- Stop Loss / Take Profit (Gold H1: 2x ATR SL, 4x ATR TP = 1:2 R:R)
input string   Inp_Separator3       = "=== SL/TP SETTINGS ===";        // ----
input double   Inp_SL_ATR           = 0.6;     // SL ATR multiplier (moderate SL for high-WR mode)
input double   Inp_TP_ATR           = 0.3;     // TP ATR multiplier (tight TP for 55%+ win rate)
input double   Inp_MinSL            = 150.0;   // Minimum SL points (auto-scaled)
input double   Inp_MaxSL            = 600.0;   // Maximum SL points (auto-scaled)
input double   Inp_TrailActivation  = 99.0;    // Disabled in high-WR mode
input double   Inp_TrailDistance    = 99.0;    // Disabled in high-WR mode
input double   Inp_MaxSpread        = 35.0;    // Max allowed spread (points)

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
input double   Inp_RSI_Overbought   = 75.0;    // RSI overbought level
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
input int      Inp_ExitHour         = 21;      // Session exit hour (UTC)

//--- Mean Reversion Strategy (Strategy 4)
input string   Inp_Separator6b      = "=== MEAN REVERSION STRATEGY ==="; // ----
input bool     Inp_EnableMeanRevert = true;    // Enable Mean Reversion Strategy
input int      Inp_BB_Period        = 20;      // Bollinger Band period
input double   Inp_BB_Deviation     = 2.0;     // Bollinger Band deviation
input double   Inp_BB_TouchBuffer   = 0.2;     // Band touch buffer (% of width)

//--- Smart Money Concepts (Strategy 5)
input string   Inp_Separator6f      = "=== SMART MONEY CONCEPTS ===";  // ----
input bool     Inp_EnableSMC        = false;   // Enable SMC Strategy
input int      Inp_SMC_SwingStr     = 3;       // Swing point strength (bars each side)
input double   Inp_SMC_ImpulseATR   = 2.5;     // Impulse detection ATR multiplier
input int      Inp_SMC_OBMaxAge     = 72;      // Order Block max age (bars)
input double   Inp_SMC_FVGMinSize   = 2.0;     // FVG minimum size ($)
input double   Inp_SMC_FVGMaxSize   = 15.0;    // FVG maximum size ($)
input double   Inp_SMC_SweepATR     = 1.5;     // Liquidity sweep max depth (ATR)
input double   Inp_SMC_RoundNum     = 50.0;    // Round number interval ($)

//--- Adaptive Brain
input string   Inp_Separator6g      = "=== ADAPTIVE BRAIN ===";        // ----
input bool     Inp_EnableBrain      = true;    // Enable adaptive strategy weighting
input double   Inp_Brain_ADXTrend   = 20.0;    // ADX threshold for trending
input double   Inp_Brain_ADXStrong  = 30.0;    // ADX threshold for strong trend
input double   Inp_Brain_ATRHigh    = 1.5;     // ATR ratio for volatile detection
input double   Inp_Brain_ATRLow     = 0.8;     // ATR ratio for compression detection

//--- Multi-Timeframe Filter
input string   Inp_Separator6c      = "=== MTF FILTER ===";             // ----
input bool     Inp_EnableMTF        = false;   // Enable H4 trend filter
input ENUM_TIMEFRAMES Inp_MTF_TF    = PERIOD_H4; // Higher timeframe for filter

//--- Pending Orders
input string   Inp_Separator6d      = "=== PENDING ORDERS ===";         // ----
input bool     Inp_UsePendingOrders = true;    // Use limit orders instead of market
input int      Inp_PendingExpBars   = 4;       // Pending order expiry (bars)
input double   Inp_PullbackATR      = 0.3;     // Pullback distance for limit entry (ATR)

//--- Dynamic Position Closure
input string   Inp_Separator6h      = "=== DYNAMIC CLOSURE ===";        // ----
input bool     Inp_EnableDynClosure = true;    // Enable dynamic position closure
input double   Inp_DynCls_MaxLossATR = 0.4;   // Max loss cap (ATR mult) - hard ceiling on loss
input double   Inp_DynCls_StaleBars  = 8;     // Bars before stale trade check
input double   Inp_DynCls_StaleRange = 0.2;    // Stale P/L range (ATR mult) for exit
input double   Inp_DynCls_AdverseMom = 0.2;   // Adverse momentum loss threshold (ATR mult)

//--- Dynamic Take Profit
input string   Inp_Separator6i      = "=== DYNAMIC TP ===";             // ----
input bool     Inp_EnableDynamicTP  = false;   // Disabled: keeps TP tight for high WR
input double   Inp_DynTP_TrendMult  = 2.5;    // TP regime multiplier for trending (bigger targets)
input double   Inp_DynTP_RangeMult  = 0.8;    // TP regime multiplier for ranging (take what you can)

//--- Partial Close / Profit Locking
input string   Inp_Separator6e      = "=== PROFIT LOCKING ===";         // ----
input bool     Inp_EnablePartialClose = true;  // Auto-adjusted based on account equity
input double   Inp_TP1_ATR          = 1.2;     // TP1 distance (ATR mult) - only partial at real profit
input double   Inp_PartialClosePct  = 0.15;    // Fraction to close at TP1 (15%) - maximize runner

//--- Confluence Settings
input string   Inp_Separator7       = "=== CONFLUENCE SETTINGS ===";   // ----
input int      Inp_MinScore         = 45;      // Minimum total score for entry (higher = better quality)
input int      Inp_MinStrategies    = 2;       // Min strategies agreeing (require confluence)
input int      Inp_MinStrategyScore = 30;      // Min individual strategy score to count
input int      Inp_CooldownAfterLosses = 2;    // Consecutive losses before cooldown (faster response)
input int      Inp_CooldownBars     = 6;       // Bars to skip during cooldown (longer recovery)

//--- Backtest / Audit Settings
input string   Inp_Separator8       = "=== AUDIT SETTINGS ===";        // ----
input double   Inp_WinRateThreshold = 55.0;    // Win rate threshold (%) - 55% profitable at 1:2 R:R
input string   Inp_ReportPath       = "CLAWBOT_Reports"; // Report folder

//+------------------------------------------------------------------+
//| Global Objects                                                      |
//+------------------------------------------------------------------+
CClawTrendStrategy       g_trendStrategy;
CClawMomentumStrategy    g_momentumStrategy;
CClawSessionStrategy     g_sessionStrategy;
CClawMeanRevertStrategy  g_meanRevertStrategy;
CClawSMC                 g_smc;
CClawBrain               g_brain;
CClawMTF                 g_mtfFilter;
CClawRiskManager         g_riskManager;
CClawAudit               g_audit;

//--- State variables
bool   g_initialized = false;
string g_activeSymbol;
int    g_serverUTCOffset = 0;
int    g_consecutiveLosses = 0;
int    g_cooldownRemaining = 0;
int    g_lastDominantStrategy = 0;   // Dominant strategy for last trade (for audit)

//--- Effective parameters (set by equity scaler, override input defaults)
double g_eff_RiskPerTrade;
double g_eff_MaxDailyLoss;
double g_eff_MaxDrawdown;
int    g_eff_MaxConcurrent;
int    g_eff_MaxDailyTrades;
double g_eff_MinSL;
double g_eff_MaxSL;
double g_eff_MaxLot;
bool   g_eff_EnablePartialClose;

//+------------------------------------------------------------------+
//| Linear interpolation helper                                        |
//+------------------------------------------------------------------+
double Lerp(double bal, double lo_bal, double hi_bal, double lo_val, double hi_val)
{
   if(bal <= lo_bal) return lo_val;
   if(bal >= hi_bal) return hi_val;
   double t = (bal - lo_bal) / (hi_bal - lo_bal);
   return lo_val + t * (hi_val - lo_val);
}

//+------------------------------------------------------------------+
//| Dynamic equity scaling - adjusts all params to account size        |
//+------------------------------------------------------------------+
void ScaleParamsToEquity()
{
   double bal = AccountInfoDouble(ACCOUNT_EQUITY);
   if(bal <= 0) bal = AccountInfoDouble(ACCOUNT_BALANCE);
   if(bal <= 0) bal = 100.0;  // Fallback

   // Risk per trade: 1.5% (micro) -> 3.0% (large)
   g_eff_RiskPerTrade = NormalizeDouble(Lerp(bal, 50, 10000, 1.5, 3.0), 1);

   // Max daily loss: 8% (micro) -> 4% (large)
   g_eff_MaxDailyLoss = NormalizeDouble(Lerp(bal, 50, 10000, 8.0, 4.0), 1);

   // Max drawdown: 30% (micro) -> 12% (large)
   g_eff_MaxDrawdown = NormalizeDouble(Lerp(bal, 50, 10000, 30.0, 12.0), 1);

   // Max concurrent: 1 (micro) -> 3 (medium+)
   if(bal < 500)       g_eff_MaxConcurrent = 1;
   else if(bal < 2000) g_eff_MaxConcurrent = 2;
   else                g_eff_MaxConcurrent = 3;

   // Max daily trades: 2 (micro) -> 5 (medium+)
   if(bal < 200)       g_eff_MaxDailyTrades = 2;
   else if(bal < 1000) g_eff_MaxDailyTrades = 3;
   else if(bal < 5000) g_eff_MaxDailyTrades = 4;
   else                g_eff_MaxDailyTrades = 5;

   // SL range: tighter for small, wider for large
   g_eff_MinSL = NormalizeDouble(Lerp(bal, 50, 5000, 80.0, 150.0), 0);
   g_eff_MaxSL = NormalizeDouble(Lerp(bal, 50, 5000, 300.0, 600.0), 0);

   // Max lot: scale with account
   g_eff_MaxLot = NormalizeDouble(Lerp(bal, 50, 50000, 0.2, 10.0), 2);

   // Partial close: only if lot is large enough to split
   // min lot for split = min_lot / partial_close_pct = 0.01 / 0.15 ≈ 0.067
   double typicalSLpts = 300.0;
   double typicalLot = (bal * g_eff_RiskPerTrade / 100.0) / (typicalSLpts * 1.0);
   double minLotForSplit = 0.01 / MathMax(Inp_PartialClosePct, 0.01);
   g_eff_EnablePartialClose = (typicalLot >= minLotForSplit);

   string tier = (bal < 500 ? "MICRO" : (bal < 2000 ? "SMALL" : (bal < 10000 ? "MEDIUM" : "LARGE")));
   LogMessage("EQUITY", "Account: $" + DoubleToString(bal, 0) + " (" + tier + ")");
   LogMessage("EQUITY", "Risk: " + DoubleToString(g_eff_RiskPerTrade, 1) + "% | "
              + "MaxDD: " + DoubleToString(g_eff_MaxDrawdown, 1) + "% | "
              + "Concurrent: " + IntegerToString(g_eff_MaxConcurrent) + " | "
              + "Daily: " + IntegerToString(g_eff_MaxDailyTrades) + " | "
              + "SL: " + DoubleToString(g_eff_MinSL, 0) + "-" + DoubleToString(g_eff_MaxSL, 0) + "pts | "
              + "Partial: " + (g_eff_EnablePartialClose ? "ON" : "OFF"));
}

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
   if(Inp_MinScore < 0 || Inp_MinScore > 200)
   {
      LogMessage("INIT", "ERROR: MinScore must be 0-200. Got: " + IntegerToString(Inp_MinScore));
      valid = false;
   }
   if(Inp_MinStrategies < 1 || Inp_MinStrategies > 4)
   {
      LogMessage("INIT", "ERROR: MinStrategies must be 1-4. Got: " + IntegerToString(Inp_MinStrategies));
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

   return valid;
}

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   LogMessage("INIT", "==========================================");
   LogMessage("INIT", "  CLAWBOT v2.00 - SMC Adaptive System");
   LogMessage("INIT", "  Symbol: " + Inp_Symbol);
   LogMessage("INIT", "  Timeframe: " + EnumToString(Inp_Timeframe));
   LogMessage("INIT", "  Mode: " + (Inp_BotMode == MODE_BACKTEST ? "BACKTEST" : "LIVE"));
   LogMessage("INIT", "  SMC: " + (Inp_EnableSMC ? "ON" : "OFF"));
   LogMessage("INIT", "  Brain: " + (Inp_EnableBrain ? "ON" : "OFF"));
   LogMessage("INIT", "==========================================");

   if(!ValidateInputs())
   {
      LogMessage("INIT", "FATAL: Input validation failed.");
      return INIT_FAILED;
   }

   // Dynamic equity scaling - auto-adjust params to account size
   ScaleParamsToEquity();

   g_serverUTCOffset = GetServerUTCOffset();
   LogMessage("INIT", "Server UTC offset: " + IntegerToString(g_serverUTCOffset) + " hours");

   // Validate symbol
   g_activeSymbol = Inp_Symbol;
   if(!ValidateSymbol(g_activeSymbol))
   {
      bool found = false;
      string alts[] = {"XAUUSD", "XAUUSDm", "#XAUUSD", "Gold"};
      for(int i = 0; i < ArraySize(alts); i++)
      {
         if(ValidateSymbol(alts[i])) { g_activeSymbol = alts[i]; found = true; break; }
      }
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

   bool initOk = true;

   // Initialize strategies
   if(Inp_EnableTrend)
   {
      if(!g_trendStrategy.Init(g_activeSymbol, Inp_Timeframe,
            Inp_EMA_Fast, Inp_EMA_Signal, Inp_EMA_Trend, Inp_EMA_Major,
            Inp_ADX_Period, Inp_ADX_Threshold, Inp_CrossoverLookback))
      { LogMessage("INIT", "ERROR: Trend strategy init failed"); initOk = false; }
   }

   if(Inp_EnableMomentum)
   {
      if(!g_momentumStrategy.Init(g_activeSymbol, Inp_Timeframe,
            Inp_RSI_Period, Inp_RSI_Oversold, Inp_RSI_Overbought,
            Inp_MACD_Fast, Inp_MACD_Slow, Inp_MACD_Signal,
            Inp_Stoch_K, Inp_Stoch_D, Inp_Stoch_Slowing))
      { LogMessage("INIT", "ERROR: Momentum strategy init failed"); initOk = false; }
   }

   if(Inp_EnableSession)
   {
      if(!g_sessionStrategy.Init(g_activeSymbol, Inp_Timeframe,
            14, 0.5, Inp_AsianStart, Inp_AsianEnd,
            Inp_LondonStart, Inp_LondonEnd, Inp_ExitHour))
      { LogMessage("INIT", "ERROR: Session strategy init failed"); initOk = false; }
   }

   if(Inp_EnableMeanRevert)
   {
      if(!g_meanRevertStrategy.Init(g_activeSymbol, Inp_Timeframe,
            Inp_BB_Period, Inp_BB_Deviation,
            Inp_RSI_Period, Inp_RSI_Oversold, Inp_RSI_Overbought,
            Inp_BB_TouchBuffer))
      { LogMessage("INIT", "ERROR: Mean Reversion strategy init failed"); initOk = false; }
   }

   // Initialize SMC module
   if(Inp_EnableSMC)
   {
      if(!g_smc.Init(g_activeSymbol, Inp_Timeframe,
            Inp_SMC_SwingStr, Inp_SMC_ImpulseATR, Inp_SMC_OBMaxAge,
            Inp_SMC_FVGMinSize, Inp_SMC_FVGMaxSize, 50,
            Inp_SMC_SweepATR, Inp_SMC_RoundNum))
      { LogMessage("INIT", "ERROR: SMC module init failed"); initOk = false; }
   }

   // Initialize Brain
   if(Inp_EnableBrain)
   {
      if(!g_brain.Init(g_activeSymbol, Inp_Timeframe,
            Inp_Brain_ADXTrend, Inp_Brain_ADXStrong,
            Inp_Brain_ATRHigh, Inp_Brain_ATRLow))
      { LogMessage("INIT", "WARNING: Brain init failed, using equal weights"); }
   }

   // Initialize MTF filter
   if(Inp_EnableMTF)
   {
      if(!g_mtfFilter.Init(g_activeSymbol, Inp_MTF_TF))
         LogMessage("INIT", "WARNING: MTF filter init failed, continuing without it");
   }

   // Initialize risk manager with equity-scaled effective parameters
   if(!g_riskManager.Init(g_activeSymbol, Inp_Timeframe, Inp_MagicNumber,
         g_eff_RiskPerTrade, g_eff_MaxDailyLoss, g_eff_MaxDrawdown,
         g_eff_MaxConcurrent, g_eff_MaxDailyTrades, Inp_MinRiskReward,
         Inp_SL_ATR, Inp_TP_ATR, g_eff_MinSL, g_eff_MaxSL,
         Inp_TrailActivation, Inp_TrailDistance))
   { LogMessage("INIT", "ERROR: Risk manager init failed"); initOk = false; }

   if(!g_audit.Init(AccountInfoDouble(ACCOUNT_BALANCE), Inp_ReportPath))
   { LogMessage("INIT", "ERROR: Audit module init failed"); initOk = false; }

   if(!initOk)
   {
      LogMessage("INIT", "FATAL: One or more modules failed to initialize");
      return INIT_FAILED;
   }

   EventSetTimer(60);
   g_initialized = true;
   LogMessage("INIT", "CLAWBOT v2.0 initialized. SMC + Brain active. Waiting for signals...");
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
         Alert("CLAWBOT BACKTEST PASSED! Win rate: " +
               DoubleToString(g_audit.GetWinRate(), 1) + "%");
      }
      else
      {
         g_audit.GenerateWeaknessReport();
         LogMessage("DEINIT", "*** BACKTEST DID NOT MEET THRESHOLD ***");
         LogMessage("DEINIT", "Win rate: " + DoubleToString(g_audit.GetWinRate(), 1) + "%");
         Alert("CLAWBOT BACKTEST: Win rate " + DoubleToString(g_audit.GetWinRate(), 1) +
               "% (target: " + DoubleToString(Inp_WinRateThreshold, 0) + "%).");
      }
      Print(g_audit.GetReportSummary());
   }

   DeleteAllPendingOrders(g_activeSymbol, Inp_MagicNumber);

   g_trendStrategy.Deinit();
   g_momentumStrategy.Deinit();
   g_sessionStrategy.Deinit();
   g_meanRevertStrategy.Deinit();
   g_smc.Deinit();
   g_brain.Deinit();
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
   if(Inp_EnableDynClosure)
      g_riskManager.ManageDynamicClosure(Inp_DynCls_MaxLossATR, Inp_DynCls_StaleBars,
                                          Inp_DynCls_StaleRange, Inp_DynCls_AdverseMom);
   if(g_eff_EnablePartialClose)
      g_riskManager.ManagePartialClose(Inp_TP1_ATR, Inp_PartialClosePct);
   g_riskManager.ManageBreakeven();
   g_riskManager.ManageTrailingStops();

   // === PHASE 2: NEW BAR LOGIC ===
   if(!IsNewBar(g_activeSymbol, Inp_Timeframe)) return;

   if(!g_riskManager.CanOpenTrade()) return;

   if(g_cooldownRemaining > 0) { g_cooldownRemaining--; return; }

   double currentSpread = GetCurrentSpread(g_activeSymbol);
   if(currentSpread > Inp_MaxSpread) return;

   // === UPDATE SMC MARKET STRUCTURE ===
   if(Inp_EnableSMC)
      g_smc.Update();

   // === UPDATE BRAIN (regime detection, session awareness) ===
   ENUM_MARKET_TREND smcTrend     = Inp_EnableSMC ? g_smc.GetMarketTrend() : TREND_UNDEFINED;
   ENUM_PRICE_ZONE   smcZone      = Inp_EnableSMC ? g_smc.GetPriceZone() : ZONE_EQUILIBRIUM;
   ENUM_STRUCTURE_EVENT smcEvent   = Inp_EnableSMC ? g_smc.GetLastStructEvent() : STRUCT_NONE;

   if(Inp_EnableBrain)
      g_brain.Update(smcTrend, smcZone, smcEvent);

   // === GET STRATEGY WEIGHTS FROM BRAIN ===
   StrategyWeights weights;
   weights.Reset();
   if(Inp_EnableBrain)
   {
      weights = g_brain.GetWeights(smcTrend, smcZone, smcEvent);
      if(!weights.allowTrading) return; // Brain says don't trade now
   }

   // === H4 MTF FILTER ===
   ENUM_SIGNAL_TYPE mtfDirection = SIGNAL_NONE;
   if(Inp_EnableMTF)
      mtfDirection = g_mtfFilter.GetTrendDirection();

   // Delete stale pending orders
   DeleteAllPendingOrders(g_activeSymbol, Inp_MagicNumber);

   // === EVALUATE ALL 5 STRATEGIES ===
   SignalResult trendSignal, momentumSignal, sessionSignal, meanRevertSignal, smcSignal;
   trendSignal.Reset();
   momentumSignal.Reset();
   sessionSignal.Reset();
   meanRevertSignal.Reset();
   smcSignal.Reset();

   if(Inp_EnableTrend)      trendSignal      = g_trendStrategy.Evaluate();
   if(Inp_EnableMomentum)   momentumSignal   = g_momentumStrategy.Evaluate();
   if(Inp_EnableSession)    sessionSignal    = g_sessionStrategy.Evaluate();
   if(Inp_EnableMeanRevert) meanRevertSignal = g_meanRevertStrategy.Evaluate();
   if(Inp_EnableSMC)        smcSignal        = g_smc.Evaluate();

   // === WEIGHTED CONFLUENCE ENGINE ===
   int buyVotes  = 0, sellVotes = 0;
   double buyScore  = 0, sellScore = 0;
   string buyReasons = "", sellReasons = "";
   double bestBuyEntry = 0, bestSellEntry = 0;
   double bestBuyTP = 0, bestSellTP = 0;
   double bestBuySL = 0, bestSellSL = 0;
   // Track dominant strategy for audit (0=Trend, 1=Mom, 2=Sess, 3=MRev, 4=SMC)
   double bestBuyStratScore = 0, bestSellStratScore = 0;
   int    bestBuyStrat = 0, bestSellStrat = 0;

   int minStratScore = Inp_MinStrategyScore;

   // Helper: tally a weighted strategy vote
   // Trend (strategy index 0)
   if(trendSignal.direction == SIGNAL_BUY && trendSignal.score >= minStratScore)
   {  double ws = trendSignal.score * weights.trend;
      buyVotes++; buyScore += ws;
      if(ws > bestBuyStratScore) { bestBuyStratScore = ws; bestBuyStrat = 0; }
      buyReasons += "[TREND:" + IntegerToString(trendSignal.score) + "x" + DoubleToString(weights.trend, 1) + "] "; }
   else if(trendSignal.direction == SIGNAL_SELL && trendSignal.score >= minStratScore)
   {  double ws = trendSignal.score * weights.trend;
      sellVotes++; sellScore += ws;
      if(ws > bestSellStratScore) { bestSellStratScore = ws; bestSellStrat = 0; }
      sellReasons += "[TREND:" + IntegerToString(trendSignal.score) + "x" + DoubleToString(weights.trend, 1) + "] "; }

   // Momentum (strategy index 1)
   if(momentumSignal.direction == SIGNAL_BUY && momentumSignal.score >= minStratScore)
   {  double ws = momentumSignal.score * weights.momentum;
      buyVotes++; buyScore += ws;
      if(ws > bestBuyStratScore) { bestBuyStratScore = ws; bestBuyStrat = 1; }
      buyReasons += "[MOM:" + IntegerToString(momentumSignal.score) + "x" + DoubleToString(weights.momentum, 1) + "] "; }
   else if(momentumSignal.direction == SIGNAL_SELL && momentumSignal.score >= minStratScore)
   {  double ws = momentumSignal.score * weights.momentum;
      sellVotes++; sellScore += ws;
      if(ws > bestSellStratScore) { bestSellStratScore = ws; bestSellStrat = 1; }
      sellReasons += "[MOM:" + IntegerToString(momentumSignal.score) + "x" + DoubleToString(weights.momentum, 1) + "] "; }

   // Session (strategy index 2)
   if(sessionSignal.direction == SIGNAL_BUY && sessionSignal.score >= minStratScore)
   {  double ws = sessionSignal.score * weights.session;
      buyVotes++; buyScore += ws;
      if(ws > bestBuyStratScore) { bestBuyStratScore = ws; bestBuyStrat = 2; }
      buyReasons += "[SESS:" + IntegerToString(sessionSignal.score) + "x" + DoubleToString(weights.session, 1) + "] ";
      if(sessionSignal.entryPrice > 0) bestBuyEntry = sessionSignal.entryPrice; }
   else if(sessionSignal.direction == SIGNAL_SELL && sessionSignal.score >= minStratScore)
   {  double ws = sessionSignal.score * weights.session;
      sellVotes++; sellScore += ws;
      if(ws > bestSellStratScore) { bestSellStratScore = ws; bestSellStrat = 2; }
      sellReasons += "[SESS:" + IntegerToString(sessionSignal.score) + "x" + DoubleToString(weights.session, 1) + "] ";
      if(sessionSignal.entryPrice > 0) bestSellEntry = sessionSignal.entryPrice; }

   // Mean Reversion (strategy index 3)
   if(meanRevertSignal.direction == SIGNAL_BUY && meanRevertSignal.score >= minStratScore)
   {  double ws = meanRevertSignal.score * weights.meanRevert;
      buyVotes++; buyScore += ws;
      if(ws > bestBuyStratScore) { bestBuyStratScore = ws; bestBuyStrat = 3; }
      buyReasons += "[MREV:" + IntegerToString(meanRevertSignal.score) + "x" + DoubleToString(weights.meanRevert, 1) + "] ";
      if(meanRevertSignal.entryPrice > 0) bestBuyEntry = meanRevertSignal.entryPrice;
      if(meanRevertSignal.suggestedTP > 0) bestBuyTP = meanRevertSignal.suggestedTP; }
   else if(meanRevertSignal.direction == SIGNAL_SELL && meanRevertSignal.score >= minStratScore)
   {  double ws = meanRevertSignal.score * weights.meanRevert;
      sellVotes++; sellScore += ws;
      if(ws > bestSellStratScore) { bestSellStratScore = ws; bestSellStrat = 3; }
      sellReasons += "[MREV:" + IntegerToString(meanRevertSignal.score) + "x" + DoubleToString(weights.meanRevert, 1) + "] ";
      if(meanRevertSignal.entryPrice > 0) bestSellEntry = meanRevertSignal.entryPrice;
      if(meanRevertSignal.suggestedTP > 0) bestSellTP = meanRevertSignal.suggestedTP; }

   // SMC (strategy index 4) - provides entry, SL, TP from order blocks/FVGs
   if(smcSignal.direction == SIGNAL_BUY && smcSignal.score >= 10)
   {  double ws = smcSignal.score * weights.smc;
      buyVotes++; buyScore += ws;
      if(ws > bestBuyStratScore) { bestBuyStratScore = ws; bestBuyStrat = 4; }
      buyReasons += "[SMC:" + IntegerToString(smcSignal.score) + "x" + DoubleToString(weights.smc, 1) + " " + smcSignal.reason + "] ";
      if(smcSignal.entryPrice > 0) bestBuyEntry = smcSignal.entryPrice;
      if(smcSignal.suggestedTP > 0) bestBuyTP = smcSignal.suggestedTP;
      if(smcSignal.suggestedSL > 0) bestBuySL = smcSignal.suggestedSL; }
   else if(smcSignal.direction == SIGNAL_SELL && smcSignal.score >= 10)
   {  double ws = smcSignal.score * weights.smc;
      sellVotes++; sellScore += ws;
      if(ws > bestSellStratScore) { bestSellStratScore = ws; bestSellStrat = 4; }
      sellReasons += "[SMC:" + IntegerToString(smcSignal.score) + "x" + DoubleToString(weights.smc, 1) + " " + smcSignal.reason + "] ";
      if(smcSignal.entryPrice > 0) bestSellEntry = smcSignal.entryPrice;
      if(smcSignal.suggestedTP > 0) bestSellTP = smcSignal.suggestedTP;
      if(smcSignal.suggestedSL > 0) bestSellSL = smcSignal.suggestedSL; }

   // === SMC PREMIUM/DISCOUNT ZONE FILTER ===
   // If in premium, suppress buys; if in discount, suppress sells
   if(Inp_EnableSMC)
   {
      if(smcZone == ZONE_PREMIUM || smcZone == ZONE_EXTREME_PREMIUM)
         buyScore *= 0.5;  // Heavily penalize buys from premium
      if(smcZone == ZONE_DISCOUNT || smcZone == ZONE_EXTREME_DISCOUNT)
         sellScore *= 0.5; // Heavily penalize sells from discount
   }

   // === DETERMINE FINAL DIRECTION ===
   int adjustedMinScore = Inp_MinScore + weights.minScoreAdj;
   if(adjustedMinScore < 10) adjustedMinScore = 10;

   ENUM_SIGNAL_TYPE finalDirection = SIGNAL_NONE;
   int finalScore = 0;
   string finalReason = "";
   double suggestedEntry = 0;
   double suggestedTP = 0;
   double suggestedSL = 0;

   int dominantStrategy = 0;
   if(buyVotes >= Inp_MinStrategies && buyScore >= adjustedMinScore && buyScore > sellScore)
   {
      finalDirection = SIGNAL_BUY; finalScore = (int)buyScore; finalReason = buyReasons;
      suggestedEntry = bestBuyEntry; suggestedTP = bestBuyTP; suggestedSL = bestBuySL;
      dominantStrategy = bestBuyStrat;
   }
   else if(sellVotes >= Inp_MinStrategies && sellScore >= adjustedMinScore && sellScore > buyScore)
   {
      finalDirection = SIGNAL_SELL; finalScore = (int)sellScore; finalReason = sellReasons;
      suggestedEntry = bestSellEntry; suggestedTP = bestSellTP; suggestedSL = bestSellSL;
      dominantStrategy = bestSellStrat;
   }

   if(finalDirection == SIGNAL_NONE) return;

   // === MTF FILTER: only trade in H4 trend direction ===
   if(Inp_EnableMTF && mtfDirection != SIGNAL_NONE)
   {
      if(finalDirection != mtfDirection) return;
      finalScore += 10;
      finalReason += "[MTF:H4] ";
   }

   // === BRAIN REGIME CONTEXT IN LOG ===
   if(Inp_EnableBrain)
   {
      finalReason += "[" + g_brain.GetRegimeName() + "] ";
   }

   // Store dominant strategy for audit tracking in OnTrade
   g_lastDominantStrategy = dominantStrategy;

   // Place trade
   PlaceOrder(finalDirection, finalScore, finalReason,
              suggestedEntry, suggestedTP, suggestedSL, weights.lotMultiplier);
}

//+------------------------------------------------------------------+
//| Place a pending limit order or market order                        |
//| Now accepts SMC-based SL and brain lot multiplier                  |
//+------------------------------------------------------------------+
void PlaceOrder(ENUM_SIGNAL_TYPE direction, int score, string reason,
                double suggestedEntry, double suggestedTP, double suggestedSL,
                double lotMultiplier)
{
   if(direction == SIGNAL_BUY && CountBuyPositions(g_activeSymbol, Inp_MagicNumber) > 0) return;
   if(direction == SIGNAL_SELL && CountSellPositions(g_activeSymbol, Inp_MagicNumber) > 0) return;
   if(CountPendingOrders(g_activeSymbol, Inp_MagicNumber) > 0) return;

   double point = SymbolInfoDouble(g_activeSymbol, SYMBOL_POINT);
   if(point <= 0) return;
   int digits = (int)SymbolInfoInteger(g_activeSymbol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(g_activeSymbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(g_activeSymbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) return;

   // --- Determine entry price ---
   double entryPrice = 0;
   bool usePending = Inp_UsePendingOrders;

   if(suggestedEntry > 0)
      entryPrice = NormalizeDouble(suggestedEntry, digits);
   else if(usePending)
   {
      double atr = g_riskManager.GetCurrentATR();

      // === RETRACEMENT ENTRY LOGIC ===
      // Priority 1: OTE zone (only when very close to the zone - within 0.5 ATR)
      if(Inp_EnableSMC && g_smc.IsOTEActive())
      {
         int oteDir = g_smc.GetOTEDirection();
         if((direction == SIGNAL_BUY && oteDir == 1) ||
            (direction == SIGNAL_SELL && oteDir == -1))
         {
            double oteMid = (g_smc.GetOTEHigh() + g_smc.GetOTELow()) / 2.0;
            double distToOTE = 0;
            if(direction == SIGNAL_BUY)
               distToOTE = ask - oteMid;
            else
               distToOTE = oteMid - bid;

            // Only use OTE if price is within 0.5 ATR of the zone (reachable)
            if(distToOTE >= 0 && distToOTE < atr * 0.5)
               entryPrice = NormalizeDouble(oteMid, digits);
         }
      }

      // Priority 2: Fibonacci retracement (only shallow 38.2%-50% for better fill rate)
      if(entryPrice <= 0 && Inp_EnableSMC)
      {
         double swHigh = g_smc.GetSwingRangeHigh();
         double swLow  = g_smc.GetSwingRangeLow();
         double swRange = swHigh - swLow;

         if(swRange > atr * 0.8 && swRange < atr * 6.0) // Valid but not extreme swing
         {
            if(direction == SIGNAL_BUY)
            {
               // Use shallower 38.2% retracement for better fill probability
               double fib382 = swHigh - swRange * 0.382;
               double fib500 = swHigh - swRange * 0.500;
               double distTo382 = ask - fib382;
               double distTo500 = ask - fib500;

               // 50% only if very close (within 0.3 ATR), else 38.2%, else skip
               if(distTo500 >= 0 && distTo500 < atr * 0.3)
                  entryPrice = NormalizeDouble(fib500, digits);
               else if(distTo382 >= 0 && distTo382 < atr * 0.5)
                  entryPrice = NormalizeDouble(fib382, digits);
            }
            else
            {
               double fib382 = swLow + swRange * 0.382;
               double fib500 = swLow + swRange * 0.500;
               double distTo382 = fib382 - bid;
               double distTo500 = fib500 - bid;

               if(distTo500 >= 0 && distTo500 < atr * 0.3)
                  entryPrice = NormalizeDouble(fib500, digits);
               else if(distTo382 >= 0 && distTo382 < atr * 0.5)
                  entryPrice = NormalizeDouble(fib382, digits);
            }
         }
      }

      // Priority 3: ATR pullback fallback (always available)
      if(entryPrice <= 0)
      {
         double pullback = atr * Inp_PullbackATR;
         if(direction == SIGNAL_BUY)
            entryPrice = NormalizeDouble(ask - pullback, digits);
         else
            entryPrice = NormalizeDouble(bid + pullback, digits);
      }
   }

   double minStopPts = GetMinStopLevel(g_activeSymbol);
   double minStopDist = minStopPts * point;

   if(usePending && entryPrice > 0)
   {
      if(direction == SIGNAL_BUY && entryPrice >= ask - minStopDist)
         usePending = false;
      else if(direction == SIGNAL_SELL && entryPrice <= bid + minStopDist)
         usePending = false;
   }

   if(!usePending || entryPrice <= 0)
      entryPrice = (direction == SIGNAL_BUY) ? ask : bid;

   // --- Calculate SL: prefer SMC-based, fallback to ATR ---
   double slPrice = 0;
   if(suggestedSL > 0)
   {
      slPrice = NormalizeDouble(suggestedSL, digits);
      // Validate SMC SL is on the correct side
      if(direction == SIGNAL_BUY && slPrice >= entryPrice) slPrice = 0;
      if(direction == SIGNAL_SELL && slPrice <= entryPrice) slPrice = 0;
   }

   if(slPrice <= 0)
      slPrice = g_riskManager.CalculateSLPriceFromEntry(direction, entryPrice);
   if(slPrice <= 0) return;

   // Enforce minimum stop level
   double slDist = MathAbs(entryPrice - slPrice) / point;
   if(slDist < minStopPts)
   {
      if(direction == SIGNAL_BUY)
         slPrice = NormalizeDouble(entryPrice - minStopPts * point, digits);
      else
         slPrice = NormalizeDouble(entryPrice + minStopPts * point, digits);
   }

   // --- Calculate TP: dynamic TP with SMC targets ---
   double tpPrice = 0;
   if(Inp_EnableDynamicTP && Inp_EnableSMC)
   {
      // Find nearest SMC structural target for TP
      double smcTarget = 0;
      if(direction == SIGNAL_BUY)
         smcTarget = g_smc.GetNearestBuyTarget(entryPrice);
      else
         smcTarget = g_smc.GetNearestSellTarget(entryPrice);

      // Determine regime multiplier for TP scaling
      double regimeMult = 1.0;
      if(Inp_EnableBrain)
      {
         string regime = g_brain.GetRegimeName();
         if(StringFind(regime, "TREND") >= 0)
            regimeMult = Inp_DynTP_TrendMult;
         else if(StringFind(regime, "RANG") >= 0)
            regimeMult = Inp_DynTP_RangeMult;
      }

      // Use suggested TP from strategies if available, otherwise use SMC target
      if(suggestedTP > 0)
      {
         // Blend: use the closer of suggestedTP and dynamic TP
         double dynTP = g_riskManager.CalculateDynamicTP(direction, entryPrice, slPrice, smcTarget, regimeMult);
         if(dynTP > 0)
         {
            double sugDist = MathAbs(suggestedTP - entryPrice);
            double dynDist = MathAbs(dynTP - entryPrice);
            // Use the more conservative (closer) target
            tpPrice = (sugDist < dynDist) ? suggestedTP : dynTP;
         }
         else
            tpPrice = NormalizeDouble(suggestedTP, digits);
      }
      else
         tpPrice = g_riskManager.CalculateDynamicTP(direction, entryPrice, slPrice, smcTarget, regimeMult);
   }
   else if(suggestedTP > 0)
      tpPrice = NormalizeDouble(suggestedTP, digits);
   else
      tpPrice = g_riskManager.CalculateTPPriceFromEntry(direction, entryPrice, slPrice);

   if(tpPrice <= 0) return;

   double tpDist = MathAbs(entryPrice - tpPrice) / point;
   if(tpDist < minStopPts)
   {
      if(direction == SIGNAL_BUY)
         tpPrice = NormalizeDouble(entryPrice + minStopPts * point, digits);
      else
         tpPrice = NormalizeDouble(entryPrice - minStopPts * point, digits);
   }

   // --- Calculate lot size with brain multiplier ---
   double slPoints = MathAbs(entryPrice - slPrice) / point;
   double lotSize = g_riskManager.CalculateLotSize(slPoints);
   if(lotSize <= 0) return;

   // Apply brain's regime-based lot multiplier
   lotSize = NormalizeLot(g_activeSymbol, lotSize * lotMultiplier);

   // Scale by confluence strength (less aggressive reduction)
   if(score < 50)
      lotSize = NormalizeLot(g_activeSymbol, lotSize * 0.60);
   else if(score < 70)
      lotSize = NormalizeLot(g_activeSymbol, lotSize * 0.80);
   // Score >= 70: full lot size (reward high-confidence signals)
   if(lotSize <= 0) return;

   // --- Build order request ---
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   request.symbol   = g_activeSymbol;
   request.volume   = lotSize;
   request.sl       = slPrice;
   request.tp       = tpPrice;
   request.magic    = Inp_MagicNumber;
   request.comment  = "CLAWv2|S=" + IntegerToString(score) + "|" +
                       TimeToString(TimeCurrent(), TIME_DATE);

   if(usePending && MathAbs(entryPrice - ((direction == SIGNAL_BUY) ? ask : bid)) > minStopDist)
   {
      request.action = TRADE_ACTION_PENDING;
      request.price  = entryPrice;

      if(direction == SIGNAL_BUY)
         request.type = (entryPrice < ask) ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_BUY_STOP;
      else
         request.type = (entryPrice > bid) ? ORDER_TYPE_SELL_LIMIT : ORDER_TYPE_SELL_STOP;

      request.type_time  = ORDER_TIME_SPECIFIED;
      request.expiration = TimeCurrent() + Inp_PendingExpBars * PeriodSeconds(Inp_Timeframe);
      request.type_filling = ORDER_FILLING_RETURN;
   }
   else
   {
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
      LogMessage("ORDER", "*** " + typeStr + dirStr + " ***");
      LogMessage("ORDER", "Entry: " + DoubleToString(entryPrice, digits) +
                 " | Lot: " + DoubleToString(lotSize, 2) +
                 " | SL: " + DoubleToString(slPrice, digits) +
                 " | TP: " + DoubleToString(tpPrice, digits));
      LogMessage("ORDER", "Score: " + IntegerToString(score) +
                 " | LotMult: " + DoubleToString(lotMultiplier, 2) +
                 " | " + reason);

      if(request.action == TRADE_ACTION_DEAL)
         g_riskManager.IncrementDailyTrades();
   }
   else
   {
      LogMessage("ORDER", "Order failed. Code: " + IntegerToString(result.retcode) +
                 " | " + result.comment);
   }
}

//+------------------------------------------------------------------+
//| Trade event handler                                                |
//+------------------------------------------------------------------+
void OnTrade()
{
   if(!g_initialized) return;

   static int lastDealsTotal = 0;

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

         int dealType = (HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_SELL) ? 0 : 1;
         MqlDateTime dt;
         TimeToStruct((datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME), dt);

         g_audit.RecordTrade(profit, 0, dealType, g_lastDominantStrategy, dt.hour, dt.day_of_week);
         g_audit.UpdateBalance(AccountInfoDouble(ACCOUNT_BALANCE));

         if(profit >= 0)
            g_consecutiveLosses = 0;
         else
         {
            g_consecutiveLosses++;
            if(g_consecutiveLosses >= Inp_CooldownAfterLosses)
            {
               g_cooldownRemaining = Inp_CooldownBars;
               LogMessage("CLOSED", "Cooldown: " + IntegerToString(g_consecutiveLosses) + " consecutive losses");
               g_consecutiveLosses = 0;
            }
         }

         string pStr = (profit >= 0) ? "+" : "";
         LogMessage("CLOSED", "#" + IntegerToString((int)dealTicket) +
                    " P/L: " + pStr + DoubleToString(profit, 2) +
                    " Bal: " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2));
      }
   }
   lastDealsTotal = newDealsTotal;
}

//+------------------------------------------------------------------+
//| Timer function                                                     |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_initialized) return;

   if(g_riskManager.IsDrawdownExceeded())
   {
      LogMessage("ALERT", "!!! DRAWDOWN LIMIT EXCEEDED !!!");
      if(Inp_BotMode == MODE_LIVE) CloseAllPositions();
   }
   if(g_riskManager.IsDailyLossExceeded())
      LogMessage("ALERT", "Daily loss limit reached.");
}

//+------------------------------------------------------------------+
//| Emergency close all positions                                      |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != g_activeSymbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != (long)Inp_MagicNumber) continue;

      for(int retry = 0; retry < 3; retry++)
      {
         MqlTradeRequest request = {};
         MqlTradeResult  result  = {};

         request.action   = TRADE_ACTION_DEAL;
         request.position = ticket;
         request.symbol   = g_activeSymbol;
         request.volume   = PositionGetDouble(POSITION_VOLUME);
         request.deviation = 100;
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
            LogMessage("CLOSE", "Emergency closed #" + IntegerToString((int)ticket));
            break;
         }
         Sleep(500 * (retry + 1));
      }
   }
}

//+------------------------------------------------------------------+
//| Tester event                                                       |
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

   Print("=== CLAWBOT v2.0 BACKTEST COMPLETE ===");
   Print(g_audit.GetReportSummary());
   Print("Fitness Score: " + DoubleToString(fitness, 2));

   return fitness;
}
