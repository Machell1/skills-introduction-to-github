//+------------------------------------------------------------------+
//|                                                   ClawAudit.mqh  |
//|                    CLAWBOT - Backtesting Audit & Reporting       |
//|                         For XAUUSD H1 on Deriv MT5               |
//+------------------------------------------------------------------+
#property copyright "CLAWBOT"
#property version   "1.00"

#include "ClawUtils.mqh"

//+------------------------------------------------------------------+
//| Backtesting Audit Module                                          |
//|                                                                    |
//| Features:                                                          |
//|   - Tracks every trade during backtest                            |
//|   - Calculates comprehensive performance metrics                  |
//|   - Win rate, profit factor, max drawdown, Sharpe ratio           |
//|   - Generates detailed CSV report                                  |
//|   - 55% threshold evaluation                                       |
//|   - Weakness identification and reporting                          |
//|   - Strategy-level breakdown                                       |
//|   - Session/time analysis                                          |
//+------------------------------------------------------------------+
class CClawAudit
{
private:
   // Trade log arrays
   double m_tradeProfits[];
   double m_tradeRR[];             // Risk:Reward achieved
   int    m_tradeTypes[];          // 0=buy, 1=sell
   int    m_tradeStrategies[];     // Which strategy triggered
   int    m_tradeHours[];          // Entry hour
   int    m_tradeDays[];           // Day of week
   double m_balanceHistory[];

   // Running statistics
   TradeStats m_stats;
   double m_currentBalance;
   double m_initialBalance;
   int    m_currentConsecWins;
   int    m_currentConsecLosses;

   // Strategy-level stats (5 strategies: Trend, Momentum, Session, MeanRevert, SMC)
   int    m_strategyWins[5];       // Wins per strategy
   int    m_strategyTotal[5];      // Total per strategy
   double m_strategyProfit[5];     // Profit per strategy

   // Session stats
   int    m_sessionWins[5];        // Wins per session
   int    m_sessionTotal[5];       // Total per session

   // Day of week stats
   int    m_dayWins[7];
   int    m_dayTotal[7];

   // Hour stats
   int    m_hourWins[24];
   int    m_hourTotal[24];

   string m_reportPath;
   bool   m_initialized;

   // Weakness detection
   string m_weaknesses[];
   int    m_weaknessCount;

   void   IdentifyWeaknesses();
   void   AddWeakness(string weakness);

public:
   CClawAudit();
   ~CClawAudit();

   bool Init(double initialBalance, string reportPath = "CLAWBOT_Reports");
   void Deinit();

   // Trade recording
   void RecordTrade(double profit, double riskReward, int type,
                    int strategy, int hour, int dayOfWeek);
   void UpdateBalance(double balance);

   // Analysis
   void   CalculateStatistics();
   bool   MeetsThreshold(double winRateThreshold = 55.0);
   double GetWinRate()      { return m_stats.winRate; }
   double GetProfitFactor() { return m_stats.profitFactor; }
   double GetMaxDrawdown()  { return m_stats.maxDrawdownPercent; }
   double GetExpectancy()   { return m_stats.expectancy; }
   int    GetTotalTrades()  { return m_stats.totalTrades; }
   TradeStats GetStats()    { return m_stats; }

   // Reporting
   bool GenerateFullReport();
   bool GenerateWeaknessReport();
   bool GeneratePassReport();
   string GetReportSummary();
};

//+------------------------------------------------------------------+
CClawAudit::CClawAudit()
{
   m_initialized = false;
   m_currentBalance = 0;
   m_initialBalance = 0;
   m_currentConsecWins = 0;
   m_currentConsecLosses = 0;
   m_weaknessCount = 0;
   m_stats.Reset();

   ArrayInitialize(m_strategyWins, 0);
   ArrayInitialize(m_strategyTotal, 0);
   ArrayInitialize(m_strategyProfit, 0);
   ArrayInitialize(m_sessionWins, 0);
   ArrayInitialize(m_sessionTotal, 0);
   ArrayInitialize(m_dayWins, 0);
   ArrayInitialize(m_dayTotal, 0);
   ArrayInitialize(m_hourWins, 0);
   ArrayInitialize(m_hourTotal, 0);
}

