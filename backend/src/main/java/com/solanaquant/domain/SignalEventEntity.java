package com.solanaquant.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.List;
import java.util.Map;

@Entity
@Table(name = "signal_events")
public class SignalEventEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "token_id")
    private Long tokenId;

    @Column(name = "mint_address", nullable = false)
    private String mintAddress;

    @Column(name = "observed_at", nullable = false)
    private Instant observedAt;

    @Column(nullable = false)
    private String action;

    @Column(nullable = false)
    private short score;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private Map<String, Object> breakdown;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false)
    private List<String> reasons;

    public void setTokenId(Long tokenId) {
        this.tokenId = tokenId;
    }

    public void setMintAddress(String mintAddress) {
        this.mintAddress = mintAddress;
    }

    public void setObservedAt(Instant observedAt) {
        this.observedAt = observedAt;
    }

    public void setAction(String action) {
        this.action = action;
    }

    public void setScore(short score) {
        this.score = score;
    }

    public void setBreakdown(Map<String, Object> breakdown) {
        this.breakdown = breakdown;
    }

    public void setReasons(List<String> reasons) {
        this.reasons = reasons;
    }

    public String getAction() {
        return action;
    }

    public String getMintAddress() {
        return mintAddress;
    }

    public short getScore() {
        return score;
    }

    public Instant getObservedAt() {
        return observedAt;
    }
}
