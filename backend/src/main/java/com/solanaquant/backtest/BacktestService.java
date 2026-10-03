package com.solanaquant.backtest;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.solanaquant.config.SolanaQuantProperties;
import com.solanaquant.domain.BacktestRunEntity;
import com.solanaquant.domain.BacktestTradeEntity;
import com.solanaquant.domain.SwapEntity;
import com.solanaquant.domain.TokenEntity;
import com.solanaquant.domain.TokenSnapshotEntity;
import com.solanaquant.persistence.BacktestRunRepository;
import com.solanaquant.persistence.BacktestTradeRepository;
import com.solanaquant.persistence.SwapRepository;
import com.solanaquant.persistence.TokenRepository;
import com.solanaquant.persistence.TokenSnapshotRepository;
import com.solanaquant.persistence.WalletRepository;
import com.solanaquant.risk.RiskEngine;
import com.solanaquant.strategy.SignalDecision;
import com.solanaquant.strategy.SignalEngine;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Service
public class BacktestService {

    private final SolanaQuantProperties properties;
    private final TokenRepository tokenRepository;
    private final TokenSnapshotRepository snapshotRepository;
    private final SwapRepository swapRepository;
    private final WalletRepository walletRepository;
    private final BacktestRunRepository backtestRunRepository;
    private final BacktestTradeRepository backtestTradeRepository;
    private final SignalEngine signalEngine;
    private final RiskEngine riskEngine;
    private final ObjectMapper objectMapper;