//+------------------------------------------------------------------+
CClawAudit::~CClawAudit()
{
   Deinit();
}

//+------------------------------------------------------------------+
bool CClawAudit::Init(double initialBalance, string reportPath)
{
   m_initialBalance = initialBalance;
   m_currentBalance = initialBalance;
   m_stats.peakBalance = initialBalance;
   m_reportPath = reportPath;

   // Create report directory in COMMON files area so reports are
   // accessible from both live mode AND Strategy Tester (tester sandbox
   // normally writes to Agent-xxx/MQL5/Files/ which Python can't find)
   FolderCreate(m_reportPath, FILE_COMMON);

   m_initialized = true;
   LogMessage("AUDIT", "Audit module initialized. Initial balance: " + DoubleToString(initialBalance, 2));
   return true;
}

//+------------------------------------------------------------------+
void CClawAudit::Deinit()
{
   m_initialized = false;
}

//+------------------------------------------------------------------+
//| Record a completed trade                                           |
//+------------------------------------------------------------------+
void CClawAudit::RecordTrade(double profit, double riskReward, int type,
                              int strategy, int hour, int dayOfWeek)
{
   int idx = ArraySize(m_tradeProfits);
   ArrayResize(m_tradeProfits, idx + 1);
   ArrayResize(m_tradeRR, idx + 1);
   ArrayResize(m_tradeTypes, idx + 1);
   ArrayResize(m_tradeStrategies, idx + 1);
   ArrayResize(m_tradeHours, idx + 1);
   ArrayResize(m_tradeDays, idx + 1);

   m_tradeProfits[idx]    = profit;
   m_tradeRR[idx]         = riskReward;
   m_tradeTypes[idx]      = type;
   m_tradeStrategies[idx] = strategy;
   m_tradeHours[idx]      = hour;
   m_tradeDays[idx]       = dayOfWeek;

   // Update balance
   m_currentBalance += profit;
   int balIdx = ArraySize(m_balanceHistory);
   ArrayResize(m_balanceHistory, balIdx + 1);
   m_balanceHistory[balIdx] = m_currentBalance;

   // Update peak
   if(m_currentBalance > m_stats.peakBalance)
      m_stats.peakBalance = m_currentBalance;

   // Update strategy stats
   if(strategy >= 0 && strategy < 5)
   {
      m_strategyTotal[strategy]++;
      m_strategyProfit[strategy] += profit;
      if(profit > 0) m_strategyWins[strategy]++;
   }

   // Update session/time stats
   ENUM_SESSION session = SESSION_OFF;
   if(hour >= 0 && hour < 7) session = SESSION_ASIAN;
   else if(hour >= 12 && hour < 16) session = SESSION_OVERLAP;
   else if(hour >= 7 && hour < 16) session = SESSION_LONDON;
   else if(hour >= 16 && hour < 21) session = SESSION_NEWYORK;

   m_sessionTotal[(int)session]++;
   if(profit > 0) m_sessionWins[(int)session]++;

   if(dayOfWeek >= 0 && dayOfWeek < 7)
   {
      m_dayTotal[dayOfWeek]++;
      if(profit > 0) m_dayWins[dayOfWeek]++;
   }

   if(hour >= 0 && hour < 24)
   {
      m_hourTotal[hour]++;
      if(profit > 0) m_hourWins[hour]++;
   }

   // Consecutive wins/losses
   if(profit > 0)
   {
      m_currentConsecWins++;
      m_currentConsecLosses = 0;
      if(m_currentConsecWins > m_stats.maxConsecWins)
         m_stats.maxConsecWins = m_currentConsecWins;
   }
   else
   {
      m_currentConsecLosses++;
      m_currentConsecWins = 0;
      if(m_currentConsecLosses > m_stats.maxConsecLosses)
         m_stats.maxConsecLosses = m_currentConsecLosses;
   }
}

