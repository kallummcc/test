//+------------------------------------------------------------------+
//| GoldTrendFTMO.mq5                                                |
//|                                                                  |
//| Native MT5 Expert Advisor port of the tournament winner          |
//| `gold_trend` (prop_fx/strategies/gold_trend.py) for XAUUSD,      |
//| with FTMO guards and a DAILY RISK BUDGET.                        |
//|                                                                  |
//| Strategy (H1, times in UTC):                                     |
//|  * At the close of the bars ending 08:00 and 13:00 UTC, trade in |
//|    the direction of gold's last `mom` hours (momentum).          |
//|  * Stop = stopAtr x ATR(24), target = targetR x stop.            |
//|  * Exit after `maxHold` hours, at the 20:00 UTC close, or bank   |
//|    profit once a trade is +0.1 x stop up after `beAfter` hours.  |
//|  * Max 1 position, max 2 trades per (Prague) day, no weekends.   |
//|                                                                  |
//| Self-learning: every Monday it replays the last 12 weeks for 48  |
//| parameter sets (mom, stopAtr, targetR, maxHold, beAfter), picks  |
//| the best Sharpe of R (>= 15 trades), and trades it for the week. |
//| With too little history it uses the fixed PRIOR set.             |
//|                                                                  |
//| Guards (checked every tick):                                     |
//|  * daily stop (strategy, default 2.5%) and hard daily guard 4%:  |
//|    flatten + halt for the rest of the Prague day                 |
//|  * max-loss guard 9%: flatten + halt for good                    |
//|  * DAILY RISK BUDGET 4.5%: never open a trade if today's loss +  |
//|    open risk + this trade's risk could exceed it, so a second    |
//|    loser can't breach FTMO's 5% daily limit (at double risk the  |
//|    backtest breached it once without this).                      |
//|  * flat before the weekend; stop trading at the phase target.    |
//+------------------------------------------------------------------+
#property copyright "prop_fx tournament"
#property version   "1.00"
#property description "gold_trend for FTMO: momentum at 08/13 UTC, weekly walk-forward, daily risk budget"

#include <Trade/Trade.mqh>

enum ENUM_SERVER_TZ
  {
   TZ_GMT2_US_DST = 0,   // GMT+2 / GMT+3 on US DST (most prop-firm MT5 servers)
   TZ_GMT2_EU_DST = 1,   // GMT+2 / GMT+3 on EU DST
   TZ_FIXED       = 2    // fixed offset (InpFixedOffsetHours)
  };

input group "FTMO account"
input double InpInitialBalance      = 100000.0; // Initial challenge balance
input double InpPhaseTargetPct      = 10.0;     // Stop at this profit (10 = phase 1, 5 = phase 2, 0 = funded)
input double InpDailyGuardPct       = 4.0;      // Hard daily guard: flatten + halt day
input double InpMaxGuardPct         = 9.0;      // Max-loss guard: flatten + halt for good
input double InpDailyRiskBudgetPct  = 4.5;      // Daily risk budget (keep under FTMO's 5%)

input group "Risk"
input double InpRiskPct             = 1.5;      // Risk per trade, % of initial balance
input double InpRiskMult            = 1.0;      // Risk multiplier (2 = double risk)
input double InpDailyStopPct        = 2.5;      // Strategy daily stop, % of initial balance
input int    InpMaxTradesPerDay     = 2;        // Max new trades per Prague day

input group "Strategy"
input int    InpClockHour1          = 8;        // Decide at the close of the bar ending this UTC hour
input int    InpClockHour2          = 13;       // ... and this one
input int    InpFlatHourUTC         = 20;       // Flat at the close of the bar ending this UTC hour
input int    InpAtrPeriod           = 24;       // ATR period (simple average of true range)

input group "Self-learning (weekly walk-forward)"
input bool   InpLearn               = true;     // Re-tune every Monday on trailing data
input int    InpTrainWeeks          = 12;       // Training window (weeks)
input int    InpMinTrades           = 15;       // Min trades for a parameter set to qualify
input double InpSimHalfSpread       = 0.151;    // Simulated half spread + slippage ($/oz)
input double InpSimCommissionPerLot = 5.0;      // Simulated commission per lot, round turn

input group "Server time"
input ENUM_SERVER_TZ InpServerTZ    = TZ_GMT2_US_DST;
input int    InpFixedOffsetHours    = 2;        // Used when InpServerTZ = TZ_FIXED

