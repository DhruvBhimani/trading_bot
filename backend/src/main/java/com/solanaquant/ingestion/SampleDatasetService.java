package com.solanaquant.ingestion;

import com.solanaquant.domain.SwapEntity;
import com.solanaquant.domain.TokenEntity;
import com.solanaquant.domain.TokenSnapshotEntity;
import com.solanaquant.domain.WalletEntity;
import com.solanaquant.persistence.SwapRepository;
import com.solanaquant.persistence.TokenRepository;
import com.solanaquant.persistence.TokenSnapshotRepository;
import com.solanaquant.persistence.WalletRepository;
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

@Service
public class SampleDatasetService {

    private final TokenRepository tokenRepository;
    private final TokenSnapshotRepository snapshotRepository;
    private final WalletRepository walletRepository;
    private final SwapRepository swapRepository;

    public SampleDatasetService(
            TokenRepository tokenRepository,
            TokenSnapshotRepository snapshotRepository,
            WalletRepository walletRepository,
            SwapRepository swapRepository
    ) {
        this.tokenRepository = tokenRepository;
        this.snapshotRepository = snapshotRepository;
        this.walletRepository = walletRepository;
        this.swapRepository = swapRepository;
    }

    @Transactional
    public Map<String, Object> loadSampleDataset() {
        if (tokenRepository.count() > 0) {
            return Map.of(
                    "status", "skipped",
                    "reason", "database already contains tokens",
                    "token_count", tokenRepository.count()
            );
        }

        Instant base = Instant.parse("2026-03-01T12:00:00Z");
        List<WalletEntity> wallets = createTrackedWallets(base);
        walletRepository.saveAll(wallets);

        TokenEntity historyToken = tokenRepository.save(
                token("HIST_mint", "HIST", "Historical Training Token", "creator_hist", base.minus(60, ChronoUnit.DAYS))
        );
        seedWalletHistory(wallets.get(0), historyToken, base, 0.82);
        seedWalletHistory(wallets.get(1), historyToken, base, 0.78);
        seedWalletHistory(wallets.get(2), historyToken, base, 0.74);

        TokenBundle good = createGoodToken(base, wallets);
        TokenBundle weak = createWeakToken(base, wallets);
        TokenBundle rug = createRugToken(base);

        persistBundle(good);
        persistBundle(weak);
        persistBundle(rug);

        return Map.of(
                "status", "loaded",
                "tokens", List.of(good.symbol(), weak.symbol(), rug.symbol()),
                "wallet_count", wallets.size()
        );
    }

    private List<WalletEntity> createTrackedWallets(Instant base) {
        List<WalletEntity> wallets = new ArrayList<>();
        wallets.add(wallet("wallet_alpha", "Alpha Trader", base.minus(30, ChronoUnit.DAYS), Map.of("tracked", true)));
        wallets.add(wallet("wallet_beta", "Beta Trader", base.minus(20, ChronoUnit.DAYS), Map.of("tracked", true)));
        wallets.add(wallet("wallet_gamma", "Gamma Trader", base.minus(15, ChronoUnit.DAYS), Map.of("tracked", true)));
        wallets.add(wallet("wallet_noise", "Noise Wallet", base.minus(10, ChronoUnit.DAYS), Map.of("tracked", false)));
        return wallets;
    }

    private void persistBundle(TokenBundle bundle) {
        TokenEntity savedToken = tokenRepository.save(bundle.token());
        for (TokenSnapshotEntity snapshot : bundle.snapshots()) {
            snapshot.setTokenId(savedToken.getId());
        }
        snapshotRepository.saveAll(bundle.snapshots());

        for (SwapEntity swap : bundle.swaps()) {
            swap.setTokenId(savedToken.getId());
            walletRepository.findByAddress(swap.getWalletAddress()).ifPresent(w -> swap.setWalletId(w.getId()));
        }
        swapRepository.saveAll(bundle.swaps());
    }

    private TokenBundle createGoodToken(Instant base, List<WalletEntity> wallets) {
        TokenEntity token = token("GOOD_mint_abc", "GOOD", "Good Recovery Coin", "creator_good", base.minus(2, ChronoUnit.DAYS));
        Map<String, Object> safeFeatures = Map.of(
                "mint_authority_revoked", true,
                "freeze_authority_revoked", true,
                "liquidity_locked", true,
                "top10_holder_pct", 22,
                "bundled_launch", false,
                "deployer_sold_recently", false
        );

        List<TokenSnapshotEntity> snapshots = new ArrayList<>();
        double[] prices = {1.0, 1.2, 1.5, 1.45, 1.0, 0.95, 1.0, 1.08, 1.25, 1.6, 1.9};
        for (int i = 0; i < prices.length; i++) {
            snapshots.add(snapshot(base.plus(i * 15L, ChronoUnit.MINUTES), prices[i], 85000, safeFeatures, (short) 92));
        }

        List<SwapEntity> swaps = new ArrayList<>();
        Instant buyTime = base.plus(105, ChronoUnit.MINUTES);
        swaps.add(swap("sig_good_1", token.getMintAddress(), wallets.get(0).getAddress(), "buy", buyTime, 1.0));
        swaps.add(swap("sig_good_2", token.getMintAddress(), wallets.get(1).getAddress(), "buy", buyTime.plus(2, ChronoUnit.MINUTES), 1.01));
        swaps.add(swap("sig_good_3", token.getMintAddress(), wallets.get(2).getAddress(), "buy", buyTime.plus(4, ChronoUnit.MINUTES), 1.02));

        return new TokenBundle("GOOD", token, snapshots, swaps);
    }