//+------------------------------------------------------------------+
void CClawAudit::UpdateBalance(double balance)
{
   m_currentBalance = balance;
   if(balance > m_stats.peakBalance)
      m_stats.peakBalance = balance;
}

//+------------------------------------------------------------------+
//| Calculate all performance statistics                                |
//+------------------------------------------------------------------+
void CClawAudit::CalculateStatistics()
{
   int total = ArraySize(m_tradeProfits);
   m_stats.totalTrades = total;

   if(total == 0) return;

   m_stats.winTrades = 0;
   m_stats.lossTrades = 0;
   m_stats.grossProfit = 0;
   m_stats.grossLoss = 0;
   m_stats.totalProfit = 0;

   double returns[];
   ArrayResize(returns, total);

   for(int i = 0; i < total; i++)
   {
      m_stats.totalProfit += m_tradeProfits[i];

      if(m_tradeProfits[i] > 0)
      {
         m_stats.winTrades++;
         m_stats.grossProfit += m_tradeProfits[i];
      }
      else
      {
         m_stats.lossTrades++;
         m_stats.grossLoss += MathAbs(m_tradeProfits[i]);
      }

      // Calculate return for Sharpe
      returns[i] = (i == 0) ? m_tradeProfits[i] / m_initialBalance :
                   m_tradeProfits[i] / m_balanceHistory[i > 0 ? i - 1 : 0];
   }

   // Win rate
   m_stats.winRate = (total > 0) ? ((double)m_stats.winTrades / total) * 100.0 : 0;

   // Profit factor
   m_stats.profitFactor = (m_stats.grossLoss > 0) ? m_stats.grossProfit / m_stats.grossLoss : 999.0;

   // Average win/loss
   m_stats.avgWin  = (m_stats.winTrades > 0)  ? m_stats.grossProfit / m_stats.winTrades : 0;
   m_stats.avgLoss = (m_stats.lossTrades > 0) ? m_stats.grossLoss / m_stats.lossTrades : 0;

   // Expectancy
   double winProb = m_stats.winRate / 100.0;
   double lossProb = 1.0 - winProb;
   m_stats.expectancy = (winProb * m_stats.avgWin) - (lossProb * m_stats.avgLoss);

   // Max drawdown from balance curve
   double peak = m_initialBalance;
   m_stats.maxDrawdown = 0;
   m_stats.maxDrawdownPercent = 0;

   for(int i = 0; i < ArraySize(m_balanceHistory); i++)
   {
      if(m_balanceHistory[i] > peak) peak = m_balanceHistory[i];
      double dd = peak - m_balanceHistory[i];
      double ddPercent = (peak > 0) ? (dd / peak) * 100.0 : 0;
      if(dd > m_stats.maxDrawdown) m_stats.maxDrawdown = dd;
      if(ddPercent > m_stats.maxDrawdownPercent) m_stats.maxDrawdownPercent = ddPercent;
   }

   // Sharpe Ratio (annualized, assuming ~250 trading days)
   double meanReturn = 0;
   for(int i = 0; i < total; i++) meanReturn += returns[i];
   meanReturn /= total;

   double variance = 0;
   for(int i = 0; i < total; i++)
      variance += MathPow(returns[i] - meanReturn, 2);
   variance /= (total > 1) ? (total - 1) : 1;

   double stdDev = MathSqrt(variance);
   m_stats.sharpeRatio = (stdDev > 0) ? (meanReturn / stdDev) * MathSqrt(250) : 0;
}

