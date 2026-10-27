//+------------------------------------------------------------------+
//|                                             TradeJournalSync.mq5 |
//|  Exports this terminal's account history for the local trading   |
//|  journal. It only reads and writes files: it never places,       |
//|  modifies or closes trades.                                      |
//|                                                                  |
//|  Files (in <Common>\Files\TradeJournal\):                        |
//|    account_<login>.json    account info + server UTC offset      |
//|    symbols_<login>.json    specs of every traded symbol          |
//|    deals_<login>.json      full deal history                     |
//|    positions_<login>.json  open positions, floating P&L          |
//|    excursions_<login>.csv  high/low while each position was open |
//|    stops_<login>.csv       first stop-loss seen on each position  |
//+------------------------------------------------------------------+
#property copyright   "Trading Journal"
#property version     "1.10"
#property description "Exports account history to Common\\Files\\TradeJournal for the local trading journal. Read-only: never trades."

#include <Generic\HashMap.mqh>

input string InpFolder            = "TradeJournal"; // Export folder under Common\Files
input int    InpTimerSeconds      = 5;              // Check for changes every N seconds
input int    InpExcursionDays     = 180;            // Compute MFE/MAE for positions closed in the last N days
input int    InpExcursionsPerPass = 200;            // Max MFE/MAE calculations per pass

#define EA_VERSION         "1.1"
#define POSITIONS_UNSET    "<unset>"
#define HEARTBEAT_SECONDS  60
#define HISTORY_CHECK_SECS 30
#define MAX_EXC_ATTEMPTS   3

long     g_login            = 0;
bool     g_dirty            = true;
int      g_lastDealCount    = -1;
string   g_lastPositions    = POSITIONS_UNSET; // forces the first write
datetime g_lastHistoryCheck = 0;
datetime g_lastAccountWrite = 0;

// MFE/MAE cache, persisted to excursions_<login>.csv
long               g_excIds[];
double             g_excHigh[];
double             g_excLow[];
CHashMap<long,int> g_excIndex;
CHashMap<long,int> g_excFails;

// First stop-loss seen on each position (catches stops added after entry),
// persisted to stops_<login>.csv
long               g_stopIds[];
double             g_stopSl[];
long               g_stopTime[];
CHashMap<long,int> g_stopIndex;

//+------------------------------------------------------------------+
int OnInit()
  {
   FolderCreate(InpFolder, FILE_COMMON);
   g_login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(g_login != 0)
     {
      LoadExcursions();
      LoadStops();
     }
   EventSetTimer(MathMax(1, InpTimerSeconds));
   PrintFormat("TradeJournalSync %s: exporting to %s\\Files\\%s", EA_VERSION,
               TerminalInfoString(TERMINAL_COMMONDATA_PATH), InpFolder);
   g_dirty = true;
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      g_dirty = true;
  }

//+------------------------------------------------------------------+
void OnTimer()
  {
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   if(login == 0)
      return; // not connected yet
   if(login != g_login)
     {
      g_login         = login;
      g_dirty         = true;
      g_lastDealCount = -1;
      g_lastPositions = POSITIONS_UNSET;
      LoadExcursions();
      LoadStops();
     }

   // Safety net for deals that arrived without a transaction event.
   if(!g_dirty && TimeLocal() - g_lastHistoryCheck >= HISTORY_CHECK_SECS)
     {
      g_lastHistoryCheck = TimeLocal();
      if(HistorySelect(0, TimeCurrent() + 86400) && HistoryDealsTotal() != g_lastDealCount)
         g_dirty = true;
     }

   if(g_dirty)
      ExportAll();
   ExportPositionsIfChanged();
   if(TimeLocal() - g_lastAccountWrite >= HEARTBEAT_SECONDS)
      ExportAccount();
  }

