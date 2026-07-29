"""Analyst rules: what happened, and which round decided it.

Every rule here returns claims whose numbers come from the cited feature rows.
Nothing is computed from raw tables, and nothing is asserted that a citation
can't back.
"""

from __future__ import annotations

from src.agents import constants as C
from src.agents.base import Conclusion, pct
from src.agents.view import FeatureView
from src.features.constants import BUY_NAMES, other_team


def _pivotal(view: FeatureView):
    """(round_num, winner, loser, [pivotal citations]) or None."""
    pivotal = view.match_value("pivotal_round")
    if pivotal is None:
        return None
    round_num = int(pivotal.value)

    winner = None
    won_refs = []
    for team in view.teams:
        ref = view.at(f"round_won:{team}", round_num)
        if ref is None:
            return None
        won_refs.append(ref)
        if ref.value == 1.0:
            winner = team
    if winner is None:
        return None
    return round_num, winner, other_team(winner), [pivotal, *won_refs]


class PivotalRoundRule:
    id = "analyst.pivotal_round"
    agent = "Analyst"
    severity = "info"
    inputs = ["pivotal_round", "pivotal_round_swing", "round_won:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        found = _pivotal(view)
        swing = view.match_value("pivotal_round_swing")
        if found is None or swing is None:
            return []
        round_num, winner, loser, refs = found
        return [Conclusion(
            rule_id=self.id, agent=self.agent, severity=self.severity,
            text=(f"R{round_num} was the match's pivotal round -- the largest single swing "
                  f"({swing.value:.3f}) in the win-probability proxy. {winner} took it, "
                  f"{loser} lost it."),
            citations=[*refs, swing],
        )]


class PivotalBrokenBuyRule:
    id = "analyst.pivotal_broken_buy"
    agent = "Analyst"
    severity = "critical"
    inputs = ["pivotal_round", "round_won:{team}", "broken_buy:{team}", "buy_type:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        found = _pivotal(view)
        if found is None:
            return []
        round_num, _winner, loser, refs = found

        broken = view.at(f"broken_buy:{loser}", round_num)
        buy = view.at(f"buy_type:{loser}", round_num)
        if broken is None or buy is None or broken.value != 1.0:
            return []
        return [Conclusion(
            rule_id=self.id, agent=self.agent, severity=self.severity,
            text=(f"{loser} lost R{round_num} on a broken buy: the loss bonus had escalated "
                  f"far enough to fund a real buy, but the team still walked in on a "
                  f"{BUY_NAMES[buy.value]}."),
            citations=[*refs, broken, buy],
        )]


class PivotalStreakRule:
    id = "analyst.pivotal_streak"
    agent = "Analyst"
    severity = "warning"
    inputs = ["pivotal_round", "round_won:{team}", "loss_streak:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        found = _pivotal(view)
        if found is None:
            return []
        round_num, _winner, loser, refs = found

        streak = view.at(f"loss_streak:{loser}", round_num)
        if streak is None or streak.value < C.PIVOTAL_STREAK:
            return []
        return [Conclusion(
            rule_id=self.id, agent=self.agent, severity=self.severity,
            text=(f"{loser} went into the pivotal R{round_num} already {int(streak.value)} "
                  f"rounds into a losing streak -- the round that decided the match was "
                  f"played on bonus money."),
            citations=[*refs, streak],
        )]


class PivotalTradeCollapseRule:
    id = "analyst.pivotal_trade_collapse"
    agent = "Analyst"
    severity = "warning"
    inputs = ["pivotal_round", "round_won:{team}", "trade_efficiency_sim_approx:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        found = _pivotal(view)
        if found is None:
            return []
        round_num, _winner, loser, refs = found

        trade = view.at(f"trade_efficiency_sim_approx:{loser}", round_num)
        if trade is None or trade.value >= C.TRADE_SHARE_PIVOTAL:
            return []
        return [Conclusion(
            rule_id=self.id, agent=self.agent, severity=self.severity,
            text=(f"{loser} was simply out-fought in the pivotal R{round_num}, taking only "
                  f"{pct(trade.value)}% of the round's kills (sim-approx: kill share stands "
                  f"in for real trade windows)."),
            citations=[*refs, trade],
        )]


class PostPlantConversionRule:
    id = "analyst.post_plant_conversion"
    agent = "Analyst"
    severity = "warning"
    inputs = ["win_after_plant:{team}", "plant_rate:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            win_after = view.match_value(f"win_after_plant:{team}")
            plant_rate = view.match_value(f"plant_rate:{team}")
            if win_after is None or plant_rate is None:
                continue
            if plant_rate.value == 0 or win_after.value >= C.WIN_AFTER_PLANT_RATE:
                continue
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} got the spike down but could not hold it -- only "
                      f"{pct(win_after.value)}% of its plants converted into round wins."),
                citations=[win_after, plant_rate],
            ))
        return out


class PlantRateRule:
    id = "analyst.plant_rate"
    agent = "Analyst"
    severity = "info"
    inputs = ["plant_rate:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            plant_rate = view.match_value(f"plant_rate:{team}")
            if plant_rate is None or plant_rate.value >= C.PLANT_RATE:
                continue
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} reached a plant in only {pct(plant_rate.value)}% of its "
                      f"attack rounds -- most of those rounds were lost before the spike "
                      f"ever went down."),
                citations=[plant_rate],
            ))
        return out


class TradeEfficiencyRule:
    id = "analyst.trade_efficiency"
    agent = "Analyst"
    severity = "warning"
    inputs = ["trade_efficiency_sim_approx:{team}"]

    def evaluate(self, view: FeatureView) -> list[Conclusion]:
        out = []
        for team in view.teams:
            series = view.series(f"trade_efficiency_sim_approx:{team}")
            if not series:
                continue
            mean = sum(r.value for r in series) / len(series)
            if mean >= C.TRADE_SHARE_MATCH:
                continue
            out.append(Conclusion(
                rule_id=self.id, agent=self.agent, severity=self.severity,
                text=(f"{team} was out-traded across the match, taking {pct(mean)}% of round "
                      f"kills over {len(series)} rounds against a {pct(0.5)}% even split "
                      f"(sim-approx: kill share stands in for real trade windows)."),
                citations=list(series),
            ))
        return out


RULES = [
    PivotalRoundRule(),
    PivotalBrokenBuyRule(),
    PivotalStreakRule(),
    PivotalTradeCollapseRule(),
    PostPlantConversionRule(),
    PlantRateRule(),
    TradeEfficiencyRule(),
]