//+------------------------------------------------------------------+
//| Check if performance meets the 55% threshold                       |
//+------------------------------------------------------------------+
bool CClawAudit::MeetsThreshold(double winRateThreshold)
{
   CalculateStatistics();

   // Primary criteria: win rate
   bool winRatePassed = (m_stats.winRate >= winRateThreshold);

   // Secondary criteria for overall viability
   bool profitFactorPassed = (m_stats.profitFactor >= 1.5);
   bool drawdownPassed = (m_stats.maxDrawdownPercent <= 15.0);
   bool expectancyPassed = (m_stats.expectancy > 0);
   bool sufficientTrades = (m_stats.totalTrades >= 50);

   // Need win rate + at least 2 secondary criteria
   int secondaryPassed = 0;
   if(profitFactorPassed) secondaryPassed++;
   if(drawdownPassed) secondaryPassed++;
   if(expectancyPassed) secondaryPassed++;
   if(sufficientTrades) secondaryPassed++;

   bool passed = winRatePassed && (secondaryPassed >= 2);

   LogMessage("AUDIT", "=== THRESHOLD CHECK ===");
   LogMessage("AUDIT", "Win Rate: " + DoubleToString(m_stats.winRate, 1) + "% (need >=" +
              DoubleToString(winRateThreshold, 1) + "%) -> " + (winRatePassed ? "PASS" : "FAIL"));
   LogMessage("AUDIT", "Profit Factor: " + DoubleToString(m_stats.profitFactor, 2) +
              " (need >=1.5) -> " + (profitFactorPassed ? "PASS" : "FAIL"));
   LogMessage("AUDIT", "Max DD: " + DoubleToString(m_stats.maxDrawdownPercent, 1) +
              "% (need <=15%) -> " + (drawdownPassed ? "PASS" : "FAIL"));
   LogMessage("AUDIT", "Expectancy: $" + DoubleToString(m_stats.expectancy, 2) +
              " (need >0) -> " + (expectancyPassed ? "PASS" : "FAIL"));
   LogMessage("AUDIT", "Total Trades: " + IntegerToString(m_stats.totalTrades) +
              " (need >=50) -> " + (sufficientTrades ? "PASS" : "FAIL"));
   LogMessage("AUDIT", "=== OVERALL: " + (passed ? "PASSED" : "FAILED") + " ===");

   return passed;
}

//+------------------------------------------------------------------+
//| Add a weakness to the list                                         |
//+------------------------------------------------------------------+
void CClawAudit::AddWeakness(string weakness)
{
   ArrayResize(m_weaknesses, m_weaknessCount + 1);
   m_weaknesses[m_weaknessCount] = weakness;
   m_weaknessCount++;
}