input group "Misc"
input long   InpMagic               = 212500;   // Magic number (only these positions are managed)
input bool   InpDryRun              = false;    // Log orders instead of sending them

//--- parameter set
struct Params
  {
   int    mom;      // momentum lookback (hours)
   double stopAtr;  // stop in ATRs
   double targetR;  // target as a multiple of the stop
   int    maxHold;  // time exit (hours after the latest signal)
   int    beAfter;  // bank profit from this many hours after the signal
  };

const double BE_R = 0.1;  // bank-profit threshold, fraction of the stop

CTrade  trade;

void SaveState();   // forward declarations
void LoadState();
Params  g_cand[];
Params  g_prior;
Params  g_params;
string  g_paramSource = "prior";
double  g_trainScore  = 0.0;

//--- persisted state (terminal global variables)
int      g_dayKey        = -1;
double   g_dayStartBal   = 0.0;
int      g_tradesToday   = 0;
bool     g_haltedDay     = false;
bool     g_haltForever   = false;
datetime g_sigTime       = 0;      // server open time of the latest signal bar
int      g_sigSide       = 0;
double   g_sigFill       = 0.0;    // open of the bar after the signal
double   g_sigStop0      = 0.0;    // stop distance at the signal
datetime g_paramWeek     = 0;      // UTC Monday the current params were fitted for
datetime g_lastBar       = 0;
bool     g_targetLogged  = false;

//+------------------------------------------------------------------+
//| Time helpers                                                     |
//+------------------------------------------------------------------+
datetime Ymd(const int y, const int m, const int d, const int h)
  {
   MqlDateTime s;
   s.year = y; s.mon = m; s.day = d; s.hour = h; s.min = 0; s.sec = 0;
   return StructToTime(s);
  }

int UDow(const datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.day_of_week; } // 0 = Sunday
int UHour(const datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.hour; }
int UYear(const datetime t) { MqlDateTime s; TimeToStruct(t, s); return s.year; }

datetime NthSunday(const int y, const int m, const int n, const int h)
  {
   datetime t = Ymd(y, m, 1, h);
   while(UDow(t) != 0) t += 86400;
   return t + (n - 1) * 7 * 86400;
  }

datetime LastSunday(const int y, const int m, const int h)
  {
   int ny = y, nm = m + 1;
   if(nm > 12) { nm = 1; ny++; }
   datetime t = Ymd(ny, nm, 1, h) - 86400;
   while(UDow(t) != 0) t -= 86400;
   return t;
  }

bool UsDst(const datetime utc)   // 2nd Sunday of March 07:00 UTC -> 1st Sunday of Nov 06:00 UTC
  {
   int y = UYear(utc);
   return utc >= NthSunday(y, 3, 2, 7) && utc < NthSunday(y, 11, 1, 6);
  }

bool EuDst(const datetime utc)   // last Sunday of March 01:00 UTC -> last Sunday of Oct 01:00 UTC
  {
   int y = UYear(utc);
   return utc >= LastSunday(y, 3, 1) && utc < LastSunday(y, 10, 1);
  }

int ServerOffsetSec(const datetime serverTime)
  {
   if(InpServerTZ == TZ_FIXED) return InpFixedOffsetHours * 3600;
   datetime approxUtc = serverTime - 2 * 3600;
   bool dst = (InpServerTZ == TZ_GMT2_US_DST) ? UsDst(approxUtc) : EuDst(approxUtc);
   return (dst ? 3 : 2) * 3600;
  }

datetime ToUTC(const datetime serverTime) { return serverTime - ServerOffsetSec(serverTime); }

int PragueDayKey(const datetime utc)  // FTMO resets the daily loss at midnight CE(S)T
  {
   long p = (long)utc + (EuDst(utc) ? 2 : 1) * 3600;
   return (int)(p / 86400);
  }

datetime MondayUTC(const datetime utc)
  {
   int dow = UDow(utc);                       // 0 = Sunday
   int back = (dow + 6) % 7;                 // days since Monday
   long d = (long)utc - back * 86400;
   d -= d % 86400;
   return (datetime)d;
  }

