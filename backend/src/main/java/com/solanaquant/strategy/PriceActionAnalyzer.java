package com.solanaquant.strategy;

import com.solanaquant.domain.TokenSnapshotEntity;

import java.math.BigDecimal;
import java.util.List;

public final class PriceActionAnalyzer {

    private PriceActionAnalyzer() {
    }

    public record PullbackState(double drawdownPct, double recoveryPct, BigDecimal localHigh, BigDecimal localLow) {
    }

    public static PullbackState analyze(List<TokenSnapshotEntity> historyIncludingCurrent) {
        if (historyIncludingCurrent.isEmpty()) {
            return new PullbackState(0, 0, BigDecimal.ZERO, BigDecimal.ZERO);
        }

        BigDecimal localHigh = BigDecimal.ZERO;
        BigDecimal localLow = null;
        for (TokenSnapshotEntity snap : historyIncludingCurrent) {
            BigDecimal price = snap.getPriceUsd();
            if (price == null) {
                continue;
            }
            if (price.compareTo(localHigh) > 0) {
                localHigh = price;
            }
            if (localLow == null || price.compareTo(localLow) < 0) {
                localLow = price;
            }
        }

        TokenSnapshotEntity current = historyIncludingCurrent.get(historyIncludingCurrent.size() - 1);
        BigDecimal price = current.getPriceUsd() == null ? BigDecimal.ZERO : current.getPriceUsd();
        if (localLow == null || localHigh.compareTo(BigDecimal.ZERO) == 0) {
            return new PullbackState(0, 0, localHigh, localLow == null ? BigDecimal.ZERO : localLow);
        }

        double drawdown = localHigh.subtract(price)
                .divide(localHigh, 8, java.math.RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100))
                .doubleValue();
        double recovery = price.subtract(localLow)
                .divide(localLow, 8, java.math.RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100))
                .doubleValue();

        return new PullbackState(drawdown, recovery, localHigh, localLow);
    }
}
