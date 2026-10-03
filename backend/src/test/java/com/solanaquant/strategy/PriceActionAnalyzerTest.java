package com.solanaquant.strategy;

import com.solanaquant.domain.TokenSnapshotEntity;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class PriceActionAnalyzerTest {

    @Test
    void detectsDrawdownAndRecovery() {
        List<TokenSnapshotEntity> history = List.of(
                snap("2026-01-01T00:00:00Z", 1.5),
                snap("2026-01-01T00:15:00Z", 1.0),
                snap("2026-01-01T00:30:00Z", 1.08)
        );

        PriceActionAnalyzer.PullbackState state = PriceActionAnalyzer.analyze(history);
        assertTrue(state.drawdownPct() >= 28);
        assertTrue(state.recoveryPct() >= 5);
    }

    private static TokenSnapshotEntity snap(String time, double price) {
        TokenSnapshotEntity entity = new TokenSnapshotEntity();
        entity.setObservedAt(Instant.parse(time));
        entity.setPriceUsd(BigDecimal.valueOf(price));
        return entity;
    }
}
