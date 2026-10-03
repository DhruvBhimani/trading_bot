package com.solanaquant.paper;

import com.solanaquant.config.SolanaQuantProperties;
import com.solanaquant.domain.PaperAccountEntity;
import com.solanaquant.domain.PaperPositionEntity;
import com.solanaquant.domain.SignalEventEntity;
import com.solanaquant.domain.SwapEntity;
import com.solanaquant.domain.TokenEntity;
import com.solanaquant.domain.TokenSnapshotEntity;
import com.solanaquant.persistence.PaperAccountRepository;
import com.solanaquant.persistence.PaperPositionRepository;
import com.solanaquant.persistence.SignalEventRepository;
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
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class PaperTradingService {

    private final SolanaQuantProperties properties;
    private final PaperAccountRepository accountRepository;
    private final PaperPositionRepository positionRepository;
    private final TokenRepository tokenRepository;
    private final TokenSnapshotRepository snapshotRepository;
    private final SwapRepository swapRepository;
    private final WalletRepository walletRepository;
    private final SignalEventRepository signalEventRepository;
    private final SignalEngine signalEngine;
    private final RiskEngine riskEngine;

    public PaperTradingService(
            SolanaQuantProperties properties,
            PaperAccountRepository accountRepository,
            PaperPositionRepository positionRepository,
            TokenRepository tokenRepository,
            TokenSnapshotRepository snapshotRepository,
            SwapRepository swapRepository,
            WalletRepository walletRepository,
            SignalEventRepository signalEventRepository,
            SignalEngine signalEngine,
            RiskEngine riskEngine
    ) {
        this.properties = properties;
        this.accountRepository = accountRepository;
        this.positionRepository = positionRepository;
        this.tokenRepository = tokenRepository;
        this.snapshotRepository = snapshotRepository;
        this.swapRepository = swapRepository;
        this.walletRepository = walletRepository;
        this.signalEventRepository = signalEventRepository;
        this.signalEngine = signalEngine;
        this.riskEngine = riskEngine;
    }

    @Transactional
    public PaperAccountEntity ensureAccount() {
        return accountRepository.findByName(properties.paper().accountName())
                .orElseGet(() -> {
                    PaperAccountEntity account = new PaperAccountEntity();
                    account.setName(properties.paper().accountName());
                    account.setCashUsd(properties.paper().startingBalanceUsd());
                    return accountRepository.save(account);
                });
    }

    @Transactional
    public Map<String, Object> runTick() {
        PaperAccountEntity account = ensureAccount();
        List<String> actions = new ArrayList<>();

        for (PaperPositionEntity open : positionRepository.findByAccountIdAndStatus(account.getId(), "open")) {
            TokenSnapshotEntity latest = latestSnapshot(open.getTokenId());
            if (latest == null) {
                continue;
            }
            Optional<String> exit = riskEngine.evaluateExit(
                    new RiskEngine.OpenPosition(open.getEntryTime(), open.getEntryPrice()),
                    latest
            );
            if (exit.isPresent()) {
                closePosition(account, open, latest, exit.get());
                actions.add("SELL " + open.getMintAddress() + " (" + exit.get() + ")");
            }
        }

        for (TokenEntity token : tokenRepository.findAll()) {
            if (hasOpenPosition(account.getId(), token.getId())) {
                continue;
            }
            List<TokenSnapshotEntity> history = snapshotRepository.findByTokenIdOrderByObservedAtAsc(token.getId());
            if (history.isEmpty()) {
                continue;
            }
            TokenSnapshotEntity latest = history.get(history.size() - 1);
            List<SwapEntity> recent = swapRepository.findTokenSwapsBetween(
                    token.getId(),
                    latest.getObservedAt().minus(properties.strategy().smartWalletLookbackMinutes(), ChronoUnit.MINUTES),
                    latest.getObservedAt()
            );
            Map<String, List<SwapEntity>> walletHistory = buildWalletHistory(recent, latest);
            SignalDecision decision = signalEngine.evaluate(latest, history, recent, walletHistory);
            persistSignal(token, latest, decision);

            if ("BUY".equals(decision.action()) && canAfford(account)) {
                openPosition(account, token, latest, decision);
                actions.add("BUY " + token.getMintAddress());
            }
        }

        Map<String, Object> result = new HashMap<>();
        result.put("cash_usd", account.getCashUsd());
        result.put("open_positions", positionRepository.findByAccountIdAndStatus(account.getId(), "open").size());
        result.put("actions", actions);
        return result;
    }

    @Transactional(readOnly = true)
    public Map<String, Object> status() {
        PaperAccountEntity account = ensureAccount();
        List<PaperPositionEntity> open = positionRepository.findByAccountIdAndStatus(account.getId(), "open");
        BigDecimal deployed = open.stream()
                .map(PaperPositionEntity::getQuantityUsd)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return Map.of(
                "account", account.getName(),
                "cash_usd", account.getCashUsd(),
                "deployed_usd", deployed,
                "equity_estimate_usd", account.getCashUsd().add(deployed),
                "open_positions", open.size(),
                "live_execution_enabled", properties.execution().liveEnabled()
        );
    }

    private boolean canAfford(PaperAccountEntity account) {
        return account.getCashUsd().compareTo(properties.paper().positionSizeUsd()) >= 0;
    }

    private boolean hasOpenPosition(Long accountId, Long tokenId) {
        return positionRepository.findByAccountIdAndStatus(accountId, "open").stream()
                .anyMatch(p -> p.getTokenId().equals(tokenId));
    }

    private TokenSnapshotEntity latestSnapshot(Long tokenId) {
        List<TokenSnapshotEntity> history = snapshotRepository.findByTokenIdOrderByObservedAtAsc(tokenId);
        if (history.isEmpty()) {
            return null;
        }
        return history.get(history.size() - 1);
    }

    private void openPosition(
            PaperAccountEntity account,
            TokenEntity token,
            TokenSnapshotEntity snapshot,
            SignalDecision decision
    ) {
        BigDecimal size = properties.paper().positionSizeUsd();
        account.setCashUsd(account.getCashUsd().subtract(size));

        PaperPositionEntity position = new PaperPositionEntity();
        position.setAccountId(account.getId());
        position.setTokenId(token.getId());
        position.setMintAddress(token.getMintAddress());
        position.setEntryTime(snapshot.getObservedAt());
        position.setEntryPrice(snapshot.getPriceUsd());
        position.setQuantityUsd(size);
        position.setStatus("open");
        position.setSignalDetails(Map.of(
                "score", decision.score(),
                "reasons", decision.reasons(),
                "breakdown", decision.breakdown()
        ));
        positionRepository.save(position);
        accountRepository.save(account);
    }

    private void closePosition(
            PaperAccountEntity account,
            PaperPositionEntity position,
            TokenSnapshotEntity snapshot,
            String reason
    ) {
        BigDecimal pnlPct = snapshot.getPriceUsd()
                .subtract(position.getEntryPrice())
                .divide(position.getEntryPrice(), 8, RoundingMode.HALF_UP)
                .multiply(BigDecimal.valueOf(100));
        BigDecimal proceeds = position.getQuantityUsd().multiply(
                BigDecimal.ONE.add(pnlPct.divide(BigDecimal.valueOf(100), 8, RoundingMode.HALF_UP))
        );

        position.setStatus("closed");
        position.setExitTime(snapshot.getObservedAt());
        position.setExitPrice(snapshot.getPriceUsd());
        position.setPnlPct(pnlPct);
        position.setExitReason(reason);
        positionRepository.save(position);

        account.setCashUsd(account.getCashUsd().add(proceeds));
        accountRepository.save(account);
    }

    private void persistSignal(TokenEntity token, TokenSnapshotEntity snapshot, SignalDecision decision) {
        SignalEventEntity event = new SignalEventEntity();
        event.setTokenId(token.getId());
        event.setMintAddress(token.getMintAddress());
        event.setObservedAt(Instant.now());
        event.setAction(decision.action());
        event.setScore(decision.score());
        event.setBreakdown(decision.breakdown());
        event.setReasons(decision.reasons());
        signalEventRepository.save(event);
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
}
