package com.solanaquant.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.math.BigDecimal;

@ConfigurationProperties(prefix = "solana-quant")
public record SolanaQuantProperties(
        String dataDir,
        Execution execution,
        boolean bootstrapSampleData,
        Strategy strategy,
        Paper paper
) {
    public record Execution(boolean liveEnabled) {
    }

    public record Strategy(
            BigDecimal minLiquidityUsd,
            int minSafetyScore,
            double minDrawdownPct,
            double minRecoveryPct,
            double stopLossPct,
            double takeProfitPct,
            int maxHoldMinutes,
            int minSmartWalletBuys,
            int smartWalletMinScore,
            int smartWalletLookbackMinutes
    ) {
    }

    public record Paper(
            String accountName,
            BigDecimal startingBalanceUsd,
            BigDecimal positionSizeUsd,
            int tickIntervalSeconds
    ) {
    }
}
