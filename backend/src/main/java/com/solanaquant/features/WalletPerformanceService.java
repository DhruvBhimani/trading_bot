package com.solanaquant.features;

import com.solanaquant.domain.SwapEntity;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class WalletPerformanceService {

    public record WalletScore(int score, Map<String, Object> metrics) {
    }

    public WalletScore scoreFromSwaps(List<SwapEntity> swaps) {
        if (swaps.isEmpty()) {
            return new WalletScore(0, Map.of("trades", 0));
        }

        int wins = 0;
        int losses = 0;
        int roundTrips = 0;
        BigDecimal openBuyPrice = null;

        for (SwapEntity swap : swaps) {
            if ("buy".equalsIgnoreCase(swap.getSide())) {
                openBuyPrice = swap.getPriceUsd();
            } else if ("sell".equalsIgnoreCase(swap.getSide()) && openBuyPrice != null) {
                roundTrips++;
                BigDecimal sell = swap.getPriceUsd();
                if (sell.compareTo(openBuyPrice) > 0) {
                    wins++;
                } else {
                    losses++;
                }
                openBuyPrice = null;
            }
        }

        double winRate = roundTrips == 0 ? 0 : (double) wins / roundTrips;
        int score = (int) Math.round(winRate * 70 + Math.min(roundTrips, 20) * 1.5);
        score = Math.max(0, Math.min(100, score));

        Map<String, Object> metrics = new HashMap<>();
        metrics.put("trades", swaps.size());
        metrics.put("round_trips", roundTrips);
        metrics.put("wins", wins);
        metrics.put("losses", losses);
        metrics.put("win_rate", winRate);

        return new WalletScore(score, metrics);
    }
}
