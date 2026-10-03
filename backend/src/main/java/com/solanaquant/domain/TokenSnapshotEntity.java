package com.solanaquant.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "token_snapshots")
public class TokenSnapshotEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "token_id", nullable = false)
    private Long tokenId;

    @Column(name = "observed_at", nullable = false)
    private Instant observedAt;

    @Column(name = "price_usd")
    private BigDecimal priceUsd;

    @Column(name = "liquidity_usd")
    private BigDecimal liquidityUsd;

    @Column(name = "market_cap_usd")
    private BigDecimal marketCapUsd;

    @Column(name = "holder_count")
    private Integer holderCount;

    @Column(name = "volume_24h_usd")
    private BigDecimal volume24hUsd;

    @Column(name = "safety_score")
    private Short safetyScore;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private Map<String, Object> features;

    public Long getId() {
        return id;
    }

    public Long getTokenId() {
        return tokenId;
    }

    public void setTokenId(Long tokenId) {
        this.tokenId = tokenId;
    }

    public Instant getObservedAt() {
        return observedAt;
    }

    public void setObservedAt(Instant observedAt) {
        this.observedAt = observedAt;
    }

    public BigDecimal getPriceUsd() {
        return priceUsd;
    }

    public void setPriceUsd(BigDecimal priceUsd) {
        this.priceUsd = priceUsd;
    }

    public BigDecimal getLiquidityUsd() {
        return liquidityUsd;
    }

    public void setLiquidityUsd(BigDecimal liquidityUsd) {
        this.liquidityUsd = liquidityUsd;
    }

    public BigDecimal getMarketCapUsd() {
        return marketCapUsd;
    }

    public void setMarketCapUsd(BigDecimal marketCapUsd) {
        this.marketCapUsd = marketCapUsd;
    }

    public Integer getHolderCount() {
        return holderCount;
    }

    public void setHolderCount(Integer holderCount) {
        this.holderCount = holderCount;
    }

    public BigDecimal getVolume24hUsd() {
        return volume24hUsd;
    }

    public void setVolume24hUsd(BigDecimal volume24hUsd) {
        this.volume24hUsd = volume24hUsd;
    }

    public Short getSafetyScore() {
        return safetyScore;
    }

    public void setSafetyScore(Short safetyScore) {
        this.safetyScore = safetyScore;
    }

    public Map<String, Object> getFeatures() {
        return features;
    }

    public void setFeatures(Map<String, Object> features) {
        this.features = features;
    }
}