    private TokenBundle createWeakToken(Instant base, List<WalletEntity> wallets) {
        TokenEntity token = token("WEAK_mint_def", "WEAK", "Weak Momentum", "creator_weak", base.minus(1, ChronoUnit.DAYS));
        Map<String, Object> features = Map.of(
                "mint_authority_revoked", true,
                "freeze_authority_revoked", true,
                "liquidity_locked", true,
                "top10_holder_pct", 28,
                "bundled_launch", false,
                "deployer_sold_recently", false
        );

        List<TokenSnapshotEntity> snapshots = new ArrayList<>();
        double[] prices = {1.0, 1.05, 1.03, 1.02, 1.01, 1.0, 0.99};
        for (int i = 0; i < prices.length; i++) {
            snapshots.add(snapshot(base.plus(i * 20L, ChronoUnit.MINUTES), prices[i], 40000, features, (short) 80));
        }

        List<SwapEntity> swaps = List.of(
                swap("sig_weak_1", token.getMintAddress(), wallets.get(3).getAddress(), "buy",
                        base.plus(40, ChronoUnit.MINUTES), 1.02)
        );
        return new TokenBundle("WEAK", token, snapshots, swaps);
    }

    private TokenBundle createRugToken(Instant base) {
        TokenEntity token = token("RUG_mint_xyz", "RUG", "Unsafe Launch", "creator_rug", base.minus(6, ChronoUnit.HOURS));
        Map<String, Object> unsafe = Map.of(
                "mint_authority_revoked", false,
                "freeze_authority_revoked", false,
                "liquidity_locked", false,
                "top10_holder_pct", 72,
                "bundled_launch", true,
                "deployer_sold_recently", true
        );

        List<TokenSnapshotEntity> snapshots = new ArrayList<>();
        double[] prices = {1.0, 1.4, 0.6, 0.2};
        for (int i = 0; i < prices.length; i++) {
            snapshots.add(snapshot(base.plus(i * 10L, ChronoUnit.MINUTES), prices[i], 12000, unsafe, (short) 15));
        }
        return new TokenBundle("RUG", token, List.copyOf(snapshots), List.of());
    }

    private void seedWalletHistory(WalletEntity wallet, TokenEntity historyToken, Instant base, double winRate) {
        List<SwapEntity> history = new ArrayList<>();
        for (int i = 0; i < 10; i++) {
            Instant t = base.minus(7, ChronoUnit.DAYS).plus(i * 12L, ChronoUnit.HOURS);
            history.add(swap("hist_" + wallet.getAddress() + "_b" + i, historyToken.getMintAddress(), wallet.getAddress(), "buy", t, 1.0));
            double sellPrice = i < (int) (winRate * 10) ? 1.25 : 0.85;
            history.add(swap("hist_" + wallet.getAddress() + "_s" + i, historyToken.getMintAddress(), wallet.getAddress(), "sell",
                    t.plus(30, ChronoUnit.MINUTES), sellPrice));
        }
        for (SwapEntity swap : history) {
            swap.setTokenId(historyToken.getId());
            swap.setWalletId(wallet.getId());
        }
        swapRepository.saveAll(history);
    }

    private static WalletEntity wallet(String address, String label, Instant firstSeen, Map<String, Object> stats) {
        WalletEntity entity = new WalletEntity();
        entity.setAddress(address);
        entity.setLabel(label);
        entity.setFirstSeenAt(firstSeen);
        entity.setStats(new HashMap<>(stats));
        return entity;
    }

    private static TokenEntity token(String mint, String symbol, String name, String creator, Instant createdAt) {
        TokenEntity entity = new TokenEntity();
        entity.setMintAddress(mint);
        entity.setSymbol(symbol);
        entity.setName(name);
        entity.setCreatorWallet(creator);
        entity.setCreatedAt(createdAt);
        entity.setFirstSeenAt(createdAt);
        entity.setMetadata(Map.of("source", "sample"));
        return entity;
    }

    private static TokenSnapshotEntity snapshot(
            Instant observedAt,
            double price,
            double liquidity,
            Map<String, Object> features,
            short safetyScore
    ) {
        TokenSnapshotEntity entity = new TokenSnapshotEntity();
        entity.setObservedAt(observedAt);
        entity.setPriceUsd(BigDecimal.valueOf(price).setScale(8, RoundingMode.HALF_UP));
        entity.setLiquidityUsd(BigDecimal.valueOf(liquidity));
        entity.setMarketCapUsd(BigDecimal.valueOf(price * 1_000_000));
        entity.setHolderCount(500);
        entity.setVolume24hUsd(BigDecimal.valueOf(liquidity * 1.5));
        entity.setSafetyScore(safetyScore);
        entity.setFeatures(new HashMap<>(features));
        return entity;
    }

    private static SwapEntity swap(
            String signature,
            String mint,
            String wallet,
            String side,
            Instant time,
            double price
    ) {
        SwapEntity entity = new SwapEntity();
        entity.setTxSignature(signature);
        entity.setWalletAddress(wallet);
        entity.setSide(side);
        entity.setBlockTime(time);
        entity.setPriceUsd(BigDecimal.valueOf(price).setScale(8, RoundingMode.HALF_UP));
        entity.setAmountUsd(BigDecimal.valueOf(250));
        entity.setAmountToken(BigDecimal.valueOf(250 / price));
        entity.setDex("sample-dex");
        return entity;
    }

    private record TokenBundle(String symbol, TokenEntity token, List<TokenSnapshotEntity> snapshots, List<SwapEntity> swaps) {
    }
}