//+------------------------------------------------------------------+
//| Indicators                                                       |
//+------------------------------------------------------------------+
void ComputeATR(const MqlRates &r[], const int n, double &atr[])
  {
   ArrayResize(atr, n);
   double sum = 0.0;
   double tr[];
   ArrayResize(tr, n);
   for(int i = 0; i < n; i++)
     {
      double hl = r[i].high - r[i].low;
      if(i == 0) tr[i] = hl;
      else
         tr[i] = MathMax(hl, MathMax(MathAbs(r[i].high - r[i - 1].close),
                                     MathAbs(r[i].low - r[i - 1].close)));
      sum += tr[i];
      if(i >= InpAtrPeriod) sum -= tr[i - InpAtrPeriod];
      // same as pandas rolling(InpAtrPeriod).mean(): first value once the window is full
      atr[i] = (i >= InpAtrPeriod - 1) ? sum / InpAtrPeriod : 0.0;
     }
  }

//+------------------------------------------------------------------+
//| Walk-forward simulator (mirrors prop_fx/engine.py for one symbol)|
//+------------------------------------------------------------------+
int Signal(const MqlRates &r[], const datetime &tu[], const int i, const int mom)
  {
   int closeHour = UHour(tu[i] + 3600);
   if(closeHour != InpClockHour1 && closeHour != InpClockHour2) return 0;
   if(i - mom < 0) return 0;
   double mv = r[i].close - r[i - mom].close;
   return mv > 0 ? 1 : (mv < 0 ? -1 : 0);
  }

void Record(double &rs[], const datetime entryTime, const datetime w0, const datetime w1,
            const int side, const double entry, const double px, const double sdist)
  {
   if(entryTime < w0 || entryTime >= w1 || sdist <= 0) return;
   double comm = InpSimCommissionPerLot / SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   int k = ArraySize(rs);
   ArrayResize(rs, k + 1);
   rs[k] = (side * (px - entry) - comm) / sdist;
  }

// Returns the Sharpe of R for trades entered in [w0, w1), or -DBL_MAX if it doesn't qualify.
double SimScore(const MqlRates &r[], const datetime &tu[], const double &atr[], const int n,
                const Params &p, const datetime w0, const datetime w1, int &ntrades)
  {
   double rs[];
   ArrayResize(rs, 0);
   double half = InpSimHalfSpread;
   bool inPos = false;
   int side = 0, opened = 0, dayKey = -1;
   double entry = 0, stop = 0, target = 0, sdist = 0;
   datetime entryTime = 0;
   int pend = 0, pendSide = 0;           // pend: 0 none, 1 open, 2 close
   double pendSd = 0, pendTd = 0;
   int sigIdx = -1, sigSide = 0;
   double sigFill = 0, sigStop0 = 0;

   int i0 = 0;
   while(i0 < n && tu[i0] < w0 - 2 * 86400) i0++;
   if(i0 < 1) i0 = 1;
   for(int i = i0; i < n && tu[i] < w1; i++)
     {
      // data gap (holiday / missing day): close at the last price before it
      if(inPos && tu[i] - tu[i - 1] > 6 * 3600)
        {
         Record(rs, entryTime, w0, w1, side, entry, r[i - 1].close - side * half, sdist);
         inPos = false; pend = 0;
        }
      int dk = PragueDayKey(tu[i]);
      if(dk != dayKey) { dayKey = dk; opened = 0; }

      // 1) fills at the open
      if(pend == 2)
        {
         if(inPos) { Record(rs, entryTime, w0, w1, side, entry, r[i].open - side * half, sdist); inPos = false; }
         pend = 0;
        }
      else if(pend == 1)
        {
         pend = 0;
         bool doOpen = true;
         if(inPos)
           {
            if(side == pendSide) doOpen = false;
            else { Record(rs, entryTime, w0, w1, side, entry, r[i].open - side * half, sdist); inPos = false; }
           }
         if(doOpen && !inPos && opened < InpMaxTradesPerDay)
           {
            side = pendSide; entry = r[i].open + side * half; sdist = pendSd;
            stop = entry - side * sdist; target = entry + side * pendTd;
            entryTime = tu[i]; inPos = true; opened++;
           }
        }

      // 2) intrabar stop / target (stop first)
      if(inPos)
        {
         double o = r[i].open - side * half, hi = r[i].high - side * half, lo = r[i].low - side * half;
         if(side > 0)
           {
            if(lo <= stop) { Record(rs, entryTime, w0, w1, side, entry, MathMin(o, stop), sdist); inPos = false; }
            else if(hi >= target) { Record(rs, entryTime, w0, w1, side, entry, MathMax(o, target), sdist); inPos = false; }
           }
         else
           {
            if(hi >= stop) { Record(rs, entryTime, w0, w1, side, entry, MathMax(o, stop), sdist); inPos = false; }
            else if(lo <= target) { Record(rs, entryTime, w0, w1, side, entry, MathMin(o, target), sdist); inPos = false; }
           }
        }

      // 3) decisions at the close -> next open
      datetime nxt = tu[i] + 3600;
      int ndow = UDow(nxt), nh = UHour(nxt);
      if((ndow == 5 && nh >= 20) || ndow == 6 || ndow == 0)
        {
         if(inPos) pend = 2;
         continue;
        }
      bool noNew = (ndow == 5 && nh >= 16) || opened >= InpMaxTradesPerDay;
      int sig = Signal(r, tu, i, p.mom);
      if(sig != 0)
        {
         sigIdx = i; sigSide = sig;
         sigFill = (i + 1 < n) ? r[i + 1].open : r[i].close;
         sigStop0 = p.stopAtr * atr[i];
        }
      if(inPos && sig == 0)
        {
         bool ex = (nh == InpFlatHourUTC);
         if(sigIdx >= 0)
           {
            int age = i - sigIdx;
            if(age >= p.maxHold) ex = true;
            if(p.beAfter > 0 && age >= p.beAfter && sigSide * (r[i].close - sigFill) >= BE_R * sigStop0)
               ex = true;
           }
         if(ex) pend = 2;
        }
      if(sig != 0 && !noNew && atr[i] > 0 && !(inPos && side == sig))
        {
         pend = 1; pendSide = sig; pendSd = p.stopAtr * atr[i]; pendTd = p.targetR * pendSd;
        }
     }

   ntrades = ArraySize(rs);
   if(ntrades < InpMinTrades) return -DBL_MAX;
   double mean = 0;
   for(int k = 0; k < ntrades; k++) mean += rs[k];
   mean /= ntrades;
   double var = 0;
   for(int k = 0; k < ntrades; k++) var += (rs[k] - mean) * (rs[k] - mean);
   double sd = MathSqrt(var / ntrades);
   return sd > 0 ? mean / sd : -DBL_MAX;
  }

