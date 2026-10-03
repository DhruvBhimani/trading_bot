package com.solanaquant.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

@Entity
@Table(name = "paper_positions")
public class PaperPositionEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "account_id", nullable = false)
    private Long accountId;

    @Column(name = "token_id", nullable = false)
    private Long tokenId;

    @Column(name = "mint_address", nullable = false)
    private String mintAddress;

    @Column(name = "entry_time", nullable = false)
    private Instant entryTime;

    @Column(name = "entry_price", nullable = false)
    private BigDecimal entryPrice;

    @Column(name = "quantity_usd", nullable = false)
    private BigDecimal quantityUsd;

    @Column(nullable = false)
    private String status;

    @Column(name = "exit_time")
    private Instant exitTime;

    @Column(name = "exit_price")
    private BigDecimal exitPrice;

    @Column(name = "pnl_pct")
    private BigDecimal pnlPct;

    @Column(name = "exit_reason")
    private String exitReason;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "signal_details", nullable = false)
    private Map<String, Object> signalDetails;

    public Long getId() {
        return id;
    }

    public Long getAccountId() {
        return accountId;
    }

    public void setAccountId(Long accountId) {
        this.accountId = accountId;
    }

    public Long getTokenId() {
        return tokenId;
    }

    public void setTokenId(Long tokenId) {
        this.tokenId = tokenId;
    }

    public String getMintAddress() {
        return mintAddress;
    }

    public void setMintAddress(String mintAddress) {
        this.mintAddress = mintAddress;
    }

    public Instant getEntryTime() {
        return entryTime;
    }

    public void setEntryTime(Instant entryTime) {
        this.entryTime = entryTime;
    }

    public BigDecimal getEntryPrice() {
        return entryPrice;
    }

    public void setEntryPrice(BigDecimal entryPrice) {
        this.entryPrice = entryPrice;
    }

    public BigDecimal getQuantityUsd() {
        return quantityUsd;
    }

    public void setQuantityUsd(BigDecimal quantityUsd) {
        this.quantityUsd = quantityUsd;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Instant getExitTime() {
        return exitTime;
    }

    public void setExitTime(Instant exitTime) {
        this.exitTime = exitTime;
    }

    public BigDecimal getExitPrice() {
        return exitPrice;
    }

    public void setExitPrice(BigDecimal exitPrice) {
        this.exitPrice = exitPrice;
    }

    public BigDecimal getPnlPct() {
        return pnlPct;
    }

    public void setPnlPct(BigDecimal pnlPct) {
        this.pnlPct = pnlPct;
    }

    public String getExitReason() {
        return exitReason;
    }

    public void setExitReason(String exitReason) {
        this.exitReason = exitReason;
    }

    public Map<String, Object> getSignalDetails() {
        return signalDetails;
    }

    public void setSignalDetails(Map<String, Object> signalDetails) {
        this.signalDetails = signalDetails;
    }
}