//+------------------------------------------------------------------+
//| JSON helpers                                                     |
//+------------------------------------------------------------------+
string J(const string s)
  {
   string r = s;
   StringReplace(r, "\\", "\\\\");
   StringReplace(r, "\"", "\\\"");
   StringReplace(r, "\n", "\\n");
   StringReplace(r, "\r", "\\r");
   StringReplace(r, "\t", "\\t");
   return("\"" + r + "\"");
  }

string N(const double v)
  {
   if(!MathIsValidNumber(v))
      return("null");
   string s   = DoubleToString(v, 8);
   int    len = StringLen(s);
   while(len > 0 && StringGetCharacter(s, len - 1) == '0')
      len--;
   if(len > 0 && StringGetCharacter(s, len - 1) == '.')
      len--;
   s = StringSubstr(s, 0, len);
   if(s == "" || s == "-")
      s = "0";
   return(s);
  }

string I(const long v)
  {
   return(IntegerToString(v));
  }

string Path(const string name)
  {
   return(InpFolder + "\\" + name + "_" + I(g_login));
  }

bool WriteFileAtomic(const string path, const string content)
  {
   string tmp = path + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON, 0, CP_UTF8);
   if(h == INVALID_HANDLE)
     {
      PrintFormat("TradeJournalSync: cannot write %s (error %d)", tmp, GetLastError());
      return(false);
     }
   FileWriteString(h, content);
   FileClose(h);
   if(!FileMove(tmp, FILE_COMMON, path, FILE_COMMON | FILE_REWRITE))
     {
      PrintFormat("TradeJournalSync: cannot replace %s (error %d)", path, GetLastError());
      return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Exports                                                          |
//+------------------------------------------------------------------+
void ExportAccount()
  {
   // Broker server time minus UTC, rounded to 15 minutes.
   long offset = (long)MathRound((double)(TimeTradeServer() - TimeGMT()) / 900.0) * 900;
   string margin = AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING ? "hedging" : "netting";
   string body = "{"
                 + "\"ea_version\":" + J(EA_VERSION)
                 + ",\"exported_at\":" + I((long)TimeGMT())
                 + ",\"login\":" + I(g_login)
                 + ",\"name\":" + J(AccountInfoString(ACCOUNT_NAME))
                 + ",\"server\":" + J(AccountInfoString(ACCOUNT_SERVER))
                 + ",\"company\":" + J(AccountInfoString(ACCOUNT_COMPANY))
                 + ",\"currency\":" + J(AccountInfoString(ACCOUNT_CURRENCY))
                 + ",\"leverage\":" + I(AccountInfoInteger(ACCOUNT_LEVERAGE))
                 + ",\"trade_mode\":" + J(EnumToString((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)))
                 + ",\"margin_mode\":" + J(margin)
                 + ",\"balance\":" + N(AccountInfoDouble(ACCOUNT_BALANCE))
                 + ",\"equity\":" + N(AccountInfoDouble(ACCOUNT_EQUITY))
                 + ",\"server_utc_offset\":" + I(offset)
                 + "}";
   if(WriteFileAtomic(Path("account") + ".json", body))
      g_lastAccountWrite = TimeLocal();
  }

void AddUnique(string &arr[], const string value)
  {
   int n = ArraySize(arr);
   for(int i = 0; i < n; i++)
      if(arr[i] == value)
         return;
   ArrayResize(arr, n + 1);
   arr[n] = value;
  }

void ExportSymbols(const string &symbols[])
  {
   string items = "";
   for(int i = 0; i < ArraySize(symbols); i++)
     {
      string s = symbols[i];
      if(i > 0)
         items += ",";
      items += "{"
               + "\"name\":" + J(s)
               + ",\"description\":" + J(SymbolInfoString(s, SYMBOL_DESCRIPTION))
               + ",\"path\":" + J(SymbolInfoString(s, SYMBOL_PATH))
               + ",\"digits\":" + I(SymbolInfoInteger(s, SYMBOL_DIGITS))
               + ",\"point\":" + N(SymbolInfoDouble(s, SYMBOL_POINT))
               + ",\"tick_size\":" + N(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE))
               + ",\"tick_value\":" + N(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE))
               + ",\"contract_size\":" + N(SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE))
               + ",\"base\":" + J(SymbolInfoString(s, SYMBOL_CURRENCY_BASE))
               + ",\"profit_ccy\":" + J(SymbolInfoString(s, SYMBOL_CURRENCY_PROFIT))
               + ",\"calc_mode\":" + J(EnumToString((ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(s, SYMBOL_TRADE_CALC_MODE)))
               + "}";
     }
   WriteFileAtomic(Path("symbols") + ".json",
                   "{\"login\":" + I(g_login) + ",\"exported_at\":" + I((long)TimeGMT()) + ",\"symbols\":[" + items + "]}");
  }