//+------------------------------------------------------------------+
//| Identify weaknesses in the strategy                                |
//+------------------------------------------------------------------+
void CClawAudit::IdentifyWeaknesses()
{
   m_weaknessCount = 0;
   ArrayFree(m_weaknesses);

   // Win rate weakness
   if(m_stats.winRate < 55.0)
      AddWeakness("WIN_RATE: Win rate is " + DoubleToString(m_stats.winRate, 1) +
                  "% which is below the 55% target. With 1:2 R:R, 55%+ WR is profitable.");

   if(m_stats.winRate < 50.0)
      AddWeakness("CRITICAL_WIN_RATE: Win rate below 50% indicates fundamental strategy issues.");

   // Profit factor
   if(m_stats.profitFactor < 1.5)
      AddWeakness("PROFIT_FACTOR: PF=" + DoubleToString(m_stats.profitFactor, 2) +
                  " is below 1.5. Average wins are too small relative to losses.");

   if(m_stats.profitFactor < 1.0)
      AddWeakness("CRITICAL_PF: Profit factor below 1.0 means the strategy is net losing money.");

   // Drawdown
   if(m_stats.maxDrawdownPercent > 15.0)
      AddWeakness("DRAWDOWN: Max drawdown " + DoubleToString(m_stats.maxDrawdownPercent, 1) +
                  "% exceeds 15% limit. Reduce position sizing or improve stop losses.");

   if(m_stats.maxDrawdownPercent > 25.0)
      AddWeakness("CRITICAL_DD: Drawdown above 25% is dangerous for live trading.");

   // Expectancy
   if(m_stats.expectancy <= 0)
      AddWeakness("EXPECTANCY: Negative expectancy ($" + DoubleToString(m_stats.expectancy, 2) +
                  "). The strategy has no statistical edge.");

   // Consecutive losses
   if(m_stats.maxConsecLosses > 6)
      AddWeakness("CONSEC_LOSSES: Maximum " + DoubleToString(m_stats.maxConsecLosses, 0) +
                  " consecutive losses. This can cause psychological stress in live trading.");

   // Sample size
   if(m_stats.totalTrades < 50)
      AddWeakness("SAMPLE_SIZE: Only " + IntegerToString(m_stats.totalTrades) +
                  " trades. Need minimum 50 for statistical significance.");

   if(m_stats.totalTrades < 100)
      AddWeakness("LOW_SAMPLE: " + IntegerToString(m_stats.totalTrades) +
                  " trades is borderline. 200+ trades recommended for confidence.");

   // Sharpe Ratio
   if(m_stats.sharpeRatio < 1.0)
      AddWeakness("SHARPE: Sharpe ratio " + DoubleToString(m_stats.sharpeRatio, 2) +
                  " is below 1.0. Risk-adjusted returns are poor.");

   // Strategy-level analysis
   string stratNames[] = {"Trend", "Momentum", "Session", "MeanRevert", "SMC"};
   for(int i = 0; i < 5; i++)
   {
      if(m_strategyTotal[i] > 10)
      {
         double stratWR = (m_strategyTotal[i] > 0) ?
                          ((double)m_strategyWins[i] / m_strategyTotal[i]) * 100.0 : 0;
         if(stratWR < 40.0)
            AddWeakness("STRATEGY_" + stratNames[i] + ": Win rate only " +
                        DoubleToString(stratWR, 1) + "%. Consider disabling or recalibrating.");

         if(m_strategyProfit[i] < 0)
            AddWeakness("STRATEGY_" + stratNames[i] + "_LOSS: Net loss of $" +
                        DoubleToString(MathAbs(m_strategyProfit[i]), 2) + ". Dragging overall performance.");
      }
   }

   // Session analysis
   string sessNames[] = {"Asian", "London", "NewYork", "Overlap", "Off-hours"};
   for(int i = 0; i < 5; i++)
   {
      if(m_sessionTotal[i] > 5)
      {
         double sessWR = ((double)m_sessionWins[i] / m_sessionTotal[i]) * 100.0;
         if(sessWR < 35.0)
            AddWeakness("SESSION_" + sessNames[i] + ": Win rate " + DoubleToString(sessWR, 1) +
                        "% during " + sessNames[i] + " session. Consider avoiding this session.");
      }
   }

   // Day of week analysis
   for(int i = 0; i < 7; i++)
   {
      if(m_dayTotal[i] > 5)
      {
         double dayWR = ((double)m_dayWins[i] / m_dayTotal[i]) * 100.0;
         if(dayWR < 35.0)
            AddWeakness("DAY_" + GetDayName(i) + ": Win rate " + DoubleToString(dayWR, 1) +
                        "% on " + GetDayName(i) + ". Consider not trading this day.");
      }
   }

   // Average win vs loss ratio
   if(m_stats.avgLoss > 0)
   {
      double rrRatio = m_stats.avgWin / m_stats.avgLoss;
      if(rrRatio < 1.0)
         AddWeakness("R_R_RATIO: Average R:R is " + DoubleToString(rrRatio, 2) +
                     ":1 which is below 1:1. Winning trades too small relative to losses.");
   }
}

