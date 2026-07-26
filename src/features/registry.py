"""Features the runner executes, in order."""

from __future__ import annotations

from src.features.base import Feature
from src.features.economy import BuyClassificationFeature, EconomyCurveFeature
from src.features.loss_streak import LossStreakFeature
from src.features.pivotal_round import PivotalRoundFeature
from src.features.post_plant import PostPlantConversionFeature
from src.features.trade_efficiency import TradeEfficiencyFeature

REGISTRY: list[Feature] = [
    BuyClassificationFeature(),
    EconomyCurveFeature(),
    LossStreakFeature(),
    PostPlantConversionFeature(),
    PivotalRoundFeature(),
    TradeEfficiencyFeature(),
]