void ExportAll()
  {
   if(!HistorySelect(0, TimeCurrent() + 86400))
      return;
   int total = HistoryDealsTotal();

   string             symbols[];
   CHashMap<long,int> posIndex;
   long               posIds[];
   string             posSym[];
   datetime           posOpen[];
   datetime           posClose[];
   double             posIn[];
   double             posOut[];
   bool               posReversed[];

   string deals = "";
   int    n     = 0;
   for(int i = 0; i < total; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      string          sym   = HistoryDealGetString(ticket, DEAL_SYMBOL);
      long            posId = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      ENUM_DEAL_TYPE  type  = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      datetime        t     = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      double          vol   = HistoryDealGetDouble(ticket, DEAL_VOLUME);

      if(n > 0)
         deals += ",";
      n++;
      deals += "{"
               + "\"ticket\":" + I((long)ticket)
               + ",\"order\":" + I(HistoryDealGetInteger(ticket, DEAL_ORDER))
               + ",\"position_id\":" + I(posId)
               + ",\"time\":" + I((long)t)
               + ",\"time_msc\":" + I(HistoryDealGetInteger(ticket, DEAL_TIME_MSC))
               + ",\"type\":" + J(EnumToString(type))
               + ",\"entry\":" + J(EnumToString(entry))
               + ",\"symbol\":" + J(sym)
               + ",\"volume\":" + N(vol)
               + ",\"price\":" + N(HistoryDealGetDouble(ticket, DEAL_PRICE))
               + ",\"sl\":" + N(HistoryDealGetDouble(ticket, DEAL_SL))
               + ",\"tp\":" + N(HistoryDealGetDouble(ticket, DEAL_TP))
               + ",\"commission\":" + N(HistoryDealGetDouble(ticket, DEAL_COMMISSION))
               + ",\"fee\":" + N(HistoryDealGetDouble(ticket, DEAL_FEE))
               + ",\"swap\":" + N(HistoryDealGetDouble(ticket, DEAL_SWAP))
               + ",\"profit\":" + N(HistoryDealGetDouble(ticket, DEAL_PROFIT))
               + ",\"reason\":" + J(EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(ticket, DEAL_REASON)))
               + ",\"magic\":" + I(HistoryDealGetInteger(ticket, DEAL_MAGIC))
               + ",\"comment\":" + J(HistoryDealGetString(ticket, DEAL_COMMENT))
               + "}";

      if(sym == "" || (type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL))
         continue;
      AddUnique(symbols, sym);
      int idx;
      if(!posIndex.TryGetValue(posId, idx))
        {
         idx = ArraySize(posIds);
         ArrayResize(posIds, idx + 1);
         ArrayResize(posSym, idx + 1);
         ArrayResize(posOpen, idx + 1);
         ArrayResize(posClose, idx + 1);
         ArrayResize(posIn, idx + 1);
         ArrayResize(posOut, idx + 1);
         ArrayResize(posReversed, idx + 1);
         posIndex.Add(posId, idx);
         posIds[idx]      = posId;
         posSym[idx]      = sym;
         posOpen[idx]     = t;
         posClose[idx]    = 0;
         posIn[idx]       = 0;
         posOut[idx]      = 0;
         posReversed[idx] = false;
        }
      if(entry == DEAL_ENTRY_IN)
         posIn[idx] += vol;
      else
         if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
           {
            posOut[idx] += vol;
            posClose[idx] = t;
           }
         else
            if(entry == DEAL_ENTRY_INOUT)
               posReversed[idx] = true;
     }

   WriteFileAtomic(Path("deals") + ".json",
                   "{\"login\":" + I(g_login) + ",\"exported_at\":" + I((long)TimeGMT()) + ",\"deals\":[" + deals + "]}");
   ExportSymbols(symbols);
   ExportAccount();
   g_lastDealCount = total;
   g_dirty         = false;

   // MFE/MAE for closed positions not yet cached, a batch per pass.
   datetime cutoff   = TimeCurrent() - (datetime)((long)InpExcursionDays * 86400);
   int      computed = 0;
   for(int k = 0; k < ArraySize(posIds); k++)
     {
      if(posReversed[k] || posIn[k] <= 0 || posOut[k] + 1e-8 < posIn[k] || posClose[k] < cutoff)
         continue;
      if(g_excIndex.ContainsKey(posIds[k]))
         continue;
      int fails = 0;
      g_excFails.TryGetValue(posIds[k], fails);
      if(fails >= MAX_EXC_ATTEMPTS)
         continue;
      if(computed >= InpExcursionsPerPass)
        {
         g_dirty = true; // continue on the next timer tick
         break;
        }
      double hi, lo;
      if(ComputeExcursion(posSym[k], posOpen[k], posClose[k], hi, lo))
        {
         AddExcursion(posIds[k], hi, lo);
         computed++;
        }
      else
        {
         // Bars may still be downloading; retry on a later pass.
         if(!g_excFails.TrySetValue(posIds[k], fails + 1))
            g_excFails.Add(posIds[k], fails + 1);
         g_dirty = true;
        }
     }
   if(computed > 0)
      SaveExcursions();
  }