void Refit(const datetime weekStartUTC)
  {
   g_paramWeek = weekStartUTC;
   g_params = g_prior;
   g_paramSource = "prior";
   g_trainScore = 0.0;
   if(!InpLearn) { g_paramSource = "fixed prior (learning off)"; return; }

   int want = (InpTrainWeeks + 1) * 7 * 24 + 100;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_H1, 1, want, r);
   if(n < 200) { PrintFormat("Refit: only %d bars, using prior", n); return; }
   datetime tu[];
   ArrayResize(tu, n);
   for(int i = 0; i < n; i++) tu[i] = ToUTC(r[i].time);
   datetime w0 = weekStartUTC - InpTrainWeeks * 7 * 86400;
   if(tu[0] > w0) { PrintFormat("Refit: history starts %s, need %s - using prior",
                                TimeToString(tu[0]), TimeToString(w0)); return; }
   double atr[];
   ComputeATR(r, n, atr);

   double best = -DBL_MAX;
   int bestK = -1, bestN = 0;
   for(int k = 0; k < ArraySize(g_cand); k++)
     {
      int nt = 0;
      double s = SimScore(r, tu, atr, n, g_cand[k], w0, weekStartUTC, nt);
      if(s > best) { best = s; bestK = k; bestN = nt; }
     }
   if(bestK >= 0)
     {
      g_params = g_cand[bestK];
      g_paramSource = "learned";
      g_trainScore = best;
     }
   PrintFormat("Refit week %s: %s mom=%d stopAtr=%.1f targetR=%.1f maxHold=%d beAfter=%d "
               "(train Sharpe %.3f, %d trades)", TimeToString(weekStartUTC, TIME_DATE),
               g_paramSource, g_params.mom, g_params.stopAtr, g_params.targetR,
               g_params.maxHold, g_params.beAfter, g_trainScore, bestN);
   SaveState();
  }

//+------------------------------------------------------------------+
//| State persistence                                                |
//+------------------------------------------------------------------+
string GV(const string key) { return StringFormat("GTF_%I64d_%s_%s", InpMagic, _Symbol, key); }
void   Put(const string key, const double v) { GlobalVariableSet(GV(key), v); }
double Get(const string key, const double dflt) { return GlobalVariableCheck(GV(key)) ? GlobalVariableGet(GV(key)) : dflt; }