//+------------------------------------------------------------------+
//| Generate complete report to CSV                                    |
//+------------------------------------------------------------------+
bool CClawAudit::GenerateFullReport()
{
   CalculateStatistics();

   string filename = m_reportPath + "\\CLAWBOT_Backtest_Report.csv";

   // Write summary section
   string header = "CLAWBOT BACKTEST REPORT";
   header += "\nGenerated: " + TimeToString(TimeCurrent());
   header += "\n\n=== OVERALL PERFORMANCE ===";
   header += "\nTotal Trades," + IntegerToString(m_stats.totalTrades);
   header += "\nWin Trades," + IntegerToString(m_stats.winTrades);
   header += "\nLoss Trades," + IntegerToString(m_stats.lossTrades);
   header += "\nWin Rate (%)," + DoubleToString(m_stats.winRate, 2);
   header += "\nGross Profit ($)," + DoubleToString(m_stats.grossProfit, 2);
   header += "\nGross Loss ($)," + DoubleToString(m_stats.grossLoss, 2);
   header += "\nNet Profit ($)," + DoubleToString(m_stats.totalProfit, 2);
   header += "\nProfit Factor," + DoubleToString(m_stats.profitFactor, 2);
   header += "\nExpectancy ($)," + DoubleToString(m_stats.expectancy, 2);
   header += "\nMax Drawdown ($)," + DoubleToString(m_stats.maxDrawdown, 2);
   header += "\nMax Drawdown (%)," + DoubleToString(m_stats.maxDrawdownPercent, 2);
   header += "\nSharpe Ratio," + DoubleToString(m_stats.sharpeRatio, 2);
   header += "\nAverage Win ($)," + DoubleToString(m_stats.avgWin, 2);
   header += "\nAverage Loss ($)," + DoubleToString(m_stats.avgLoss, 2);
   header += "\nMax Consecutive Wins," + DoubleToString(m_stats.maxConsecWins, 0);
   header += "\nMax Consecutive Losses," + DoubleToString(m_stats.maxConsecLosses, 0);
   header += "\nInitial Balance ($)," + DoubleToString(m_initialBalance, 2);
   header += "\nFinal Balance ($)," + DoubleToString(m_currentBalance, 2);
   header += "\nReturn (%)," + DoubleToString(((m_currentBalance - m_initialBalance) / m_initialBalance) * 100, 2);

   // Strategy breakdown
   header += "\n\n=== STRATEGY BREAKDOWN ===";
   header += "\nStrategy,Trades,Wins,Win Rate (%),Net Profit ($)";
   string stratNames[] = {"Trend_EMA", "Momentum_RSI", "Session_Breakout", "MeanRevert_BB", "SMC_Institutional"};
   for(int i = 0; i < 5; i++)
   {
      double wr = (m_strategyTotal[i] > 0) ? ((double)m_strategyWins[i] / m_strategyTotal[i]) * 100 : 0;
      header += "\n" + stratNames[i] + "," + IntegerToString(m_strategyTotal[i]) + "," +
                IntegerToString(m_strategyWins[i]) + "," + DoubleToString(wr, 1) + "," +
                DoubleToString(m_strategyProfit[i], 2);
   }

   // Session breakdown
   header += "\n\n=== SESSION BREAKDOWN ===";
   header += "\nSession,Trades,Wins,Win Rate (%)";
   string sessNames[] = {"Asian", "London", "NewYork", "Overlap", "Off-hours"};
   for(int i = 0; i < 5; i++)
   {
      double wr = (m_sessionTotal[i] > 0) ? ((double)m_sessionWins[i] / m_sessionTotal[i]) * 100 : 0;
      header += "\n" + sessNames[i] + "," + IntegerToString(m_sessionTotal[i]) + "," +
                IntegerToString(m_sessionWins[i]) + "," + DoubleToString(wr, 1);
   }

   // Day breakdown
   header += "\n\n=== DAY OF WEEK BREAKDOWN ===";
   header += "\nDay,Trades,Wins,Win Rate (%)";
   for(int i = 0; i < 7; i++)
   {
      if(m_dayTotal[i] > 0)
      {
         double wr = ((double)m_dayWins[i] / m_dayTotal[i]) * 100;
         header += "\n" + GetDayName(i) + "," + IntegerToString(m_dayTotal[i]) + "," +
                   IntegerToString(m_dayWins[i]) + "," + DoubleToString(wr, 1);
      }
   }

   // Hour breakdown
   header += "\n\n=== HOURLY BREAKDOWN ===";
   header += "\nHour (UTC),Trades,Wins,Win Rate (%)";
   for(int i = 0; i < 24; i++)
   {
      if(m_hourTotal[i] > 0)
      {
         double wr = ((double)m_hourWins[i] / m_hourTotal[i]) * 100;
         header += "\n" + IntegerToString(i) + ":00," + IntegerToString(m_hourTotal[i]) + "," +
                   IntegerToString(m_hourWins[i]) + "," + DoubleToString(wr, 1);
      }
   }

   // Balance curve
   header += "\n\n=== BALANCE CURVE ===";
   header += "\nTrade #,Balance ($)";
   for(int i = 0; i < ArraySize(m_balanceHistory); i++)
   {
      header += "\n" + IntegerToString(i + 1) + "," + DoubleToString(m_balanceHistory[i], 2);
   }

   // Write to FILE_COMMON so reports land in the shared MQL5/Files/ area
   // (not the tester agent sandbox which Python cannot easily find)
   int handle = FileOpen(filename, FILE_WRITE | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      // Fallback: try without FILE_COMMON (some broker builds restrict it)
      handle = FileOpen(filename, FILE_WRITE | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         LogMessage("AUDIT", "Failed to create report file. Error: " + IntegerToString(GetLastError()));
         return false;
      }
      LogMessage("AUDIT", "Warning: Report written to tester sandbox (FILE_COMMON failed).");
   }

   FileWriteString(handle, header);
   FileClose(handle);

   LogMessage("AUDIT", "Full report generated: " + filename);
   return true;
}