void ExportPositionsIfChanged()
  {
   string items    = "";
   int    n        = 0;
   bool   newStops = false;
   for(int i = 0; i < PositionsTotal(); i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      long   posId = PositionGetInteger(POSITION_IDENTIFIER);
      double sl    = PositionGetDouble(POSITION_SL);
      if(sl > 0 && !g_stopIndex.ContainsKey(posId))
        {
         AddStop(posId, sl, (long)TimeTradeServer());
         newStops = true;
        }
      if(n > 0)
         items += ",";
      n++;
      items += "{"
               + "\"position_id\":" + I(PositionGetInteger(POSITION_IDENTIFIER))
               + ",\"symbol\":" + J(PositionGetString(POSITION_SYMBOL))
               + ",\"type\":" + J(EnumToString((ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE)))
               + ",\"volume\":" + N(PositionGetDouble(POSITION_VOLUME))
               + ",\"price_open\":" + N(PositionGetDouble(POSITION_PRICE_OPEN))
               + ",\"price_current\":" + N(PositionGetDouble(POSITION_PRICE_CURRENT))
               + ",\"sl\":" + N(PositionGetDouble(POSITION_SL))
               + ",\"tp\":" + N(PositionGetDouble(POSITION_TP))
               + ",\"profit\":" + N(PositionGetDouble(POSITION_PROFIT))
               + ",\"swap\":" + N(PositionGetDouble(POSITION_SWAP))
               + ",\"time_msc\":" + I(PositionGetInteger(POSITION_TIME_MSC))
               + "}";
     }
   if(newStops)
      SaveStops();
   if(items == g_lastPositions)
      return;
   if(WriteFileAtomic(Path("positions") + ".json",
                      "{\"login\":" + I(g_login) + ",\"exported_at\":" + I((long)TimeGMT()) + ",\"positions\":[" + items + "]}"))
      g_lastPositions = items;
  }