    public BacktestService(
            SolanaQuantProperties properties,
            TokenRepository tokenRepository,
            TokenSnapshotRepository snapshotRepository,
            SwapRepository swapRepository,
            WalletRepository walletRepository,
            BacktestRunRepository backtestRunRepository,
            BacktestTradeRepository backtestTradeRepository,
            SignalEngine signalEngine,
            RiskEngine riskEngine,
            ObjectMapper objectMapper
    ) {
        this.properties = properties;
        this.tokenRepository = tokenRepository;
        this.snapshotRepository = snapshotRepository;
        this.swapRepository = swapRepository;
        this.walletRepository = walletRepository;
        this.backtestRunRepository = backtestRunRepository;
        this.backtestTradeRepository = backtestTradeRepository;
        this.signalEngine = signalEngine;
        this.riskEngine = riskEngine;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Map<String, Object> runDefaultBacktest() {
        BacktestRunEntity run = new BacktestRunEntity();
        run.setName("pullback-recovery-default");
        run.setStrategyConfig(objectMapper.convertValue(properties.strategy(), Map.class));
        backtestRunRepository.save(run);

        List<BacktestTradeEntity> trades = new ArrayList<>();
        for (TokenEntity token : tokenRepository.findAll()) {
            trades.addAll(simulateToken(token, run.getId()));
        }
        backtestTradeRepository.saveAll(trades);

        Map<String, Object> summary = summarize(trades);
        run.setSummary(summary);
        run.setFinishedAt(java.time.Instant.now());
        backtestRunRepository.save(run);

        Map<String, Object> response = new HashMap<>(summary);
        response.put("run_id", run.getId().toString());
        response.put("trade_count", trades.size());
        return response;
    }

    private List<BacktestTradeEntity> simulateToken(TokenEntity token, UUID runId) {
        List<TokenSnapshotEntity> snapshots = snapshotRepository.findByTokenIdOrderByObservedAtAsc(token.getId());
        List<BacktestTradeEntity> trades = new ArrayList<>();
        List<TokenSnapshotEntity> history = new ArrayList<>();

        OpenSimPosition open = null;
        for (TokenSnapshotEntity snapshot : snapshots) {
            history.add(snapshot);
            if (open != null) {
                Optional<String> exitReason = riskEngine.evaluateExit(
                        new RiskEngine.OpenPosition(open.entryTime(), open.entryPrice()),
                        snapshot
                );
                if (exitReason.isPresent()) {
                    trades.add(closeTrade(runId, token, open, snapshot, exitReason.get()));
                    open = null;
                }
                continue;
            }

            List<SwapEntity> recent = swapRepository.findTokenSwapsBetween(
                    token.getId(),
                    snapshot.getObservedAt().minus(properties.strategy().smartWalletLookbackMinutes(), ChronoUnit.MINUTES),
                    snapshot.getObservedAt()
            );
            Map<String, List<SwapEntity>> walletHistory = buildWalletHistory(recent, snapshot);

            SignalDecision decision = signalEngine.evaluate(snapshot, List.copyOf(history), recent, walletHistory);
            if ("BUY".equals(decision.action())) {
                open = new OpenSimPosition(snapshot.getObservedAt(), snapshot.getPriceUsd(), decision);
            }
        }

        if (open != null && !snapshots.isEmpty()) {
            TokenSnapshotEntity last = snapshots.get(snapshots.size() - 1);
            trades.add(closeTrade(runId, token, open, last, "END_OF_DATA"));
        }
        return trades;
    }

    private Map<String, List<SwapEntity>> buildWalletHistory(List<SwapEntity> recent, TokenSnapshotEntity snapshot) {
        Map<String, List<SwapEntity>> walletHistory = new HashMap<>();
        for (SwapEntity swap : recent) {
            walletHistory.computeIfAbsent(swap.getWalletAddress(), key ->
                    swapRepository.findWalletSwapsBefore(key, snapshot.getObservedAt())
            );
        }
        walletRepository.findAll().forEach(wallet ->
                walletHistory.computeIfAbsent(wallet.getAddress(), key ->
                        swapRepository.findWalletSwapsBefore(key, snapshot.getObservedAt())
                )
        );
        return walletHistory;
    }

    private BacktestTradeEntity closeTrade(
            UUID runId,
            TokenEntity token,
            OpenSimPosition open,
            TokenSnapshotEntity exitSnapshot,
            String reason
    ) {
        BigDecimal pnlPct = exitSnapshot.getPriceUsd()
                .subtract(open.entryPrice())
                .divide(open.entryPrice(), 8, RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100));

        BacktestTradeEntity trade = new BacktestTradeEntity();
        trade.setRunId(runId);
        trade.setTokenId(token.getId());
        trade.setMintAddress(token.getMintAddress());
        trade.setEntryTime(open.entryTime());
        trade.setExitTime(exitSnapshot.getObservedAt());
        trade.setEntryPrice(open.entryPrice());
        trade.setExitPrice(exitSnapshot.getPriceUsd());
        trade.setPnlPct(pnlPct);
        trade.setExitReason(reason);
        trade.setSignalDetails(open.signalDetails());
        return trade;
    }

    private Map<String, Object> summarize(List<BacktestTradeEntity> trades) {
        if (trades.isEmpty()) {
            return Map.of("trades", 0, "win_rate", 0, "avg_pnl_pct", 0, "total_pnl_pct", 0);
        }
        int wins = 0;
        BigDecimal total = BigDecimal.ZERO;
        for (BacktestTradeEntity trade : trades) {
            if (trade.getPnlPct().compareTo(BigDecimal.ZERO) > 0) {
                wins++;
            }
            total = total.add(trade.getPnlPct());
        }
        double winRate = (double) wins / trades.size();
        BigDecimal avg = total.divide(BigDecimal.valueOf(trades.size()), 6, RoundingMode.HALF_UP);
        return Map.of(
                "trades", trades.size(),
                "win_rate", winRate,
                "avg_pnl_pct", avg,
                "total_pnl_pct", total
        );
    }

    private record OpenSimPosition(
            java.time.Instant entryTime,
            BigDecimal entryPrice,
            SignalDecision decision
    ) {
        Map<String, Object> signalDetails() {
            Map<String, Object> map = new HashMap<>();
            map.put("score", decision.score());
            map.put("reasons", decision.reasons());
            map.put("breakdown", decision.breakdown());
            return map;
        }
    }
}