//+------------------------------------------------------------------+
//| Generate weakness report for failed backtest                       |
//+------------------------------------------------------------------+
bool CClawAudit::GenerateWeaknessReport()
{
   CalculateStatistics();
   IdentifyWeaknesses();

   string filename = m_reportPath + "\\CLAWBOT_Weakness_Report.csv";

   string report = "CLAWBOT WEAKNESS REPORT - BACKTEST DID NOT MEET THRESHOLD";
   report += "\nGenerated: " + TimeToString(TimeCurrent());
   report += "\n\nThis report identifies areas where the CLAWBOT strategy underperformed.";
   report += "\nUpload this report to Claude for analysis and optimization recommendations.";

   report += "\n\n=== PERFORMANCE SUMMARY ===";
   report += "\nWin Rate: " + DoubleToString(m_stats.winRate, 2) + "% (TARGET: >=55%)";
   report += "\nProfit Factor: " + DoubleToString(m_stats.profitFactor, 2) + " (TARGET: >=1.5)";
   report += "\nMax Drawdown: " + DoubleToString(m_stats.maxDrawdownPercent, 2) + "% (TARGET: <=15%)";
   report += "\nExpectancy: $" + DoubleToString(m_stats.expectancy, 2) + " (TARGET: >$0)";
   report += "\nSharpe Ratio: " + DoubleToString(m_stats.sharpeRatio, 2) + " (TARGET: >=1.0)";
   report += "\nTotal Trades: " + IntegerToString(m_stats.totalTrades) + " (TARGET: >=50)";

   report += "\n\n=== IDENTIFIED WEAKNESSES (" + IntegerToString(m_weaknessCount) + ") ===";
   report += "\nPriority,Category,Description";

   for(int i = 0; i < m_weaknessCount; i++)
   {
      string priority = "MEDIUM";
      if(StringFind(m_weaknesses[i], "CRITICAL") >= 0) priority = "CRITICAL";
      else if(StringFind(m_weaknesses[i], "STRATEGY") >= 0) priority = "HIGH";
      else if(StringFind(m_weaknesses[i], "SESSION") >= 0 ||
              StringFind(m_weaknesses[i], "DAY") >= 0) priority = "LOW";

      // Extract category
      int colonPos = StringFind(m_weaknesses[i], ":");
      string category = StringSubstr(m_weaknesses[i], 0, colonPos);
      string description = StringSubstr(m_weaknesses[i], colonPos + 2);

      report += "\n" + priority + "," + category + "," + description;
   }

   // Strategy breakdown for context
   report += "\n\n=== STRATEGY PERFORMANCE FOR CONTEXT ===";
   string stratNames[] = {"Trend_EMA", "Momentum_RSI", "Session_Breakout", "MeanRevert_BB", "SMC_Institutional"};
   for(int i = 0; i < 5; i++)
   {
      double wr = (m_strategyTotal[i] > 0) ? ((double)m_strategyWins[i] / m_strategyTotal[i]) * 100 : 0;
      report += "\n" + stratNames[i] + ": " + IntegerToString(m_strategyTotal[i]) +
                " trades, " + DoubleToString(wr, 1) + "% WR, $" +
                DoubleToString(m_strategyProfit[i], 2) + " net";
   }

   report += "\n\n=== RECOMMENDED ACTIONS ===";
   report += "\n1. Upload this file to Claude for detailed optimization suggestions";
   report += "\n2. Focus on CRITICAL and HIGH priority weaknesses first";
   report += "\n3. Consider adjusting parameters for underperforming strategies";
   report += "\n4. Consider disabling strategies with consistently negative performance";
   report += "\n5. Re-run backtest after adjustments to verify improvement";

   // Write to FILE_COMMON area for Python access
   int handle = FileOpen(filename, FILE_WRITE | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(filename, FILE_WRITE | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         LogMessage("AUDIT", "Failed to create weakness report. Error: " + IntegerToString(GetLastError()));
         return false;
      }
   }

   FileWriteString(handle, report);
   FileClose(handle);

   LogMessage("AUDIT", "Weakness report generated: " + filename);
   return true;
}