//+------------------------------------------------------------------+
//| MFE/MAE                                                          |
//+------------------------------------------------------------------+
bool ComputeExcursion(const string sym, const datetime from, const datetime to, double &hi, double &lo)
  {
   MqlRates rates[];
   datetime start = (datetime)((long)from - (long)from % 60);
   int n = CopyRates(sym, PERIOD_M1, start, to, rates);
   if(n <= 0)
      return(false);
   hi = rates[0].high;
   lo = rates[0].low;
   for(int i = 1; i < n; i++)
     {
      if(rates[i].high > hi)
         hi = rates[i].high;
      if(rates[i].low < lo)
         lo = rates[i].low;
     }
   return(true);
  }

void AddExcursion(const long id, const double hi, const double lo)
  {
   int n = ArraySize(g_excIds);
   ArrayResize(g_excIds, n + 1);
   ArrayResize(g_excHigh, n + 1);
   ArrayResize(g_excLow, n + 1);
   g_excIds[n]  = id;
   g_excHigh[n] = hi;
   g_excLow[n]  = lo;
   g_excIndex.Add(id, n);
  }

void LoadExcursions()
  {
   ArrayResize(g_excIds, 0);
   ArrayResize(g_excHigh, 0);
   ArrayResize(g_excLow, 0);
   g_excIndex.Clear();
   g_excFails.Clear();
   string path = Path("excursions") + ".csv";
   if(!FileIsExist(path, FILE_COMMON))
      return;
   int h = FileOpen(path, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
      return;
   while(!FileIsEnding(h))
     {
      long   id = StringToInteger(FileReadString(h));
      double hi = StringToDouble(FileReadString(h));
      double lo = StringToDouble(FileReadString(h));
      if(id > 0 && !g_excIndex.ContainsKey(id))
         AddExcursion(id, hi, lo);
     }
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| Stop tracking                                                    |
//+------------------------------------------------------------------+
void AddStop(const long id, const double sl, const long serverTime)
  {
   int n = ArraySize(g_stopIds);
   ArrayResize(g_stopIds, n + 1);
   ArrayResize(g_stopSl, n + 1);
   ArrayResize(g_stopTime, n + 1);
   g_stopIds[n]  = id;
   g_stopSl[n]   = sl;
   g_stopTime[n] = serverTime;
   g_stopIndex.Add(id, n);
  }

void LoadStops()
  {
   ArrayResize(g_stopIds, 0);
   ArrayResize(g_stopSl, 0);
   ArrayResize(g_stopTime, 0);
   g_stopIndex.Clear();
   string path = Path("stops") + ".csv";
   if(!FileIsExist(path, FILE_COMMON))
      return;
   int h = FileOpen(path, FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
      return;
   while(!FileIsEnding(h))
     {
      long   id = StringToInteger(FileReadString(h));
      double sl = StringToDouble(FileReadString(h));
      long   t  = StringToInteger(FileReadString(h));
      if(id > 0 && !g_stopIndex.ContainsKey(id))
         AddStop(id, sl, t);
     }
   FileClose(h);
  }

void SaveStops()
  {
   string body = "position_id,first_sl,first_sl_time\r\n";
   for(int i = 0; i < ArraySize(g_stopIds); i++)
      body += I(g_stopIds[i]) + "," + N(g_stopSl[i]) + "," + I(g_stopTime[i]) + "\r\n";
   WriteFileAtomic(Path("stops") + ".csv", body);
  }

void SaveExcursions()
  {
   string body = "position_id,high,low\r\n";
   for(int i = 0; i < ArraySize(g_excIds); i++)
      body += I(g_excIds[i]) + "," + N(g_excHigh[i]) + "," + N(g_excLow[i]) + "\r\n";
   WriteFileAtomic(Path("excursions") + ".csv", body);
  }
//+------------------------------------------------------------------+
