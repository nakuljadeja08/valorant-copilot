"""Economist rules: buy discipline, bonus-round handling, and bank misuse."""

from __future__ import annotations

from src.agents import constants as C
from src.agents.base import Conclusion, pct
from src.agents.view import FeatureView
from src.features.constants import BUY_CODES


class ForceBuyFrequencyRule:
    id = "economist.force_buy_frequency"
    agent = "Economist"
    severity = "warning"
    inputs = ["buy_type:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            series = view.series(f"buy_type:{team}")
            if not series:
                continue
            forced = [r for r in series if r.value == BUY_CODES["force"]]
            rate = len(forced) / len(series)
            if rate <= C.FORCE_BUY_RATE:
                continue
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} force-bought in {len(forced)} of {len(series)} rounds "
                      f"({pct(rate)}%), past the {pct(C.FORCE_BUY_RATE)}% mark where forcing "
                      f"stops being a read and starts being a habit."),
                citations=list(series),
            ))
        return out


class EcoConversionRule:
    id = "economist.eco_conversion"
    agent = "Economist"
    severity = "info"
    inputs = ["buy_type:{team}", "round_won:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            buys = [r for r in view.series(f"buy_type:{team}") if r.value == BUY_CODES["eco"]]
            if not buys:
                continue
            won = [
                view.at(f"round_won:{team}", r.round_num) for r in buys
            ]
            if any(w is None for w in won):
                continue
            wins = [w for w in won if w.value == 1.0]
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} stole {len(wins)} of its {len(buys)} eco rounds "
                      f"({pct(len(wins) / len(buys))}%)."),
                citations=[*buys, *won],
            ))
        return out


class BrokenBuyCountRule:
    id = "economist.broken_buy_count"
    agent = "Economist"
    severity = "critical"
    inputs = ["broken_buy:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            series = view.series(f"broken_buy:{team}")
            broken = [r for r in series if r.value == 1.0]
            if len(broken) < C.BROKEN_BUY_COUNT:
                continue
            rounds = ", ".join(f"R{r.round_num}" for r in broken)
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} broke its buy {len(broken)} times ({rounds}) -- rounds where "
                      f"the escalated loss bonus should have funded a real buy and the team "
                      f"went in short anyway."),
                citations=list(broken),
            ))
        return out


class ConsecutiveForceBuyRule:
    """Forcing once is a read. Forcing three rounds running is an economy in a spiral."""

    id = "economist.consecutive_force"
    agent = "Economist"
    severity = "warning"
    inputs = ["buy_type:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            forced = [r for r in view.series(f"buy_type:{team}")
                      if r.value == BUY_CODES["force"]]

            # Longest run of consecutive round numbers among the forced rounds.
            best: list = []
            run: list = []
            for ref in forced:
                if run and ref.round_num == run[-1].round_num + 1:
                    run.append(ref)
                else:
                    run = [ref]
                if len(run) > len(best):
                    best = list(run)

            if len(best) < C.CONSECUTIVE_FORCE_RUN:
                continue
            span = ", ".join(f"R{r.round_num}" for r in best)
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} force-bought {len(best)} rounds back to back ({span}). One "
                      f"force is a read; a run this long means the team never got off the "
                      f"back foot long enough to rebuild."),
                citations=best,
            ))
        return out


class SpendDisadvantageRule:
    id = "economist.spend_disadvantage"
    agent = "Economist"
    severity = "warning"
    inputs = ["spend_diff"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        series = view.series("spend_diff")
        teams = view.teams
        if not series or len(teams) != 2:
            return []

        # `spend_diff` is built in src/features/economy.py as
        # `sorted(teams)[0].spend - sorted(teams)[1].spend`. Mirror that convention
        # here rather than re-deriving it, so the sign can only be wrong in one place.
        first, second = teams
        total = sum(r.value for r in series)
        if abs(total) < C.SPEND_DEFICIT_MATCH:
            return []

        behind, ahead = (second, first) if total > 0 else (first, second)
        return [Conclusion(
            rule_id=self.id, agent=self.agent, severity=self.severity,
            text=(f"{behind} was out-spent by {ahead} by {round(abs(total))} credits across "
                  f"the match's {len(series)} rounds -- roughly a third of a full team buy "
                  f"in equipment {behind} never got to bring."),
            citations=list(series),
        )]


RULES = [
    ForceBuyFrequencyRule(),
    EcoConversionRule(),
    BrokenBuyCountRule(),
    ConsecutiveForceBuyRule(),
    SpendDisadvantageRule(),
]