//+------------------------------------------------------------------+
//| Generate pass report when backtest succeeds                        |
//+------------------------------------------------------------------+
bool CClawAudit::GeneratePassReport()
{
   CalculateStatistics();

   string filename = m_reportPath + "\\CLAWBOT_Pass_Report.csv";

   string report = "CLAWBOT BACKTEST PASSED - READY FOR LIVE DEPLOYMENT";
   report += "\nGenerated: " + TimeToString(TimeCurrent());

   report += "\n\n=== PERFORMANCE SUMMARY ===";
   report += "\nWin Rate: " + DoubleToString(m_stats.winRate, 2) + "% -- PASSED";
   report += "\nProfit Factor: " + DoubleToString(m_stats.profitFactor, 2);
   report += "\nMax Drawdown: " + DoubleToString(m_stats.maxDrawdownPercent, 2) + "%";
   report += "\nNet Profit: $" + DoubleToString(m_stats.totalProfit, 2);
   report += "\nReturn: " + DoubleToString(((m_currentBalance - m_initialBalance) / m_initialBalance) * 100, 2) + "%";
   report += "\nSharpe Ratio: " + DoubleToString(m_stats.sharpeRatio, 2);
   report += "\nTotal Trades: " + IntegerToString(m_stats.totalTrades);

   report += "\n\n=== DEPLOYMENT INSTRUCTIONS ===";
   report += "\n1. The bot has passed backtesting with >=55% win rate";
   report += "\n2. Please provide your Deriv MT5 login credentials when prompted";
   report += "\n3. Credentials will be stored securely in an encrypted .env file";
   report += "\n4. Start with MINIMUM lot sizes for the first 2 weeks of live trading";
   report += "\n5. Monitor performance daily and compare with backtest metrics";

   report += "\n\nPROCEED TO LIVE TRADING SETUP";

   int handle = FileOpen(filename, FILE_WRITE | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(filename, FILE_WRITE | FILE_ANSI);
      if(handle == INVALID_HANDLE) return false;
   }

   FileWriteString(handle, report);
   FileClose(handle);

   LogMessage("AUDIT", "Pass report generated: " + filename);
   return true;
}

//+------------------------------------------------------------------+
//| Get a text summary of results                                      |
//+------------------------------------------------------------------+
string CClawAudit::GetReportSummary()
{
   CalculateStatistics();

   string summary = "=== CLAWBOT BACKTEST SUMMARY ===\n";
   summary += "Trades: " + IntegerToString(m_stats.totalTrades) + " | ";
   summary += "Win Rate: " + DoubleToString(m_stats.winRate, 1) + "% | ";
   summary += "PF: " + DoubleToString(m_stats.profitFactor, 2) + " | ";
   summary += "Net: $" + DoubleToString(m_stats.totalProfit, 2) + " | ";
   summary += "MaxDD: " + DoubleToString(m_stats.maxDrawdownPercent, 1) + "% | ";
   summary += "Sharpe: " + DoubleToString(m_stats.sharpeRatio, 2);

   return summary;
}
