package com.solanaquant.strategy;

import com.solanaquant.config.SolanaQuantProperties;
import com.solanaquant.domain.SwapEntity;
import com.solanaquant.domain.TokenSnapshotEntity;
import com.solanaquant.features.TokenSafetyEvaluator;
import com.solanaquant.features.WalletPerformanceService;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Service
public class SignalEngine {

    private final SolanaQuantProperties properties;
    private final TokenSafetyEvaluator safetyEvaluator;
    private final WalletPerformanceService walletPerformanceService;

    public SignalEngine(
            SolanaQuantProperties properties,
            TokenSafetyEvaluator safetyEvaluator,
            WalletPerformanceService walletPerformanceService
    ) {
        this.properties = properties;
        this.safetyEvaluator = safetyEvaluator;
        this.walletPerformanceService = walletPerformanceService;
    }

    public SignalDecision evaluate(
            TokenSnapshotEntity snapshot,
            List<TokenSnapshotEntity> historyIncludingCurrent,
            List<SwapEntity> recentSwaps,
            Map<String, List<SwapEntity>> walletHistory
    ) {
        SolanaQuantProperties.Strategy strategy = properties.strategy();
        Map<String, Object> breakdown = new HashMap<>();
        List<String> reasons = new ArrayList<>();

        Map<String, Object> features = snapshot.getFeatures() == null ? Map.of() : snapshot.getFeatures();
        TokenSafetyEvaluator.SafetyResult safety = safetyEvaluator.evaluate(features);
        breakdown.put("safety", safety.score());

        if (safety.score() < strategy.minSafetyScore()) {
            reasons.add("token safety below threshold");
            safety.flags().forEach(flag -> reasons.add("safety:" + flag));
            return SignalDecision.block(safety.score(), reasons, breakdown);
        }

        BigDecimal liquidity = snapshot.getLiquidityUsd() == null ? BigDecimal.ZERO : snapshot.getLiquidityUsd();
        breakdown.put("liquidity_usd", liquidity);
        if (liquidity.compareTo(strategy.minLiquidityUsd()) < 0) {
            reasons.add("liquidity below minimum");
            return SignalDecision.skip((short) 30, reasons, breakdown);
        }

        PriceActionAnalyzer.PullbackState pullback = PriceActionAnalyzer.analyze(historyIncludingCurrent);
        breakdown.put("drawdown_pct", pullback.drawdownPct());
        breakdown.put("recovery_pct", pullback.recoveryPct());

        int smartWalletBuys = countSmartWalletBuys(recentSwaps, walletHistory, strategy, snapshot.getObservedAt());
        breakdown.put("smart_wallet_buys", smartWalletBuys);

        int momentumScore = scoreMomentum(pullback, strategy);
        int walletScoreComponent = Math.min(20, smartWalletBuys * 7);
        int liquidityScore = liquidity.compareTo(BigDecimal.valueOf(100_000)) >= 0 ? 20 : 15;
        short totalScore = (short) Math.min(
                100,
                safety.score() / 5 + momentumScore + walletScoreComponent + liquidityScore
        );
        breakdown.put("momentum_score", momentumScore);
        breakdown.put("wallet_score_component", walletScoreComponent);

        if (smartWalletBuys < strategy.minSmartWalletBuys()) {
            reasons.add("not enough high-quality wallet accumulation");
            return SignalDecision.watch(totalScore, reasons, breakdown);
        }

        if (pullback.drawdownPct() < strategy.minDrawdownPct()) {
            reasons.add("drawdown too shallow");
            return SignalDecision.watch(totalScore, reasons, breakdown);
        }
        if (pullback.recoveryPct() < strategy.minRecoveryPct()) {
            reasons.add("recovery not confirmed");
            return SignalDecision.watch(totalScore, reasons, breakdown);
        }

        reasons.add("pullback recovery confirmed");
        reasons.add("smart wallets accumulating");
        reasons.add("liquidity acceptable");
        return SignalDecision.buy(totalScore, reasons, breakdown);
    }

    private int countSmartWalletBuys(
            List<SwapEntity> recentSwaps,
            Map<String, List<SwapEntity>> walletHistory,
            SolanaQuantProperties.Strategy strategy,
            Instant asOf
    ) {
        Set<String> wallets = new HashSet<>();
        Instant since = asOf.minus(strategy.smartWalletLookbackMinutes(), ChronoUnit.MINUTES);

        for (SwapEntity swap : recentSwaps) {
            if (!"buy".equalsIgnoreCase(swap.getSide())) {
                continue;
            }
            if (swap.getBlockTime().isBefore(since)) {
                continue;
            }
            List<SwapEntity> history = walletHistory.getOrDefault(swap.getWalletAddress(), List.of());
            int score = walletPerformanceService.scoreFromSwaps(history).score();
            if (score >= strategy.smartWalletMinScore()) {
                wallets.add(swap.getWalletAddress());
            }
        }
        return wallets.size();
    }

    private static int scoreMomentum(PriceActionAnalyzer.PullbackState pullback, SolanaQuantProperties.Strategy strategy) {
        int score = 0;
        if (pullback.drawdownPct() >= strategy.minDrawdownPct()) {
            score += 10;
        }
        if (pullback.recoveryPct() >= strategy.minRecoveryPct()) {
            score += 10;
        }
        if (pullback.recoveryPct() >= strategy.minRecoveryPct() * 2) {
            score += 5;
        }
        return score;
    }
}
