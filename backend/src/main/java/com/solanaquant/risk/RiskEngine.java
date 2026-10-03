package com.solanaquant.risk;

import com.solanaquant.config.SolanaQuantProperties;
import com.solanaquant.domain.TokenSnapshotEntity;
import com.solanaquant.features.TokenSafetyEvaluator;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;

@Component
public class RiskEngine {

    private final SolanaQuantProperties properties;
    private final TokenSafetyEvaluator safetyEvaluator;

    public RiskEngine(SolanaQuantProperties properties, TokenSafetyEvaluator safetyEvaluator) {
        this.properties = properties;
        this.safetyEvaluator = safetyEvaluator;
    }

    public record OpenPosition(
            Instant entryTime,
            BigDecimal entryPrice
    ) {
    }

    public Optional<String> evaluateExit(OpenPosition position, TokenSnapshotEntity snapshot) {
        SolanaQuantProperties.Strategy strategy = properties.strategy();
        BigDecimal price = snapshot.getPriceUsd();
        if (price == null || position.entryPrice() == null || position.entryPrice().compareTo(BigDecimal.ZERO) == 0) {
            return Optional.empty();
        }

        BigDecimal movePct = price.subtract(position.entryPrice())
                .divide(position.entryPrice(), 8, RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100));

        Map<String, Object> features = snapshot.getFeatures() == null ? Map.of() : snapshot.getFeatures();
        TokenSafetyEvaluator.SafetyResult safety = safetyEvaluator.evaluate(features);
        if (safety.score() < Math.max(20, strategy.minSafetyScore() - 30)) {
            return Optional.of("EMERGENCY_SAFETY_COLLAPSE");
        }
        if (snapshot.getLiquidityUsd() != null
                && snapshot.getLiquidityUsd().compareTo(strategy.minLiquidityUsd().multiply(BigDecimal.valueOf(0.4))) < 0) {
            return Optional.of("EMERGENCY_LIQUIDITY_COLLAPSE");
        }

        long heldMinutes = Duration.between(position.entryTime(), snapshot.getObservedAt()).toMinutes();
        if (heldMinutes >= strategy.maxHoldMinutes()) {
            return Optional.of("MAX_HOLD");
        }
        if (movePct.doubleValue() <= -strategy.stopLossPct()) {
            return Optional.of("STOP_LOSS");
        }
        if (movePct.doubleValue() >= strategy.takeProfitPct()) {
            return Optional.of("TAKE_PROFIT");
        }

        return Optional.empty();
    }
}
