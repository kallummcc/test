# region imports
from AlgorithmImports import *
import csv
import io
from bisect import bisect_right
# endregion


class ShortInterestLongOnly(QCAlgorithm):
    """
    Short Interest Effect - Long Only version (Quantpedia).

    Universe : NYSE, AMEX and NASDAQ common stocks.
    Signal   : short-interest ratio (short interest / shares outstanding by default).
    Portfolio: hold the 1st percentile (lowest short interest), equally weighted,
               rebalanced monthly.

    Source paper: Boehmer, Huszar, Jordan - "The Good News in Short Interest" (2010).
    The paper finds the effect is strongest among relatively heavily traded stocks,
    so an optional liquidity filter keeps only the most liquid part of the universe.

    LEAN has no built-in short interest dataset, so short interest is read from a CSV
    (Object Store key or URL) with the columns:
        date,ticker,short_interest[,avg_daily_volume]
    where `date` is the FINRA settlement date (YYYY-MM-DD). See README.md for how to
    build this file.
    """

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100_000)

        # ---- parameters (override in the QC project "Parameters" panel) ----
        self._data_key = self.get_parameter("short_interest_key", "short_interest.csv")
        self._data_url = self.get_parameter("short_interest_url", "")
        # "relative": short interest / shares outstanding (as in the source paper)
        # "days_to_cover": short interest / average daily volume
        self._metric = self.get_parameter("metric", "relative")
        self._percentile = self.get_parameter("percentile", 0.01)
        self._min_holdings = self.get_parameter("min_holdings", 10)
        self._max_holdings = self.get_parameter("max_holdings", 100)
        self._min_price = self.get_parameter("min_price", 5.0)
        # keep the most traded fraction of the universe ("heavily traded" stocks);
        # set to 1.0 to disable
        self._liquidity_fraction = self.get_parameter("liquidity_fraction", 0.5)
        # FINRA publishes short interest ~8 business days after settlement; lag the
        # data to avoid look-ahead bias
        self._publication_lag = timedelta(days=self.get_parameter("publication_lag_days", 12))
        # ignore short interest records older than this
        self._max_staleness = timedelta(days=self.get_parameter("max_staleness_days", 45))

        self._short_interest = self._load_short_interest()

        self.set_benchmark("SPY")
        self.settings.minimum_order_margin_portfolio_percentage = 0
        self.universe_settings.resolution = Resolution.DAILY
        self.universe_settings.schedule.on(self.date_rules.month_start())
        self.add_universe(self._select)

        self._targets = []
        self._rebalance_pending = False

        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self._rebalance,
        )
        self.add_equity("SPY", Resolution.DAILY)

    # ------------------------------------------------------------------ data

    def _load_short_interest(self):
        content = None
        if self.object_store.contains_key(self._data_key):
            content = self.object_store.read(self._data_key)
        elif self._data_url:
            content = self.download(self._data_url)

        if not content:
            raise ValueError(
                f"No short interest data: add '{self._data_key}' to the Object Store "
                "or set the 'short_interest_url' parameter."
            )

        # ticker -> (list of availability dates, list of (short_interest, avg_daily_volume))
        records = {}
        for row in csv.DictReader(io.StringIO(content)):
            try:
                settlement = datetime.strptime(row["date"].strip()[:10], "%Y-%m-%d")
                ticker = row["ticker"].strip().upper()
                short_interest = float(row["short_interest"])
            except (KeyError, ValueError, AttributeError):
                continue
            adv = row.get("avg_daily_volume")
            try:
                adv = float(adv) if adv not in (None, "") else None
            except ValueError:
                adv = None
            records.setdefault(ticker, []).append(
                (settlement + self._publication_lag, short_interest, adv)
            )

        data = {}
        for ticker, rows in records.items():
            rows.sort(key=lambda x: x[0])
            data[ticker] = ([r[0] for r in rows], [(r[1], r[2]) for r in rows])

        self.log(f"Loaded short interest for {len(data)} tickers")
        return data

    def _latest_short_interest(self, ticker):
        series = self._short_interest.get(ticker)
        if series is None:
            return None
        dates, values = series
        i = bisect_right(dates, self.time) - 1
        if i < 0 or self.time - dates[i] > self._max_staleness:
            return None
        return values[i]

    # -------------------------------------------------------------- universe

    def _select(self, fundamental):
        candidates = [
            f for f in fundamental
            if f.has_fundamental_data
            and f.price > self._min_price
            and f.security_reference.exchange_id in ("NYS", "ASE", "NAS")
            and f.security_reference.security_type == "ST00000001"  # common stock
            and not f.security_reference.is_depositary_receipt
            and f.company_profile.shares_outstanding > 0
            and f.dollar_volume > 0
        ]

        if self._liquidity_fraction < 1:
            candidates.sort(key=lambda f: f.dollar_volume, reverse=True)
            candidates = candidates[: int(len(candidates) * self._liquidity_fraction)]

        scored = []
        for f in candidates:
            record = self._latest_short_interest(f.symbol.value)
            if record is None:
                continue
            short_interest, adv = record
            if self._metric == "days_to_cover":
                if not adv:
                    continue
                score = short_interest / adv
            else:
                score = short_interest / f.company_profile.shares_outstanding
            scored.append((score, f.symbol))

        if not scored:
            self.log(f"{self.time.date()}: no stocks with short interest data")
            self._targets = []
            self._rebalance_pending = True
            return []

        scored.sort(key=lambda x: x[0])
        count = int(len(scored) * self._percentile)
        count = max(self._min_holdings, min(self._max_holdings, count))
        selected = [symbol for _, symbol in scored[:count]]

        self.log(f"{self.time.date()}: {len(scored)} scored, holding {len(selected)} lowest short interest")
        self._targets = selected
        self._rebalance_pending = True
        return selected

    # ------------------------------------------------------------- trading

    def _rebalance(self):
        if not self._rebalance_pending:
            return
        self._rebalance_pending = False

        tradable = [
            s for s in self._targets
            if s in self.securities and self.securities[s].price > 0
        ]
        if not tradable:
            self.liquidate()
            return

        weight = 1.0 / len(tradable)
        self.set_holdings([PortfolioTarget(s, weight) for s in tradable], liquidate_existing_holdings=True)