void SaveState()
  {
   Put("dayKey", (double)g_dayKey);            Put("dayStartBal", g_dayStartBal);
   Put("tradesToday", (double)g_tradesToday);  Put("haltedDay", g_haltedDay ? 1.0 : 0.0);
   Put("haltForever", g_haltForever ? 1.0 : 0.0); Put("sigTime", (double)g_sigTime);
   Put("sigSide", (double)g_sigSide);          Put("sigFill", g_sigFill);
   Put("sigStop0", g_sigStop0);                Put("paramWeek", (double)g_paramWeek);
   Put("p_mom", (double)g_params.mom);         Put("p_stopAtr", g_params.stopAtr);
   Put("p_targetR", g_params.targetR);         Put("p_maxHold", (double)g_params.maxHold);
   Put("p_beAfter", (double)g_params.beAfter);
  }

void LoadState()
  {
   g_dayKey      = (int)Get("dayKey", -1);
   g_dayStartBal = Get("dayStartBal", 0.0);
   g_tradesToday = (int)Get("tradesToday", 0);
   g_haltedDay   = Get("haltedDay", 0.0) != 0.0;
   g_haltForever = Get("haltForever", 0.0) != 0.0;
   g_sigTime     = (datetime)(long)Get("sigTime", 0);
   g_sigSide     = (int)Get("sigSide", 0);
   g_sigFill     = Get("sigFill", 0.0);
   g_sigStop0    = Get("sigStop0", 0.0);
   g_paramWeek   = (datetime)(long)Get("paramWeek", 0);
   if(g_paramWeek != 0)
     {
      g_params.mom     = (int)Get("p_mom", g_prior.mom);
      g_params.stopAtr = Get("p_stopAtr", g_prior.stopAtr);
      g_params.targetR = Get("p_targetR", g_prior.targetR);
      g_params.maxHold = (int)Get("p_maxHold", g_prior.maxHold);
      g_params.beAfter = (int)Get("p_beAfter", g_prior.beAfter);
      g_paramSource = "restored";
     }
  }

//+------------------------------------------------------------------+
//| Trading helpers                                                  |
//+------------------------------------------------------------------+
double RiskMoney() { return MathMin(InpRiskPct * InpRiskMult, 5.0) / 100.0 * InpInitialBalance; }

bool MyPosition(ulong &ticket, int &side)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      ticket = t;
      side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      return true;
     }
   return false;
  }

int CountMyPositions()
  {
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic) c++;
     }
   return c;
  }

void CloseAll(const string reason)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0 || PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      PrintFormat("CLOSE #%I64u (%s) profit %.2f", t, reason, PositionGetDouble(POSITION_PROFIT));
      if(!InpDryRun && !trade.PositionClose(t))
         PrintFormat("Close failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
     }
  }

double LotsFor(const double stopDist)
  {
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(tv <= 0 || ts <= 0 || stopDist <= 0 || step <= 0) return 0.0;
   double lossPerLot = stopDist / ts * tv;
   double lots = MathFloor(RiskMoney() / lossPerLot / step) * step;
   if(lots < vmin) return 0.0;
   int digits = (int)MathMax(0, MathCeil(-MathLog10(step)));
   return NormalizeDouble(MathMin(lots, vmax), digits);
  }

// The daily risk budget: today's loss + open risk + this trade's risk must stay under budget.
bool RiskBudgetAllows(const double newRisk)
  {
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double dayLoss = MathMax(g_dayStartBal - equity, 0.0);
   double openRisk = CountMyPositions() * RiskMoney();
   double budget  = InpDailyRiskBudgetPct / 100.0 * InpInitialBalance;
   if(dayLoss + openRisk + newRisk > budget)
     {
      PrintFormat("SKIP (risk budget): day loss %.2f + open risk %.2f + new risk %.2f > budget %.2f",
                  dayLoss, openRisk, newRisk, budget);
      return false;
     }
   return true;
  }

bool OpenTrade(const int side, const double stopDist, const double targetDist)
  {
   double lots = LotsFor(stopDist);
   if(lots <= 0) { Print("SKIP: position size rounds to zero"); return false; }
   if(!RiskBudgetAllows(RiskMoney())) return false;
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double price = side > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = NormalizeDouble(price - side * stopDist, digits);
   double tp = NormalizeDouble(price + side * targetDist, digits);
   PrintFormat("OPEN %s %.2f lots @ %.2f sl %.2f tp %.2f (risk %.2f)", side > 0 ? "BUY" : "SELL",
               lots, price, sl, tp, RiskMoney());
   if(InpDryRun) return true;
   bool ok = side > 0 ? trade.Buy(lots, _Symbol, price, sl, tp, "gold_trend")
                      : trade.Sell(lots, _Symbol, price, sl, tp, "gold_trend");
   if(!ok || (trade.ResultRetcode() != TRADE_RETCODE_DONE && trade.ResultRetcode() != TRADE_RETCODE_PLACED))
     {
      PrintFormat("Order failed: %d %s", trade.ResultRetcode(), trade.ResultRetcodeDescription());
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| FTMO guards: run on every tick. Returns true if new trades are OK|
//+------------------------------------------------------------------+
bool Guard()
  {
   datetime utc = ToUTC(TimeCurrent());
   int dk = PragueDayKey(utc);
   double bal = AccountInfoDouble(ACCOUNT_BALANCE);
   double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
   if(dk != g_dayKey)
     {
      g_dayKey = dk; g_dayStartBal = bal; g_tradesToday = 0; g_haltedDay = false;
      PrintFormat("New FTMO day: start balance %.2f equity %.2f", bal, eq);
      SaveState();
     }
   if(g_haltForever) return false;
   if(eq <= InpInitialBalance * (1.0 - InpMaxGuardPct / 100.0))
     {
      CloseAll("max-loss guard");
      g_haltForever = true; SaveState();
      PrintFormat("HALTED FOR GOOD: equity %.2f", eq);
      return false;
     }
   if(g_haltedDay) return false;
   double floorPct = MathMin(InpDailyGuardPct, InpDailyStopPct);
   if(eq <= g_dayStartBal - floorPct / 100.0 * InpInitialBalance)
     {
      CloseAll("daily stop");
      g_haltedDay = true; SaveState();
      PrintFormat("Halted for the day: equity %.2f, day start %.2f", eq, g_dayStartBal);
      return false;
     }
   int dow = UDow(utc), h = UHour(utc);
   if((dow == 5 && h >= 20) || dow == 6 || dow == 0)
     {
      CloseAll("weekend");
      return false;
     }
   if(InpPhaseTargetPct > 0 && bal >= InpInitialBalance * (1.0 + InpPhaseTargetPct / 100.0))
     {
      ulong t = 0; int s = 0;
      if(!MyPosition(t, s))
        {
         if(!g_targetLogged) { PrintFormat("PHASE TARGET REACHED: balance %.2f - no new trades", bal); g_targetLogged = true; }
         return false;
        }
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Strategy: runs once per new H1 bar, on the bar that just closed  |
//+------------------------------------------------------------------+
void OnNewBar()
  {
   bool allowed = Guard();

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int need = 24 + InpAtrPeriod + 5;
   int n = CopyRates(_Symbol, PERIOD_H1, 1, need, r);   // closed bars, oldest first
   if(n < need) { PrintFormat("Waiting for H1 history (%d/%d bars)", n, need); return; }
   datetime tu[];
   ArrayResize(tu, n);
   for(int i = 0; i < n; i++) tu[i] = ToUTC(r[i].time);
   double atr[];
   ComputeATR(r, n, atr);
   int last = n - 1;
   datetime nxt = tu[last] + 3600;       // the bar that just opened (UTC)
   int ndow = UDow(nxt), nh = UHour(nxt);

   // weekly self-learning refit
   datetime wk = MondayUTC(nxt);
   if(wk != g_paramWeek) Refit(wk);

   ulong ticket = 0; int side = 0;
   bool hasPos = MyPosition(ticket, side);

   if((ndow == 5 && nh >= 20) || ndow == 6 || ndow == 0)
     {
      if(hasPos) CloseAll("weekend");
      return;
     }

   int sig = Signal(r, tu, last, g_params.mom);
   if(sig != 0)
     {
      g_sigTime = r[last].time; g_sigSide = sig;
      g_sigFill = iOpen(_Symbol, PERIOD_H1, 0);
      g_sigStop0 = g_params.stopAtr * atr[last];
      SaveState();
     }

   // exits (only on bars without a new signal, as in the backtest)
   if(hasPos && sig == 0)
     {
      bool ex = (nh == InpFlatHourUTC);
      string why = "flat hour";
      if(g_sigTime != 0)
        {
         int age = iBarShift(_Symbol, PERIOD_H1, g_sigTime) - 1;
         if(age >= g_params.maxHold) { ex = true; why = "time exit"; }
         if(g_params.beAfter > 0 && age >= g_params.beAfter &&
            g_sigSide * (r[last].close - g_sigFill) >= BE_R * g_sigStop0)
           { ex = true; why = "bank profit"; }
        }
      if(ex) { CloseAll(why); hasPos = false; }
     }

   // entries
   if(!allowed || sig == 0 || atr[last] <= 0) return;
   if(ndow == 5 && nh >= 16) return;
   if(g_tradesToday >= InpMaxTradesPerDay) return;
   if(hasPos && side == sig) return;
   if(hasPos) CloseAll("reverse");
   double sd = g_params.stopAtr * atr[last];
   if(OpenTrade(sig, sd, g_params.targetR * sd))
     {
      g_tradesToday++;
      SaveState();
     }
  }

//+------------------------------------------------------------------+
//| MT5 event handlers                                               |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_prior.mom = 12; g_prior.stopAtr = 2.5; g_prior.targetR = 0.7; g_prior.maxHold = 8; g_prior.beAfter = 1;
   g_params = g_prior;

   // 48 candidates, same order as prop_fx.adaptive.grid (first best wins ties)
   int moms[] = {6, 12, 24};
   double stops[] = {1.5, 2.5};
   double targets[] = {0.5, 0.7};
   int holds[] = {4, 8};
   int bes[] = {1, 2};
   ArrayResize(g_cand, 0);
   for(int a = 0; a < 3; a++)
      for(int b = 0; b < 2; b++)
         for(int c = 0; c < 2; c++)
            for(int d = 0; d < 2; d++)
               for(int e = 0; e < 2; e++)
                 {
                  int k = ArraySize(g_cand);
                  ArrayResize(g_cand, k + 1);
                  g_cand[k].mom = moms[a]; g_cand[k].stopAtr = stops[b]; g_cand[k].targetR = targets[c];
                  g_cand[k].maxHold = holds[d]; g_cand[k].beAfter = bes[e];
                 }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFillingBySymbol(_Symbol);

   LoadState();

   if(!MQLInfoInteger(MQL_TESTER))
     {
      int actual = (int)MathRound((double)(TimeCurrent() - TimeGMT()) / 3600.0);
      int model = ServerOffsetSec(TimeCurrent()) / 3600;
      if(actual != model)
         PrintFormat("WARNING: server is UTC%+d but InpServerTZ models UTC%+d - fix InpServerTZ "
                     "or the 08/13 UTC decision hours will be wrong", actual, model);
     }
   if(StringFind(_Symbol, "XAU") < 0)
      PrintFormat("WARNING: built and tested for XAUUSD, attached to %s", _Symbol);
   PrintFormat("GoldTrendFTMO on %s: risk %.2f%%/trade (x%.1f), daily stop %.1f%%, risk budget %.1f%%, "
               "guards %.1f%%/%.1f%%, %s", _Symbol, InpRiskPct * InpRiskMult, InpRiskMult,
               InpDailyStopPct, InpDailyRiskBudgetPct, InpDailyGuardPct, InpMaxGuardPct,
               InpDryRun ? "DRY RUN" : "LIVE ORDERS");
   EventSetTimer(30);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   SaveState();
   Comment("");
  }

void OnTick()
  {
   datetime bar = iTime(_Symbol, PERIOD_H1, 0);
   if(bar != g_lastBar)
     {
      g_lastBar = bar;
      OnNewBar();
     }
   else
      Guard();
   Comment(StringFormat("GoldTrendFTMO  [%s]\nparams (%s): mom %d  stop %.1f ATR  target %.1fR  hold %dh  bank@%dh\n"
                        "day start %.2f  equity %.2f  trades today %d/%d\n%s",
                        InpDryRun ? "DRY RUN" : "LIVE", g_paramSource, g_params.mom, g_params.stopAtr,
                        g_params.targetR, g_params.maxHold, g_params.beAfter, g_dayStartBal,
                        AccountInfoDouble(ACCOUNT_EQUITY), g_tradesToday, InpMaxTradesPerDay,
                        g_haltForever ? "HALTED (max-loss guard)" : (g_haltedDay ? "halted for today" : "active")));
  }

void OnTimer() { Guard(); }   // keeps the guards running between ticks
//+------------------------------------------------------------------+
